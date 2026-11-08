"""Persistent scan configuration over ProjectPreview and the shared bounded queue."""
import fnmatch
import hashlib
import json
import os
import stat
import struct
import threading
import time
import uuid
import zipfile
from pathlib import Path, PurePosixPath

from fastapi import HTTPException
from sqlalchemy import update

from . import jobs, models as m, projectpreview as preview
from .config import get_settings
from .db import new_session
from .filetypes import KNOWN_EXT
from .pathsafety import plain_path

ACTIVE = ('queued','running','pausing','cancelling')
EXTRA = {'.exe','.safetensors','.ckpt','.pth','.pt','.gguf','.svg','.clip','.psb','.lrc','.srt','.vtt'}
IGNORED = {'.git','.svn','.hg','node_modules','__pycache__','.venv','$recycle.bin','system volume information'}


class BudgetReached(Exception):
    pass


def folder(value):
    path = plain_path(value)
    data = get_settings().data_dir.resolve()
    if not path.is_dir():raise ValueError('目录不存在或不可读取')
    if path == Path(path.anchor) or str(path.drive).startswith('\\\\'):
        raise ValueError('请选择本地具体文件夹，不扫描整盘或网络共享根目录')
    if path.is_relative_to(data):raise ValueError('不能扫描Front自己的数据目录')
    return path


def signature(config):
    return hashlib.sha256(json.dumps(config,sort_keys=True).encode()).hexdigest()


class ScanJob:
    def __init__(self, job, seconds, report_id):
        object.__setattr__(self,'job',job)
        object.__setattr__(self,'deadline',time.monotonic()+seconds)
        object.__setattr__(self,'id',report_id)
    def __getattr__(self,name):return getattr(self.job,name)
    def __setattr__(self,name,value):setattr(self.job,name,value)
    def check(self):
        self.job.check()
        if time.monotonic() >= self.deadline:raise BudgetReached('time_budget')
    def step(self,message=None):
        self.job.step(message);self.check()


def walk(root, config, job):
    """Bound entries as well as accepted files; do not materialize a huge directory."""
    files, unsupported, skipped, visited, size = [], 0, 0, 0, 0
    stack=[(root,0)]
    reason=None
    try:
        while stack:
            job.check()
            directory,depth=stack.pop()
            plain_path(directory)
            with os.scandir(directory) as entries:
                for entry in entries:
                    job.check();visited+=1
                    if visited>config['max_entries']:raise BudgetReached('entry_budget')
                    path=Path(entry.path);rel=path.relative_to(root).as_posix()
                    if entry.name.lower() in IGNORED or any(fnmatch.fnmatchcase(rel.casefold(),p.casefold()) or fnmatch.fnmatchcase(entry.name.casefold(),p.casefold()) for p in config['ignores']):
                        skipped+=1;continue
                    try:
                        info=entry.stat(follow_symlinks=False)
                        if stat.S_ISLNK(info.st_mode) or getattr(info,'st_file_attributes',0)&0x400:
                            skipped+=1;continue
                        if path.is_relative_to(get_settings().data_dir.resolve()):skipped+=1;continue
                        if stat.S_ISDIR(info.st_mode):
                            if depth<config['max_depth']:stack.append((path,depth+1))
                            else:skipped+=1
                        elif stat.S_ISREG(info.st_mode):
                            if path.suffix.lower() not in KNOWN_EXT|EXTRA:unsupported+=1;continue
                            if len(files)>=config['max_files']:raise BudgetReached('file_budget')
                            if size+info.st_size>config['max_bytes']:raise BudgetReached('size_budget')
                            size+=info.st_size;files.append(path)
                    except OSError:skipped+=1
    except BudgetReached as exc:reason=str(exc)
    files.sort(key=lambda p:p.relative_to(root).as_posix().casefold())
    return files,unsupported,{'visited':visited,'skipped':skipped,'listed_bytes':size,'limit':reason}


