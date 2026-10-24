import uuid
from pathlib import Path
from typing import Literal

from fastapi import APIRouter,Depends,HTTPException,Query,Response
from pydantic import BaseModel,Field
from sqlalchemy import select,update,func,or_,and_,exists
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .. import models as m,projectarchive as archive,projectpreview
from ..crud import get_or_404,resolve_tags,tag_descendants
from ..db import get_session
from .projectpreview import report

router=APIRouter(prefix='/api',tags=['世界观项目归档'])


class Selection(BaseModel):
    index:int=Field(ge=0)
    title:str=Field(default='',max_length=300)
    category:str=Field(default='',max_length=80)
    tag_ids:list[int]=Field(default_factory=list,max_length=100)
    label_ids:list[int]=Field(default_factory=list,max_length=100)


class ImportRequest(BaseModel):
    report_id:str
    world_id:int|None=None
    new_world_name:str|None=Field(default=None,min_length=1,max_length=200)
    mode:Literal['index','managed']
    files:list[Selection]=Field(min_length=1,max_length=5000)


def labels_for(session,world_id,ids):
    rows=list(session.scalars(select(m.WorldLabel).where(m.WorldLabel.world_id==world_id,m.WorldLabel.id.in_(ids))))
    if {r.id for r in rows}!=set(ids):
        raise HTTPException(422,'局部标签不属于当前世界观或已经失效')
    return rows


@router.post('/project-imports',status_code=202)
def start(req:ImportRequest,session:Session=Depends(get_session)):
    if (req.world_id is None)==(req.new_world_name is None):
        raise HTTPException(422,'请选择一个目标世界观或填写新世界观名称')
    data=report(req.report_id)
    if len({f.index for f in req.files})!=len(req.files):
        raise HTTPException(422,'确认列表中有重复文件')
    selections=[]
    for choice in req.files:
        try:item,path=projectpreview.file_of(data,choice.index)
        except (ValueError,OSError) as exc:raise HTTPException(409,str(exc)) from None
        if not item.get('sha256') or item.get('error'):
            raise HTTPException(422,'文件缺少有效预览，请重新扫描')
        resolve_tags(session,choice.tag_ids)
        if req.world_id is not None:labels_for(session,req.world_id,choice.label_ids)
        elif choice.label_ids:raise HTTPException(422,'新世界观尚无局部标签，请先创建或导入后设置')
        selections.append(choice.model_dump()|{'path':str(path),'root':data['root'],'stamp':item['stamp'],'sha256':item['sha256'],'category':choice.category or item.get('candidate','resource')})
    if req.world_id is not None:
        world=get_or_404(session,m.World,req.world_id)
    else:
        if not req.new_world_name.strip():raise HTTPException(422,'世界观名称不能为空')
        world=m.World(name=req.new_world_name.strip());session.add(world);session.flush()
    run=m.ProjectImport(id=uuid.uuid4().hex,world_id=world.id,mode=req.mode,report_id=req.report_id)
    session.add(run);session.flush()
    for choice in selections:session.add(m.ProjectImportItem(import_id=run.id,file_index=choice['index'],selection=choice))
    session.commit()
    return archive.enqueue(session,run)


@router.get('/project-imports')
def imports(world_id:int|None=None,session:Session=Depends(get_session)):
    stmt=select(m.ProjectImport)
    if world_id is not None:stmt=stmt.where(m.ProjectImport.world_id==world_id)
    rows=list(session.scalars(stmt.order_by(m.ProjectImport.created_at.desc()).limit(100)))
    for run in rows:archive.reconcile(run)
    session.commit()
    return [{'id':r.id,'world_id':r.world_id,'mode':r.mode,'status':r.status,'job_id':r.job_id} for r in rows]


@router.get('/project-imports/{import_id}')
def import_detail(import_id:str,offset:int=Query(0,ge=0),limit:int=Query(50,ge=1,le=100),session:Session=Depends(get_session)):
    run=get_or_404(session,m.ProjectImport,import_id)
    if archive.reconcile(run):session.commit()
    states=list(session.execute(select(m.ProjectImportItem.status,func.count()).where(m.ProjectImportItem.import_id==import_id).group_by(m.ProjectImportItem.status)))
    rows=session.scalars(select(m.ProjectImportItem).where(m.ProjectImportItem.import_id==import_id).order_by(m.ProjectImportItem.id).limit(limit).offset(offset))
    return {'id':run.id,'world_id':run.world_id,'status':run.status,'job_id':run.job_id,'mode':run.mode,'report_id':run.report_id,'counts':dict(states),
            'items':[{'index':i.file_index,'title':i.selection.get('title') or Path(i.selection['path']).name,'status':i.status,'resource_id':i.resource_id,'message':i.message} for i in rows]}


