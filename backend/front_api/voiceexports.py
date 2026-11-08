"""Bounded, explicit exports of accepted PCM WAVs; never inference or transcoding."""
import hashlib
import html
import json
import tempfile
import uuid
import wave
import zipfile
from contextlib import ExitStack
from pathlib import Path

from fastapi import HTTPException
from pydantic import BaseModel,ConfigDict,Field, StrictInt, field_validator
from sqlalchemy import select, update

from . import models as m, jobs, versions as v, voiceprojects as vp, voicestudio as vs
from .config import get_settings
from .crud import get_or_404
from .db import new_session
from .ingest import ingest_stream

MAX_INPUT = 64 * 1024 * 1024
MAX_PCM = 128 * 1024 * 1024


class SegmentRef(BaseModel):
    model_config=ConfigDict(extra='forbid')
    id:StrictInt=Field(gt=0,le=9223372036854775807)
    uid:str=Field(pattern=r'^[0-9a-f]{32}$')
    version:int=Field(gt=0)


class Preview(vp.Mutation):
    segment_ids: list[StrictInt] = Field(min_length=1, max_length=100)
    segment_refs:list[SegmentRef]|None=Field(default=None,min_length=1,max_length=100)
    pause_ms:StrictInt=Field(default=0,ge=0,le=10000)

    @field_validator('segment_ids')
    @classmethod
    def unique_ids(cls, value):
        if any(type(i) is not int or not 1 <= i <= 9223372036854775807 for i in value) or len(set(value)) != len(value):
            raise ValueError('请选择不重复的有效片段')
        return value


class Request(Preview):
    fingerprint: str = Field(pattern=r'^[0-9a-f]{64}$')
    idempotency_key: str = Field(min_length=1, max_length=100, pattern=r'^[A-Za-z0-9_-]+$')


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()


def plan(session, project, ids, pause_ms=0,refs=None):
    rows=session.scalars(vp.active(project.id).where(m.VoiceSegment.id.in_(ids)).order_by(m.VoiceSegment.position,m.VoiceSegment.id)).all()
    if len(rows)!=len(ids):raise HTTPException(409,'选定片段已删除、归档或不属于当前工程')
    if refs is not None:
        tokens={r.id:r for r in refs}
        if len(tokens)!=len(refs) or set(tokens)!=set(ids):raise HTTPException(422,'跨页选择身份清单不匹配')
        if any(obj.uid!=tokens[obj.id].uid or vs.version_id(session,obj)!=tokens[obj.id].version for obj in rows):
            raise HTTPException(409,'跨页选择中的片段已变化，请清空后重新选择')
    entries=[]
    for obj in rows:
        if obj.source.get('suggestion') and not obj.source.get('speaker_confirmed'):
            raise HTTPException(409,'小说片段须先人工确认说话人')
        current=vp.fingerprint(session,obj)[0]
        candidates=session.scalars(select(m.VoiceRender).where(m.VoiceRender.segment_id==obj.id,m.VoiceRender.status=='accepted')).all()
        if len(candidates)!=1:raise HTTPException(409,'每条片段须先明确采纳一个音频版本')
        render=candidates[0]
        state=vp.render(session,render,current)
        if state['stale'] or state['audio_status']!='ok':
            raise HTTPException(409,'已采纳音频或台词发生变化，请重新审核')
        entries.append({'segment_id':obj.id,'segment_uid':obj.uid,'segment_version':vs.version_id(session,obj),
            'fingerprint':current,'render_uid':render.uid,'audio_ref':render.snapshot['audio_ref'],
            'audio_version':render.snapshot.get('audio_version'),'origin':render.snapshot.get('origin'),
            'speaker':obj.source.get('speaker','旁白'),'text':obj.text,'source':obj.source.get('book'),
            'generation':{key:render.snapshot.get(key) for key in ('contract','request_fingerprint','local_request','reference_version','registered_model_version','loaded_model_verified','server_revision_verified','quality_verified')},
            'recipe':obj.recipe,'synthesis_identity':{key:render.snapshot.get(key) for key in ('profile','model','provider','synthesis')}})
    if sum(len(row['text']) for row in entries)>200000:raise HTTPException(422,'单次导出文本超过20万字符，请分批选择')
    data={'project_id':project.id,'project_uid':project.uid,'project_version':vs.version_id(session,project),
        'world_id':project.world_id,'items':entries,'alignment':'sequential_segments','contains_mock':any(e['origin']=='mock' for e in entries)}
    if pause_ms:data['pause_ms']=pause_ms  # Zero preserves legacy immutable export fingerprints.
    return {'fingerprint':digest(data),'snapshot':data}