def archive_summary(path):
    """Central-directory only, with a budget before constructing ZipFile; no extraction."""
    if path.stat().st_size>32*1024*1024:return {'status':'deferred','reason':'archive_file_budget'}
    with path.open('rb') as handle:
        handle.seek(max(0,path.stat().st_size-65557));tail=handle.read(65557)
    pos=tail.rfind(b'PK\x05\x06')
    if pos<0 or pos+22>len(tail):raise ValueError('archive_invalid_directory')
    _,disk,cd_disk,n_disk,count,cd_size,cd_offset,_=struct.unpack_from('<4s4H2LH',tail,pos)
    if disk or cd_disk or n_disk!=count or count>1000 or cd_size>2*1024*1024 or cd_offset+cd_size>path.stat().st_size:
        raise ValueError('archive_directory_budget')
    with zipfile.ZipFile(path) as archive:
        infos=archive.infolist()
        if len(infos)>1000:raise ValueError('archive_entry_budget')
        total=0
        for info in infos:
            name=PurePosixPath(info.filename.replace('\\','/'))
            if name.is_absolute() or '..' in name.parts or any(':' in p for p in name.parts) or stat.S_ISLNK(info.external_attr>>16):raise ValueError('archive_unsafe_path')
            total+=info.file_size
            if info.flag_bits&1 or info.file_size>64*1024*1024 or total>256*1024*1024 or info.file_size>max(1,info.compress_size)*200:raise ValueError('archive_expansion_budget')
        return {'status':'listed','entries':len(infos),'declared_bytes':total,'names':[i.filename for i in infos[:30]],'extracted_bytes':0,'crc_verified':False}


def suggested_groups(files,root):
    """Prefer an explicitly named book/model boundary; never create or merge a Work."""
    anchors={p.parent for p in files if (p.suffix.lower() in {'.png','.jpg','.jpeg','.webp'} and p.stem.casefold() in {'cover','folder','封面','表紙'}) or p.stem.casefold() in {'正文','全本','正篇','text','novel'} or p.name.casefold().endswith('.model3.json')}
    result={}
    for path in files:
        parent=path.parent
        while parent!=root and parent not in anchors:parent=parent.parent
        relative=path.relative_to(root).as_posix()
        result[relative]=parent.relative_to(root).as_posix() if parent!=root else relative.split('/')[0] if '/' in relative else ''
    return result


def decorate(item,path,kind,group=None):
    parts=PurePosixPath(item['relative']).parts
    group=group if group is not None else parts[0] if len(parts)>1 else ''
    stem=path.stem.casefold()
    role='cover' if path.suffix.lower() in {'.png','.jpg','.jpeg','.webp'} and stem in {'cover','folder','封面','表紙'} else 'body' if item['kind']=='novel' else 'related'
    if item['kind']=='novel':
        if any(word in stem for word in ('附录','附錄','后记','後記','appendix','readme')):role='appendix'
        if item['candidate']=='resource':
            item.update(candidate='novel',reason='文本格式候选；正文、附录和作品归属仍需人工确认')
    item.update(group=group,suggested_title=PurePosixPath(group).name if group else path.stem,role=role,initial_tags=[kind,role],suggestion_only=True)
    if path.suffix.lower()=='.zip' and not item.get('error'):
        try:
            item['archive']=archive_summary(path)
            if item['archive']['status']!='listed':item['error']='archive_unverified'
        except ValueError as exc:item['error']=str(exc)
        except (OSError,zipfile.BadZipFile,struct.error):item['error']='archive_unreadable_or_invalid'


def summary(report, previous, complete, config):
    current={i['relative']:i for i in report['files']}
    comparable=bool(previous) and previous.get('discovery',{}).get('config_fingerprint')==signature(config)
    before={i['relative']:i for i in (previous or {}).get('files',[])} if comparable else {}
    return {'files':len(current),'new':sum(k not in before for k in current),
        'changed':sum(k in before and v.get('stamp')!=before[k].get('stamp') for k,v in current.items()),
        'missing':sum(k not in current for k in before) if complete and comparable else None,
        'duplicates':report['duplicate_files'],'deferred_hashes':sum(bool(i.get('hash_deferred')) for i in current.values()),
        'errors':report['errors']+bool(report.get('discovery',{}).get('enumeration',{}).get('error_code')),
        'limit':report.get('discovery',{}).get('enumeration',{}).get('limit'),
        'error_code':report.get('discovery',{}).get('enumeration',{}).get('error_code'),
        'reused_hashes':report['reused_hashes'],'hash_bytes_read':report.get('hash_bytes_read',0),'comparison_available':comparable,'finished_at':jobs.now()}


