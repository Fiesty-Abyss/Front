"""Bounded collection reads and optimistic writes; existing shared tables only."""
from __future__ import annotations

import base64
import hashlib
import json
from datetime import date

from fastapi import HTTPException
from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.orm import raiseload

from . import models as m
from .crud import resolve_tags, tag_descendants
from .search import matching_ids

LINK = m.collection_assets


def collection(session, collection_id):
    row = session.scalar(select(m.Collection).where(m.Collection.id == collection_id).options(raiseload(m.Collection.assets)))
    if row is None:
        raise HTTPException(404, '收藏集不存在')
    return row


def lock(session, collection_id, expected=None):
    # The first statement is a write: SQLite serializes competing writers before
    # any membership read. CAS runs in SQLite, not against an ORM cached revision.
    stmt = update(m.Collection).where(m.Collection.id == collection_id)
    if expected is not None:
        stmt = stmt.where(m.Collection.members_revision == expected)
    result = session.execute(stmt.values(members_revision=m.Collection.members_revision).execution_options(synchronize_session=False))
    if result.rowcount != 1:
        if session.scalar(select(m.Collection.id).where(m.Collection.id == collection_id)) is None:
            raise HTTPException(404, '收藏集不存在')
        raise HTTPException(409, '收藏集已变化，请刷新后重试；未写入修改')


def summaries_query():
    fields = ('id', 'name', 'description', 'work_id', 'cover_asset_id', 'position', 'created_at', 'updated_at')
    count = select(func.count()).select_from(LINK).where(LINK.c.collection_id == m.Collection.id).correlate(m.Collection).scalar_subquery()
    first = select(LINK.c.asset_id).where(LINK.c.collection_id == m.Collection.id).order_by(LINK.c.position, LINK.c.asset_id).limit(1).correlate(m.Collection).scalar_subquery()
    return select(*(getattr(m.Collection, f) for f in fields), m.Collection.members_revision,
                  count.label('member_count'), func.coalesce(m.Collection.cover_asset_id, first).label('effective_cover_id'))


def summary(session, row):
    return dict(session.execute(summaries_query().where(m.Collection.id == row.id)).mappings().one())


def filtered(session, collection_id, filters):
    stmt = select(LINK.c.asset_id).where(LINK.c.collection_id == collection_id)
    # Avoid joining every asset just to count an unfiltered collection.
    if any(v is not None and v != '' and v != [] for v in filters.values()):
        stmt = stmt.join(m.Asset, LINK.c.asset_id == m.Asset.id)
    if filters.get('q'):
        stmt = stmt.where(m.Asset.id.in_(matching_ids(session, 'asset', filters['q'])))
    if filters.get('kind'):
        stmt = stmt.where(m.Asset.kind == filters['kind'])
    for tag in filters.get('tag', []):
        stmt = stmt.where(m.Asset.tags.any(m.Tag.id.in_(tag_descendants(session, tag))))
    for name, col in (('min_stars', m.Asset.stars), ('min_preference', m.Asset.preference)):
        if filters.get(name) is not None:
            stmt = stmt.where(col >= filters[name])
    if filters.get('date_from'):
        stmt = stmt.where(m.Asset.work_date >= date.fromisoformat(str(filters['date_from'])))
    if filters.get('date_to'):
        stmt = stmt.where(m.Asset.work_date <= date.fromisoformat(str(filters['date_to'])))
    return stmt


def _scope(collection_id, filters):
    return hashlib.sha256(json.dumps([collection_id, filters], sort_keys=True, default=str).encode()).hexdigest()[:24]


def page(session, collection_id, filters, limit, cursor):
    # Explicit read transaction pins revision/count/page to one SQLite snapshot.
    # pysqlite legacy mode otherwise doesn't BEGIN on SELECT.
    conn = session.connection()
    if not conn.connection.driver_connection.in_transaction:
        conn.exec_driver_sql('BEGIN')
    row = collection(session, collection_id)
    revision = row.members_revision
    scope = _scope(collection_id, filters)
    stmt = filtered(session, collection_id, filters)
    total = session.scalar(select(func.count()).select_from(stmt.subquery()))
    if cursor:
        try:
            value = json.loads(base64.urlsafe_b64decode(cursor.encode() + b'=' * (-len(cursor) % 4)))
            if (not isinstance(value, list) or len(value) != 4 or value[0] != scope
                    or any(type(x) is not int for x in value[1:])):
                raise ValueError()
        except (ValueError, TypeError, UnicodeError):
            raise HTTPException(422, '分页游标无效或筛选条件已改变') from None
        if value[1] != revision:
            raise HTTPException(409, '收藏集成员或排序已变化，请从第一页重新加载')
        pos, asset_id = value[2:]
        if session.scalar(select(LINK.c.asset_id).where(LINK.c.collection_id == collection_id, LINK.c.position == pos, LINK.c.asset_id == asset_id)) is None:
            raise HTTPException(422, '分页位置已失效')
        stmt = stmt.where(or_(LINK.c.position > pos, and_(LINK.c.position == pos, LINK.c.asset_id > asset_id)))
    keys = session.execute(stmt.with_only_columns(LINK.c.position, LINK.c.asset_id).order_by(LINK.c.position, LINK.c.asset_id).limit(limit + 1)).all()
    more = len(keys) > limit
    keys = keys[:limit]
    # Deliberately do not decode content, arbitrary metadata or original paths.
    columns = ('id', 'title', 'kind', 'width', 'height', 'mime', 'size', 'work_date', 'favorite', 'stars', 'preference')
    ids = [k[1] for k in keys]
    rows = session.execute(select(*(getattr(m.Asset, k) for k in columns), func.json_extract(m.Asset.meta, '$.file.thumb').label('thumb')).where(m.Asset.id.in_(ids))).mappings().all() if ids else []
    mapped = {r['id']: r for r in rows}
    items = [{**{k: mapped[aid][k] for k in columns}, 'position': pos,
              'meta': {'file': {'thumb': bool(mapped[aid]['thumb'])}}} for pos, aid in keys]
    next_cursor = base64.urlsafe_b64encode(json.dumps([scope, revision, *keys[-1]]).encode()).decode().rstrip('=') if more else None
    return {'items': items, 'total': total, 'next_cursor': next_cursor, 'members_revision': revision}