def describe(row,detail=True):
    effective=row.status
    if row.status in ('queued','running','interrupted') and row.job_id:
        job=jobs.get(row.job_id)
        if job and job.status in ('cancelled','error','interrupted'):
            from sqlalchemy.orm import object_session
            session=object_session(row)
            if session:session.refresh(row)
            effective=row.status
            if row.status in ('queued','running','interrupted'):effective=job.status
    result={'id':row.id,'uid':row.uid,'project_id':row.project_id,'fingerprint':row.fingerprint,
        'status':effective,'recorded_status':row.status,'job_id':row.job_id,'error_code':row.error_code,'asset_id':row.asset_id,
        'created_at':row.created_at}
    if detail:result['snapshot']=row.snapshot
    return result


def recover(engine):
    with engine.begin() as conn:
        conn.execute(update(m.VoiceExport).where(m.VoiceExport.status.in_(('queued','running'))).values(status='interrupted',error_code='process_interrupted'))


def terminal(uid,status,code):
    with new_session() as session:
        row=session.scalar(select(m.VoiceExport).where(m.VoiceExport.uid==uid))
        if row and row.status in ('queued','running'):
            row.status=status;row.error_code=code;session.commit()


def checked_plan(session,row):
    project=get_or_404(session,m.VoiceProject,row.project_id)
    if project.uid!=row.snapshot['project_uid']:raise HTTPException(409,'工程身份变化')
    current=plan(session,project,[e['segment_id'] for e in row.snapshot['items']],row.snapshot.get('pause_ms',0))
    if current['fingerprint']!=row.fingerprint:raise HTTPException(409,'工程或已采纳片段发生变化，原导出保留，请重新预览')
    return project


def copy_audio(session, entry, dest, job):
    # External files are read only after explicit export, through existing guards.
    from .routers.assets import _file_of
    ref=vs.sample(session,entry['audio_ref'])
    asset=get_or_404(session,m.Asset,ref['id'])
    source=_file_of(asset)
    digestor=hashlib.sha256();size=0
    with source.open('rb') as src, dest.open('xb') as out:
        while block:=src.read(65536):
            job.check();size+=len(block)
            if size>MAX_INPUT:raise HTTPException(413,'单个音频超过64MiB，请先拆分')
            digestor.update(block);out.write(block)
    if digestor.hexdigest()!=ref['sha256']:raise HTTPException(409,'音频实际内容与已采纳Hash不一致')


