"""OC learning collections and non-destructive raster jobs."""
import uuid
import re,time
from datetime import date
from pathlib import Path
from typing import Literal
from fastapi import APIRouter,Depends,HTTPException,Query
from fastapi.responses import FileResponse
from pydantic import BaseModel,Field,model_validator
from sqlalchemy import select,func
from sqlalchemy.orm import Session,defer
from .. import models as m,ocstudio as studio,ocstudy as study,versions,jobs
from ..db import get_session,new_session
from ..config import get_settings
from ..crud import get_or_404
from ..ingest import ingest_stream,make_thumb
from .ocimages import image_ref,reference_path

router=APIRouter(tags=['OC绘画学习'])


def owned(session,study_id,profile_id=None):
    item=get_or_404(session,m.OCStudy,study_id);obj=study.profile(session,item)
    if profile_id is not None and obj.id!=profile_id:raise HTTPException(422,'学习集不属于当前OC')
    return item,obj


class StudyDraft(BaseModel):
    title:str=Field(min_length=1,max_length=200)
    notes:str=Field(default='',max_length=30000)


class StudyUpdate(StudyDraft):
    expected_version:int=Field(ge=1)


class EntryEdit(BaseModel):
    stage:Literal['original','reference','sketch','lineart','color','modification','three-view','expression','clothing','hatching']='reference'
    notes:str=Field(default='',max_length=10000)
    learned_on:date=Field(default_factory=date.today)
    expected_version:int=Field(ge=1)


class EntryCreate(EntryEdit):
    reference_id:str


@router.get('/api/oc/{profile_id}/studies')
def listing(profile_id:int,offset:int=Query(0,ge=0),session:Session=Depends(get_session)):
    obj=get_or_404(session,m.OCProfile,profile_id)
    stmt=select(m.OCStudy).where(m.OCStudy.profile_id==obj.id,m.OCStudy.profile_identity==studio.identity(obj))
    total=session.scalar(select(func.count()).select_from(stmt.subquery()))
    return {'total':total,'items':[{'id':s.id,'title':s.title,'collection_id':s.collection_id} for s in session.scalars(stmt.options(defer(m.OCStudy.entries),defer(m.OCStudy.notes)).order_by(m.OCStudy.updated_at.desc()).offset(offset).limit(30))]}


@router.post('/api/oc/{profile_id}/studies',status_code=201)
def create(profile_id:int,body:StudyDraft,session:Session=Depends(get_session)):
    obj=get_or_404(session,m.OCProfile,profile_id)
    col=m.Collection(name=body.title,description='OC绘画学习素材引用；移除练习记录不删除原图');session.add(col);session.flush()
    item=m.OCStudy(profile_id=obj.id,profile_identity=studio.identity(obj),collection_id=col.id,**body.model_dump());session.add(item);session.flush();versions.enable(session,item,'创建绘画学习集');session.commit();return study.detail(session,item)


@router.get('/api/oc-studies/{study_id}')
def detail(study_id:int,session:Session=Depends(get_session)):
    item,_=owned(session,study_id);return study.detail(session,item)


@router.put('/api/oc-studies/{study_id}')
def update(study_id:int,body:StudyUpdate,session:Session=Depends(get_session)):
    session.connection().exec_driver_sql('BEGIN IMMEDIATE');item,_=owned(session,study_id);study.guard(session,item,body.expected_version)
    item.title=body.title;item.notes=body.notes;session.commit();return study.detail(session,item)


@router.post('/api/oc-studies/{study_id}/entries')
def entry_create(study_id:int,body:EntryCreate,session:Session=Depends(get_session)):
    session.connection().exec_driver_sql('BEGIN IMMEDIATE');item,obj=owned(session,study_id);study.guard(session,item,body.expected_version)
    ref=next((r for r in obj.references if r['id']==body.reference_id),None)
    if ref is None:raise HTTPException(404,'OC素材引用不存在')
    study.append(session,item,ref,body.stage,body.notes,body.learned_on);session.commit();return study.detail(session,item)


