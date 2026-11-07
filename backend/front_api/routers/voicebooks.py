from fastapi import APIRouter,Depends,HTTPException,Query
from pydantic import Field
from sqlalchemy import select,update
from sqlalchemy.orm import Session
from .. import models as m,versions as v,voicestudio as vs,voiceprojects as vp,voicebooks as book,jobs
from ..crud import get_or_404
from ..db import get_session

router=APIRouter(prefix='/api/voice/books',tags=['Novel voice drafts'])


class FromNovel(vs.Draft):
    source_fingerprint:str=Field(min_length=64,max_length=64)


class Queue(vp.Mutation):
    source_fingerprint:str=Field(min_length=64,max_length=64)
    chapter_index:int=Field(ge=0)


def status(row):
    return {'id':row.id,'uid':row.uid,'chapter_index':row.chapter_index,'cursor':row.cursor,'end':row.end,
        'status':row.status,'job_id':row.job_id,'error_code':row.error_code}


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


@router.post('/projects/{project_id}/imports',status_code=202)
def queue(project_id:int,body:Queue,session:Session=Depends(get_session)):
    session.connection().exec_driver_sql('BEGIN IMMEDIATE')
    project=get_or_404(session,m.VoiceProject,project_id)
    if project.uid!=body.project_uid:raise HTTPException(409,'工程身份已变化')
    frame,revision,_=book.frozen(session,project)
    if frame['fingerprint']!=body.source_fingerprint:raise HTTPException(409,'来源版本不匹配')
    if body.chapter_index>=len(revision.chapters):raise HTTPException(422,'章节不存在')
    row=session.scalar(select(m.VoiceChapterImport).where(m.VoiceChapterImport.project_id==project_id,m.VoiceChapterImport.chapter_index==body.chapter_index))
    if row and row.status in ('queued','running','done'):return {'project':vs.serialize(session,project),'import':status(row)}
    vs.guard(session,project,body.project_uid,body.expected_project_version)
    if not row:
        chapter=revision.chapters[body.chapter_index]
        row=m.VoiceChapterImport(project_id=project_id,chapter_index=body.chapter_index,cursor=chapter.get('body_start',chapter['start']),end=chapter['end'])
        session.add(row)
    row.status='queued';row.error_code='';vp.touch(session,project,'排队小说章节朗读草稿');session.commit();uid=row.uid
    try:job=jobs.start('voice-chapter','小说朗读草稿（不执行AI）',0,lambda j:book.run(j,uid))
    except HTTPException:
        book.terminal(uid,'error','queue_unavailable');raise
    session.execute(update(m.VoiceChapterImport).where(m.VoiceChapterImport.uid==uid).values(job_id=job.id))
    session.commit();session.refresh(row)
    return {'project':vs.serialize(session,project),'import':status(row)}


@router.post('/projects/{project_id}/imports/{import_id}/cancel')
def cancel(project_id:int,import_id:int,body:vp.Mutation,session:Session=Depends(get_session)):
    session.connection().exec_driver_sql('BEGIN IMMEDIATE')
    project=get_or_404(session,m.VoiceProject,project_id);row=get_or_404(session,m.VoiceChapterImport,import_id)
    if project.uid!=body.project_uid or row.project_id!=project_id:raise HTTPException(404,'导入请求不属于当前工程')
    if row.status not in ('queued','running'):raise HTTPException(409,'本次任务已结束；已保存片段保留')
    job=jobs.get(row.job_id)
    if job:job.cancel_requested=True;jobs.manager().save(job)
    row.status='cancelled';vp.touch(session,project,'取消章节导入，保留可续导位置');session.commit()
    return {'project':vs.serialize(session,project),'import':status(row)}
