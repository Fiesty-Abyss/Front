"""Opt-in immutable, content-addressed snapshots in the same DB transaction."""
import hashlib
import json
import uuid
from datetime import date, datetime
from sqlalchemy import event, select, insert, update
from sqlalchemy.orm import Session
from fastapi import HTTPException
from . import models as m

ENTITIES = dict(asset=m.Asset, character=m.Character, entry=m.WorldEntry, note=m.Note,
                world=m.World, work=m.Work, relation=m.Relation,oc=m.OCProfile,study=m.OCStudy,bonus=m.BonusArchive,bonus_item=m.BonusItem)
KINDS = {v:k for k,v in ENTITIES.items()}
SKIP = {'id','created_at','updated_at'}


def get_entity(session, kind, entity_id):
    model = ENTITIES.get(kind)
    obj = session.get(model, entity_id) if model else None
    if obj is None:
        raise HTTPException(404, '资料不存在或不支持版本记录')
    return obj


def head(connection, kind, entity_id):
    t = m.VersionHead.__table__
    return connection.execute(select(t).where(t.c.kind==kind,t.c.entity_id==entity_id)).mappings().first()


def latest(connection, generation):
    t = m.EntityVersion.__table__
    return connection.execute(select(t).where(t.c.generation==generation).order_by(t.c.id.desc()).limit(1)).mappings().first()


def payload(session, obj):
    value = {c.key:getattr(obj,c.key) for c in obj.__table__.columns if c.key not in SKIP}
    if hasattr(obj,'tags'):
        value['_tag_ids'] = sorted(t.id for t in obj.tags)
        value['_tag_identity'] = {str(t.id):[t.name,t.category] for t in obj.tags}
    references={}
    for col in obj.__table__.columns:
        for fk in col.foreign_keys:
            identity=getattr(obj,col.key)
            if identity is None:continue
            table=fk.column.table
            if 'created_at' in table.c:
                created=session.connection().scalar(select(table.c.created_at).where(fk.column==identity))
                references[col.key]=created.isoformat() if created else None
    value['_references']=references
    if isinstance(obj,m.OCProfile):
        char=session.get(m.Character,obj.character_id) if obj.character_id else None
        value['_oc_scope']={'character_id':char.id if char else None,'world_id':char.world_id if char else None,'work_id':char.work_id if char else None}
    if isinstance(obj,m.OCStudy):
        from . import ocstudio
        profile=session.get(m.OCProfile,obj.profile_id) if obj.profile_id else None
        value['_study_scope']=ocstudio.scope(session,profile) if profile and ocstudio.identity(profile)==obj.profile_identity else None
    if isinstance(obj,m.BonusItem):
        archive=session.get(m.BonusArchive,obj.archive_id)
        value['_bonus_scope']=[archive.id,archive.world_id,archive.work_id] if archive else None
    if isinstance(obj,m.Asset):
        plan = session.connection().execute(select(m.ChapterRevision.__table__).where(m.ChapterRevision.asset_id==obj.id).order_by(m.ChapterRevision.id.desc()).limit(1)).mappings().first()
        value['_chapters'] = {'text_hash':plan['text_hash'],'chapters':plan['chapters']} if plan else None
        value['_indexed'] = session.connection().scalar(select(m.ExternalAssetFile.asset_id).where(m.ExternalAssetFile.asset_id==obj.id)) is not None
    return json.loads(json.dumps(value,ensure_ascii=False,default=lambda x:x.isoformat() if isinstance(x,(date,datetime)) else str(x)))


def record(session, obj, note='', source='automatic', force=False):
    conn=session.connection(); kind=KINDS[type(obj)]; h=head(conn,kind,obj.id)
    if not h or not h['present'] or not h['enabled']:
        return None
    data=payload(session,obj)
    digest=hashlib.sha256(json.dumps(data,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
    last=latest(conn,h['generation'])
    if last and last['blob_sha']==digest and not force:
        return last['id']
    if not conn.scalar(select(m.VersionBlob.sha256).where(m.VersionBlob.sha256==digest)):
        conn.execute(insert(m.VersionBlob).values(sha256=digest,payload=data))
    if isinstance(obj,m.Asset) and obj.file_path:
        # Protect originals in historical managed versions from generic asset cleanup.
        conn.exec_driver_sql('INSERT OR IGNORE INTO retained_media(path) VALUES (?)',(obj.file_path,))
    result=conn.execute(insert(m.EntityVersion).values(generation=h['generation'],blob_sha=digest,note=note,source=source,created_at=m.utcnow()))
    return result.inserted_primary_key[0]


def enable(session,obj,note='开始记录版本'):
    conn=session.connection();kind=KINDS[type(obj)];h=head(conn,kind,obj.id)
    if not h:
        conn.execute(insert(m.VersionHead).values(kind=kind,entity_id=obj.id,generation=uuid.uuid4().hex,present=True,enabled=True))
    elif not h['present'] or not h['enabled']:
        conn.execute(update(m.VersionHead).where(m.VersionHead.kind==kind,m.VersionHead.entity_id==obj.id).values(generation=uuid.uuid4().hex,present=True,enabled=True))
    return record(session,obj,note,'manual')


@event.listens_for(Session,'before_flush')
def collect(session,context,instances):
    pending=[]
    for obj in list(session.new)+list(session.dirty)+list(session.deleted):
        if type(obj) in KINDS:
            pending.append((obj,obj in session.deleted,obj in session.new))
        elif isinstance(obj,m.ChapterRevision) and obj in session.new:
            asset=session.get(m.Asset,obj.asset_id)
            if asset:pending.append((asset,False,False))
    session.info['version_pending']=pending


@event.listens_for(Session,'after_flush_postexec')
def capture(session,context):
    conn=session.connection()
    for obj,deleted,new in session.info.pop('version_pending',[]):
        kind=KINDS[type(obj)];h=head(conn,kind,obj.id)
        if not h:continue
        if deleted:
            conn.execute(update(m.VersionHead).where(m.VersionHead.kind==kind,m.VersionHead.entity_id==obj.id).values(present=False))
        elif new:
            conn.execute(update(m.VersionHead).where(m.VersionHead.kind==kind,m.VersionHead.entity_id==obj.id).values(generation=uuid.uuid4().hex,present=True,enabled=False))
        elif h['present'] and h['enabled']:
            if not session.info.get('version_explicit'):
                record(session,obj)


@event.listens_for(Session,'after_soft_rollback')
def discard(session,previous):
    session.info.pop('version_pending',None)
