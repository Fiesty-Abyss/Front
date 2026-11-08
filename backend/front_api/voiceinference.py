"""Explicit loopback-only TTS requests over VoiceRender/Asset and shared jobs.

No model imports, environment installs, downloads, weight switches or service
control. Audition samples are never implicitly used as cloning references.
"""
import os
import tempfile
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit
from fastapi import HTTPException
from pydantic import BaseModel,ConfigDict,Field,StrictInt,field_validator
from sqlalchemy import select,update,func
from . import models as m,jobs,versions as v,voiceprojects as vp,voicestudio as vs,voicerenders as vr
from .config import get_settings
from .db import new_session


class Parameters(BaseModel):
    model_config=ConfigDict(extra='forbid')
    top_k:StrictInt|None=Field(default=None,ge=1,le=100)
    top_p:float|None=Field(default=None,ge=.01,le=1,allow_inf_nan=False)
    temperature:float|None=Field(default=None,ge=.01,le=2,allow_inf_nan=False)
    text_split_method:Literal['cut0','cut5']|None=None

    @field_validator('top_p','temperature',mode='before')
    @classmethod
    def numeric_not_boolean(cls,value):
        if isinstance(value,bool):raise ValueError('数值参数不能使用布尔值')
        return value


class AudioRef(BaseModel):
    model_config=ConfigDict(extra='forbid')
    id:StrictInt=Field(gt=0,le=9223372036854775807)
    identity:str=Field(min_length=1,max_length=50)
    sha256:str=Field(pattern=r'^[0-9a-f]{64}$')


class Request(vp.Mutation):
    fingerprint:str=Field(pattern=r'^[0-9a-f]{64}$')
    idempotency_key:str=Field(min_length=1,max_length=80,pattern=r'^[A-Za-z0-9_-]+$')
    reference:AudioRef
    reference_text:str=Field(default='',max_length=20000)
    reference_language:str=Field(min_length=1,max_length=40)
    rights_source:str=Field(min_length=1,max_length=2000)
    seed:StrictInt=Field(default=-1,ge=-1,le=4294967295)
    parameters:Parameters=Field(default_factory=Parameters)
    rights_authorized:Literal[True]
    confirm_local_request:Literal[True]
    confirm_loaded_model_unverified:Literal[True]
    confirm_model_rights:Literal[True]

    @field_validator('rights_source','reference_language')
    @classmethod
    def nonblank(cls,value):
        if not value.strip():raise ValueError('请填写非空来源与语言')
        return value.strip()

    @field_validator('rights_authorized','confirm_local_request','confirm_loaded_model_unverified','confirm_model_rights',mode='before')
    @classmethod
    def explicit(cls,value):
        if value is not True:raise ValueError('需要明确确认授权、本机调用及外部模型尚未核验')
        return value


def enabled():
    if os.environ.get('FRONT_ENABLE_LOCAL_TTS')!='1':
        raise HTTPException(404,'本机TTS API默认关闭；请先单独配置并明确启用，不会自动启动服务')


def endpoint(provider):
    from .tts import endpoint as parse,AdapterError
    if provider.engine!='gpt_sovits':raise HTTPException(422,'当前受控入口仅支持已核对的GPT-SoVITS协议')
    if provider.credential_id:raise HTTPException(422,'此本机适配入口暂不支持凭据代理，不读取聊天API密钥')
    try:
        base,_=parse(provider.endpoint);url=urlsplit(base)
        if url.hostname not in ('127.0.0.1','::1') or url.path not in ('','/'):
            raise ValueError()
    except (AdapterError,ValueError):
        raise HTTPException(422,'仅支持用户已配置的字面回环地址与根API路径；不代理远程或DNS地址') from None
    return base


def request_data(body):
    return body.model_dump(exclude={'project_uid','expected_project_version','expected_segment_version','idempotency_key'})


def reference_scope(session,project,reference,profile=None):
    ref=vs.sample(session,reference);asset=session.get(m.Asset,ref['id'])
    if asset.world_id and asset.world_id!=project.world_id:raise HTTPException(422,'参考音频属于不同世界观')
    source=session.get(m.VoiceBookSource,project.id)
    if source and source.snapshot.get('work_id') and asset.work_id and asset.work_id!=source.snapshot['work_id']:
        raise HTTPException(422,'参考音频属于不同小说作品')
    from .voicereferences import validate_synthesis
    validate_synthesis(session,asset,profile)
    return asset


def plan(session,project,segment,body):
    from .tts import GPT_CONTRACT
    from .voicefingerprints import digest
    vp.editable(segment)
    if segment.source.get('suggestion') and not segment.source.get('speaker_confirmed'):
        raise HTTPException(409,'请先人工确认说话人')
    current,snapshot=vp.fingerprint(session,segment)
    if current!=body.fingerprint:raise HTTPException(409,'台词或合成配置已变化，请重新预览')
    if not segment.text.strip():raise HTTPException(422,'请先填写台词')
    profile=session.get(m.VoiceProfile,segment.profile_id) if segment.profile_id else None
    model=session.get(m.VoiceModel,profile.model_id) if profile and profile.model_id else None
    provider=session.get(m.VoiceProvider,model.provider_id) if model and model.provider_id else None
    if not profile or not model or not provider:raise HTTPException(422,'请先关联声线、模型与引擎登记')
    if not model.source.strip() or not model.license.strip():raise HTTPException(422,'请先登记模型来源与使用许可，再明确确认本次使用权')
    if any(not snapshot[k].get('version') for k in ('profile','model','provider')):
        raise HTTPException(409,'请启用声线、模型与引擎的版本记录后重试')
    base=endpoint(provider)
    if vs.inspect_file(model.file_path)['status']!='file_present':raise HTTPException(409,'登记的模型文件缺失或不可读；不会替换/下载权重')
    language=segment.recipe.get('language') or profile.language
    if not language:raise HTTPException(422,'请填写实际请求语言')
    asset=reference_scope(session,project,body.reference.model_dump(),profile)
    if (asset.original_name or '').lower().endswith('.wav') is False:
        raise HTTPException(422,'此入口只接受已导入PCM WAV作为参考，不自动转码原件')
    from .routers.assets import _file_of
    path=_file_of(asset)
    try:
        if path.stat().st_size>64*1024*1024:raise HTTPException(413,'参考WAV超过64MiB，请先制作独立短片段')
    except OSError:raise HTTPException(409,'参考文件不可读') from None
    settings=request_data(body)
    snapshot.update(origin='gpt_sovits',speech=None,contract=GPT_CONTRACT,project_uid=project.uid,world_id=project.world_id,
        local_request=settings,request_fingerprint=digest({'contract':GPT_CONTRACT,**settings}),
        local_provider={'id':provider.id,'uid':provider.uid,'endpoint':base},effective_language=language,
        registered_model_version=model.model_version,loaded_model_verified=False,server_revision_verified=False,quality_verified=False,job_id=None)
    return current,snapshot,asset


