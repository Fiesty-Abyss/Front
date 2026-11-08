"""Paged novel speaker review; explicit atomic updates never replace narration."""
from types import SimpleNamespace
from fastapi import HTTPException
from pydantic import BaseModel,ConfigDict,Field,StrictInt,field_validator
from sqlalchemy import select,func
from . import models as m,voiceprojects as vp,voicestudio as vs


class Entry(BaseModel):
    model_config=ConfigDict(extra='forbid')
    id:StrictInt=Field(gt=0,le=9223372036854775807)
    uid:str=Field(pattern=r'^[0-9a-f]{32}$')
    version:int=Field(gt=0)
    speaker:str=Field(max_length=200)
    profile_id:int|None=Field(default=None,gt=0)
    confirm:bool=False


class Review(vp.Mutation):
    entries:list[Entry]=Field(min_length=1,max_length=100)

    @field_validator('entries')
    @classmethod
    def unique(cls,value):
        if len({e.id for e in value})!=len(value):raise ValueError('同一片段不得重复提交')
        return value


class Selection(vp.Mutation):
    entries:list[Entry]=Field(min_length=1,max_length=100)
    _unique=field_validator('entries')(Review.unique.__func__)


def query(project_id,chapter=None,review='pending'):
    q=vp.active(project_id).where(m.VoiceSegment.source['book'].is_not(None),
        func.json_type(m.VoiceSegment.source,'$.book')=='object')
    if chapter is not None:q=q.where(m.VoiceSegment.source['book']['chapter_index'].as_integer()==chapter)
    confirmed=m.VoiceSegment.source['speaker_confirmed'].as_boolean()
    if review=='pending':q=q.where(confirmed.is_not(True))
    elif review=='confirmed':q=q.where(confirmed.is_(True))
    return q


def brief(session,obj):
    source=obj.source;book=source['book'];suggestion=source.get('suggestion') or {}
    return {'id':obj.id,'uid':obj.uid,'version':vs.version_id(session,obj),'preview':obj.text[:200],
        'speaker':source.get('speaker','待确认'),'confirmed':bool(source.get('speaker_confirmed')),
        'profile_id':obj.profile_id,'chapter_index':book['chapter_index'],
        'start':book['start'],'end':book['end'],'evidence':suggestion.get('evidence','')[:300],
        'evidence_truncated':len(suggestion.get('evidence',''))>300,'kind':suggestion.get('kind'),
        'method':suggestion.get('method'),'source_fingerprint':book['fingerprint']}


def checked(session,project,entries):
    rows=[]
    for entry in entries:
        obj=vp.segment(session,project,entry.id);vp.editable(obj)
        if obj.uid!=entry.uid or vs.version_id(session,obj)!=entry.version:
            raise HTTPException(409,'选定片段已变化，请重新核对；本批未写入')
        if not obj.source.get('book'):raise HTTPException(422,'请选择当前小说工程的来源片段')
        rows.append(obj)
    return rows


def apply(session,project,body):
    rows=checked(session,project,body.entries)
    validated=[]
    for obj,entry in zip(rows,body.entries):
        speaker=entry.speaker.strip()
        if entry.confirm and (not speaker or speaker in ('待确认','未知','?')):
            raise HTTPException(422,'未知说话人须保留待确认；请先人工设置姓名或旁白')
        recipe=vp.recipe(session,project,SimpleNamespace(profile_id=entry.profile_id,
            language=obj.recipe.get('language',''),speed=obj.recipe.get('speed',1)))
        validated.append((obj,entry,speaker,recipe))
    # Validate the complete batch before mutating any ORM object (no autoflush
    # partial writes). Text, source evidence, language, speed and order are intact.
    for obj,entry,speaker,recipe in validated:
        obj.profile_id=entry.profile_id
        obj.recipe={**obj.recipe,'profile':recipe['profile']}
        obj.source={**obj.source,'speaker':speaker or '待确认','speaker_confirmed':entry.confirm}
    vp.touch(session,project,'人工批量审核说话人/声线；朗读稿与证据保留')
    return len(rows)


def prepare(session,project,entries):
    rows=checked(session,project,entries)
    result=[];files={}
    for obj in rows:
        issues=[];fingerprint=None
        if not obj.source.get('speaker_confirmed'):issues.append('speaker_review_required')
        if not obj.text.strip():issues.append('empty_text')
        try:fingerprint=vp.fingerprint(session,obj)[0]
        except HTTPException:issues.append('voice_reference_invalid')
        profile=session.get(m.VoiceProfile,obj.profile_id) if obj.profile_id else None
        model=session.get(m.VoiceModel,profile.model_id) if profile and profile.model_id else None
        provider=session.get(m.VoiceProvider,model.provider_id) if model and model.provider_id else None
        if not profile:issues.append('voice_missing')
        if not model:issues.append('model_missing')
        else:
            if model.uid not in files:files[model.uid]=vs.inspect_file(model.file_path)
            if files[model.uid]['status']!='file_present':issues.append('model_file_'+files[model.uid]['status'])
        if not provider or provider.engine=='unconfigured' or not provider.endpoint:issues.append('engine_unconfigured')
        if not (obj.recipe.get('language') or (profile.language if profile else '')):issues.append('language_missing')
        candidates=session.scalars(select(m.VoiceRender).where(m.VoiceRender.segment_id==obj.id,m.VoiceRender.status=='accepted')).all()
        state=vp.render(session,candidates[0],fingerprint) if len(candidates)==1 else None
        accepted=bool(state and not state['stale'] and state['audio_status']=='ok')
        result.append({'id':obj.id,'uid':obj.uid,'version':vs.version_id(session,obj),'fingerprint':fingerprint,
            'configuration_ready':not issues,'issues':issues,'accepted_current':accepted,
            'runtime_verified':False,'will_synthesize':False})
    return result
