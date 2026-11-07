"""Confirmed-chapter narration drafts; source files remain read-only."""
import hashlib
import json
import re
import uuid
from itertools import islice
from pathlib import Path
from fastapi import HTTPException
from sqlalchemy import select,update,func
from sqlalchemy.orm import defer
from . import models as m,chapterplans,chapters,jobs,versions as v,voiceprojects as vp,voicestudio as vs
from .crud import get_or_404
from .db import new_session


def scope_identity(session,model,key):
    obj=session.get(model,key) if key else None
    return vs.identity(obj) if obj else None


def describe_source(session,asset,revision,digest):
    frame={'asset_id':asset.id,'asset_identity':vs.identity(asset),'revision_id':revision.id,'revision_identity':vs.identity(revision),
        'text_hash':digest,'world_id':asset.world_id,'work_id':asset.work_id,
        'world_identity':scope_identity(session,m.World,asset.world_id),'work_identity':scope_identity(session,m.Work,asset.work_id)}
    frame['fingerprint']=hashlib.sha256(json.dumps(frame,sort_keys=True).encode()).hexdigest()
    return frame


def confirmed(session,asset_id):
    asset=get_or_404(session,m.Asset,asset_id)
    ext=Path(asset.original_name or '').suffix.lower()
    if ext and ext not in ('.txt','.md','.markdown','.epub'):
        raise HTTPException(422,'当前仅使用已保存全文、TXT、Markdown或EPUB，不把其他文档预览视作完整小说')
    revision=chapterplans.current(session,asset_id)
    if not revision:raise HTTPException(409,'请先在章节整理中确认并保存目录')
    text=chapterplans.source_text(asset);digest=chapters.fingerprint(text)
    if revision.text_hash!=digest:raise HTTPException(409,'正文已变化，请重新确认章节后创建新配音工程')
    return asset,revision,text,describe_source(session,asset,revision,digest)


def frozen(session,project,read_text=False):
    source=session.get(m.VoiceBookSource,project.id)
    if not source:raise HTTPException(404,'当前不是小说配音工程')
    frame=source.snapshot
    asset=session.get(m.Asset,project.source_asset_id,options=[defer(m.Asset.content)]) if project.source_asset_id else None
    revision=session.get(m.ChapterRevision,frame['revision_id'])
    if not asset or not revision or vs.identity(asset)!=frame['asset_identity'] or vs.identity(revision)!=frame['revision_identity'] or revision.asset_id!=asset.id:
        raise HTTPException(409,'原小说或确认目录已删除/身份变化；已有台词保留')
    if describe_source(session,asset,revision,frame['text_hash'])!=frame:
        raise HTTPException(409,'小说世界观或作品归属变化；请创建新工程，不自动混用')
    text=chapterplans.source_text(asset) if read_text else None
    if read_text and chapters.fingerprint(text)!=frame['text_hash']:
        raise HTTPException(409,'小说正文已变化；旧台词保留，请为新版创建独立工程')
    return frame,revision,text


def check_work(session,project,profile):
    source=session.get(m.VoiceBookSource,project.id)
    work=profile.binding.get('work')
    if source and source.snapshot.get('work_id') is not None and work and work[0]!=source.snapshot['work_id']:
        raise HTTPException(422,'声线与小说属于不同作品，请使用本作品或独立声线')


def pieces(text,start,end):
    # At most 100k characters and 1000 fragments per explicitly queued part.
    stop=min(end,start+100000)
    for match in re.finditer(r'\S[^\n]*',text[start:stop]):
        begin=start+match.start();finish=start+match.end()
        for pos in range(begin,finish,2000):
            yield pos,min(pos+2000,finish),text[pos:min(pos+2000,finish)]


def terminal(uid,status,code=''):
    with new_session() as session:
        row=session.scalar(select(m.VoiceChapterImport).where(m.VoiceChapterImport.uid==uid))
        if row and row.status in ('queued','running'):
            row.status=status;row.error_code=code;session.commit()