def inspect_pcm(path,job):
    """Explicit background scan, bounded blocks; no resampling or source writes."""
    import array,math,sys
    try:
        with wave.open(str(path),'rb') as audio:
            channels,width,rate,frames=audio.getnchannels(),audio.getsampwidth(),audio.getframerate(),audio.getnframes()
            if audio.getcomptype()!='NONE' or channels not in (1,2) or width not in (1,2,3,4) or not 8000<=rate<=192000 or frames*1000//rate<1:
                raise HTTPException(422,'仅支持完整PCM WAV')
            count=0;peak=0;squares=0;near_full=0;near_zero=0;remaining=frames
            while remaining:
                job.check();n=min(remaining,8192);block=audio.readframes(n)
                if len(block)!=n*channels*width:raise HTTPException(422,'WAV数据截断')
                remaining-=n
                if width==2:
                    values=array.array('h');values.frombytes(block)
                    if sys.byteorder!='little':values.byteswap()
                    count+=len(values)
                    for value in values:
                        magnitude=abs(value)
                        if magnitude>peak:peak=magnitude
                        squares+=value*value;near_full+=magnitude>=32760;near_zero+=magnitude<=32
            db=lambda value:round(20*math.log10(value/32768),2) if value else None
            return {'channels':channels,'sample_width':width,'sample_rate':rate,'frames':frames,'pcm_bytes':frames*channels*width,
                'duration_seconds':frames/rate,'peak_dbfs':db(peak) if width==2 else None,
                'rms_dbfs':db(math.sqrt(squares/count)) if count else None,'level_measured':width==2,
                'silent':peak==0 if width==2 else None,'levels_method':'all_samples_pcm16' if width==2 else 'unsupported_bit_depth',
                'near_full_scale_samples_ratio':near_full/count if count else None,
                'near_zero_samples_ratio':near_zero/count if count else None}
    except (wave.Error,EOFError):raise HTTPException(422,'音频不是支持的PCM WAV') from None


def preflight(snapshot,fingerprint):
    # Job data contains only the bounded immutable selection, never an open DB.
    from types import SimpleNamespace
    expected=SimpleNamespace(project_id=snapshot['project_id'],snapshot=snapshot,fingerprint=fingerprint)
    def probe(job):
        with new_session() as session:checked_plan(session,expected)
        staging=get_settings().data_dir/'.staging';staging.mkdir(parents=True,exist_ok=True)
        rows=[];pcm=0;formats=set();levels=[];duration=0;limited=False
        with tempfile.TemporaryDirectory(prefix='voice-preflight-',dir=staging) as temp:
            for index,entry in enumerate(snapshot['items']):
                job.check();item={'segment_id':entry['segment_id'],'segment_uid':entry['segment_uid']}
                if limited:rows.append({**item,'issue':'not_checked_total_limit'});continue
                path=Path(temp)/f'{index}.wav'
                try:
                    with new_session() as session:copy_audio(session,entry,path,job)
                    info=inspect_pcm(path,job);pcm+=info['pcm_bytes'];duration+=info['duration_seconds']
                    if index:pcm+=(snapshot.get('pause_ms',0)*info['sample_rate']+500)//1000*info['channels']*info['sample_width']
                    formats.add((info['channels'],info['sample_width'],info['sample_rate']))
                    if info['rms_dbfs'] is not None:levels.append(info['rms_dbfs'])
                    rows.append({**item,**info,'issue':None})
                    if pcm>MAX_PCM:limited=True
                except HTTPException as exc:rows.append({**item,'issue':'audio_validation_'+str(exc.status_code)})
                except OSError:rows.append({**item,'issue':'audio_unreadable'})
                finally:
                    if path.exists():path.unlink()
                job.step('只读校验选定音轨格式、Hash与PCM16音量；未转码')
        with new_session() as session:checked_plan(session,expected)
        compatible=not limited and len(formats)==1 and all(r['issue'] is None for r in rows)
        complete=all(r['issue'] is None for r in rows)
        job.result={'fingerprint':fingerprint,'items':rows,'compatible':compatible,'formats_match':len(formats)==1,
            'pcm_bytes_with_pauses':pcm,'total_limit_exceeded':limited,'pause_ms':snapshot.get('pause_ms',0),
            'duration_seconds_with_pauses':duration+max(0,len(rows)-1)*snapshot.get('pause_ms',0)/1000 if complete else None,
            'level_difference_warning':len(levels)>1 and max(levels)-min(levels)>6,
            'not_loudness_normalization':True,'will_modify_sources':False}
    return jobs.start('voice-export-preflight','导出音轨兼容预检',len(snapshot['items']),probe)


