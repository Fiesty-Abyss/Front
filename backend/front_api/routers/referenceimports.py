from typing import Literal
from fastapi import APIRouter,Depends,Query,HTTPException
from pydantic import BaseModel,Field
from sqlalchemy import select,func,update
from sqlalchemy.orm import Session
from .. import models as m,referenceimports as imports
from ..db import get_session
from ..crud import get_or_404

router=APIRouter(prefix='/api/library-imports',tags=['共享资料导入'])


class Import(BaseModel):
    report_id:str
    indices:list[int]=Field(min_length=1,max_length=5000)
    mode:Literal['indexed','managed']='indexed'
    collection_id:int|None=None
    world_id:int|None=None
    work_id:int|None=None
    allow_cross_scope:bool=False


@router.post('',status_code=202)
def start(body:Import,session:Session=Depends(get_session)):
    try:return imports.start(session,body)
    except ValueError as exc:raise HTTPException(422,str(exc)) from None


@router.get('')
def listing(collection_id:int|None=None,offset:int=Query(0,ge=0),session:Session=Depends(get_session)):
    stmt=select(m.LibraryImport)
    if collection_id is not None:stmt=stmt.where(m.LibraryImport.collection_id==collection_id)
    return {'items':[{'id':r.id,'status':r.status,'job_id':r.job_id,'mode':r.mode,'created_at':r.created_at} for r in session.scalars(stmt.order_by(m.LibraryImport.created_at.desc()).offset(offset).limit(30))]}


@router.get('/{run_id}')
def detail(run_id:str,offset:int=Query(0,ge=0),limit:int=Query(50,ge=1,le=100),session:Session=Depends(get_session)):
    run=get_or_404(session,m.LibraryImport,run_id)
    counts=dict(session.execute(select(m.LibraryImportItem.status,func.count()).where(m.LibraryImportItem.import_id==run_id).group_by(m.LibraryImportItem.status)).all())
    items=session.scalars(select(m.LibraryImportItem).where(m.LibraryImportItem.import_id==run_id).order_by(m.LibraryImportItem.file_index).offset(offset).limit(limit))
    return {'id':run.id,'status':run.status,'counts':counts,'job_id':run.job_id,'items':[{'index':i.file_index,'status':i.status,'asset_id':i.asset_id,'message':i.message} for i in items]}


@router.post('/{run_id}/resume',status_code=202)
def resume(run_id:str,session:Session=Depends(get_session)):
    run=get_or_404(session,m.LibraryImport,run_id)
    from .. import jobs
    job=jobs.get(run.job_id) if run.job_id else None
    if job and job.status in ('running','queued'):raise HTTPException(409,'任务仍在进行')
    if run.status in ('running','queued'):run.status='interrupted';session.flush()
    if not session.execute(update(m.LibraryImport).where(m.LibraryImport.id==run_id,m.LibraryImport.status.in_(['partial','cancelled','interrupted'])).values(status='queued')).rowcount:raise HTTPException(409,'当前任务无需恢复')
    session.commit();return imports.dispatch(session,run)
