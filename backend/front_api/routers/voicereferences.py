"""Reference annotations reuse Asset versions/media; no inference endpoints."""
from fastapi import APIRouter,Depends,Query
from sqlalchemy import select,func
from sqlalchemy.orm import Session
from .. import models as m,voicereferences as refs
from ..db import get_session

router=APIRouter(prefix='/api/voice/references',tags=['Reference audio records'])


@router.get('')
def listing(q:str=Query('',max_length=200),limit:int=Query(20,ge=1,le=100),offset:int=Query(0,ge=0,le=2147483647),session:Session=Depends(get_session)):
    conditions=[m.Asset.kind=='audio',func.json_type(m.Asset.meta,'$.voice_reference')=='object']
    if q:conditions.append(m.Asset.title.contains(q,autoescape=True))
    total=session.scalar(select(func.count()).select_from(m.Asset).where(*conditions))
    rows=session.execute(select(m.Asset.id,m.Asset.title,m.Asset.created_at,func.json_extract(m.Asset.meta,'$.voice_reference.data.kind').label('kind'))
        .where(*conditions).order_by(m.Asset.id.desc()).offset(offset).limit(limit)).mappings().all()
    return {'total':total,'items':[dict(r) for r in rows]}


@router.get('/{asset_id}')
def detail(asset_id:int,session:Session=Depends(get_session)):
    return refs.detail(session,refs.asset(session,asset_id))


@router.put('/{asset_id}')
def save(asset_id:int,body:refs.Save,session:Session=Depends(get_session)):
    session.connection().exec_driver_sql('BEGIN IMMEDIATE')
    return refs.save(session,refs.asset(session,asset_id),body)


@router.post('/{asset_id}/inspect')
def inspect(asset_id:int,body:refs.Inspect,session:Session=Depends(get_session)):
    session.connection().exec_driver_sql('BEGIN IMMEDIATE')
    return refs.inspect(session,refs.asset(session,asset_id),body).to_dict()