def stamp(frames, rate, sep):
    millis=(frames*1000+rate//2)//rate
    hours,millis=divmod(millis,3600000);minutes,millis=divmod(millis,60000);seconds,millis=divmod(millis,1000)
    return f'{hours:02}:{minutes:02}:{seconds:02}{sep}{millis:03}'


def subtitle_text(speaker,text):
    # Escape player markup and prevent blank lines from injecting extra cues.
    clean=lambda value:'\n'.join(line.strip() for line in value.replace('\x00','').splitlines() if line.strip())
    return html.escape('['+clean(speaker).replace('\n',' ')+'] '+clean(text))


def package(session,snapshot,folder,job):
    output=folder/'audio.wav';srt=[];vtt=['WEBVTT\n'];cues=[];total_frames=0;pcm_bytes=0;fmt=None
    with ExitStack() as stack:
        target=None
        for index,entry in enumerate(snapshot['items'],1):
            job.check();source=folder/f'{index}.wav';copy_audio(session,entry,source,job)
            try:
                with wave.open(str(source),'rb') as audio:
                    shape=(audio.getnchannels(),audio.getsampwidth(),audio.getframerate())
                    if audio.getcomptype()!='NONE' or shape[0] not in (1,2) or shape[1] not in (1,2,3,4) or not 8000<=shape[2]<=192000:
                        raise HTTPException(422,'仅支持同格式PCM WAV，不自动安装转码器')
                    if fmt is None:
                        fmt=shape;target=stack.enter_context(wave.open(str(output),'wb'))
                        target.setnchannels(fmt[0]);target.setsampwidth(fmt[1]);target.setframerate(fmt[2])
                    if shape!=fmt:raise HTTPException(422,'所选WAV采样率、声道及位深必须一致；未重采样或修改原件')
                    frames=audio.getnframes();width=shape[0]*shape[1]
                    if frames<=0 or (frames*1000)//shape[2]<1:raise HTTPException(422,'音轨为空或短于1毫秒')
                    gap=(snapshot.get('pause_ms',0)*shape[2]+500)//1000 if index>1 else 0
                    if pcm_bytes+(frames+gap)*width>MAX_PCM:raise HTTPException(413,'单次导出PCM含停顿超过128MiB，请分批选择')
                    remaining_gap=gap
                    while remaining_gap:
                        job.check();count=min(remaining_gap,max(1,65536//width))
                        block=(b'\x80' if shape[1]==1 else b'\0')*(count*width)
                        target.writeframesraw(block);remaining_gap-=count;pcm_bytes+=len(block)
                    total_frames+=gap
                    remaining=frames
                    while remaining:
                        job.check();count=min(remaining,max(1,65536//width));block=audio.readframes(count)
                        if len(block)!=count*width:raise HTTPException(422,'WAV数据截断，未生成可下载成品')
                        target.writeframesraw(block);remaining-=count;pcm_bytes+=len(block)
            except (wave.Error,EOFError):
                raise HTTPException(422,'音频不是支持的完整PCM WAV；MP3等格式暂不转码') from None
            start=total_frames;total_frames+=frames
            content=subtitle_text(entry['speaker'],entry['text'])
            srt.append(f'{index}\n{stamp(start,fmt[2],",")} --> {stamp(total_frames,fmt[2],",")}\n{content}\n')
            vtt.append(f'{index}\n{stamp(start,fmt[2],".")} --> {stamp(total_frames,fmt[2],".")}\n{content}\n')
            cues.append({**entry,'start_frame':start,'end_frame':total_frames})
            source.unlink();job.step('已校验并拼接选定片段；字幕仅按片段顺序计时')
    manifest={**snapshot,'items':cues,'format':{'channels':fmt[0],'sample_width':fmt[1],'sample_rate':fmt[2],'frames':total_frames},
        'alignment':'sequential_segments','not_forced_alignment':True,'not_inference':True}
    result=folder/'export.zip'
    with zipfile.ZipFile(result,'w',compression=zipfile.ZIP_STORED) as bundle:
        with output.open('rb') as audio, bundle.open('audio.wav','w') as member:
            while block:=audio.read(65536):
                job.check();member.write(block)
        bundle.writestr('subtitles.srt','\n'.join(srt))
        bundle.writestr('subtitles.vtt','\n'.join(vtt))
        bundle.writestr('manifest.json',json.dumps(manifest,ensure_ascii=False,sort_keys=True,indent=2))
    job.check()
    return result


def run(job,uid):
    try:
        with new_session() as session:
            session.connection().exec_driver_sql('BEGIN IMMEDIATE')
            row=session.scalar(select(m.VoiceExport).where(m.VoiceExport.uid==uid))
            if not row or row.status!='queued':return
            checked_plan(session,row);snapshot=row.snapshot;row.status='running';session.commit()
        folder=get_settings().data_dir/'.staging';folder.mkdir(parents=True,exist_ok=True)
        with tempfile.TemporaryDirectory(dir=folder,prefix='voice-export-') as temp:
            with new_session() as session:
                result=package(session,snapshot,Path(temp),job)
            with new_session() as session:
                session.connection().exec_driver_sql('BEGIN IMMEDIATE')
                row=session.scalar(select(m.VoiceExport).where(m.VoiceExport.uid==uid))
                if not row or row.status!='running':raise jobs.Cancelled()
                project=checked_plan(session,row);job.check()
                with result.open('rb') as data:
                    asset,_=ingest_stream(session,data,'voice-export.zip',mime='application/zip',kind='archive',
                        title='配音片段导出（含Mock测试音）' if snapshot['contains_mock'] else '配音片段导出',
                        world_id=project.world_id,extra_meta={'voice_export':{'uid':uid,'fingerprint':row.fingerprint,'contains_mock':snapshot['contains_mock']}})
                if asset.world_id!=project.world_id:raise HTTPException(409,'导出文件已有其他世界观归属')
                v.enable(session,asset,'保留音频与字幕导出版本')
                row.asset_id=asset.id;row.status='done';job.check();session.commit()
                job.result={'export_uid':uid,'asset_id':asset.id,'contains_mock':snapshot['contains_mock']}
    except jobs.Cancelled:
        terminal(uid,'cancelled','cancelled');raise
    except HTTPException as exc:
        terminal(uid,'error','export_validation_failed_'+str(exc.status_code));raise
    except Exception:
        terminal(uid,'error','export_failed');raise


def enqueue(session,project,body):
    uid=uuid.uuid5(uuid.NAMESPACE_URL,project.uid+'/export/'+body.idempotency_key).hex
    existing=session.scalar(select(m.VoiceExport).where(m.VoiceExport.uid==uid))
    if existing:
        if existing.fingerprint!=body.fingerprint or set(body.segment_ids)!={e['segment_id'] for e in existing.snapshot['items']} or existing.snapshot.get('pause_ms',0)!=body.pause_ms:
            raise HTTPException(409,'幂等键对应其他导出请求')
        return existing
    vs.guard(session,project,body.project_uid,body.expected_project_version)
    preview=plan(session,project,body.segment_ids,body.pause_ms,body.segment_refs)
    if preview['fingerprint']!=body.fingerprint:raise HTTPException(409,'导出预览已变化，请重新确认')
    row=m.VoiceExport(uid=uid,project_id=project.id,fingerprint=body.fingerprint,snapshot=preview['snapshot'],status='queued')
    session.add(row);session.commit()
    try:job=jobs.start('voice-export','已采纳音频与顺序字幕导出',len(body.segment_ids),lambda j:run(j,uid))
    except HTTPException:
        terminal(uid,'error','queue_unavailable');raise
    session.execute(update(m.VoiceExport).where(m.VoiceExport.uid==uid).values(job_id=job.id));session.commit();session.expire_all()
    return session.scalar(select(m.VoiceExport).where(m.VoiceExport.uid==uid))
