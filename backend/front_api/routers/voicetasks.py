"""Opt-in test-audio API. No real provider or reference audio is sent anywhere."""
import os
from typing import Literal
from fastapi import APIRouter,Depends,HTTPException
from pydantic import Field,field_validator
from sqlalchemy.orm import Session
from .. import jobs,models as m,voiceprojects as vp,voicestudio as vs,voicerenders as vr
from ..crud import get_or_404
from ..db import get_session

router=APIRouter(prefix='/api/voice/projects',tags=['Voice Mock workflow'])


class MockRequest(vp.Mutation):
    idempotency_key:str=Field(min_length=1,max_length=80)
    fingerprint:str=Field(min_length=64,max_length=64)
    confirm_mock:Literal[True]

    @field_validator('confirm_mock',mode='before')
    @classmethod
    def explicit_confirmation(cls,value):
        if value is not True:raise ValueError('必须明确确认这是Mock测试音')
        return value


def enabled():
    if os.environ.get('FRONT_ENABLE_VOICE_MOCK')!='1':
        raise HTTPException(404,'Mock流程未启用；这不是实际语音合成接口')


@router.post('/{project_id}/segments/{segment_id}/mock-requests',status_code=201)
def create(project_id:int,segment_id:int,body:MockRequest,session:Session=Depends(get_session)):
    enabled();session.connection().exec_driver_sql('BEGIN IMMEDIATE')
    project=get_or_404(session,m.VoiceProject,project_id)
    if project.uid!=body.project_uid:raise HTTPException(409,'工程身份已变化')
    segment=vp.segment(session,project,segment_id)
    row=vr.enqueue(session,project,segment,body)
    try:current=vp.fingerprint(session,segment)[0]
    except HTTPException:current=None
    return {'project':vs.serialize(session,project),'render':vp.render(session,row,current)}


@router.post('/{project_id}/segments/{segment_id}/mock-requests/{render_id}/cancel')
def cancel(project_id:int,segment_id:int,render_id:int,body:vp.Mutation,session:Session=Depends(get_session)):
    enabled();session.connection().exec_driver_sql('BEGIN IMMEDIATE')
    project=get_or_404(session,m.VoiceProject,project_id)
    if project.uid!=body.project_uid:raise HTTPException(409,'工程身份已变化')
    segment=vp.segment(session,project,segment_id);row=get_or_404(session,m.VoiceRender,render_id)
    if row.segment_id!=segment.id or row.snapshot.get('origin')!='mock':raise HTTPException(404,'请求不属于当前片段')
    if row.status not in ('queued','running'):raise HTTPException(409,'请求已经结束，保留已有结果')
    job=jobs.get(row.snapshot.get('job_id'))
    if job:
        job.cancel_requested=True;jobs.manager().save(job)
    row.status='cancelled';vp.touch(session,project,'取消Mock测试请求');session.commit()
    return {'project':vs.serialize(session,project),'render':vp.render(session,row,body.fingerprint if hasattr(body,'fingerprint') else None)}
