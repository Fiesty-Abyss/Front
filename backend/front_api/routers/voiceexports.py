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
    return ve.plan(session,project,body.segment_ids)


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
