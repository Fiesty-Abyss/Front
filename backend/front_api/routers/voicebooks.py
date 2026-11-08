from typing import Literal
from fastapi import APIRouter,Depends,HTTPException,Query
from pydantic import Field,model_validator
from sqlalchemy import select,update,func
from sqlalchemy.orm import Session
from .. import models as m,versions as v,voicestudio as vs,voiceprojects as vp,voicebooks as book,jobs,voicebatch as batch,voicereview as review
from ..crud import get_or_404
from ..db import get_session

router=APIRouter(prefix='/api/voice/books',tags=['Novel voice drafts'])


class FromNovel(vs.Draft):
    source_fingerprint:str=Field(min_length=64,max_length=64)


class Queue(vp.Mutation):
    source_fingerprint:str=Field(min_length=64,max_length=64)
    chapter_index:int=Field(ge=0)


class Range(vp.Mutation):
    source_fingerprint:str=Field(pattern=r'^[0-9a-f]{64}$')
    first:int=Field(ge=0)
    last:int=Field(ge=0)

    @model_validator(mode='after')
    def bounded(self):
        if self.last<self.first or self.last-self.first>=20:raise ValueError('每批请选择连续至多20章')
        return self


status=batch.status


def range_rows(session,project,first,last):
    frame,revision,_=book.frozen(session,project)
    if first<0 or last<first or last-first>=20 or last>=len(revision.chapters):raise HTTPException(422,'请选择存在的连续至多20章')
    found={r.chapter_index:r for r in session.scalars(select(m.VoiceChapterImport).where(m.VoiceChapterImport.project_id==project.id,
        m.VoiceChapterImport.chapter_index.between(first,last)))}
    return frame,revision,[{'index':i,'title':revision.chapters[i]['title'],'import':status(found[i]) if i in found else None} for i in range(first,last+1)]


@router.get('/sources/{asset_id}')
def preview(asset_id:int,limit:int=Query(30,ge=1,le=100),offset:int=Query(0,ge=0),session:Session=Depends(get_session)):
    asset,revision,text,frame=book.confirmed(session,asset_id)
    return {'title':asset.title,'source':frame,'total':len(revision.chapters),
        'chapters':[{'index':i,**chapter} for i,chapter in enumerate(revision.chapters) if offset<=i<offset+limit]}


@router.post('/sources/{asset_id}/projects',status_code=201)
def create(asset_id:int,body:FromNovel,session:Session=Depends(get_session)):
    session.connection().exec_driver_sql('BEGIN IMMEDIATE')
    asset,revision,text,frame=book.confirmed(session,asset_id)
    if frame['fingerprint']!=body.source_fingerprint:raise HTTPException(409,'小说或确认目录已变化，请重新预览')
    project=m.VoiceProject(title=body.title,notes=body.notes,world_id=asset.world_id,source_asset_id=asset.id)
    session.add(project);session.flush()
    session.add(m.VoiceBookSource(project_id=project.id,snapshot=frame));session.flush()
    v.enable(session,project,'从已确认小说创建独立配音工程');session.commit()
    return vs.serialize(session,project)


@router.get('/projects/{project_id}')
def listing(project_id:int,limit:int=Query(30,ge=1,le=100),offset:int=Query(0,ge=0),session:Session=Depends(get_session)):
    project=get_or_404(session,m.VoiceProject,project_id)
    frame,revision,_=book.frozen(session,project)
    indices=range(offset,min(offset+limit,len(revision.chapters)))
    imported={r.chapter_index:status(r) for r in session.scalars(select(m.VoiceChapterImport).where(m.VoiceChapterImport.project_id==project_id,m.VoiceChapterImport.chapter_index.in_(indices)))}
    return {'source':frame,'project':vs.serialize(session,project),'total':len(revision.chapters),
        'chapters':[{'index':i,**revision.chapters[i],'import':imported.get(i)} for i in indices]}


@router.get('/projects/{project_id}/imports/range')
def range_status(project_id:int,first:int=Query(ge=0),last:int=Query(ge=0),session:Session=Depends(get_session)):
    project=get_or_404(session,m.VoiceProject,project_id)
    _,_,items=range_rows(session,project,first,last)
    return {'project':vs.serialize(session,project),'items':items}


@router.post('/projects/{project_id}/imports/preview')
def range_preview(project_id:int,body:Range,session:Session=Depends(get_session)):
    project=vp.start(session,project_id,body)
    frame,_,items=range_rows(session,project,body.first,body.last)
    if frame['fingerprint']!=body.source_fingerprint:raise HTTPException(409,'来源版本不匹配')
    return {'project':vs.serialize(session,project),'items':items,'source_fingerprint':frame['fingerprint'],
        'limit_per_chapter':{'characters':100000,'segments':1000},'will_synthesize':False}


