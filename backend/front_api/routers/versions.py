"""Immutable history, explicit media pinning, optimistic restore and bounded diffs."""
from datetime import date
from pathlib import Path
import difflib
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import select, func, Date
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from ..db import get_session
from .. import models as m, versions as v
from ..config import get_settings
from ..crud import resolve_tags

router=APIRouter(prefix='/api/versions',tags=['版本记录'])


class Save(BaseModel):
    note:str=Field(default='手动保存',max_length=500)


class Restore(BaseModel):
    expected_latest:int
    note:str=Field(default='恢复历史版本',max_length=500)


class Adopt(BaseModel):
    asset_id:int
    expected_latest:int
    note:str=Field(default='采用新的文件版本',max_length=500)


def generation(session,kind,entity_id):
    obj=v.get_entity(session,kind,entity_id)
    h=v.head(session.connection(),kind,entity_id)
    return obj,h if h and h['present'] and h['enabled'] else None


def revision(session,kind,entity_id,version_id):
    obj,h=generation(session,kind,entity_id)
    row=session.get(m.EntityVersion,version_id)
    if not h or not row or row.generation!=h['generation']:
        raise HTTPException(404,'版本不属于当前资料')
    return obj,row,session.get(m.VersionBlob,row.blob_sha).payload


def check_latest(session,h,expected):
    last=v.latest(session.connection(),h['generation']) if h else None
    if not last or last['id']!=expected:
        raise HTTPException(409,'版本已变化，请重新加载后确认')


@router.get('/{kind}/{entity_id}')
def listing(kind:str,entity_id:int,limit:int=Query(50,ge=1,le=100),offset:int=Query(0,ge=0),session:Session=Depends(get_session)):
    _,h=generation(session,kind,entity_id)
    if not h:return {'enabled':False,'items':[],'total':0}
    query=select(m.EntityVersion).where(m.EntityVersion.generation==h['generation'])
    rows=session.scalars(query.order_by(m.EntityVersion.id.desc()).offset(offset).limit(limit)).all()
    return {'enabled':True,'total':session.scalar(select(func.count()).select_from(query.subquery())),
            'items':[{'id':r.id,'created_at':r.created_at,'note':r.note,'source':r.source,'sha256':r.blob_sha} for r in rows]}


@router.post('/{kind}/{entity_id}')
def save(kind:str,entity_id:int,body:Save,session:Session=Depends(get_session)):
    session.connection().exec_driver_sql('BEGIN IMMEDIATE')
    obj=v.get_entity(session,kind,entity_id)
    rid=v.enable(session,obj,body.note);session.commit()
    return {'id':rid}


@router.get('/{kind}/{entity_id}/compare')
def compare(kind:str,entity_id:int,left:int,right:int,session:Session=Depends(get_session)):
    _,_,a=revision(session,kind,entity_id,left);_,_,b=revision(session,kind,entity_id,right)
    fields=[]
    def visit(x,y,path=''):
        if x==y:return
        if isinstance(x,dict) and isinstance(y,dict):
            for key in sorted(x.keys()|y.keys()):visit(x.get(key),y.get(key),f'{path}.{key}' if path else key)
        else:
            item={'field':path,'before':x,'after':y}
            if isinstance(x,str) and isinstance(y,str):
                if max(len(x),len(y))>500_000 or max(x.count('\n'),y.count('\n'))>6000:
                    item.update(before=x[:2000],after=y[:2000],truncated=True)
                else:
                    aa=x.splitlines(keepends=True);bb=y.splitlines(keepends=True)
                    ops=difflib.SequenceMatcher(None,aa,bb,autojunk=True).get_opcodes()
                    item['paragraphs']=[{'op':op,'before':''.join(aa[i:j]),'after':''.join(bb[k:l])} for op,i,j,k,l in ops if op!='equal'][:500]
            fields.append(item)
    visit(a,b)
    return {'left':left,'right':right,'changed_fields':len(fields),'fields':fields}


@router.get('/{kind}/{entity_id}/{version_id}')
def detail(kind:str,entity_id:int,version_id:int,session:Session=Depends(get_session)):
    _,r,data=revision(session,kind,entity_id,version_id)
    return {'id':r.id,'note':r.note,'source':r.source,'created_at':r.created_at,'payload':data,
            'media_saved':bool(data.get('file_path')),'indexed_notice':'索引不会自动保留旧原件；固定媒体版本后才保存原始字节' if data.get('_indexed') and not data.get('file_path') else ''}


