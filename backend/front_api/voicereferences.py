"""Optional reference annotations on shared Asset, never a second media store.

Self-declared permissions are records, not legal verification or authority to
start inference/training. Technical QC is explicit, bounded and local only.
"""
import tempfile
from pathlib import Path
from typing import Literal
from fastapi import HTTPException
from pydantic import BaseModel,ConfigDict,Field,StrictBool,StrictInt,model_validator,field_validator
from . import models as m,versions as v,voicestudio as vs,jobs,voiceexports as ve
from .voiceinference import AudioRef
from .crud import get_or_404
from .config import get_settings
from .db import new_session


class ProfileRef(BaseModel):
    model_config=ConfigDict(extra='forbid')
    id:StrictInt=Field(gt=0,le=9223372036854775807)
    uid:str=Field(pattern=r'^[0-9a-f]{32}$')


class Declaration(BaseModel):
    model_config=ConfigDict(extra='forbid')
    speaker_authorized:StrictBool=False
    allow_zero_shot:StrictBool=False
    allow_training:StrictBool=False
    statement:str=Field(default='',max_length=2000)


class Data(BaseModel):
    model_config=ConfigDict(extra='forbid')
    kind:Literal['audition','zero_shot','training']='audition'
    profile_ref:ProfileRef|None=None
    language:str=Field(default='',max_length=40)
    reference_text:str=Field(default='',max_length=20000)
    source:str=Field(default='',max_length=2000)
    license:str=Field(default='',max_length=20000)
    notes:str=Field(default='',max_length=5000)
    declaration:Declaration=Field(default_factory=Declaration)

    @model_validator(mode='after')
    def explicit_permissions(self):
        d=self.declaration
        if (d.allow_zero_shot or d.allow_training) and (not d.speaker_authorized or not d.statement.strip() or not self.source.strip() or not self.license.strip()):
            raise ValueError('用途许可需同时记录声音使用权、来源、许可和声明；未获授权可保留待审核档案')
        return self


class Mutation(BaseModel):
    model_config=ConfigDict(extra='forbid')
    asset_ref:AudioRef
    expected_asset_version:StrictInt|None=Field(default=None,gt=0)


class Save(Mutation):
    data:Data


class Inspect(Mutation):
    confirm_local_analysis:Literal[True]

    @field_validator('confirm_local_analysis',mode='before')
    @classmethod
    def explicit(cls,value):
        if value is not True:raise ValueError('请明确确认本机技术分析，不发送音频到服务')
        return value


def asset(session,aid):
    if type(aid) is not int or not 1<=aid<=9223372036854775807:raise HTTPException(422,'素材编号超出有效范围')
    row=get_or_404(session,m.Asset,aid)
    if row.kind!='audio':raise HTTPException(422,'请选择素材库中的音频')
    return row


def scope(session,row,data):
    ref=data.profile_ref
    if ref is None:return None
    profile=get_or_404(session,m.VoiceProfile,ref.id)
    if profile.uid!=ref.uid or vs.diagnostics(session,profile,include_sample=False):raise HTTPException(409,'关联声线身份或归属变化')
    binding=vs.binding(session,profile.character_id,profile.oc_id)
    for key in ('world','work'):
        actual=getattr(row,key+'_id');bound=binding.get(key)
        if actual and (not bound or bound[0]!=actual):raise HTTPException(422,'参考音频与声线的世界观/作品不同，不自动跨范围关联')
    return binding


def guard(session,row,body):
    if body.asset_ref.id!=row.id:raise HTTPException(409,'素材身份不匹配')
    vs.sample(session,body.asset_ref.model_dump())
    if vs.version_id(session,row)!=body.expected_asset_version:raise HTTPException(409,'素材或参考档案已变化，请刷新后合并；未覆盖资料')


def detail(session,row):
    envelope=(row.meta or {}).get('voice_reference')
    value=None;issues=[]
    if envelope:
        try:
            if envelope.get('schema')!=1:raise ValueError()
            data=Data.model_validate(envelope['data']);value=data.model_dump()
            if envelope.get('identity')!=vs.identity(row) or envelope.get('sha256')!=row.sha256:issues.append('reference_content_changed')
            if scope(session,row,data)!=envelope.get('profile_scope'):issues.append('profile_scope_changed')
        except HTTPException:issues.append('profile_missing_or_scope_changed')
        except (ValueError,TypeError,KeyError,AttributeError):issues.append('invalid_reference_annotation')
    qc=(row.meta or {}).get('voice_reference_qc')
    if not isinstance(qc,dict):qc=None
    if qc and qc.get('schema')!=1:issues.append('unsupported_qc_schema');qc=None
    if qc and qc.get('audio_ref')!={'id':row.id,'identity':vs.identity(row),'sha256':row.sha256}:issues.append('qc_content_changed')
    return {'asset_ref':{'id':row.id,'identity':vs.identity(row),'sha256':row.sha256},'title':row.title,
        'version':vs.version_id(session,row),'world_id':row.world_id,'work_id':row.work_id,'data':value,'issues':issues,
        'qc':qc,'rights_verified':False,'inference_enabled_by_record':False,'training_enabled_by_record':False}


