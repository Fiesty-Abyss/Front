"""Column-only chat summaries. The paged path never reads a conversation tree."""
import base64
import hashlib
import json
from datetime import datetime

from fastapi import HTTPException
from sqlalchemy import and_, func, select, text

from . import models as m


def page(db, *, card_id=None, q='', limit=50, cursor=None, offset=0, legacy=False):
    signature = hashlib.sha256(json.dumps([card_id, q], ensure_ascii=False).encode()).hexdigest()
    stmt = select(m.ChatSession.id, m.ChatSession.card_id, m.ChatSession.title,
                  m.ChatSession.head_id, m.ChatSession.updated_at,
                  func.substr(m.ChatMessage.content, 1, 60).label('last')).outerjoin(
                      m.ChatMessage, and_(m.ChatMessage.id == m.ChatSession.head_id,
                                         m.ChatMessage.session_id == m.ChatSession.id))
    if card_id is not None:
        stmt = stmt.where(m.ChatSession.card_id == card_id)
    if q:
        stmt = stmt.where(func.instr(func.lower(m.ChatSession.title), func.lower(q)) > 0)
    if cursor:
        try:
            value = json.loads(base64.b64decode(cursor, altchars=b'-_', validate=True))
            assert set(value) == {'time', 'id', 'filter'} and value['filter'] == signature
            assert type(value['id']) is int and 0 < value['id'] < 2**63
            assert isinstance(value['time'], str) and len(value['time']) <= 32
            stamp = datetime.fromisoformat(value['time'])
            assert stamp.tzinfo is None
        except (ValueError, TypeError, KeyError, AssertionError):
            raise HTTPException(422, '分页游标无效或筛选已变化，请刷新首页') from None
        stmt = stmt.where((m.ChatSession.updated_at < stamp) |
                          ((m.ChatSession.updated_at == stamp) & (m.ChatSession.id < value['id'])))
    rows = db.execute(stmt.order_by(m.ChatSession.updated_at.desc(), m.ChatSession.id.desc()).offset(offset).limit(limit+1)).mappings().all()
    more, rows = len(rows) > limit, rows[:limit]
    ids = [r['id'] for r in rows]
    totals = dict(db.execute(select(m.ChatMessage.session_id, func.count()).where(
        m.ChatMessage.session_id.in_(ids)).group_by(m.ChatMessage.session_id)).all()) if ids else {}
    depths = {}
    if legacy and ids:
        # Only the legacy array API preserves the exact path-count field. Walk IDs,
        # not ORM messages/content, for this bounded page; UNION also terminates cycles.
        marks = ','.join(':'+str(i) for i in range(len(ids)))
        sql = f'''WITH RECURSIVE path(sid,id,parent) AS (
            SELECT c.id,m.id,m.parent_id FROM chat_sessions c JOIN chat_messages m
            ON m.id=c.head_id AND m.session_id=c.id WHERE c.id IN ({marks})
            UNION SELECT p.sid,m.id,m.parent_id FROM path p JOIN chat_messages m
            ON m.id=p.parent AND m.session_id=p.sid)
            SELECT sid,count(*) FROM path GROUP BY sid'''
        depths = dict(db.execute(text(sql), {str(i): value for i, value in enumerate(ids)}).all())
    items = [dict(id=r['id'], card_id=r['card_id'], title=r['title'], last=r['last'] or '',
                  total_messages=totals.get(r['id'], 0), updated_at=r['updated_at'].isoformat(),
                  **({'messages': depths.get(r['id'], 0)} if legacy else {})) for r in rows]
    next_cursor = None
    if more and rows:
        last = rows[-1]
        next_cursor = base64.urlsafe_b64encode(json.dumps({'time': last['updated_at'].isoformat(),
            'id': last['id'], 'filter': signature}).encode()).decode()
    return {'items': items, 'has_more': more, 'next_cursor': next_cursor}
