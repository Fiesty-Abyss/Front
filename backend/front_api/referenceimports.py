"""Restart-safe orchestration around existing previews/ingest/collections, no file store."""
import uuid
from pathlib import Path
from fastapi import HTTPException
from sqlalchemy import select,func,update
from . import models as m,jobs,projectpreview
from .db import new_session
from .ingest import index_file,ingest_stream
from .ocstudio import identity


def scope(session,run):
    result={}
    for key,model in [('world_id',m.World),('work_id',m.Work),('collection_id',m.Collection)]:
        value=getattr(run,key);obj=session.get(model,value) if value else None
        result[key]=[value,identity(obj) if obj else None]
    return result


def link(session,collection_id,asset_id):
    if collection_id is None:return
    table=m.collection_assets
    if session.scalar(select(table.c.asset_id).where(table.c.collection_id==collection_id,table.c.asset_id==asset_id)) is None:
        pos=session.scalar(select(func.coalesce(func.max(table.c.position),-1)).where(table.c.collection_id==collection_id))+1
        session.execute(table.insert().values(collection_id=collection_id,asset_id=asset_id,position=pos))


def start(session,body):
    report=projectpreview.load(body.report_id)
    indices=list(dict.fromkeys(body.indices))
    if any(i<0 or i>=len(report['files']) or report['files'][i].get('error') or report['files'][i]['kind']=='bundle' for i in indices):raise HTTPException(422,'选择包含失效条目或关联模型包，请重新预览')
    run=m.LibraryImport(id=uuid.uuid4().hex,report_id=body.report_id,mode=body.mode,collection_id=body.collection_id,world_id=body.world_id,work_id=body.work_id,allow_cross_scope=body.allow_cross_scope)
    for key,model in [('world_id',m.World),('work_id',m.Work),('collection_id',m.Collection)]:
        value=getattr(run,key)
        if value is not None and session.get(model,value) is None:raise HTTPException(422,'导入归属不存在')
    run.scope=scope(session,run);session.add(run);session.flush()
    session.add_all(m.LibraryImportItem(import_id=run.id,file_index=i) for i in indices);session.commit()
    return dispatch(session,run)


def dispatch(session,run):
    rid=run.id
    def work(job):
        try:
            with new_session() as ses:
                current=ses.get(m.LibraryImport,rid);current.status='running';current.job_id=job.id;ses.commit()
                report=projectpreview.load(current.report_id)
                ids=list(ses.scalars(select(m.LibraryImportItem.id).where(m.LibraryImportItem.import_id==rid,m.LibraryImportItem.status!='done').order_by(m.LibraryImportItem.file_index)))
                job.total=len(ids);job.result={'import_id':rid,'imported':0}
                for iid in ids:
                    job.check();item=ses.get(m.LibraryImportItem,iid)
                    try:
                        if scope(ses,current)!=current.scope:raise HTTPException(409,'导入归属已删除或变化，停止自动归档')
                        info,path=projectpreview.file_of(report,item.file_index)
                        if current.mode=='indexed':
                            binding=ses.scalar(select(m.ExternalAssetFile).join(m.Asset).where(m.ExternalAssetFile.path==str(path),m.Asset.sha256==info['sha256']))
                            if binding and binding.stamp==info['stamp']:asset=ses.get(m.Asset,binding.asset_id);created=False
                            else:asset,created=index_file(ses,path,Path(report['root']),info['sha256'],job.check)
                        else:
                            with path.open('rb') as stream:asset,created=ingest_stream(ses,stream,path.name,expected_sha=info['sha256'])
                        if not created and not current.allow_cross_scope and any(getattr(asset,k) is not None and getattr(asset,k)!=getattr(current,k) for k in ('world_id','work_id')):raise HTTPException(422,'既有素材属于不同世界观/作品，需明确允许跨范围引用')
                        if created:asset.world_id=current.world_id;asset.work_id=current.work_id
                        link(ses,current.collection_id,asset.id);item.asset_id=asset.id;item.status='done';item.message='已登记新素材' if created else '已引用现有素材，未复制或覆盖'
                        ses.commit();job.result['imported']+=1
                    except jobs.Cancelled:raise
                    except Exception as exc:
                        ses.rollback();item=ses.get(m.LibraryImportItem,iid);item.status='error';item.message=str(exc.detail)[:400] if isinstance(exc,HTTPException) else str(exc)[:400] if isinstance(exc,ValueError) else type(exc).__name__;ses.commit()
                    job.step('逐项保存导入进度')
                current=ses.get(m.LibraryImport,rid);errors=ses.scalar(select(func.count()).select_from(m.LibraryImportItem).where(m.LibraryImportItem.import_id==rid,m.LibraryImportItem.status!='done'));current.status='partial' if errors else 'done';ses.commit()
        finally:
            with new_session() as ses:
                current=ses.get(m.LibraryImport,rid)
                if current and current.status in ('queued','running'):current.status='cancelled' if job.cancel_requested else 'interrupted';ses.commit()
    try:
        job=jobs.start('library-import','资料引用导入',0,work);run.job_id=job.id;session.commit();return {'import_id':rid,'job':job.to_dict()}
    except HTTPException:
        run.status='interrupted';session.commit();raise


def recover(engine):
    with engine.begin() as conn:conn.execute(update(m.LibraryImport).where(m.LibraryImport.status.in_(['queued','running'])).values(status='interrupted'))
