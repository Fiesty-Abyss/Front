"""Explicit exports from accepted segments; shared bounded jobs and Asset store."""
from fastapi import APIRouter,Depends,Query,HTTPException
from sqlalchemy import select,func
from sqlalchemy.orm import Session,defer
from .. import models as m,voiceexports as ve,voiceprojects as vp,voicestudio as vs,jobs
from ..crud import get_or_404
from ..db import get_session

router=APIRouter(prefix='/api/voice/projects',tags=['Voice exports'])


@router.post('/{project_id}/exports/preview')
def preview(project_id:int,body:ve.Preview,session:Session=Depends(get_session)):
    project=vp.start(session,project_id,body)
    return ve.plan(session,project,body.segment_ids,body.pause_ms,body.segment_refs)


@router.post('/{project_id}/exports/preflight')
def preflight(project_id:int,body:ve.Preview,session:Session=Depends(get_session)):
    project=vp.start(session,project_id,body)
    result=ve.plan(session,project,body.segment_ids,body.pause_ms,body.segment_refs)
    session.rollback()
    return ve.preflight(result['snapshot'],result['fingerprint']).to_dict()


@router.get('/{project_id}/exports/segments')
def candidates(project_id:int,chapter:int|None=Query(None,ge=0,le=2147483647),limit:int=Query(20,ge=1,le=100),
               offset:int=Query(0,ge=0,le=2147483647),session:Session=Depends(get_session)):
    project=get_or_404(session,m.VoiceProject,project_id);q=vp.active(project_id)
    if chapter is not None:q=q.where(m.VoiceSegment.source['book']['chapter_index'].as_integer()==chapter)
    total=session.scalar(select(func.count()).select_from(q.subquery()))
    rows=session.scalars(q.order_by(m.VoiceSegment.position,m.VoiceSegment.id).offset(offset).limit(limit)).all()
    result=[]
    for row in rows:
        accepted=session.scalars(select(m.VoiceRender).where(m.VoiceRender.segment_id==row.id,m.VoiceRender.status=='accepted')).all()
        issue='';valid=False
        try:
            fingerprint=vp.fingerprint(session,row)[0]
            if len(accepted)==1:
                state=vp.render(session,accepted[0],fingerprint);valid=not state['stale'] and state['audio_status']=='ok'
        except HTTPException:issue='reference_invalid'
        confirmed=not row.source.get('suggestion') or bool(row.source.get('speaker_confirmed'))
        result.append({'id':row.id,'uid':row.uid,'version':vs.version_id(session,row),'preview':row.text[:160],
            'speaker':row.source.get('speaker','旁白'),'chapter_index':(row.source.get('book') or {}).get('chapter_index'),
            'confirmed':confirmed,'accepted_current':valid,'issue':issue})
    return {'total':total,'project_uid':project.uid,'project_version':vs.version_id(session,project),'items':result}


@router.post('/{project_id}/exports',status_code=201)
def create(project_id:int,body:ve.Request,session:Session=Depends(get_session)):
    session.connection().exec_driver_sql('BEGIN IMMEDIATE')
    project=get_or_404(session,m.VoiceProject,project_id)
    if project.uid!=body.project_uid:raise HTTPException(409,'工程身份变化')
    return ve.describe(ve.enqueue(session,project,body))


@router.get('/{project_id}/exports')
def listing(project_id:int,limit:int=Query(20,ge=1,le=100),offset:int=Query(0,ge=0,le=2147483647),session:Session=Depends(get_session)):
    get_or_404(session,m.VoiceProject,project_id)
    query=select(m.VoiceExport).where(m.VoiceExport.project_id==project_id)
    total=session.scalar(select(func.count()).select_from(m.VoiceExport).where(m.VoiceExport.project_id==project_id))
    rows=session.scalars(query.options(defer(m.VoiceExport.snapshot)).order_by(m.VoiceExport.id.desc()).offset(offset).limit(limit)).all()
    # Full immutable manifests live in the downloaded archive, not every list page.
    return {'total':total,'items':[ve.describe(row,False) for row in rows]}


@router.post('/{project_id}/exports/{export_id}/cancel')
def cancel(project_id:int,export_id:int,body:vp.Mutation,session:Session=Depends(get_session)):
    project=vp.start(session,project_id,body);row=get_or_404(session,m.VoiceExport,export_id)
    if row.project_id!=project.id:raise HTTPException(404,'导出不属于当前工程')
    if row.status not in ('queued','running'):raise HTTPException(409,'导出已结束')
    row.status='cancelled';row.error_code='cancelled';session.commit()
    job=jobs.get(row.job_id) if row.job_id else None
    if job:job.cancel_requested=True;jobs.manager().save(job)
    return ve.describe(row)