def append(session, collection_id, asset_ids):
    ids = list(dict.fromkeys(asset_ids))
    found = set(session.scalars(select(m.Asset.id).where(m.Asset.id.in_(ids))))
    if found != set(ids):
        raise HTTPException(422, '存在已失效素材；整批未加入')
    present = set(session.scalars(select(LINK.c.asset_id).where(LINK.c.collection_id == collection_id, LINK.c.asset_id.in_(ids))))
    pos = session.scalar(select(func.coalesce(func.max(LINK.c.position), -1)).where(LINK.c.collection_id == collection_id)) + 1
    values = [{'collection_id': collection_id, 'asset_id': aid, 'position': pos + i} for i, aid in enumerate(a for a in ids if a not in present)]
    if values:
        session.execute(LINK.insert(), values)


def reorder_window(session, collection_id, first_asset_id, asset_ids):
    if len(asset_ids) != len(set(asset_ids)):
        raise HTTPException(422, '排序不能包含重复项')
    first = session.execute(select(LINK.c.position, LINK.c.asset_id).where(LINK.c.collection_id == collection_id, LINK.c.asset_id == first_asset_id)).first()
    if first is None:
        raise HTTPException(409, '排序起点已失效')
    rows = session.execute(select(LINK.c.position, LINK.c.asset_id).where(LINK.c.collection_id == collection_id,
        or_(LINK.c.position > first[0], and_(LINK.c.position == first[0], LINK.c.asset_id >= first[1])))
        .order_by(LINK.c.position, LINK.c.asset_id).limit(len(asset_ids))).all()
    if {r[1] for r in rows} != set(asset_ids):
        raise HTTPException(409, '只能重排完整连续窗口；筛选结果不可拖动排序')
    positions = [r[0] for r in rows]
    peers = session.scalar(select(func.count()).select_from(LINK).where(LINK.c.collection_id == collection_id, LINK.c.position.in_(positions)))
    if len(set(positions)) != len(positions) or peers != len(positions):
        raise HTTPException(409, '旧收藏含重复位置；分页排序已安全拒绝，请先用完整排序整理')
    for pos, aid in zip(positions, asset_ids):
        session.execute(LINK.update().where(LINK.c.collection_id == collection_id, LINK.c.asset_id == aid).values(position=pos))


def batch(session, collection_id, body):
    ids = set(body.asset_ids)
    present = set(session.scalars(select(LINK.c.asset_id).where(LINK.c.collection_id == collection_id, LINK.c.asset_id.in_(ids))))
    if ids != present:
        raise HTTPException(409, '选择包含已移出的素材；整批未修改')
    if body.remove:
        session.execute(LINK.delete().where(LINK.c.collection_id == collection_id, LINK.c.asset_id.in_(ids)))
        session.execute(update(m.Collection).where(m.Collection.id == collection_id, m.Collection.cover_asset_id.in_(ids)).values(cover_asset_id=None))
        return
    tags = resolve_tags(session, body.add_tag_ids)
    # ORM events preserve opt-in version history and FTS hooks. Bounded to 1000.
    ordered = sorted(ids)
    for start in range(0, len(ordered), 25):
        rows = session.scalars(select(m.Asset).where(m.Asset.id.in_(ordered[start:start + 25]))).all()
        for asset in rows:
            for field in ('favorite', 'stars', 'preference'):
                value = getattr(body, field)
                if value is not None:
                    setattr(asset, field, value)
            if tags:
                current = {t.id for t in asset.tags}
                asset.tags = [*asset.tags, *(t for t in tags if t.id not in current)]
        session.flush()  # existing immutable version and FTS hooks, same transaction
        for asset in rows:
            session.expunge(asset)
    session.execute(update(m.Collection).where(m.Collection.id == collection_id).values(members_revision=m.Collection.members_revision + 1))
