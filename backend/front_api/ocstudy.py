"""Practice journals reuse collection asset references and immutable versions."""
import uuid,json
from datetime import date
from fastapi import HTTPException
from sqlalchemy import select,func
from . import models as m,versions,ocstudio as studio

STAGES=['original','reference','sketch','lineart','color','modification','three-view','expression','clothing','hatching']


def profile(session,study):
    obj=session.get(m.OCProfile,study.profile_id) if study.profile_id else None
    if obj is None or studio.identity(obj)!=study.profile_identity:raise HTTPException(409,'学习集的OC档案已失效，不自动关联复用ID')
    return obj


def revision(session,study):
    h=versions.head(session.connection(),'study',study.id);last=versions.latest(session.connection(),h['generation']) if h else None
    return last['id'] if last else 0


def guard(session,study,expected):
    if revision(session,study)!=expected:raise HTTPException(409,'练习记录已更新，请重新加载')


def sync_collection(session,study):
    if not study.collection_id:return
    obj=profile(session,study)
    existing=set(session.scalars(select(m.collection_assets.c.asset_id).where(m.collection_assets.c.collection_id==study.collection_id)))
    position=session.scalar(select(func.coalesce(func.max(m.collection_assets.c.position),-1)).where(m.collection_assets.c.collection_id==study.collection_id))+1
    for entry in study.entries:
        asset,status=studio.reference_status(session,obj,entry)
        if status=='ok' and asset.id not in existing:
            session.execute(m.collection_assets.insert().values(collection_id=study.collection_id,asset_id=asset.id,position=position));existing.add(asset.id);position+=1


def append(session,study,ref,stage,notes='',learned_on=None):
    if len(study.entries)>=2000:raise HTTPException(413,'单个学习集最多2000项')
    if stage not in STAGES:raise HTTPException(422,'未知练习类型')
    obj=profile(session,study);target,status=studio.reference_status(session,obj,ref)
    if status!='ok':raise HTTPException(409,status)
    if ref['kind']!='asset':raise HTTPException(422,'练习项请选择素材引用')
    value={**ref,'id':uuid.uuid4().hex,'source_reference':ref['id'],'stage':stage,'learning_notes':notes,'learned_on':(learned_on or date.today()).isoformat()}
    entries=[*study.entries,value]
    if len(json.dumps(entries,ensure_ascii=False).encode())>8*1024*1024:raise HTTPException(413,'学习集元数据超过8MiB，请拆分练习集')
    study.entries=entries;sync_collection(session,study);return value


def detail(session,study):
    obj=profile(session,study);entries=[]
    for entry in study.entries:
        asset,status=studio.reference_status(session,obj,entry)
        entries.append(entry|{'status':status,'title':asset.title if asset else '失效素材','is_image':bool(asset and asset.width),'historical_file':bool(asset and entry.get('sha256')!=asset.sha256)})
    return {'id':study.id,'profile_id':study.profile_id,'collection_id':study.collection_id,'title':study.title,'notes':study.notes,'entries':entries,'version':revision(session,study)}