@router.post('/projects/{project_id}/imports/batch',status_code=202)
def range_queue(project_id:int,body:Range,session:Session=Depends(get_session)):
    session.connection().exec_driver_sql('BEGIN IMMEDIATE')
    project=get_or_404(session,m.VoiceProject,project_id)
    if project.uid!=body.project_uid:raise HTTPException(409,'工程身份已变化')
    frame,revision,_=range_rows(session,project,body.first,body.last)
    if frame['fingerprint']!=body.source_fingerprint:raise HTTPException(409,'来源版本不匹配')
    rows=batch.submit(session,project,frame,revision,list(range(body.first,body.last+1)),body)
    return {'project':vs.serialize(session,project),'imports':[status(row) for row in rows]}


@router.post('/projects/{project_id}/imports',status_code=202)
def queue(project_id:int,body:Queue,session:Session=Depends(get_session)):
    session.connection().exec_driver_sql('BEGIN IMMEDIATE')
    project=get_or_404(session,m.VoiceProject,project_id)
    if project.uid!=body.project_uid:raise HTTPException(409,'工程身份已变化')
    frame,revision,_=book.frozen(session,project)
    if frame['fingerprint']!=body.source_fingerprint:raise HTTPException(409,'来源版本不匹配')
    rows=batch.submit(session,project,frame,revision,[body.chapter_index],body)
    return {'project':vs.serialize(session,project),'import':status(rows[0])}


@router.post('/projects/{project_id}/imports/{import_id}/cancel')
def cancel(project_id:int,import_id:int,body:vp.Mutation,session:Session=Depends(get_session)):
    session.connection().exec_driver_sql('BEGIN IMMEDIATE')
    project=get_or_404(session,m.VoiceProject,project_id);row=get_or_404(session,m.VoiceChapterImport,import_id)
    if project.uid!=body.project_uid or row.project_id!=project_id:raise HTTPException(404,'导入请求不属于当前工程')
    if row.status not in ('queued','running'):raise HTTPException(409,'本次任务已结束；已保存片段保留')
    job=jobs.get(row.job_id)
    if job:job.cancel_requested=True;jobs.manager().save(job)
    if row.job_id:
        session.execute(update(m.VoiceChapterImport).where(m.VoiceChapterImport.project_id==project_id,
            m.VoiceChapterImport.job_id==row.job_id,m.VoiceChapterImport.status.in_(('queued','running'))).values(status='cancelled',error_code='batch_cancelled'))
    else:row.status='cancelled'
    vp.touch(session,project,'取消本批章节导入，保留已保存片段及游标');session.commit();session.refresh(row)
    return {'project':vs.serialize(session,project),'import':status(row)}


@router.get('/projects/{project_id}/review')
def review_list(project_id:int,chapter:int|None=Query(None,ge=0),review_state:Literal['pending','confirmed','all']=Query('pending',alias='review'),
                speaker:str=Query('',max_length=200),limit:int=Query(20,ge=1,le=100),offset:int=Query(0,ge=0),session:Session=Depends(get_session)):
    project=get_or_404(session,m.VoiceProject,project_id);book.frozen(session,project)
    q=review.query(project_id,chapter,review_state)
    if speaker:q=q.where(m.VoiceSegment.source['speaker'].as_string()==speaker)
    total=session.scalar(select(func.count()).select_from(q.subquery()))
    rows=session.scalars(q.order_by(m.VoiceSegment.position,m.VoiceSegment.id).offset(offset).limit(limit)).all()
    all_rows=review.query(project_id,review='all').subquery()
    stats={'total':session.scalar(select(func.count()).select_from(all_rows)),
        'pending':session.scalar(select(func.count()).select_from(review.query(project_id).subquery())),
        'voice_missing':session.scalar(select(func.count()).select_from(all_rows).where(all_rows.c.profile_id.is_(None))),
        'accepted_records':session.scalar(select(func.count(func.distinct(m.VoiceRender.segment_id))).join(all_rows,m.VoiceRender.segment_id==all_rows.c.id).where(m.VoiceRender.status=='accepted'))}
    return {'project':vs.serialize(session,project),'total':total,'stats':stats,'items':[review.brief(session,row) for row in rows]}


@router.post('/projects/{project_id}/review')
def review_save(project_id:int,body:review.Review,session:Session=Depends(get_session)):
    project=vp.start(session,project_id,body);book.frozen(session,project)
    count=review.apply(session,project,body);session.commit()
    return {'project':vs.serialize(session,project),'updated':count}


@router.post('/projects/{project_id}/prepare')
def prepare_saved(project_id:int,body:review.Selection,session:Session=Depends(get_session)):
    project=vp.start(session,project_id,body);book.frozen(session,project)
    return {'project':vs.serialize(session,project),'items':review.prepare(session,project,body.entries),
        'will_synthesize':False,'runtime_verified':False}