def process(rid,uid,report_id,config,job):
    last={};previous=None;state='error';enumeration={};cache_state={}
    with new_session() as session:
        row=session.get(m.DiscoveryRoot,rid)
        if not row or row.uid!=uid or row.report_id!=report_id:return
        path=row.path;baseline=row.baseline_id;row.state='running';session.commit()
    def checkpoint(report,cache,cache_path):
        last.update(report=report)
        cache_state.update(cache=cache,path=cache_path)
        if len(report['files'])%25==0:
            report['discovery']={'state':'running','source_uid':uid,'config_fingerprint':signature(config)}
            preview.write_json(get_settings().data_dir/'project-previews'/f'{report_id}.json',report)
            preview.write_json(cache_path,cache)
    proxy=ScanJob(job,config['max_seconds'],report_id)
    try:
        root=folder(path)
        if baseline:
            try:previous=preview.load(baseline)
            except ValueError:pass
        files,unsupported,enumeration=walk(root,config,proxy)
        groups=suggested_groups(files,root)
        with new_session() as session:
            preview.build(root,files,unsupported,session,proxy,None,limits=config,checkpoint=checkpoint,decorate=lambda item,p:decorate(item,p,config['kind'],groups[item['relative']]))
        last['report']=preview.load(report_id)
        state='limited' if enumeration.get('limit') else 'done'
    except BudgetReached as exc:
        enumeration['limit']=str(exc);state='limited'
    except jobs.Cancelled:
        with new_session() as session:
            row=session.get(m.DiscoveryRoot,rid)
            state='paused' if row and row.state=='pausing' else 'cancelled'
    except (OSError,ValueError):
        state='error';enumeration['error_code']='source_unavailable';raise
    finally:
        report=last.get('report') or {'root':path,'world_id':None,'created_at':jobs.now(),'files':[],'unsupported':0,'errors':0,'duplicate_files':0,'reused_hashes':0,'bytes':0}
        report['total']=len(report['files'])
        report['discovery']={'state':state,'source_uid':uid,'config_fingerprint':signature(config),'enumeration':enumeration,'resume':'re-enumerate and reuse completed fingerprints; no automatic import'}
        stats=summary(report,previous,state=='done',config)
        preview.write_json(get_settings().data_dir/'project-previews'/f'{report_id}.json',report)
        if cache_state:preview.write_json(cache_state['path'],cache_state['cache'])
        job.result={'report_id':report_id,'state':state,**stats}
        with new_session() as session:
            values={'state':state,'stats':stats}
            if state=='done':values['baseline_id']=report_id
            session.execute(update(m.DiscoveryRoot).where(m.DiscoveryRoot.id==rid,m.DiscoveryRoot.uid==uid,m.DiscoveryRoot.report_id==report_id).values(**values));session.commit()


def reconcile(session,row):
    if row.state not in ACTIVE:return
    if not row.job_id:return  # enqueue transaction is not yet bound; restart recovery handles crashes here.
    job=jobs.get(row.job_id) if row.job_id else None
    if job and job.status in ('queued','running'):return
    state='paused' if row.state=='pausing' else 'cancelled' if row.state=='cancelling' else 'interrupted'
    session.execute(update(m.DiscoveryRoot).where(m.DiscoveryRoot.id==row.id,m.DiscoveryRoot.uid==row.uid,m.DiscoveryRoot.state.in_(ACTIVE)).values(state=state))
    session.commit();session.refresh(row)


def recover(engine):
    with engine.begin() as conn:
        conn.execute(update(m.DiscoveryRoot).where(m.DiscoveryRoot.state.in_(ACTIVE)).values(state='interrupted'))


def enqueue(session,row):
    gate=threading.Event();rid,uid,report_id,config=row.id,row.uid,row.report_id,dict(row.config)
    def work(job):
        gate.wait(15);job.check();process(rid,uid,report_id,config,job)
    job=None
    try:
        job=jobs.start('discovery-scan','只读目录发现',0,work)
        row.job_id=job.id;session.commit()
    except HTTPException:
        row.state='interrupted';session.commit();raise
    except Exception:
        session.rollback()
        if job:job.cancel_requested=True
        with new_session() as worker:
            worker.execute(update(m.DiscoveryRoot).where(m.DiscoveryRoot.id==rid,m.DiscoveryRoot.uid==uid,m.DiscoveryRoot.report_id==report_id,m.DiscoveryRoot.state.in_(ACTIVE)).values(state='interrupted'));worker.commit()
        raise HTTPException(503,'扫描任务未能提交，来源配置已保留，请稍后重试') from None
    finally:gate.set()
    return job.to_dict()