def adapter(base):
    from .tts import GPTSoVITSAdapter
    return GPTSoVITSAdapter(base,allowed_origins=[base])


def synthesize(job,snapshot,output):
    from .tts import VoiceSpec,SynthesisRequest,AdapterError,validated_wav
    from .voiceexports import copy_audio
    request=snapshot['local_request']
    try:
        with new_session() as session:
            row=session.scalar(select(m.VoiceSegment).where(m.VoiceSegment.uid==snapshot['segment_uid']))
            if not row or vp.fingerprint(session,row)[0]!=request['fingerprint']:raise AdapterError('configuration_changed')
            project=session.get(m.VoiceProject,row.project_id)
            if not project or project.uid!=snapshot['project_uid'] or project.world_id!=snapshot['world_id']:
                raise AdapterError('project_scope_changed')
            reference_scope(session,project,request['reference'],session.get(m.VoiceProfile,row.profile_id) if row.profile_id else None)
        staging=get_settings().data_dir/'.staging';staging.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='local-tts-reference-',dir=staging) as folder:
            reference=Path(folder)/'reference.wav'
            with new_session() as session:copy_audio(session,{'audio_ref':request['reference']},reference,job)
            with reference.open('rb') as stream:checked=validated_wav(stream,'reference')
            if checked.duration>30:raise AdapterError('reference_duration_exceeds_front_limit')
            voice=VoiceSpec(snapshot['profile']['uid'],snapshot['profile']['version'],snapshot['model']['uid'],snapshot['model']['version'],
                reference_path=str(reference.resolve()),reference_text=request['reference_text'],reference_language=request['reference_language'],
                rights_authorized=True,rights_source=request['rights_source'])
            actual=SynthesisRequest(snapshot['text'],snapshot['effective_language'],voice,
                speed=snapshot['recipe'].get('speed',1),seed=request['seed'],parameters={k:v for k,v in request['parameters'].items() if v is not None})
            engine=adapter(snapshot['local_provider']['endpoint'])
            try:
                job.check();health=engine.health(cancel=vr.JobToken(job))
                if not health.get('contract_matches'):raise AdapterError('contract_mismatch')
                with new_session() as session:
                    row=session.scalar(select(m.VoiceSegment).where(m.VoiceSegment.uid==snapshot['segment_uid']))
                    if not row or vp.fingerprint(session,row)[0]!=request['fingerprint']:raise AdapterError('configuration_changed')
                    reference_scope(session,session.get(m.VoiceProject,row.project_id),request['reference'],session.get(m.VoiceProfile,row.profile_id) if row.profile_id else None)
                job.step('调用已确认本机API；不切换权重，实际加载模型尚未核验')
                return engine.synthesize(actual,output,vr.JobToken(job))
            finally:engine.close()
    except HTTPException:raise AdapterError('reference_or_configuration_changed') from None
    except OSError:raise AdapterError('reference_unavailable') from None


def enqueue(session,project,segment,body):
    from .tts import GPT_CONTRACT
    from .voicefingerprints import digest
    uid=vr.request_uid(project,segment,'local-tts:'+body.idempotency_key)
    existing=session.scalar(select(m.VoiceRender).where(m.VoiceRender.uid==uid))
    expected=digest({'contract':GPT_CONTRACT,**request_data(body)})
    if existing:
        if existing.segment_id!=segment.id or existing.snapshot.get('origin')!='gpt_sovits' or existing.snapshot.get('request_fingerprint')!=expected:
            raise HTTPException(409,'幂等键已用于不同的本机合成请求')
        return existing
    vs.guard(session,project,body.project_uid,body.expected_project_version)
    fingerprint,snapshot,reference=plan(session,project,segment,body)
    snapshot['reference_version']=v.enable(session,reference,'保留本机TTS授权参考音频版本')
    row=m.VoiceRender(uid=uid,segment_id=segment.id,fingerprint=fingerprint,snapshot=snapshot,status='queued')
    session.add(row);vp.touch(session,project,'排队用户明确确认的本机TTS请求');session.commit()
    try:job=jobs.start('voice-local-tts','已授权参考的本机TTS API',3,lambda j:vr.run(j,uid))
    except HTTPException:
        vr.terminal(uid,'error','queue_unavailable');raise
    session.execute(update(m.VoiceRender).where(m.VoiceRender.uid==uid).values(snapshot=func.json_set(m.VoiceRender.snapshot,'$.job_id',job.id)))
    session.commit();session.expire_all()
    return session.scalar(select(m.VoiceRender).where(m.VoiceRender.uid==uid))
