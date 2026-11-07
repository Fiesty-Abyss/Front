"""Opt-in Mock render jobs over the existing bounded queue and Asset storage."""
import tempfile
import uuid
import hashlib
from fastapi import HTTPException
from sqlalchemy import select, update, func
from . import models as m, jobs, versions as v, voiceprojects as vp, voicestudio as vs
from .config import get_settings
from .db import new_session
from .ingest import ingest_stream


def request_uid(project,segment,key):
    return uuid.uuid5(uuid.NAMESPACE_URL,project.uid+'/'+segment.uid+'/'+key).hex


def recover(engine):
    # Completed audio never gets replayed; interrupted requests require a new key.
    with engine.begin() as conn:
        conn.execute(update(m.VoiceRender).where(m.VoiceRender.status.in_(('queued','running'))).values(status='interrupted'))


def terminal(uid,status,code):
    with new_session() as session:
        session.connection().exec_driver_sql('BEGIN IMMEDIATE')
        row=session.scalar(select(m.VoiceRender).where(m.VoiceRender.uid==uid))
        if row and row.status in ('queued','running'):
            row.status=status;row.snapshot={**row.snapshot,'error_code':code};session.commit()


class JobToken:
    def __init__(self,job):self.job=job
    def check(self):self.job.check()


def stored_hash(asset,expected_size):
    from .tts import AdapterError
    root=get_settings().media_dir.resolve()
    path=(get_settings().data_dir/(asset.file_path or '')).resolve()
    if not path.is_relative_to(root):raise AdapterError('stored_audio_unavailable')
    digest=hashlib.sha256()
    try:
        with path.open('rb') as stream:
            total=0
            while block:=stream.read(min(65536,expected_size+1-total)):
                total+=len(block)
                if total>expected_size:return None
                digest.update(block)
            if total!=expected_size:return None
    except OSError:
        raise AdapterError('stored_audio_unavailable') from None
    return digest.hexdigest()


def run(job,uid):
    from .tts import MockAdapter,SynthesisRequest,VoiceSpec,AdapterError
    try:
        with new_session() as session:
            session.connection().exec_driver_sql('BEGIN IMMEDIATE')
            row=session.scalar(select(m.VoiceRender).where(m.VoiceRender.uid==uid))
            if not row or row.status!='queued':return
            snapshot=dict(row.snapshot);row.status='running';session.commit()
        job.step('生成明确标记的测试音，不执行语音推理')
        request=SynthesisRequest(snapshot['text'],snapshot['recipe'].get('language') or 'und',VoiceSpec('mock-marker',1,'mock-marker',1))
        folder=get_settings().data_dir/'.staging';folder.mkdir(parents=True,exist_ok=True)
        with tempfile.SpooledTemporaryFile(max_size=1024*1024,dir=folder) as output:
            result=MockAdapter().synthesize(request,output,JobToken(job))
            job.step('校验测试WAV与请求身份')
            with new_session() as session:
                session.connection().exec_driver_sql('BEGIN IMMEDIATE')
                row=session.scalar(select(m.VoiceRender).where(m.VoiceRender.uid==uid))
                segment=session.get(m.VoiceSegment,row.segment_id) if row else None
                project=session.get(m.VoiceProject,segment.project_id) if segment else None
                if not row or row.status!='running' or not segment or segment.uid!=snapshot['segment_uid'] or not project or project.uid!=snapshot['project_uid']:
                    raise jobs.Cancelled()
                if project.world_id!=snapshot['world_id']:
                    raise AdapterError('project_scope_changed')
                job.check()
                asset,_=ingest_stream(session,output,'mock-marker.wav',mime='audio/wav',kind='audio',title='Mock测试音（非语音）',expected_sha=result.sha256,
                    extra_meta={'voice_origin':'mock','speech':False})
                if asset.world_id and asset.world_id!=project.world_id:
                    raise AdapterError('output_scope_conflict')
                if stored_hash(asset,result.size)!=result.sha256:
                    raise AdapterError('stored_audio_hash_mismatch')
                session.flush()
                audio_version=v.enable(session,asset,'保留Mock音频版本，非TTS推理')
                row.audio_asset_id=asset.id;row.status='candidate'
                row.snapshot={**row.snapshot,'audio_ref':{'id':asset.id,'identity':vs.identity(asset),'sha256':asset.sha256},
                    'audio_version':audio_version,'duration':result.duration,'speech':False}
                vp.touch(session,project,'保存Mock候选，未自动采纳')
                job.check();session.commit()
                job.result={'render_id':row.id,'render_uid':row.uid,'asset_id':asset.id,'origin':'mock','speech':False}
    except jobs.Cancelled:
        terminal(uid,'cancelled','cancelled');raise
    except Exception as exc:
        code=str(exc) if isinstance(exc,AdapterError) else 'render_failed'
        terminal(uid,'error',code);raise


def enqueue(session,project,segment,body):
    uid=request_uid(project,segment,body.idempotency_key)
    existing=session.scalar(select(m.VoiceRender).where(m.VoiceRender.uid==uid))
    if existing:
        if existing.segment_id!=segment.id or existing.fingerprint!=body.fingerprint or existing.snapshot.get('origin')!='mock':
            raise HTTPException(409,'幂等键已用于不同请求')
        return existing
    vs.guard(session,project,body.project_uid,body.expected_project_version)
    vp.editable(segment)
    if not segment.text.strip():raise HTTPException(422,'请先填写朗读台词')
    digest,snapshot=vp.fingerprint(session,segment)
    if digest!=body.fingerprint:raise HTTPException(409,'台词或参数已变化，请刷新后排队')
    if segment.recipe.get('speed',1)!=1:raise HTTPException(422,'Mock只输出固定标记音，不支持语速参数')
    snapshot.update(origin='mock',speech=False,project_uid=project.uid,world_id=project.world_id,job_id=None)
    row=m.VoiceRender(uid=uid,segment_id=segment.id,fingerprint=digest,snapshot=snapshot,status='queued')
    session.add(row);vp.touch(session,project,'排队Mock流程测试');session.commit()
    try:
        job=jobs.start('voice-mock','Voice Mock测试音（非语音）',2,lambda j:run(j,uid))
    except HTTPException:
        terminal(uid,'error','queue_unavailable');raise
    # The worker can finish before start returns. Atomic JSON update preserves
    # its audio_ref instead of overwriting the completed snapshot with stale data.
    session.execute(update(m.VoiceRender).where(m.VoiceRender.uid==uid).values(snapshot=func.json_set(m.VoiceRender.snapshot,'$.job_id',job.id)))
    session.commit();session.expire_all()
    return session.scalar(select(m.VoiceRender).where(m.VoiceRender.uid==uid))
