"""Resumable per-file imports and world-local references. Originals are never owned."""
import hashlib
import os
import threading
from datetime import date
from pathlib import Path

from fastapi import HTTPException
from sqlalchemy import select,update

from . import jobs,models as m,projectpreview
from .config import get_settings
from .db import new_session
from .ingest import ingest_stream,index_file,make_thumb

ENTITIES = {'asset':m.Asset,'character':m.Character,'entry':m.WorldEntry,'note':m.Note,'work':m.Work,'relation':m.Relation}
_IMPORT_LOCK=threading.Lock()


def source_key(path):
    return hashlib.sha256(os.path.normcase(str(path.resolve())).encode()).hexdigest()


def recover(engine):
    with engine.begin() as conn:
        conn.execute(update(m.ProjectImport).where(m.ProjectImport.status.in_(['queued','running'])).values(status='interrupted'))


def process(import_id,job):
    while not _IMPORT_LOCK.acquire(timeout=.25):
        job.check()
    try:
        job.check();_process(import_id,job)
    finally:
        _IMPORT_LOCK.release()


def _process(import_id,job):
    with new_session() as session:
        run=session.get(m.ProjectImport,import_id)
        run.status='running';session.commit()
        ids=list(session.scalars(select(m.ProjectImportItem.id).where(m.ProjectImportItem.import_id==import_id).order_by(m.ProjectImportItem.id)))
        job.total=len(ids);job.result={'import_id':import_id,'world_id':run.world_id}
        try:
            for item_id in ids:
                job.check()
                item=session.get(m.ProjectImportItem,item_id)
                if item.status in ('done','duplicate'):
                    job.step('已提交项目，跳过');continue
                data=item.selection
                try:
                    path,root=Path(data['path']).resolve(),Path(data['root']).resolve()
                    if not path.is_relative_to(root) or not path.is_file() or projectpreview.stamp(path)!=data['stamp']:
                        raise HTTPException(409,'原件已移动或修改，请重新预览；本次已完成项目保留')
                    valid_tags=set(session.scalars(select(m.Tag.id).where(m.Tag.id.in_(data.get('tag_ids',[])))))
                    valid_labels=set(session.scalars(select(m.WorldLabel.id).where(m.WorldLabel.world_id==run.world_id,m.WorldLabel.id.in_(data.get('label_ids',[])))))
                    if valid_tags!=set(data.get('tag_ids',[])) or valid_labels!=set(data.get('label_ids',[])):
                        raise HTTPException(409,'导入前标签发生变化，请重新审核标签')
                    existing=session.scalar(select(m.WorldResource).where(m.WorldResource.world_id==run.world_id,m.WorldResource.source_key==source_key(path)))
                    if existing:
                        old=session.get(m.Asset,existing.entity_id)
                        if old and old.sha256!=data['sha256']:
                            raise HTTPException(409,'此路径已有不同版本；请使用版本管理，不能覆盖原档案')
                    if run.mode=='managed':
                        with path.open('rb') as handle:
                            asset,created=ingest_stream(session,handle,path.name,source=str(path),work_date=date.fromtimestamp(path.stat().st_mtime),expected_sha=data['sha256'])
                    else:
                        asset,created=index_file(session,path,root,data['sha256'],job.check)
                    if projectpreview.stamp(path)!=data['stamp']:
                        raise HTTPException(409,'导入时原件变化，请重新预览')
                    resource=session.scalar(select(m.WorldResource).where(m.WorldResource.world_id==run.world_id,m.WorldResource.entity_kind=='asset',m.WorldResource.entity_id==asset.id))
                    if resource is None:
                        resource=m.WorldResource(world_id=run.world_id,entity_kind='asset',entity_id=asset.id,
                            title=data.get('title') or asset.title,category=data.get('category') or 'resource',
                            source_key=source_key(path),source_path=str(path),storage_mode=run.mode,
                            global_tag_ids=data.get('tag_ids',[]),label_ids=data.get('label_ids',[]))
                        session.add(resource);session.flush()
                        item.status='done'
                    else:
                        item.status='duplicate'
                        if run.mode=='managed':resource.storage_mode='managed'
                    item.resource_id=resource.id;item.message=''
                    session.commit()
                    if asset.width:
                        make_thumb(asset.id,get_settings().data_dir/asset.file_path if asset.file_path else path)
                except (OSError,HTTPException) as exc:
                    session.rollback()
                    item=session.get(m.ProjectImportItem,item_id)
                    item.status='error';item.message=str(exc.detail) if isinstance(exc,HTTPException) else type(exc).__name__
                    session.commit()
                job.step(Path(data['path']).name)
            states=list(session.scalars(select(m.ProjectImportItem.status).where(m.ProjectImportItem.import_id==import_id)))
            run.status='partial' if 'error' in states else 'done';session.commit()
            job.result.update(status=run.status,completed=sum(s in ('done','duplicate') for s in states),errors=states.count('error'))
        except jobs.Cancelled:
            session.rollback();run=session.get(m.ProjectImport,import_id);run.status='cancelled';session.commit();raise
        except Exception:
            session.rollback();run=session.get(m.ProjectImport,import_id);run.status='interrupted';session.commit();raise


def enqueue(session,run):
    gate=threading.Event()
    import_id=run.id
    def work(job):
        gate.wait(15)
        try:
            job.check();process(import_id,job)
        except jobs.Cancelled:
            with new_session() as worker:
                worker.execute(update(m.ProjectImport).where(m.ProjectImport.id==import_id,m.ProjectImport.status.in_(['queued','running'])).values(status='cancelled'))
                worker.commit()
            raise
    job=None
    try:
        job=jobs.start('project-import',f'项目导入 #{run.id[:8]}',0,work)
        run.job_id=job.id;session.commit()
    except Exception:
        session.rollback()
        if job:job.cancel_requested=True
        run.status='interrupted';session.commit();raise
    finally:
        gate.set()
    return {'import_id':run.id,'world_id':run.world_id,'job':job.to_dict()}