@router.post('/project-imports/{import_id}/resume',status_code=202)
def resume(import_id:str,session:Session=Depends(get_session)):
    run=get_or_404(session,m.ProjectImport,import_id)
    if archive.reconcile(run):session.flush()
    claimed=session.execute(update(m.ProjectImport).where(m.ProjectImport.id==import_id,m.ProjectImport.status.in_(['interrupted','partial','cancelled'])).values(status='queued')).rowcount
    if not claimed:raise HTTPException(409,'任务正在运行或已经全部完成')
    session.commit()
    return archive.enqueue(session,run)


class LabelInput(BaseModel):
    name:str=Field(min_length=1,max_length=80)
    aliases:list[str]=Field(default_factory=list,max_length=50)
    parent_id:int|None=None


@router.get('/worlds/{world_id}/labels')
def labels(world_id:int,session:Session=Depends(get_session)):
    get_or_404(session,m.World,world_id)
    return [{'id':r.id,'name':r.name,'aliases':r.aliases,'parent_id':r.parent_id} for r in session.scalars(select(m.WorldLabel).where(m.WorldLabel.world_id==world_id).order_by(m.WorldLabel.name))]


def apply_label(session,world_id,req,current=None):
    get_or_404(session,m.World,world_id)
    if req.parent_id:
        parent=get_or_404(session,m.WorldLabel,req.parent_id)
        seen=set()
        while parent:
            if parent.world_id!=world_id or parent.id in seen or (current and parent.id==current.id):raise HTTPException(422,'局部标签父级越界或构成循环')
            seen.add(parent.id);parent=session.get(m.WorldLabel,parent.parent_id) if parent.parent_id else None
    if not req.name.strip() or any(len(a)>80 for a in req.aliases):raise HTTPException(422,'标签名或别名长度不正确')
    label=current or m.WorldLabel(world_id=world_id)
    label.name=req.name.strip();label.aliases=list(dict.fromkeys(a.strip() for a in req.aliases if a.strip()));label.parent_id=req.parent_id
    session.add(label)
    try:session.commit()
    except IntegrityError:session.rollback();raise HTTPException(409,'当前世界观内标签名称已存在') from None
    return {'id':label.id,'name':label.name}


@router.post('/worlds/{world_id}/labels')
def create_label(world_id:int,req:LabelInput,session:Session=Depends(get_session)):
    return apply_label(session,world_id,req)


@router.put('/worlds/{world_id}/labels/{label_id}')
def edit_label(world_id:int,label_id:int,req:LabelInput,session:Session=Depends(get_session)):
    label=get_or_404(session,m.WorldLabel,label_id)
    if label.world_id!=world_id:raise HTTPException(404,'局部标签不存在')
    return apply_label(session,world_id,req,label)


class ReferenceInput(BaseModel):
    entity_kind:Literal['asset','character','entry','note','work','relation']
    entity_id:int
    allow_cross_world:bool=False


def reference(session,world_id,kind,entity_id,allow=False):
    target=get_or_404(session,archive.ENTITIES[kind],entity_id)
    source_world=getattr(target,'world_id',None)
    if kind=='relation':
        ends=[get_or_404(session,m.Character,target.source_id),get_or_404(session,m.Character,target.target_id)]
        if any(c.world_id!=world_id for c in ends) and not allow:raise HTTPException(422,'跨世界观关系引用需要明确确认')
    elif source_world is not None and source_world!=world_id and not allow:raise HTTPException(422,'跨世界观引用需要明确确认')
    row=session.scalar(select(m.WorldResource).where(m.WorldResource.world_id==world_id,m.WorldResource.entity_kind==kind,m.WorldResource.entity_id==entity_id))
    if row is None:
        row=m.WorldResource(world_id=world_id,entity_kind=kind,entity_id=entity_id,title=getattr(target,'title',None) or getattr(target,'name',None) or f'{kind} #{entity_id}',category=kind)
        session.add(row);session.flush()
    else:
        from ..archiveidentity import valid
        if not valid(row,target):raise HTTPException(409,'旧引用失效，请先移除，不能自动关联复用ID的新资料')
    return row


@router.post('/worlds/{world_id}/archive/references')
def add_reference(world_id:int,req:ReferenceInput,session:Session=Depends(get_session)):
    get_or_404(session,m.World,world_id)
    row=reference(session,world_id,req.entity_kind,req.entity_id,req.allow_cross_world);session.commit()
    return {'id':row.id}


@router.post('/worlds/{world_id}/archive/sync')
def sync(world_id:int,session:Session=Depends(get_session)):
    get_or_404(session,m.World,world_id);count=0
    for kind,model in archive.ENTITIES.items():
        if not hasattr(model,'world_id'):continue
        for entity_id in session.scalars(select(model.id).where(model.world_id==world_id)):
            reference(session,world_id,kind,entity_id);count+=1
    session.commit();return {'linked':count}


