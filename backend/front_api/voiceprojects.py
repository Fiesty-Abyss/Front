"""Dialogue projects; manual audio candidates, immutable source/recipe snapshots."""
from pydantic import BaseModel, ConfigDict, Field
from fastapi import HTTPException
from sqlalchemy import select, func
from . import models as m, versions as v, voicestudio as vs, voicefingerprints as vf
from .crud import get_or_404


class ProjectDraft(vs.Draft):
    world_id: int | None = Field(default=None, gt=0)


class Mutation(BaseModel):
    model_config = ConfigDict(extra='forbid')
    project_uid: str = Field(min_length=32, max_length=32)
    expected_project_version: int = Field(gt=0)
    expected_segment_version: int | None = Field(default=None, gt=0)


class SegmentDraft(Mutation):
    text: str = Field(default='', max_length=20000)
    speaker: str = Field(default='旁白', max_length=200)
    profile_id: int | None = Field(default=None, gt=0)
    language: str = Field(default='', max_length=40)
    speed: float = Field(default=1, ge=0.25, le=4, allow_inf_nan=False)
    confirm_speaker: bool = False


class Split(Mutation):
    at: int = Field(gt=0)


class Move(Mutation):
    direction: int = Field(ge=-1, le=1)


class Candidate(Mutation):
    audio_ref: dict
    fingerprint: str = Field(min_length=64, max_length=64)
    note: str = Field(default='', max_length=2000)


def active(project_id):
    return select(m.VoiceSegment).where(m.VoiceSegment.project_id==project_id,
        m.VoiceSegment.source['archived'].as_boolean().is_not(True))


def start(session, project_id, body):
    session.connection().exec_driver_sql('BEGIN IMMEDIATE')
    project=get_or_404(session,m.VoiceProject,project_id)
    vs.guard(session,project,body.project_uid,body.expected_project_version)
    return project


def segment(session, project, segment_id):
    obj=get_or_404(session,m.VoiceSegment,segment_id)
    if obj.project_id!=project.id:
        raise HTTPException(404,'片段不属于当前工程')
    return obj


def editable(obj):
    if obj.source.get('archived'):
        raise HTTPException(409,'片段已被拆分或合并；保留历史，但不能覆盖')


def recipe(session, project, body):
    ref={}
    if body.profile_id:
        profile=get_or_404(session,m.VoiceProfile,body.profile_id)
        issues=vs.diagnostics(session,profile,include_sample=False)
        if issues:
            raise HTTPException(409,'声线关联异常，请在声线档案审核后重试')
        from .voicebooks import check_work
        check_work(session,project,profile)
        world=profile.binding.get('world')
        if world and project.world_id!=world[0]:
            raise HTTPException(422,'声线与工程世界观不同；不自动跨世界引用')
        ref={'id':profile.id,'uid':profile.uid}
    return {'profile':ref,'language':body.language,'speed':body.speed}


def apply(session, project, obj, body):
    validated=recipe(session,project,body)
    obj.text=body.text
    obj.profile_id=body.profile_id
    obj.recipe=validated
    obj.source={**(obj.source or {}),'speaker':body.speaker,'archived':False,
        'speaker_confirmed':body.confirm_speaker if (obj.source or {}).get('suggestion') else True}


def fingerprint(session,obj):
    profile_cfg=model_cfg=provider_cfg=None
    data={'segment_uid':obj.uid,'text':obj.text,'speaker':obj.source.get('speaker','旁白'),'recipe':obj.recipe}
    ref=obj.recipe.get('profile') or {}
    if ref:
        profile=session.get(m.VoiceProfile,obj.profile_id) if obj.profile_id else None
        if not profile or profile.uid!=ref.get('uid'):
            raise HTTPException(409,'声线已删除或身份变化')
        issues=vs.diagnostics(session,profile,include_sample=False)
        if issues:
            raise HTTPException(409,'声线身份或范围绑定异常，请审核档案')
        project=session.get(m.VoiceProject,obj.project_id)
        from .voicebooks import check_work
        check_work(session,project,profile)
        world=profile.binding.get('world')
        if world and (not project or project.world_id!=world[0]):
            raise HTTPException(409,'工程与声线的世界观归属不同')
        profile_cfg={k:getattr(profile,k) for k in ('uid','voice_key','language')}
        data['profile']={'id':profile.id,'uid':profile.uid,'version':vs.version_id(session,profile),'voice_key':profile.voice_key}
        if profile.model_id:
            model=get_or_404(session,m.VoiceModel,profile.model_id)
            model_cfg={k:getattr(model,k) for k in ('uid','file_path','model_version')}
            data['model']={'id':model.id,'uid':model.uid,'version':vs.version_id(session,model)}
            if model.provider_id:
                provider=get_or_404(session,m.VoiceProvider,model.provider_id)
                provider_cfg={k:getattr(provider,k) for k in ('uid','engine','endpoint','credential_id')}
                data['provider']={'id':provider.id,'uid':provider.uid,'version':vs.version_id(session,provider),'engine':provider.engine}
    data['synthesis']=vf.synthesis(data,profile_cfg,model_cfg,provider_cfg)
    return vf.digest(data['synthesis']),data