def save(session,row,body):
    guard(session,row,body);binding=scope(session,row,body.data)
    old=(row.meta or {}).get('voice_reference') or {}
    if not isinstance(old,dict) or not isinstance(old.get('data',{}),dict):
        raise HTTPException(409,'旧参考档案结构异常，请先在素材历史中核对，不自动覆盖')
    if old and old.get('schema')!=1:raise HTTPException(409,'参考档案使用较新或未知格式，当前版本不覆盖')
    olddata=old.get('data') or {}
    if olddata.get('profile_ref') and olddata.get('profile_ref')==body.data.model_dump()['profile_ref'] and old.get('profile_scope')!=binding:
        raise HTTPException(409,'声线归属变化；先明确解除关联，再审核重新绑定')
    row.meta={**(row.meta or {}),'voice_reference':{'schema':1,'identity':vs.identity(row),'sha256':row.sha256,
        'data':body.data.model_dump(),'profile_scope':binding}}
    session.flush();v.enable(session,row,'保存参考音频档案；声明不等于克隆或训练授权验证');session.commit()
    return detail(session,row)


def validate_synthesis(session,row,profile=None):
    # Unannotated legacy references still require the explicit per-request
    # declaration at the local-TTS boundary. A saved restriction may never be
    # silently overridden by those request checkboxes.
    if 'voice_reference' not in (row.meta or {}):return
    state=detail(session,row)
    if not state['data'] or any(i!='qc_content_changed' for i in state['issues']):
        raise HTTPException(409,'参考档案或关联已变化，请先人工审核')
    data=Data.model_validate(state['data']);d=data.declaration
    if data.kind!='zero_shot' or not d.speaker_authorized or not d.allow_zero_shot:
        raise HTTPException(409,'参考档案没有零样本用途声明；试听/训练许可不能替代本次使用权')
    if data.profile_ref and profile and data.profile_ref.uid!=profile.uid:
        raise HTTPException(422,'参考档案关联另一声线，请先明确审核关联')


def inspect(session,row,body):
    guard(session,row,body)
    existing=(row.meta or {}).get('voice_reference_qc')
    if existing and (not isinstance(existing,dict) or existing.get('schema')!=1):
        raise HTTPException(409,'已有较新或未知技术报告，当前版本不覆盖')
    v.enable(session,row,'技术分析前保留素材版本');session.commit()
    expected=vs.version_id(session,row);ref=body.asset_ref.model_dump()
    def checked(session):
        obj=asset(session,ref['id']);vs.sample(session,ref)
        if vs.version_id(session,obj)!=expected:raise HTTPException(409,'分析期间素材已变化，结果未覆盖现有档案')
        return obj
    def perform(job):
        with new_session() as s:checked(s)
        folder=get_settings().data_dir/'.staging';folder.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='voice-reference-qc-',dir=folder) as temp:
            dest=Path(temp)/'reference.wav';job.check()
            with new_session() as s:ve.copy_audio(s,{'audio_ref':ref},dest,job)
            job.step('已在自有暂存校验音频Hash；未改原文件')
            info=ve.inspect_pcm(dest,job);job.step('完整PCM技术分析；不识别说话人、转写或评定音质')
            report={'schema':1,'audio_ref':ref,'analyzed_at':m.utcnow().isoformat(),'job_id':job.id,'pcm':info,
                'reference_exceeds_front_tts_30s':info['duration_seconds']>30,'speech_quality_verified':False,'rights_verified':False,
                'will_synthesize':False,'will_train':False,'method':'bounded_pcm_scan_v1'}
            with new_session() as s:
                s.connection().exec_driver_sql('BEGIN IMMEDIATE');obj=checked(s);job.check()
                obj.meta={**(obj.meta or {}),'voice_reference_qc':report};s.flush();v.enable(s,obj,'保存只读PCM技术检查报告');job.check();s.commit()
                job.result={'asset_id':obj.id,'asset_version':vs.version_id(s,obj),'report':report}
            job.step('报告与版本已保存；声音使用权和真实语音质量仍需人工核对')
    def analyze(job):
        try:perform(job)
        except HTTPException as exc:
            job.result={'error_code':'reference_validation_failed_'+str(exc.status_code)};raise
        except OSError:
            job.result={'error_code':'reference_file_unreadable'};raise
    return jobs.start('voice-reference-qc','参考音频本机PCM技术检查',3,analyze)
