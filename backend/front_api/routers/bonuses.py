from datetime import date
from fastapi import APIRouter,Depends,HTTPException,Query
from pydantic import BaseModel,Field
from sqlalchemy import select,func,exists
from sqlalchemy.orm import Session
from .. import models as m,bonuses as b,versions,jobs
from ..db import get_session,new_session
from ..crud import get_or_404,resolve_tags,tag_descendants
from ..ocstudio import identity

router=APIRouter(prefix='/api/bonuses',tags=['作品特典'])


class Preference(BaseModel):
    source:str=Field(default='',max_length=2000)
    version_label:str=Field(default='',max_length=100)
    acquired_on:date|None=None
    favorite:bool=False
    stars:int=Field(default=0,ge=0,le=5)
    preference:int=Field(default=0,ge=0,le=100)
    notes:str=Field(default='',max_length=30000)
    tag_ids:list[int]=Field(default_factory=list,max_length=100)


class Archive(Preference):
    title:str=Field(min_length=1,max_length=200)
    work_id:int|None=None
    world_id:int|None=None
    cover_asset_id:int|None=None


class ArchiveEdit(Archive):
    expected_version:int=Field(ge=1)


class Item(Preference):
    category:str=Field(default='未确认',max_length=80)
    group_id:int|None=None
    expected_version:int=Field(ge=1)


class Attach(BaseModel):
    asset_ids:list[int]=Field(min_length=1,max_length=500)
    allow_cross_scope:bool=False
    group_id:int|None=None


def validate(session,body):
    for key,model in [('work_id',m.Work),('world_id',m.World),('cover_asset_id',m.Asset)]:
        value=getattr(body,key)
        if value is not None:get_or_404(session,model,value)
    if body.cover_asset_id:
        asset=session.get(m.Asset,body.cover_asset_id)
        if any(getattr(asset,k) is not None and getattr(asset,k)!=getattr(body,k) for k in ('world_id','work_id')):raise HTTPException(422,'封面归属不同，请选择当前作品资料或全局图片')


def archive_dict(session,row):
    keys=('id','title','collection_id','world_id','work_id','cover_asset_id','source','version_label','acquired_on','favorite','stars','preference','notes')
    cover=session.get(m.Asset,row.cover_asset_id) if row.cover_asset_id else None
    data={k:getattr(row,k) for k in keys}
    if cover and any(getattr(cover,k) is not None and getattr(cover,k)!=getattr(row,k) for k in ('world_id','work_id')):data['cover_asset_id']=None
    return data|{'version':b.revision(session,'bonus',row),'tags':[{'id':t.id,'name':t.name,'color':t.color} for t in row.tags]}


@router.get('')
def listing(q:str='',work_id:int|None=None,offset:int=Query(0,ge=0),session:Session=Depends(get_session)):
    stmt=select(m.BonusArchive)
    if q:stmt=stmt.where(m.BonusArchive.title.contains(q,autoescape=True))
    if work_id:stmt=stmt.where(m.BonusArchive.work_id==work_id)
    total=session.scalar(select(func.count()).select_from(stmt.subquery()))
    return {'total':total,'items':[archive_dict(session,r) for r in session.scalars(stmt.order_by(m.BonusArchive.favorite.desc(),m.BonusArchive.updated_at.desc()).offset(offset).limit(30))]}


@router.post('',status_code=201)
def create(body:Archive,session:Session=Depends(get_session)):
    validate(session,body);col=m.Collection(name=body.title,work_id=body.work_id,description='作品特典资料引用');session.add(col);session.flush()
    row=m.BonusArchive(**body.model_dump(exclude={'tag_ids'}),collection_id=col.id,tags=resolve_tags(session,body.tag_ids));session.add(row);session.flush();versions.enable(session,row,'创建作品特典档案');session.commit();return archive_dict(session,row)


@router.get('/{archive_id}')
def detail(archive_id:int,session:Session=Depends(get_session)):return archive_dict(session,get_or_404(session,m.BonusArchive,archive_id))


@router.put('/{archive_id}')
def update(archive_id:int,body:ArchiveEdit,session:Session=Depends(get_session)):
    session.connection().exec_driver_sql('BEGIN IMMEDIATE');row=get_or_404(session,m.BonusArchive,archive_id);b.guard(session,'bonus',row,body.expected_version);validate(session,body)
    for k,v in body.model_dump(exclude={'tag_ids','expected_version'}).items():setattr(row,k,v)
    row.tags=resolve_tags(session,body.tag_ids);session.commit();return archive_dict(session,row)


@router.get('/{archive_id}/groups')
def groups(archive_id:int,session:Session=Depends(get_session)):
    get_or_404(session,m.BonusArchive,archive_id)
    return {'items':[{'id':g.id,'parent_id':g.parent_id,'name':g.name} for g in session.scalars(select(m.BonusGroup).where(m.BonusGroup.archive_id==archive_id).order_by(m.BonusGroup.parent_id,m.BonusGroup.name).limit(1000))]}