@router.patch('/api/oc-studies/{study_id}/entries/{entry_id}')
def entry_edit(study_id:int,entry_id:str,body:EntryEdit,session:Session=Depends(get_session)):
    session.connection().exec_driver_sql('BEGIN IMMEDIATE');item,_=owned(session,study_id);study.guard(session,item,body.expected_version)
    if not any(e['id']==entry_id for e in item.entries):raise HTTPException(404,'练习记录不存在')
    item.entries=[e|{'stage':body.stage,'learning_notes':body.notes,'learned_on':body.learned_on.isoformat()} if e['id']==entry_id else e for e in item.entries]
    session.commit();return study.detail(session,item)


@router.delete('/api/oc-studies/{study_id}/entries/{entry_id}')
def remove_entry(study_id:int,entry_id:str,expected_version:int,session:Session=Depends(get_session)):
    session.connection().exec_driver_sql('BEGIN IMMEDIATE');item,_=owned(session,study_id);study.guard(session,item,expected_version)
    if not any(e['id']==entry_id for e in item.entries):raise HTTPException(404,'练习记录不存在')
    item.entries=[e for e in item.entries if e['id']!=entry_id];session.commit();return study.detail(session,item)


def study_image(session,study_id,entry_id,profile_id=None):
    item,obj=owned(session,study_id,profile_id);ref=next((e for e in item.entries if e['id']==entry_id),None)
    if ref is None:raise HTTPException(404,'练习记录不存在')
    asset,status=studio.reference_status(session,obj,ref)
    if status!='ok':raise HTTPException(409,status)
    if not asset.width:raise HTTPException(422,'该绘画工程只能原件下载或用外部编辑器打开')
    return obj,ref,asset


@router.get('/api/oc-studies/{study_id}/entries/{entry_id}/file')
def study_file(study_id:int,entry_id:str,download:bool=False,session:Session=Depends(get_session)):
    _,ref,asset=study_image(session,study_id,entry_id);path,mime=reference_path(session,ref,asset)
    return FileResponse(path,media_type=mime,filename=(asset.original_name or path.name) if download else None,headers={'X-Content-Type-Options':'nosniff'})


class Render(BaseModel):
    reference_id:str|None=None
    study_id:int|None=None
    entry_id:str|None=None
    operation:Literal['lineart','export']='export'
    format:Literal['png','jpeg','webp']='png'
    background:Literal['white','transparent']='white'
    save_to_study:bool=True
    expected_version:int=Field(ge=1)

    @model_validator(mode='after')
    def source(self):
        if bool(self.reference_id)==bool(self.entry_id):raise ValueError('请选择一个OC引用或一个练习项')
        if self.entry_id and not self.study_id:raise ValueError('练习项需要学习集ID')
        if self.operation=='lineart':self.format='png'
        return self


