import hashlib
import os
import uuid
from typing import Annotated,Literal

from fastapi import APIRouter,Depends,HTTPException,Query,Response,Path as APIPath
from pydantic import BaseModel,ConfigDict,Field,StrictInt
from sqlalchemy import select,update,delete
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .. import discovery as d,jobs,models as m
from ..crud import get_or_404
from ..db import get_session

router=APIRouter(prefix='/api/discovery-roots',tags=['扫描来源'])
SourceId=Annotated[int,APIPath(ge=1,le=2**63-1)]


class Config(BaseModel):
    model_config=ConfigDict(extra='forbid')
    kind:Literal['mixed','game','novel','drawing','audio','model3d','live2d','ai_model','document']='mixed'
    max_depth:StrictInt=Field(default=4,ge=0,le=32)
    ignores:list[str]=Field(default_factory=list,max_length=40)
    max_files:StrictInt=Field(default=1000,ge=1,le=5000)
    max_entries:StrictInt=Field(default=20000,ge=1,le=50000)
    max_bytes:StrictInt=Field(default=32*1024**3,ge=1,le=1024**4)
    hash_file_bytes:StrictInt=Field(default=16*1024**2,ge=0,le=256*1024**2)
    hash_bytes:StrictInt=Field(default=256*1024**2,ge=0,le=1024**3)
    max_seconds:StrictInt=Field(default=60,ge=1,le=600)


class Create(BaseModel):
    model_config=ConfigDict(extra='forbid')
    name:str=Field(min_length=1,max_length=120)
    path:str=Field(min_length=1,max_length=4000)
    config:Config=Field(default_factory=Config)


class Guard(BaseModel):
    model_config=ConfigDict(extra='forbid')
    uid:str=Field(pattern=r'^[a-f0-9]{32}$')
    version:StrictInt=Field(ge=1,le=2**63-1)


class Edit(Guard):
    name:str=Field(min_length=1,max_length=120)
    config:Config


def output(row):
    from ..config import get_settings
    report_id=row.report_id
    available=bool(report_id and len(report_id)==12 and all(c in '0123456789abcdef' for c in report_id) and (get_settings().data_dir/'project-previews'/f'{report_id}.json').is_file())
    return {k:getattr(row,k) for k in ('id','uid','version','name','path','config','state','job_id','report_id','stats','created_at')}|{'report_available':available,'baseline_report_id':row.baseline_id}


def current(session,rid,body):
    row=get_or_404(session,m.DiscoveryRoot,rid);d.reconcile(session,row)
    if row.uid!=body.uid or row.version!=body.version:raise HTTPException(409,'扫描来源已被其他窗口修改，请重新载入')
    return row


def change(session,row,values,states=None):
    stmt=update(m.DiscoveryRoot).where(m.DiscoveryRoot.id==row.id,m.DiscoveryRoot.uid==row.uid,m.DiscoveryRoot.version==row.version)
    if states:stmt=stmt.where(m.DiscoveryRoot.state.in_(states))
    result=session.execute(stmt.values(**values,version=row.version+1),execution_options={'synchronize_session':False})
    if not result.rowcount:session.rollback();raise HTTPException(409,'扫描来源已变化，请重新载入')
    session.commit();session.refresh(row)


def config_data(body):
    data=body.model_dump()
    if any(not p.strip() or len(p)>200 or '\x00' in p for p in data['ignores']):raise HTTPException(422,'忽略规则为空或过长')
    return data


@router.get('')
def listing(offset:int=Query(0,ge=0),limit:int=Query(20,ge=1,le=100),session:Session=Depends(get_session)):
    rows=list(session.scalars(select(m.DiscoveryRoot).order_by(m.DiscoveryRoot.id).offset(offset).limit(limit+1)))
    for row in rows[:limit]:d.reconcile(session,row)
    return {'items':[output(r) for r in rows[:limit]],'has_more':len(rows)>limit}


@router.post('',status_code=201)
def create(body:Create,session:Session=Depends(get_session)):
    try:path=d.folder(body.path)
    except (ValueError,OSError):raise HTTPException(422,'请选择可读取的实际本地文件夹，不使用整盘、符号链接、Junction或Front数据目录') from None
    if not body.name.strip():raise HTTPException(422,'来源名称不能为空')
    row=m.DiscoveryRoot(name=body.name.strip(),path=str(path),path_key=hashlib.sha256(os.path.normcase(str(path)).encode()).hexdigest(),config=config_data(body.config))
    session.add(row)
    try:session.commit()
    except IntegrityError:session.rollback();raise HTTPException(409,'该实际目录已登记，请使用现有来源') from None
    return output(row)


@router.get('/{rid}')
def detail(rid:SourceId,session:Session=Depends(get_session)):
    row=get_or_404(session,m.DiscoveryRoot,rid);d.reconcile(session,row);return output(row)


@router.patch('/{rid}')
def edit(rid:SourceId,body:Edit,session:Session=Depends(get_session)):
    row=current(session,rid,body)
    if row.state in d.ACTIVE:raise HTTPException(409,'请先暂停或取消扫描再修改配置')
    if not body.name.strip():raise HTTPException(422,'来源名称不能为空')
    change(session,row,{'name':body.name.strip(),'config':config_data(body.config)})
    return output(row)


@router.post('/{rid}/scan',status_code=202)
def scan(rid:SourceId,body:Guard,session:Session=Depends(get_session)):
    row=current(session,rid,body)
    if row.state in d.ACTIVE:raise HTTPException(409,'扫描仍在进行')
    change(session,row,{'state':'queued','job_id':None,'report_id':uuid.uuid4().hex[:12]})
    job=d.enqueue(session,row)
    return {'source':output(row),'job':job}


@router.post('/{rid}/control/{action}')
def control(rid:SourceId,action:Literal['pause','cancel'],body:Guard,session:Session=Depends(get_session)):
    row=current(session,rid,body)
    if row.state not in ('queued','running'):raise HTTPException(409,'没有可控制的活动扫描')
    change(session,row,{'state':'pausing' if action=='pause' else 'cancelling'},states=('queued','running'))
    job=jobs.get(row.job_id) if row.job_id else None
    if job:job.cancel_requested=True
    return output(row)


@router.post('/{rid}/remove',status_code=204)
def remove(rid:SourceId,body:Guard,session:Session=Depends(get_session)):
    row=current(session,rid,body)
    if row.state in d.ACTIVE:raise HTTPException(409,'请先停止扫描')
    result=session.execute(delete(m.DiscoveryRoot).where(m.DiscoveryRoot.id==rid,m.DiscoveryRoot.uid==body.uid,m.DiscoveryRoot.version==body.version))
    if not result.rowcount:session.rollback();raise HTTPException(409,'扫描来源已变化')
    session.commit();return Response(status_code=204)