class Group(BaseModel):
    name:str=Field(min_length=1,max_length=200)
    parent_id:int|None=None


@router.post('/{archive_id}/groups',status_code=201)
def add_group(archive_id:int,body:Group,session:Session=Depends(get_session)):
    get_or_404(session,m.BonusArchive,archive_id)
    if body.parent_id is not None:
        group=get_or_404(session,m.BonusGroup,body.parent_id)
        if group.archive_id!=archive_id:raise HTTPException(422,'上级分组不属于当前档案')
    group=m.BonusGroup(archive_id=archive_id,**body.model_dump());session.add(group);session.commit();return {'id':group.id}


@router.get('/{archive_id}/items')
def items(archive_id:int,q:str='',group_id:int|None=None,category:str='',tag:int|None=None,offset:int=Query(0,ge=0),session:Session=Depends(get_session)):
    archive=get_or_404(session,m.BonusArchive,archive_id);stmt=select(m.BonusItem).outerjoin(m.Asset,m.Asset.id==m.BonusItem.asset_id).where(m.BonusItem.archive_id==archive_id)
    if q:stmt=stmt.where(m.Asset.title.contains(q,autoescape=True))
    if group_id:stmt=stmt.where(m.BonusItem.group_id==group_id)
    if category:stmt=stmt.where(m.BonusItem.category==category)
    if tag:stmt=stmt.where(m.BonusItem.tags.any(m.Tag.id.in_(tag_descendants(session,tag))))
    total=session.scalar(select(func.count()).select_from(stmt.subquery()))
    return {'total':total,'items':[b.item_dict(session,archive,row) for row in session.scalars(stmt.order_by(m.BonusItem.group_id,m.BonusItem.id).offset(offset).limit(50))]}


@router.post('/{archive_id}/items')
def attach(archive_id:int,body:Attach,session:Session=Depends(get_session)):
    session.connection().exec_driver_sql('BEGIN IMMEDIATE');archive=get_or_404(session,m.BonusArchive,archive_id)
    rows=[b.attach(session,archive,get_or_404(session,m.Asset,aid),body.allow_cross_scope,body.group_id).id for aid in dict.fromkeys(body.asset_ids)];session.commit();return {'item_ids':rows}


@router.put('/{archive_id}/items/{item_id}')
def edit_item(archive_id:int,item_id:int,body:Item,session:Session=Depends(get_session)):
    session.connection().exec_driver_sql('BEGIN IMMEDIATE');archive=get_or_404(session,m.BonusArchive,archive_id);row=get_or_404(session,m.BonusItem,item_id)
    if row.archive_id!=archive_id:raise HTTPException(422,'资料不属于当前档案')
    b.guard(session,'bonus_item',row,body.expected_version)
    if body.group_id is not None:
        group=get_or_404(session,m.BonusGroup,body.group_id)
        if group.archive_id!=archive_id:raise HTTPException(422,'分组不属于当前档案')
    for k,v in body.model_dump(exclude={'tag_ids','expected_version'}).items():setattr(row,k,v)
    row.tags=resolve_tags(session,body.tag_ids);session.commit();return b.item_dict(session,archive,row)


@router.post('/{archive_id}/sync',status_code=202)
def sync(archive_id:int,allow_cross_scope:bool=False,session:Session=Depends(get_session)):
    archive=get_or_404(session,m.BonusArchive,archive_id);token=identity(archive);cid=archive.collection_id;scope=[archive.world_id,archive.work_id]
    if cid is None:raise HTTPException(409,'共享收藏集已删除，保留档案，请手动引用资料')
    def work(job):
        done=0;last=0;cache={};job.result={'linked':0,'skipped':0}
        while True:
            job.check()
            with new_session() as ses:
                ses.connection().exec_driver_sql('BEGIN IMMEDIATE');current=ses.get(m.BonusArchive,archive_id)
                if current is None or identity(current)!=token or current.collection_id!=cid or [current.world_id,current.work_id]!=scope:raise ValueError('特典档案归属或收藏集已变化，停止同步')
                ids=list(ses.scalars(select(m.collection_assets.c.asset_id).where(m.collection_assets.c.collection_id==cid,m.collection_assets.c.asset_id>last,~exists(select(1).where(m.BonusItem.archive_id==archive_id,m.BonusItem.asset_id==m.collection_assets.c.asset_id))).order_by(m.collection_assets.c.asset_id).limit(100)))
                if not ids:break
                for aid in ids:
                    job.check();last=aid
                    try:b.attach(ses,current,get_or_404(ses,m.Asset,aid),allow_cross_scope,relative=b.imported_relative(ses,cid,aid,cache));done+=1
                    except HTTPException as exc:
                        job.result['skipped']+=1;job.errors.append(str(exc.detail));continue
                ses.commit();job.result['linked']=done;job.step('批量登记特典候选，未确认来源')
        job.total=job.done
    return jobs.start('bonus-sync','登记共享特典资料',0,work).to_dict()