@router.post('/{kind}/{entity_id}/{version_id}/restore')
def restore(kind:str,entity_id:int,version_id:int,body:Restore,session:Session=Depends(get_session)):
    session.connection().exec_driver_sql('BEGIN IMMEDIATE')
    session.info['version_explicit']=True
    obj,_,data=revision(session,kind,entity_id,version_id)
    _,h=generation(session,kind,entity_id);check_latest(session,h,body.expected_latest)
    if 'world_id' in data and data['world_id']!=getattr(obj,'world_id',None):
        raise HTTPException(409,'历史世界观归属不同；请显式审核跨世界迁移，不自动恢复')
    if isinstance(obj,m.OCProfile) and data.get('_oc_scope')!=v.payload(session,obj).get('_oc_scope'):
        raise HTTPException(409,'角色的世界观/作品归属已变化，请明确审核，不自动恢复旧范围')
    for key,created_at in data.get('_references',{}).items():
        column=obj.__table__.c[key]
        for fk in column.foreign_keys:
            table=fk.column.table
            current=session.connection().scalar(select(table.c.created_at).where(fk.column==data[key]))
            if not current or current.isoformat()!=created_at:
                raise HTTPException(409,'历史关联已删除或被其他记录复用，不能自动恢复')
    for tag_id,identity in data.get('_tag_identity',{}).items():
        tag=session.get(m.Tag,int(tag_id))
        if not tag or [tag.name,tag.category]!=identity:
            raise HTTPException(409,'历史标签已更名、合并或失效，请手动审核标签')
    if isinstance(obj,m.Asset):
        if data.get('file_path'):
            media_path(data['file_path'])
        elif data.get('sha256')!=obj.sha256 or data.get('_indexed')!=bool(session.get(m.ExternalAssetFile,obj.id)):
            raise HTTPException(409,'索引历史原字节未保存；不能伪装恢复旧文件，请先定位/导入对应原件')
    try:
        for c in obj.__table__.columns:
            if c.key in v.SKIP or c.key not in data:continue
            value=data[c.key]
            if value is not None and isinstance(c.type,Date):value=date.fromisoformat(value)
            setattr(obj,c.key,value)
        if '_tag_ids' in data:obj.tags=resolve_tags(session,data['_tag_ids'])
        session.flush()
        if isinstance(obj,m.Asset) and data.get('_chapters'):
            from ..chapterplans import current, source_text
            from ..chapters import fingerprint
            plan=data['_chapters']
            if plan['text_hash']==fingerprint(source_text(obj)):
                latest=current(session,obj.id)
                session.add(m.ChapterRevision(asset_id=obj.id,parent_revision=latest.id if latest else 0,text_hash=plan['text_hash'],chapters=plan['chapters'],note=body.note))
                session.flush()
        rid=v.record(session,obj,body.note,f'restore:{version_id}',force=True)
        session.commit()
    except IntegrityError:
        session.rollback();raise HTTPException(409,'历史关联已失效，未执行恢复') from None
    return {'id':rid}


def media_path(relative):
    root=get_settings().media_dir.resolve();path=(get_settings().data_dir/relative).resolve()
    if not path.is_relative_to(root) or not path.is_file():raise HTTPException(409,'历史托管媒体已丢失')
    return path


@router.get('/asset/{entity_id}/{version_id}/media')
def media(entity_id:int,version_id:int,session:Session=Depends(get_session)):
    _,_,data=revision(session,'asset',entity_id,version_id)
    if not data.get('file_path'):raise HTTPException(409,'该索引快照未保存历史原始字节')
    path=media_path(data['file_path']);mime=data.get('mime')
    if mime in ('image/png','image/jpeg','image/webp','image/gif'):
        return FileResponse(path,media_type=mime,headers={'X-Content-Type-Options':'nosniff'})
    return FileResponse(path,filename=data.get('original_name') or path.name,media_type='application/octet-stream')


@router.post('/asset/{entity_id}/pin')
def pin(entity_id:int,body:Restore,session:Session=Depends(get_session)):
    session.connection().exec_driver_sql('BEGIN IMMEDIATE')
    session.info['version_explicit']=True
    obj,h=generation(session,'asset',entity_id);check_latest(session,h,body.expected_latest)
    if not obj.file_path:
        from ..sourcefiles import external_file
        from ..ingest import ingest_stream
        path=external_file(obj)
        with path.open('rb') as stream:ingest_stream(session,stream,path.name,expected_sha=obj.sha256)
    session.flush();rid=v.record(session,obj,body.note,'pin',force=True);session.commit()
    return {'id':rid}


@router.post('/asset/{entity_id}/adopt')
def adopt(entity_id:int,body:Adopt,session:Session=Depends(get_session)):
    session.connection().exec_driver_sql('BEGIN IMMEDIATE')
    session.info['version_explicit']=True
    obj,h=generation(session,'asset',entity_id);check_latest(session,h,body.expected_latest)
    newer=v.get_entity(session,'asset',body.asset_id)
    if not newer.file_path:raise HTTPException(422,'请先上传新文件到素材库，再明确采用该托管文件')
    media_path(newer.file_path)
    for key in ('file_path','original_name','mime','size','width','height','sha256','content','meta'):
        setattr(obj,key,getattr(newer,key))
    session.flush();rid=v.record(session,obj,body.note,'adopt',force=True);session.commit()
    from ..ingest import make_thumb
    if obj.width:make_thumb(obj.id,get_settings().data_dir/obj.file_path)
    return {'id':rid}