def run(job,uid):
    try:
        with new_session() as session:
            row=session.scalar(select(m.VoiceChapterImport).where(m.VoiceChapterImport.uid==uid))
            if not row or row.status!='queued':return
            project=get_or_404(session,m.VoiceProject,row.project_id)
            frame,revision,text=frozen(session,project,True)
            start,end=row.cursor,row.end;project_id=project.id;project_uid=project.uid;index=row.chapter_index
            if not 0<=index<len(revision.chapters):raise HTTPException(409,'导入章节状态异常')
            chapter=revision.chapters[index]
            if end!=chapter['end'] or not chapter.get('body_start',chapter['start'])<=start<=end<=len(text):
                raise HTTPException(409,'导入游标异常，原数据保留')
            row.status='running';session.commit()
        fragments=list(islice(pieces(text,start,end),1000));stop=min(end,start+100000)
        job.total=len(fragments)+1
        for begin,finish,raw in fragments:
            job.check()
            with new_session() as session:
                session.connection().exec_driver_sql('BEGIN IMMEDIATE')
                row=session.scalar(select(m.VoiceChapterImport).where(m.VoiceChapterImport.uid==uid))
                project=get_or_404(session,m.VoiceProject,project_id)
                if not row or row.status!='running' or project.uid!=project_uid:raise jobs.Cancelled()
                frozen(session,project)
                segment_uid=uuid.uuid5(uuid.NAMESPACE_URL,f'{project_uid}/{frame["fingerprint"]}/{index}/{begin}/{finish}').hex
                existing=session.scalar(select(m.VoiceSegment).where(m.VoiceSegment.uid==segment_uid))
                if not existing:
                    position=session.scalar(select(func.max(m.VoiceSegment.position)).where(m.VoiceSegment.project_id==project_id))
                    quoted=any(char in raw for char in '“”「」『』')
                    label=re.match(r'^([^\s：:]{1,30})[：:]\s*',raw)
                    name=label.group(1) if label and not label.group(1).isnumeric() else None
                    suggestion={'method':'punctuation_rule','kind':'dialogue_candidate' if quoted else 'narration_candidate',
                        'evidence':raw,'start':begin,'end':finish,'confirmed':False,'speaker_name_candidate':name}
                    segment=m.VoiceSegment(uid=segment_uid,project_id=project_id,position=position+1 if position is not None else 0,
                        text=raw.strip(),recipe={'profile':{},'language':'','speed':1},source={'archived':False,'speaker':name or ('待确认' if quoted else '旁白'),
                        'speaker_confirmed':False,'suggestion':suggestion,'book':{**frame,'chapter_index':index,'start':begin,'end':finish}})
                    session.add(segment);session.flush();v.enable(session,segment,'小说朗读草稿；原文只读')
                    vp.touch(session,project,'导入小说片段，待人工确认说话人')
                row.cursor=finish;job.check();session.commit()
            job.step('已保存朗读草稿与原文区间；不执行AI推理')
        with new_session() as session:
            session.connection().exec_driver_sql('BEGIN IMMEDIATE')
            row=session.scalar(select(m.VoiceChapterImport).where(m.VoiceChapterImport.uid==uid))
            if not row or row.status!='running':raise jobs.Cancelled()
            if len(fragments)<1000:row.cursor=stop
            row.status='done' if row.cursor>=row.end else 'partial';session.commit()
            job.result={'import_uid':uid,'project_id':project_id,'cursor':row.cursor,'end':row.end,'status':row.status,'speaker_review_required':True}
        job.step('本次导入完成；剩余正文可显式续导')
    except jobs.Cancelled:
        terminal(uid,'cancelled');raise
    except Exception:
        terminal(uid,'error','source_or_import_failed');raise


def recover(engine):
    with engine.begin() as conn:
        conn.execute(update(m.VoiceChapterImport).where(m.VoiceChapterImport.status.in_(('queued','running'))).values(status='interrupted'))