def resource_row(session,row,detail=False):
    data={k:getattr(row,k) for k in ('id','world_id','entity_kind','entity_id','title','category','source_path','storage_mode','global_tag_ids','label_ids','favorite','stars','preference','notes')}
    model=archive.ENTITIES[row.entity_kind]
    if not detail:
        data['missing_record']=session.scalar(select(model.id).where(model.id==row.entity_id,model.created_at<=row.created_at)) is None
        return data
    target=session.get(model,row.entity_id)
    from ..archiveidentity import valid
    if not valid(row,target):target=None
    data['missing_record']=target is None
    if detail and target:
        data['content']=getattr(target,'content',None) or getattr(target,'profile',None) or getattr(target,'summary',None) or getattr(target,'description',None)
        if row.entity_kind=='asset':
            data.update(asset_id=target.id,mime=target.mime,size=target.size,width=target.width,sha256=target.sha256)
            try:
                from .assets import _file_of
                _file_of(target);data['file_status']='ok'
            except HTTPException as exc:data['file_status']=exc.detail
    return data


@router.get('/worlds/{world_id}/archive')
def listing(world_id:int,q:str='',kind:str='',label_id:int|None=None,tag_id:int|None=None,offset:int=Query(0,ge=0),limit:int=Query(50,ge=1,le=100),session:Session=Depends(get_session)):
    get_or_404(session,m.World,world_id)
    stmt=select(m.WorldResource).where(m.WorldResource.world_id==world_id)
    if kind:stmt=stmt.where(m.WorldResource.entity_kind==kind)
    # JSON arrays are small world-local preference sets; hierarchy stays scoped.
    if label_id is not None:
        labels_for(session,world_id,[label_id]);family={label_id};changed=True
        all_labels=list(session.scalars(select(m.WorldLabel).where(m.WorldLabel.world_id==world_id)))
        while changed:
            previous=len(family);family.update(l.id for l in all_labels if l.parent_id in family);changed=len(family)!=previous
        members=func.json_each(m.WorldResource.label_ids).table_valued('value')
        stmt=stmt.where(exists(select(1).select_from(members).where(members.c.value.in_(family))))
    if tag_id is not None:
        family=tag_descendants(session,tag_id)
        members=func.json_each(m.WorldResource.global_tag_ids).table_valued('value')
        stmt=stmt.where(exists(select(1).select_from(members).where(members.c.value.in_(family))))
    if q:
        hits=[m.WorldResource.title.contains(q,autoescape=True),m.WorldResource.notes.contains(q,autoescape=True)]
        for entity_kind,model in archive.ENTITIES.items():
            columns=[getattr(model,k).contains(q,autoescape=True) for k in ('content','profile','summary','name','title') if hasattr(model,k)]
            if columns:hits.append(and_(m.WorldResource.entity_kind==entity_kind,m.WorldResource.entity_id.in_(select(model.id).where(or_(*columns),model.created_at<=m.WorldResource.created_at))))
        stmt=stmt.where(or_(*hits))
    total=session.scalar(select(func.count()).select_from(stmt.subquery()))
    rows=session.scalars(stmt.order_by(m.WorldResource.id.desc()).limit(limit).offset(offset))
    return {'total':total,'items':[resource_row(session,r) for r in rows]}


@router.get('/worlds/{world_id}/archive/{resource_id}')
def detail(world_id:int,resource_id:int,session:Session=Depends(get_session)):
    row=get_or_404(session,m.WorldResource,resource_id)
    if row.world_id!=world_id:raise HTTPException(404,'归档引用不存在')
    return resource_row(session,row,True)


class PreferenceInput(BaseModel):
    ids:list[int]=Field(min_length=1,max_length=500)
    title:str|None=Field(default=None,min_length=1,max_length=300)
    category:str|None=Field(default=None,max_length=80)
    global_tag_ids:list[int]|None=None
    label_ids:list[int]|None=None
    favorite:bool|None=None
    stars:int|None=Field(default=None,ge=0,le=5)
    preference:int|None=Field(default=None,ge=0,le=100)
    notes:str|None=Field(default=None,max_length=20000)


@router.patch('/worlds/{world_id}/archive')
def preferences(world_id:int,req:PreferenceInput,session:Session=Depends(get_session)):
    rows=list(session.scalars(select(m.WorldResource).where(m.WorldResource.world_id==world_id,m.WorldResource.id.in_(req.ids))))
    if len(rows)!=len(set(req.ids)):raise HTTPException(422,'包含其他世界观或已失效的归档ID')
    if req.global_tag_ids is not None:resolve_tags(session,req.global_tag_ids)
    if req.label_ids is not None:labels_for(session,world_id,req.label_ids)
    for row in rows:
        for key,value in req.model_dump(exclude_unset=True,exclude={'ids'},exclude_none=True).items():setattr(row,key,value)
    session.commit();return {'updated':len(rows)}


@router.delete('/worlds/{world_id}/archive/{resource_id}',status_code=204)
def remove(world_id:int,resource_id:int,session:Session=Depends(get_session)):
    row=get_or_404(session,m.WorldResource,resource_id)
    if row.world_id!=world_id:raise HTTPException(404,'归档引用不存在')
    session.delete(row);session.commit();return Response(status_code=204)