def describe(session,obj,brief=False):
    value={'id':obj.id,'uid':obj.uid,'project_id':obj.project_id,'position':obj.position,'text':obj.text[:120] if brief else obj.text,
        'speaker':obj.source.get('speaker','旁白'),'archived':bool(obj.source.get('archived')),'profile_id':obj.profile_id,
        'recipe':obj.recipe,'version':vs.version_id(session,obj)}
    if not brief:value['source']=obj.source
    try:
        value['fingerprint']=fingerprint(session,obj)[0];value['issue']=''
    except HTTPException as exc:
        value['fingerprint']=None;value['issue']=str(exc.detail)
    return value


def touch(session,project,note):
    session.flush()
    v.record(session,project,note,source='voice:structure',force=True)


def render(session,obj,current):
    status='ok' if obj.snapshot.get('audio_ref') else 'not_generated'
    try:
        vs.sample(session,obj.snapshot.get('audio_ref') or {})
    except HTTPException:
        status='missing_or_changed'
    if status=='ok':
        asset=session.get(m.Asset,obj.audio_asset_id) if obj.audio_asset_id else None
        segment=session.get(m.VoiceSegment,obj.segment_id)
        project=session.get(m.VoiceProject,segment.project_id) if segment else None
        if not asset or not project or (asset.world_id and asset.world_id!=project.world_id):
            status='scope_changed'
    effective=obj.status;execution_issue=''
    if obj.status in ('queued','running','interrupted') and obj.snapshot.get('job_id'):
        from . import jobs
        job=jobs.get(obj.snapshot['job_id'])
        # A list/detail transaction may still hold an older ORM row while the
        # worker has committed the candidate and marked its job done. Never
        # turn that successful concurrent completion into a fabricated error;
        # the next read sees the committed candidate. Startup recovery handles
        # genuinely unfinished DB rows without replaying the external request.
        if job and job.status in ('cancelled','error','interrupted'):
            effective=job.status
            execution_issue='任务记录已结束，未提交新候选；原有音频保留'
    return {'id':obj.id,'uid':obj.uid,'status':effective,'recorded_status':obj.status,'execution_issue':execution_issue,'origin':obj.snapshot.get('origin'),
        'note':obj.snapshot.get('note',''),'created_at':obj.created_at,'audio_ref':obj.snapshot.get('audio_ref'),
        'fingerprint':obj.fingerprint,'stale':not vf.is_current(session,obj,current),'audio_status':status,'snapshot':obj.snapshot}


def validate_restore(session,obj,data):
    if data.get('uid')!=obj.uid:
        raise HTTPException(409,'历史身份不匹配')
    if isinstance(obj,m.VoiceSegment):
        if data.get('project_id')!=obj.project_id or bool(data.get('source',{}).get('archived'))!=bool(obj.source.get('archived')):
            raise HTTPException(409,'历史目录结构不同；请手动编辑，不自动恢复拆分/合并')
        ref=(data.get('recipe') or {}).get('profile') or {}
        if ref:
            profile=session.get(m.VoiceProfile,data.get('profile_id'))
            if not profile or profile.uid!=ref.get('uid'):
                raise HTTPException(409,'历史声线已删除或身份变化')


def after_restore(session,obj):
    if isinstance(obj,m.VoiceSegment):
        touch(session,get_or_404(session,m.VoiceProject,obj.project_id),'恢复片段为新版本')
