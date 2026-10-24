import hashlib
from typing import Literal
from fastapi import APIRouter,Depends,HTTPException,Query,Response
from pydantic import BaseModel,Field
from sqlalchemy import select,func,or_,exists,String
from sqlalchemy.orm import Session,defer
from .. import models as m,ocstudio as studio,versions
from ..db import get_session
from ..crud import get_or_404,resolve_tags,tag_descendants

router=APIRouter(prefix='/api/oc',tags=['OC Studio'])


class Design(BaseModel):
    id:str|None=Field(default=None,min_length=1,max_length=80)
    name:str=Field(min_length=1,max_length=100)
    fields:dict[str,str]=Field(default_factory=dict)
    notes:str=Field(default='',max_length=10000)


class Draft(BaseModel):
    title:str=Field(min_length=1,max_length=200)
    fields:dict[str,str]=Field(default_factory=dict)
    designs:list[Design]=Field(default_factory=list,max_length=100)
    source:str=Field(default='',max_length=2000)
    favorite:bool=False
    stars:int=Field(default=0,ge=0,le=5)
    preference:int=Field(default=0,ge=0,le=100)
    notes:str=Field(default='',max_length=30000)
    tag_ids:list[int]=Field(default_factory=list,max_length=100)


class Create(Draft):
    character_id:int|None=Field(default=None,ge=1)
    world_id:int|None=None
    work_id:int|None=None


class Update(Draft):
    expected_version:int=Field(ge=1)


class Ref(BaseModel):
    kind:Literal['asset','note','prompt','model']
    entity_id:int=Field(ge=1)
    role:str=Field(default='reference',max_length=40)
    design_id:str|None=None
    allow_cross_world:bool=False
    as_cover:bool=False
    expected_version:int=Field(ge=1)


def summary(profile,character_name=None,world=None,work=None,session=None):
    cover=profile.cover_asset_id
    if cover and session:
        ref=next((r for r in profile.references if r['kind']=='asset' and r['entity_id']==cover),None)
        target,status=studio.reference_status(session,profile,ref) if ref else (None,'missing')
        if status!='ok' or (ref.get('sha256') and target.sha256!=ref['sha256']):cover=None
    return {'id':profile.id,'title':profile.title,'character_id':profile.character_id,'character_name':character_name,'world_id':world,'work_id':work,
            'cover_asset_id':cover,'favorite':profile.favorite,'stars':profile.stars,'preference':profile.preference,'tags':[{'id':t.id,'name':t.name,'color':t.color} for t in profile.tags]}


def detail(session,profile):
    char=studio.character(session,profile);data=summary(profile,char.name if char else None,char.world_id if char else None,char.work_id if char else None,session)
    refs=[]
    for r in profile.references:
        target,status=studio.reference_status(session,profile,r)
        refs.append(r|{'status':status,'title':getattr(target,'title',None) or getattr(target,'name',None) or f'#{r["entity_id"]}',
                       'is_image':bool(getattr(target,'width',None)),'historical_file':bool(target and r['kind']=='asset' and r.get('sha256')!=target.sha256),'missing_design':bool(r.get('design_id') and not any(d['id']==r['design_id'] for d in profile.designs))})
    return data|{'fields':profile.fields,'designs':profile.designs,'references':refs,'source':profile.source,'notes':profile.notes,'version':studio.revision(session,profile),'canonical_profile':char.profile if char else None,'character_missing':char is None}


@router.get('')
def listing(q:str='',world_id:str='',tag:int|None=None,favorite:bool=False,limit:int=Query(50,ge=1,le=100),offset:int=Query(0,ge=0),session:Session=Depends(get_session)):
    stmt=select(m.OCProfile,m.Character.name,m.Character.world_id,m.Character.work_id).outerjoin(m.Character,m.Character.id==m.OCProfile.character_id)
    if q:
        values=func.json_tree(m.OCProfile.fields).table_valued('value')
        looks=func.json_tree(m.OCProfile.designs).table_valued('value')
        stmt=stmt.where(or_(m.OCProfile.title.contains(q,autoescape=True),m.Character.name.contains(q,autoescape=True),m.OCProfile.notes.contains(q,autoescape=True),exists(select(1).select_from(values).where(values.c.value.cast(String).contains(q,autoescape=True))),exists(select(1).select_from(looks).where(looks.c.value.cast(String).contains(q,autoescape=True)))))
    if world_id=='none':stmt=stmt.where(m.Character.world_id.is_(None))
    elif world_id:
        try:wid=int(world_id)
        except ValueError:raise HTTPException(422,'世界观ID无效') from None
        stmt=stmt.where(m.Character.world_id==wid)
    if favorite:stmt=stmt.where(m.OCProfile.favorite.is_(True))
    if tag:stmt=stmt.where(m.OCProfile.tags.any(m.Tag.id.in_(tag_descendants(session,tag))))
    total=session.scalar(select(func.count()).select_from(stmt.subquery()))
    rows=session.execute(stmt.options(defer(m.OCProfile.fields),defer(m.OCProfile.designs),defer(m.OCProfile.references),defer(m.OCProfile.notes)).order_by(m.OCProfile.favorite.desc(),m.OCProfile.updated_at.desc()).limit(limit).offset(offset))
    return {'total':total,'items':[summary(p,n,w,k,session) for p,n,w,k in rows]}


