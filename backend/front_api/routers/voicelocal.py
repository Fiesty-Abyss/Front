"""Disabled-by-default, explicit loopback TTS. Never starts external services."""
import os
from urllib.parse import urlsplit
from typing import Literal
from fastapi import APIRouter,Depends,HTTPException,Request
from pydantic import BaseModel,ConfigDict,Field,field_validator
from sqlalchemy.orm import Session
from .. import models as m,jobs,voicestudio as vs,voiceprojects as vp,voiceinference as local,voicerenders as vr
from ..crud import get_or_404
from ..db import get_session,new_session

router=APIRouter(prefix='/api/voice',tags=['Explicit local TTS'])


def network_request(request:Request):
    local.enabled()
    origin=request.headers.get('origin')
    if not origin:return  # CLI clients have no browser Origin.
    try:
        parsed=urlsplit(origin)
        same=origin==str(request.base_url).rstrip('/')
        dev=origin in ('http://127.0.0.1:5173','http://localhost:5173')
        if parsed.hostname not in ('127.0.0.1','::1','localhost') or not (same or dev):raise ValueError()
    except ValueError:raise HTTPException(403,'本机合成不接受跨站来源') from None


@router.get('/local-capabilities')
def capabilities():
    return {'enabled':os.environ.get('FRONT_ENABLE_LOCAL_TTS')=='1','engine':'gpt_sovits',
        'endpoint_policy':'literal_loopback_root','training':False,'weight_switching':False,
        'runtime_verified':False,'cancellation':'client_only','reference_formats':['PCM WAV']}


@router.post('/projects/{project_id}/segments/{segment_id}/local-requests/preview')
def preview(project_id:int,segment_id:int,body:local.Request,request:Request,session:Session=Depends(get_session)):
    network_request(request);project=vp.start(session,project_id,body);segment=vp.segment(session,project,segment_id)
    _,snapshot,_=local.plan(session,project,segment,body)
    return {'request_fingerprint':snapshot['request_fingerprint'],'contract':snapshot['contract'],
        'provider':snapshot['provider'],'model':snapshot['model'],'profile':snapshot['profile'],
        'reference':body.reference.model_dump(),'reference_file_validation':'queued_worker',
        'will_contact_engine':False,'loaded_model_verified':False,'server_revision_verified':False}


@router.post('/projects/{project_id}/segments/{segment_id}/local-requests',status_code=201)
def create(project_id:int,segment_id:int,body:local.Request,request:Request,session:Session=Depends(get_session)):
    network_request(request);session.connection().exec_driver_sql('BEGIN IMMEDIATE')
    project=get_or_404(session,m.VoiceProject,project_id)
    if project.uid!=body.project_uid:raise HTTPException(409,'工程身份已变化')
    segment=vp.segment(session,project,segment_id);row=local.enqueue(session,project,segment,body)
    try:current=vp.fingerprint(session,segment)[0]
    except HTTPException:current=None
    return {'project':vs.serialize(session,project),'render':vp.render(session,row,current)}


@router.get('/projects/{project_id}/segments/{segment_id}/local-requests/{render_id}')
def detail(project_id:int,segment_id:int,render_id:int,session:Session=Depends(get_session)):
    project=get_or_404(session,m.VoiceProject,project_id);segment=vp.segment(session,project,segment_id)
    row=get_or_404(session,m.VoiceRender,render_id)
    if row.segment_id!=segment.id or row.snapshot.get('origin')!='gpt_sovits':raise HTTPException(404,'请求不属于此片段')
    try:current=vp.fingerprint(session,segment)[0]
    except HTTPException:current=None
    return {'project':vs.serialize(session,project),'render':vp.render(session,row,current)}


@router.post('/projects/{project_id}/segments/{segment_id}/local-requests/{render_id}/cancel')
def cancel(project_id:int,segment_id:int,render_id:int,body:vp.Mutation,request:Request,session:Session=Depends(get_session)):
    network_request(request);session.connection().exec_driver_sql('BEGIN IMMEDIATE')
    project=get_or_404(session,m.VoiceProject,project_id)
    if project.uid!=body.project_uid:raise HTTPException(409,'工程身份已变化')
    segment=vp.segment(session,project,segment_id);row=get_or_404(session,m.VoiceRender,render_id)
    if row.segment_id!=segment.id or row.snapshot.get('origin')!='gpt_sovits':raise HTTPException(404,'请求不属于此片段')
    if row.status not in ('queued','running'):raise HTTPException(409,'请求已结束，已有结果保留')
    job=jobs.get(row.snapshot.get('job_id'))
    if job:job.cancel_requested=True;jobs.manager().save(job)
    row.status='cancelled';vp.touch(session,project,'取消本机TTS客户端请求；不控制外部服务');session.commit()
    return {'project':vs.serialize(session,project),'render':vp.render(session,row,None)}


class Check(BaseModel):
    model_config=ConfigDict(extra='forbid')
    expected_uid:str=Field(pattern=r'^[0-9a-f]{32}$')
    expected_version:int=Field(gt=0)
    confirm_local_request:Literal[True]

    @field_validator('confirm_local_request',mode='before')
    @classmethod
    def explicit(cls,value):
        if value is not True:raise ValueError('请明确确认检查已配置本机服务')
        return value


@router.post('/providers/{provider_id}/check-local')
def check(provider_id:int,body:Check,request:Request,session:Session=Depends(get_session)):
    network_request(request);provider=get_or_404(session,m.VoiceProvider,provider_id)
    vs.guard(session,provider,body.expected_uid,body.expected_version);base=local.endpoint(provider)
    def probe(job):
        with new_session() as session:
            row=get_or_404(session,m.VoiceProvider,provider_id);vs.guard(session,row,body.expected_uid,body.expected_version)
        engine=local.adapter(base)
        try:job.check();job.result=engine.health(cancel=vr.JobToken(job));job.step('只检查API字段，不验证权重或实际推理')
        finally:engine.close()
    return jobs.start('voice-local-health','检查已配置本机TTS协议',1,probe).to_dict()
