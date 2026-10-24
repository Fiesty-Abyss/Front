"""Work extras use ordinary assets/collections and opt-in immutable versions."""
from pathlib import Path,PurePosixPath
from sqlalchemy import select,func
from sqlalchemy.orm import defer
from fastapi import HTTPException
from . import models as m,versions,projectpreview
from .ocstudio import identity
from .referenceimports import link


def scope(archive,asset):return {'archive':[archive.world_id,archive.work_id],'asset':[asset.world_id,asset.work_id]}


def status(session,archive,item):
    asset=session.get(m.Asset,item.asset_id,options=[defer(m.Asset.content),defer(m.Asset.description),defer(m.Asset.meta)]) if item.asset_id else None
    if asset is None or identity(asset)!=item.asset_identity:return None,'原素材已删除或ID被复用'
    foreign=any(getattr(asset,k) is not None and getattr(asset,k)!=getattr(archive,k) for k in ('world_id','work_id'))
    if foreign and item.approved_scope!=scope(archive,asset):return None,'素材归属已变化，需要重新确认引用'
    return asset,'历史文件引用' if asset.sha256!=item.sha256 else 'ok'


def suggestion(asset,relative=None):
    name=(relative or asset.original_name or asset.title).lower();ext=Path(name).suffix
    labels={'pdf':'数字设定集 / 画册','document':'文档资料','novel':'小说 / 文本','video':'视频特典','audio':'原声 / 音声','drawing':'CG / 壁纸','cg':'CG / 壁纸','reference':'参考资料','archive':'附加资料包'}
    category=labels.get(asset.kind,'自定义资料')
    if asset.kind=='audio':
        if 'asmr' in name:category='ASMR'
        elif any(x in name for x in ('drama','广播','音声')):category='Drama CD / 广播剧'
        elif any(x in name for x in ('ost','soundtrack','原声')):category='原声音乐'
    if ext=='.epub':category='EPUB画册 / 小说'
    return {'category':category,'basis':'文件格式/文件名线索','confirmed':False,'notice':'分类候选，不证明发行方、版权或作品来源'}


def group_for(session,archive_id,relative):
    parent=None
    for name in list(PurePosixPath(relative.replace('\\','/')).parts[:-1])[:16]:
        if name in ('','.','..','/'):continue
        name=name[:200]
        group=session.scalar(select(m.BonusGroup).where(m.BonusGroup.archive_id==archive_id,m.BonusGroup.parent_id==parent,m.BonusGroup.name==name))
        if group is None:group=m.BonusGroup(archive_id=archive_id,parent_id=parent,name=name);session.add(group);session.flush()
        parent=group.id
    return parent


def imported_relative(session,collection_id,asset_id,cache):
    row=session.execute(select(m.LibraryImport.report_id,m.LibraryImportItem.file_index).join(m.LibraryImportItem,m.LibraryImportItem.import_id==m.LibraryImport.id).where(m.LibraryImport.collection_id==collection_id,m.LibraryImportItem.asset_id==asset_id,m.LibraryImportItem.status=='done').order_by(m.LibraryImport.created_at.desc(),m.LibraryImportItem.id.desc()).limit(1)).first()
    if not row:return None
    try:
        if row.report_id not in cache:
            if len(cache)>=4:cache.pop(next(iter(cache)))
            cache[row.report_id]=projectpreview.load(row.report_id)
        return cache[row.report_id]['files'][row.file_index]['relative']
    except (ValueError,IndexError,KeyError):return None


def attach(session,archive,asset,allow_cross=False,group_id=None,relative=None):
    foreign=any(getattr(asset,k) is not None and getattr(asset,k)!=getattr(archive,k) for k in ('world_id','work_id'))
    if foreign and not allow_cross:raise HTTPException(422,'不同作品/世界观资料需明确确认引用')
    if group_id is not None:
        group=session.get(m.BonusGroup,group_id)
        if group is None or group.archive_id!=archive.id:raise HTTPException(422,'分组不属于当前特典档案')
    old=session.scalar(select(m.BonusItem).where(m.BonusItem.archive_id==archive.id,m.BonusItem.asset_id==asset.id))
    if old:return old
    if group_id is None and isinstance(relative,str):group_id=group_for(session,archive.id,relative)
    item=m.BonusItem(archive_id=archive.id,asset_id=asset.id,asset_identity=identity(asset),asset_version=versions.enable(session,asset,'特典引用时素材快照'),sha256=asset.sha256,group_id=group_id,suggestion=suggestion(asset,relative),approved_scope=scope(archive,asset) if allow_cross else {})
    session.add(item);session.flush();versions.enable(session,item,'建立特典资料引用');link(session,archive.collection_id,asset.id);return item


def revision(session,kind,obj):
    h=versions.head(session.connection(),kind,obj.id);last=versions.latest(session.connection(),h['generation']) if h else None
    return last['id'] if last else 0


def guard(session,kind,obj,expected):
    if revision(session,kind,obj)!=expected:raise HTTPException(409,'特典档案已变化，请重新加载比较')


def item_dict(session,archive,item):
    asset,state=status(session,archive,item)
    keys=('id','archive_id','group_id','asset_id','asset_version','category','suggestion','source','version_label','acquired_on','favorite','stars','preference','notes')
    has_thumb=bool(asset and (asset.width or session.scalar(select(func.json_extract(m.Asset.meta,'$.file.thumb')).where(m.Asset.id==asset.id))))
    return {k:getattr(item,k) for k in keys}|{'version':revision(session,'bonus_item',item),'status':state,'title':asset.title if asset else '失效素材','kind':asset.kind if asset else None,'has_thumb':has_thumb,'tags':[{'id':t.id,'name':t.name,'color':t.color} for t in item.tags]}