@router.post('/api/oc/{profile_id}/render')
def render(profile_id:int,body:Render,session:Session=Depends(get_session)):
    obj=get_or_404(session,m.OCProfile,profile_id);studio.guard(session,obj,body.expected_version)
    if body.entry_id:obj,ref,asset=study_image(session,body.study_id,body.entry_id,profile_id)
    else:obj,ref,asset=image_ref(session,profile_id,body.reference_id)
    if body.study_id:owned(session,body.study_id,profile_id)
    source,_=reference_path(session,ref,asset);scope=studio.scope(session,obj);identity=studio.identity(obj);ref=dict(ref);title=asset.title
    study_identity=studio.identity(session.get(m.OCStudy,body.study_id)) if body.study_id else None
    def work(job):
        # Lazy import: no Pillow processor is initialized on core/OC startup.
        from .. import artwork
        root=get_settings().data_dir.resolve();exports=(root/'exports').resolve()
        if not exports.is_relative_to(root):raise ValueError('导出缓存目录不在本机数据目录内')
        exports.mkdir(exist_ok=True);ext={'png':'png','jpeg':'jpg','webp':'webp'}[body.format]
        output=exports/f'{job.id}.{ext}';temporary=exports/f'{job.id}.partial'
        job.result={'recipe':body.model_dump(),'profile_id':profile_id}
        try:
            job.check();job.step('验证引用与原图Hash')
            meta=artwork.process(source,temporary,operation=body.operation,format=body.format,background=body.background,expected_sha=ref.get('sha256'),check=job.check)
            job.step('栅格处理完成')
            with new_session() as ses:
                ses.connection().exec_driver_sql('BEGIN IMMEDIATE');current=ses.get(m.OCProfile,profile_id)
                if current is None or studio.identity(current)!=identity or studio.scope(ses,current)!=scope:raise ValueError('OC归属变化，停止保存派生结果')
                target,status=studio.reference_status(ses,current,ref)
                if status!='ok':raise ValueError('源引用失效，停止处理')
                study_item=None
                if body.study_id:
                    study_item,_=owned(ses,body.study_id,profile_id)
                    if studio.identity(study_item)!=study_identity:raise ValueError('学习集已失效')
                job.check()
                if body.operation=='lineart':
                    with temporary.open('rb') as stream:
                        derived,created=ingest_stream(ses,stream,f'{title[:100]}-lineart.png',title=f'{title[:150]} · 自动栅格线稿',kind='drawing',world_id=scope['world_id'],extra_meta={'derivation':meta|{'source_asset_id':asset.id,'source_version':ref.get('asset_version'),'operation':'lineart','background':body.background}})
                    new_ref=studio.attach(ses,current,'asset',derived.id,role='lineart',design_id=ref.get('design_id') if any(d['id']==ref.get('design_id') for d in current.designs) else None)
                    if study_item and body.save_to_study:study.append(ses,study_item,new_ref,'lineart','自动提取的栅格线稿；请检查质量后练习')
                    ses.commit()
                    if created:make_thumb(derived.id,get_settings().data_dir/derived.file_path)
                    job.result.update({'asset_id':derived.id,'reference_id':new_ref['id'],'notice':'独立派生图，原件未改写；栅格而非矢量'})
                else:
                    temporary.replace(output);job.result.update({'download':f'/api/oc-exports/{job.id}','format':body.format,'notice':'格式转换副本；JPEG/WebP可能有损，无损原件请使用原文件下载'})
            job.step('派生文件已独立保存' if body.operation=='lineart' else '导出副本已就绪')
            prune_exports(exports,keep=output.name if body.operation=='export' else None)
        finally:temporary.unlink(missing_ok=True)
    job=jobs.start('oc-raster',f'绘画处理：{title[:80]}',3,work)
    job.result.setdefault('recipe',body.model_dump());job.result.setdefault('profile_id',profile_id);jobs.manager().save(job)
    return job.to_dict()


def prune_exports(root,keep=None):
    """Only generated download cache, never library media, source files or partial jobs."""
    files=[]
    for path in root.iterdir():
        if path.name==keep or path.is_symlink() or not re.fullmatch(r'[0-9a-f]{12}\.(png|jpg|webp)',path.name):continue
        job=jobs.get(path.stem)
        if job and job.status in ('queued','running'):continue
        try:files.append((path.stat().st_mtime,path.stat().st_size,path))
        except OSError:continue
    total=sum(s for _,s,_ in files)+( (root/keep).stat().st_size if keep and (root/keep).exists() else 0)
    count=len(files)+(1 if keep else 0)
    for stamp,size,path in sorted(files):
        if count<=200 and total<=512*1024*1024 and stamp>=time.time()-7*86400:continue
        try:path.unlink();count-=1;total-=size
        except OSError:pass


@router.get('/api/oc-exports/{job_id}')
def download(job_id:str):
    job=jobs.get(job_id)
    if not job or job.kind!='oc-raster' or job.status!='done' or not job.result.get('download'):raise HTTPException(404,'导出未完成或任务已过期；可重新生成副本')
    if len(job_id)!=12 or any(c not in '0123456789abcdef' for c in job_id):raise HTTPException(404)
    ext={'png':'png','jpeg':'jpg','webp':'webp'}[job.result['format']];path=get_settings().data_dir/'exports'/f'{job_id}.{ext}'
    if not path.is_file():raise HTTPException(404,'导出缓存已清理，可重新导出')
    return FileResponse(path,filename=f'front-practice-{job_id}.{ext}',media_type={'png':'image/png','jpeg':'image/jpeg','webp':'image/webp'}[job.result['format']])