@router.post('',status_code=201)
def create(body:Create,session:Session=Depends(get_session)):
    session.connection().exec_driver_sql('BEGIN IMMEDIATE')
    designs=studio.normalize(body.fields,body.designs);tags=resolve_tags(session,body.tag_ids)
    if body.character_id:
        char=get_or_404(session,m.Character,body.character_id)
        old=session.scalar(select(m.OCProfile).where(m.OCProfile.character_id==char.id))
        if old:raise HTTPException(409,{'message':'该角色已有创作档案','profile_id':old.id})
        if body.world_id not in (None,char.world_id) or body.work_id not in (None,char.work_id):raise HTTPException(422,'已有角色的归属需在百科明确编辑，不在创建档案时重置')
    else:
        if body.world_id is not None:get_or_404(session,m.World,body.world_id)
        if body.work_id is not None:get_or_404(session,m.Work,body.work_id)
        char=m.Character(name=body.title,world_id=body.world_id,work_id=body.work_id);session.add(char);session.flush()
    data=body.model_dump(exclude={'world_id','work_id','character_id','tag_ids','designs'})
    obj=m.OCProfile(**data,character_id=char.id,designs=designs,tags=tags);session.add(obj);session.flush()
    versions.enable(session,obj,'创建OC创作草稿');session.commit()
    return detail(session,obj)


@router.get('/choices')
def choices(kind:Literal['character','world','work'],q:str='',limit:int=Query(100,ge=1,le=100),session:Session=Depends(get_session)):
    # Metadata only: never transfer novel/profile bodies into a selection list.
    model,label={'character':(m.Character,m.Character.name),'world':(m.World,m.World.name),'work':(m.Work,m.Work.title)}[kind]
    columns=[model.id,label.label('name')]
    if kind=='character':columns.extend([model.world_id,model.work_id])
    stmt=select(*columns)
    if q:stmt=stmt.where(label.contains(q,autoescape=True))
    return {'items':[dict(row) for row in session.execute(stmt.order_by(label,model.id).limit(limit)).mappings()]}


@router.get('/{profile_id}')
def get(profile_id:int,session:Session=Depends(get_session)):return detail(session,get_or_404(session,m.OCProfile,profile_id))


@router.put('/{profile_id}')
def update(profile_id:int,body:Update,session:Session=Depends(get_session)):
    session.connection().exec_driver_sql('BEGIN IMMEDIATE');obj=get_or_404(session,m.OCProfile,profile_id);studio.guard(session,obj,body.expected_version)
    designs=studio.normalize(body.fields,body.designs);tags=resolve_tags(session,body.tag_ids)
    for key,value in body.model_dump(exclude={'expected_version','tag_ids','designs'}).items():setattr(obj,key,value)
    obj.designs=designs;obj.tags=tags;session.commit();return detail(session,obj)


@router.post('/{profile_id}/references')
def reference(profile_id:int,body:Ref,session:Session=Depends(get_session)):
    session.connection().exec_driver_sql('BEGIN IMMEDIATE');obj=get_or_404(session,m.OCProfile,profile_id);studio.guard(session,obj,body.expected_version)
    studio.attach(session,obj,**body.model_dump(exclude={'expected_version'}));session.commit();return detail(session,obj)


@router.delete('/{profile_id}/references/{reference_id}')
def remove_reference(profile_id:int,reference_id:str,expected_version:int,session:Session=Depends(get_session)):
    session.connection().exec_driver_sql('BEGIN IMMEDIATE');obj=get_or_404(session,m.OCProfile,profile_id);studio.guard(session,obj,expected_version)
    removed=next((r for r in obj.references if r['id']==reference_id),None)
    if not removed:raise HTTPException(404,'引用不存在')
    obj.references=[r for r in obj.references if r['id']!=reference_id]
    if removed['kind']=='asset' and obj.cover_asset_id==removed['entity_id']:obj.cover_asset_id=None
    session.commit();return detail(session,obj)


class Publish(BaseModel):
    expected_version:int
    confirmed:bool=False


@router.post('/{profile_id}/publish')
def publish(profile_id:int,body:Publish,session:Session=Depends(get_session)):
    if not body.confirmed:raise HTTPException(422,'需明确确认将草稿补充到百科，不覆盖原设定')
    session.connection().exec_driver_sql('BEGIN IMMEDIATE');obj=get_or_404(session,m.OCProfile,profile_id);studio.guard(session,obj,body.expected_version)
    char=studio.character(session,obj)
    if not char:raise HTTPException(409,'原百科角色已删除，草稿保留，请先明确建立新的关联')
    text='\n'.join(f'**{k.replace(chr(10)," ")}**：{v}' for k,v in obj.fields.items() if v.strip())
    if not text:raise HTTPException(422,'草稿暂无可发布字段')
    marker='<!-- front-oc-'+hashlib.sha256(text.encode()).hexdigest()+' -->'
    if marker not in (char.profile or ''):
        versions.enable(session,char,'OC补充前百科快照');char.profile=(char.profile or '')+'\n\n'+marker+'\n### OC创作草稿补充\n'+text
    session.commit();return {'character_id':char.id,'appended':True}


@router.delete('/{profile_id}',status_code=204)
def remove(profile_id:int,expected_version:int,session:Session=Depends(get_session)):
    session.connection().exec_driver_sql('BEGIN IMMEDIATE');obj=get_or_404(session,m.OCProfile,profile_id);studio.guard(session,obj,expected_version)
    session.delete(obj);session.commit();return Response(status_code=204)
