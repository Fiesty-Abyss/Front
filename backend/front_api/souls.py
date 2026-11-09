"""Local, reviewed fictional memory. No inference, background extraction or tools."""
import hashlib
import json

from fastapi import HTTPException
from sqlalchemy import Integer, event, or_, select, text
from sqlalchemy.orm import Session, noload

from . import models as m, versions as v
from .cardstudio import identity
from .search import _escape_like

TARGETS = {'character': m.Character, 'card': m.CharacterCard, 'oc': m.OCProfile,
           'voice_profile': m.VoiceProfile, 'live2d': m.Live2DProfile,
           'asset': m.Asset, 'chat': m.ChatSession, 'lore': m.LoreEntry}
KINDS = {'core', 'episode', 'relationship', 'summary', 'suggestion', 'fictional_state', 'world'}
SCOPES = {'character', 'session', 'branch'}
REVIEWS = {'pending', 'approved', 'rejected'}
FTS_NAMES = {'soul_memory_index' + suffix for suffix in ('', '_data', '_idx', '_content', '_docsize', '_config')}


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, default=identity).encode()).hexdigest()


def stamp(obj):
    return {'id': obj.id, 'identity': getattr(obj, 'uid', None) or identity(obj.created_at)}


def world_ref(session, world_id):
    if world_id is None:
        return {}
    obj = session.get(m.World, world_id)
    if not obj:
        raise HTTPException(409, '世界观已不存在，请审核身份范围')
    return stamp(obj)


def target(session, kind, target_id):
    model = TARGETS.get(kind)
    if not model:
        raise HTTPException(422, '不支持的角色关联类型')
    obj = session.scalar(select(model).options(noload('*')).where(model.id == target_id))
    if not obj:
        raise HTTPException(404, '关联资料不存在')
    return obj


def reference(session, kind, obj):
    """Capture identity and scope, never resolve old numeric IDs by name."""
    ref = stamp(obj)
    char = None
    if kind == 'character':
        char = obj
    elif kind in ('card', 'oc', 'voice_profile'):
        char = session.get(m.Character, obj.character_id) if obj.character_id else None
        if kind == 'voice_profile' and obj.oc_id:
            oc = session.get(m.OCProfile, obj.oc_id)
            ref['oc'] = stamp(oc) if oc else None
            if oc and oc.character_id:
                oc_char = session.get(m.Character, oc.character_id)
                if char and oc_char and stamp(char) != stamp(oc_char):
                    raise HTTPException(409, '声线的 OC 和百科人物关联不一致')
                char = oc_char or char
        if kind == 'voice_profile' and obj.model_id:
            model = session.get(m.VoiceModel, obj.model_id)
            ref['model'] = {**stamp(model), 'version': model.model_version} if model else None
    elif kind == 'chat':
        card = target(session, 'card', obj.card_id)
        ref['card'] = reference(session, 'card', card)
        ref['world'] = ref['card']['world']
        return ref
    wid = char.world_id if char else getattr(obj, 'world_id', None)
    if kind == 'lore':
        book = session.get(m.Lorebook, obj.lorebook_id)
        if not book or not obj.enabled:
            raise HTTPException(409, '来源世界书已删除或条目已停用，不能用于角色记忆')
        ref['book'] = stamp(book) if book else None
        wid = book.world_id if book else None
    if kind == 'card' and obj.lorebook_id:
        book = session.get(m.Lorebook, obj.lorebook_id)
        book_world = world_ref(session, book.world_id) if book else {}
        ref['lorebook'] = stamp(book) if book else None
        if book_world and char and book_world != world_ref(session, wid):
            raise HTTPException(409, '角色卡世界书与角色世界观不一致')
        wid = wid if char else (book.world_id if book else None)
    ref['character'] = stamp(char) if char else None
    ref['world'] = world_ref(session, wid)
    work_id = char.work_id if char else getattr(obj, 'work_id', None)
    work = session.get(m.Work, work_id) if work_id else None
    if work:
        ref['work'] = stamp(work)
    return ref


def get_soul(session, soul_id):
    obj = session.get(m.SoulIdentity, soul_id)
    if not obj:
        raise HTTPException(404, '角色身份不存在')
    return obj


def scope_issue(session, soul):
    if not soul.active:
        return '角色身份已停用'
    try:
        if soul.world_ref and world_ref(session, soul.world_ref['id']) != soul.world_ref:
            return '原世界观已删除或身份已变化'
    except HTTPException:
        return '原世界观已删除或身份已变化'
    return None


def link_issue(session, link):
    if not link.active:
        return '关联已停用'
    try:
        now = reference(session, link.kind, target(session, link.kind, link.target_id))
    except HTTPException:
        return '来源已删除或归属失效'
    return None if now == link.target_ref else '来源身份或世界观/角色归属已变化'


def links_for(session, soul_id):
    return session.scalars(select(m.SoulLink).where(m.SoulLink.soul_id == soul_id).order_by(m.SoulLink.id).limit(201)).all()


def valid_link(session, soul, kind, target_id):
    for link in links_for(session, soul.id):
        if link.kind == kind and link.target_id == target_id and not link_issue(session, link):
            return link
    raise HTTPException(409, '请先显式关联该资料到当前角色身份；失效关联不能自动复用')


def add_link(session, soul, kind, target_id):
    if issue := scope_issue(session, soul):
        raise HTTPException(409, issue)
    obj = target(session, kind, target_id)
    ref = reference(session, kind, obj)
    if ref['world'] != soul.world_ref and not (kind in ('asset', 'live2d', 'voice_profile') and not ref['world']):
        raise HTTPException(409, '世界观范围不同，不自动合并；独立角色也需明确保持范围')
    if kind == 'chat':
        card_link = valid_link(session, soul, 'card', obj.card_id)
        if card_link.target_ref != ref['card']:
            raise HTTPException(409, '会话角色卡关联已变化')
    own_links = links_for(session, soul.id)
    for old in own_links:
        if old.kind == kind and old.target_id == target_id and old.target_ref == ref and old.active:
            return old
    if len(own_links) >= 200:
        raise HTTPException(422, '单个角色身份最多保存 200 条显式关联，请先整理档案')
    # A canonical character/card/OC may have only one active Soul. Deleted IDs
    # with a different creation identity are separate and may be linked anew.
    if kind in ('character', 'card', 'oc', 'voice_profile'):
        others = session.scalars(select(m.SoulLink).where(m.SoulLink.kind == kind,
            m.SoulLink.target_id == target_id, m.SoulLink.active.is_(True))).all()
        if any(x.target_ref == ref and x.soul_id != soul.id for x in others):
            raise HTTPException(409, '该角色资料已关联其他身份，请先审核并停用旧关联')
        canonical = [x.target_ref.get('character') for x in own_links
                     if x.kind in ('character', 'card', 'oc') and not link_issue(session, x)]
        if ref.get('character') and any(c and c != ref['character'] for c in canonical):
            raise HTTPException(409, '百科人物身份不同，不能仅凭同名合并')
        if ref.get('character'):
            peers = session.scalars(select(m.SoulLink).where(m.SoulLink.soul_id != soul.id,
                m.SoulLink.kind.in_(('character', 'card', 'oc')), m.SoulLink.active.is_(True),
                m.SoulLink.target_ref['character']['id'].as_integer() == ref['character']['id']))
            if any(x.target_ref.get('character') == ref['character'] and x.target_ref.get('world') == ref['world']
                   and not link_issue(session, x) for x in peers):
                raise HTTPException(409, '同一百科人物已由其他身份关联，请显式审核')
    for old in own_links:
        if old.kind == kind and old.target_id == target_id and old.target_ref == ref:
            old.active = True
            return old
    row = m.SoulLink(soul_id=soul.id, kind=kind, target_id=target_id, target_ref=ref)
    session.add(row); session.flush(); v.enable(session, row, '显式关联资料')
    return row


def message_ref(session, message_id):
    obj = session.get(m.ChatMessage, message_id)
    if not obj:
        raise HTTPException(409, '来源消息不存在')
    return {**stamp(obj), 'session_id': obj.session_id, 'parent_id': obj.parent_id,
            'role': obj.role, 'sha256': digest(obj.content)}


def branch_path(session, session_id, head_id):
    """Read one ancestry only, never hydrate a session's entire message tree."""
    if head_id is None:
        return set()
    rows = session.execute(text('''WITH RECURSIVE path(id,parent_id,session_id,depth) AS (
        SELECT id,parent_id,session_id,1 FROM chat_messages WHERE id=:head
        UNION ALL SELECT m.id,m.parent_id,m.session_id,p.depth+1
        FROM chat_messages m JOIN path p ON m.id=p.parent_id WHERE p.depth<5001
        ) SELECT id,parent_id,session_id FROM path'''), {'head': head_id}).all()
    ids = {x.id for x in rows}
    if len(rows) > 5000 or len(ids) != len(rows):
        raise HTTPException(409, '消息路径异常或超过检查预算')
    if not rows or rows[-1].parent_id is not None or any(x.session_id != session_id for x in rows):
        raise HTTPException(409, '消息不属于该会话分支或父节点已缺失')
    return ids


def memory_scope(session, soul, scope, session_id=None, head_id=None):
    if scope not in SCOPES:
        raise HTTPException(422, '记忆范围不正确')
    result = {'world': soul.world_ref}
    if scope == 'character':
        if session_id is not None or head_id is not None:
            raise HTTPException(422, '角色共享记忆不能隐含会话或分支范围')
        return result
    if session_id is None:
        raise HTTPException(422, '会话/分支记忆需要选择会话')
    link = valid_link(session, soul, 'chat', session_id)
    result['session'] = link.target_ref
    chat = target(session, 'chat', session_id)
    if scope == 'branch':
        head_id = head_id if head_id is not None else chat.head_id
        if head_id is None:
            raise HTTPException(422, '空分支没有可记录的事件节点')
        branch_path(session, chat.id, head_id)
        result['branch'] = message_ref(session, head_id)
    elif head_id is not None:
        raise HTTPException(422, '请使用分支记忆保存分支节点')
    return result


def source_text(obj):
    return {k: getattr(obj, k) for k in ('name', 'title', 'description', 'personality', 'scenario',
            'system_prompt', 'summary', 'profile', 'content', 'fields', 'alias', 'gender',
            'first_mes', 'alternate_greetings', 'extensions', 'sha256', 'voice_key',
            'language', 'model_id', 'binding', 'sample_ref', 'license') if hasattr(obj, k)}


def make_source(session, soul, data, scope, scope_ref):
    kind = data.get('kind', 'manual')
    if kind == 'manual':
        return {'kind': 'manual', 'note': data.get('note', ''), 'origin': 'user'}
    if kind == 'message':
        ref = message_ref(session, data['id'])
        link = valid_link(session, soul, 'chat', ref['session_id'])
        chat = target(session, 'chat', ref['session_id'])
        anchor = scope_ref.get('branch', {}).get('id', chat.head_id)
        if ref['id'] not in branch_path(session, chat.id, anchor):
            raise HTTPException(409, '来源消息不在所选分支')
        if scope != 'character' and scope_ref['session'] != link.target_ref:
            raise HTTPException(409, '记忆与来源会话不同')
        return {'kind': 'message', 'ref': ref, 'session': link.target_ref,
                'branch': message_ref(session, anchor), 'note': data.get('note', ''),
                'excerpt': session.get(m.ChatMessage, ref['id']).content[:300],
                'range': {'start': 0, 'end': min(300, len(session.get(m.ChatMessage, ref['id']).content))}}
    link = valid_link(session, soul, kind, data['id'])
    obj = target(session, kind, data['id'])
    h = v.head(session.connection(), v.KINDS.get(type(obj), ''), obj.id)
    last = v.latest(session.connection(), h['generation']) if h and h['enabled'] and h['present'] else None
    return {'kind': kind, 'ref': link.target_ref, 'sha256': digest(source_text(obj)),
            'version_id': last['id'] if last else None, 'note': data.get('note', '')}


def source_issue(session, soul, source):
    if source['kind'] == 'manual':
        return None
    try:
        if source['kind'] == 'message':
            valid_link(session, soul, 'chat', source['session']['id'])
            if reference(session, 'chat', target(session, 'chat', source['session']['id'])) != source['session']:
                return '来源会话身份或角色范围已变化'
            if message_ref(session, source['ref']['id']) != source['ref']:
                return '来源消息已删除或修改'
            if message_ref(session, source['branch']['id']) != source['branch']:
                return '来源分支节点已删除或修改'
        else:
            obj = target(session, source['kind'], source['ref']['id'])
            valid_link(session, soul, source['kind'], obj.id)
            if reference(session, source['kind'], obj) != source['ref'] or digest(source_text(obj)) != source['sha256']:
                return '正式来源身份、归属或内容版本已变化；请重新审核'
    except HTTPException:
        return '来源或显式关联已失效'
    return None


def memory_issue(session, soul, row):
    if issue := scope_issue(session, soul):
        return issue
    if row.scope_ref.get('world') != soul.world_ref:
        return '记忆世界观范围不一致'
    if row.scope != 'character':
        ref = row.scope_ref.get('session', {})
        try:
            valid_link(session, soul, 'chat', ref['id'])
            if reference(session, 'chat', target(session, 'chat', ref['id'])) != ref:
                return '记忆会话身份或归属已变化'
            if row.scope == 'branch' and message_ref(session, row.scope_ref['branch']['id']) != row.scope_ref['branch']:
                return '记忆分支节点已删除或修改'
        except (HTTPException, KeyError):
            return '记忆会话或分支已失效'
    return source_issue(session, soul, row.source)


def columns(obj):
    return {c.key: getattr(obj, c.key) for c in obj.__table__.columns}


def memory_data(session, soul, row):
    return {**columns(row), 'diagnostic': memory_issue(session, soul, row)}


def ensure_fts(engine):
    with engine.begin() as conn:
        exists = conn.exec_driver_sql("SELECT 1 FROM sqlite_master WHERE name='soul_memory_index'").first()
        conn.exec_driver_sql("CREATE VIRTUAL TABLE IF NOT EXISTS soul_memory_index USING fts5(content, tokenize='trigram')")
        if not exists:
            conn.exec_driver_sql('INSERT INTO soul_memory_index(rowid,content) SELECT id,content FROM soul_memories')


@event.listens_for(Session, 'after_flush')
def sync_index(session, context):
    conn = session.connection()
    for obj in list(session.new) + list(session.dirty) + list(session.deleted):
        if not isinstance(obj, m.SoulMemory):
            continue
        conn.execute(text('DELETE FROM soul_memory_index WHERE rowid=:id'), {'id': obj.id})
        if obj not in session.deleted:
            conn.execute(text('INSERT INTO soul_memory_index(rowid,content) VALUES (:id,:content)'),
                         {'id': obj.id, 'content': obj.content})


def validate_restore(session, obj, data):
    immutable = ('uid', 'world_ref') if isinstance(obj, m.SoulIdentity) else (
        ('soul_id', 'kind', 'target_id', 'target_ref') if isinstance(obj, m.SoulLink) else
        ('uid', 'soul_id', 'scope', 'scope_ref', 'source', 'kind'))
    if any(data.get(k) != getattr(obj, k) for k in immutable):
        raise HTTPException(409, '历史身份、范围或来源不同，不能通过恢复重新绑定')
    if isinstance(obj, m.SoulIdentity):
        if obj.world_ref and world_ref(session, obj.world_ref['id']) != obj.world_ref:
            raise HTTPException(409, '原世界观已变化')
    elif isinstance(obj, m.SoulLink):
        # Inactive links can be restored only if their original target still exists.
        if reference(session, obj.kind, target(session, obj.kind, obj.target_id)) != obj.target_ref:
            raise HTTPException(409, '原关联已失效，不能恢复到复用的 ID')
        soul = get_soul(session, obj.soul_id)
        if data.get('active'):
            if issue := scope_issue(session, soul):
                raise HTTPException(409, issue)
            # Reuse all identity/ownership checks; restoring cannot steal a link.
            restored = add_link(session, soul, obj.kind, obj.target_id)
            if restored.id != obj.id:
                raise HTTPException(409, '已存在另一条有效关联')
    else:
        soul = get_soul(session, obj.soul_id)
        if issue := memory_issue(session, soul, obj):
            raise HTTPException(409, issue)


def retrieve(session, soul, q, session_id=None, head_id=None, limit=8, max_chars=4000):
    if issue := scope_issue(session, soul):
        raise HTTPException(409, issue)
    current_ref = None; path = set()
    if session_id is not None:
        link = valid_link(session, soul, 'chat', session_id)
        current_ref = link.target_ref
        chat = target(session, 'chat', session_id)
        path = branch_path(session, chat.id, head_id if head_id is not None else chat.head_id)
    elif head_id is not None:
        raise HTTPException(422, '分支节点需要会话范围')
    query = select(m.SoulMemory).where(m.SoulMemory.soul_id == soul.id,
        m.SoulMemory.active.is_(True), m.SoulMemory.review == 'approved',
        m.SoulMemory.conflict.is_(False), m.SoulMemory.allow_injection.is_(True))
    if current_ref is None:
        query = query.where(m.SoulMemory.scope == 'character')
    else:
        scoped = m.SoulMemory.scope_ref['session']['id'].as_integer() == session_id
        branch = m.SoulMemory.scope_ref['branch']['id'].as_integer().in_(path)
        query = query.where(or_(m.SoulMemory.scope == 'character',
            scoped & (m.SoulMemory.scope == 'session'), scoped & (m.SoulMemory.scope == 'branch') & branch))
    if q:
        # Keep the match inside SQLite: no unbounded Python ID materialization.
        if len(q) >= 3:
            ids = text('SELECT rowid FROM soul_memory_index WHERE soul_memory_index MATCH :term').bindparams(term='"'+q.replace('"','""')+'"')
        else:
            ids = text("SELECT rowid FROM soul_memory_index WHERE content LIKE :term ESCAPE '\\'").bindparams(term='%'+_escape_like(q)+'%')
        query = query.where(m.SoulMemory.pinned.is_(True) | m.SoulMemory.id.in_(ids.columns(rowid=Integer)))
    rows = session.scalars(query.order_by(m.SoulMemory.pinned.desc(), m.SoulMemory.importance.desc(),
                                         m.SoulMemory.updated_at.desc(), m.SoulMemory.id.desc()).limit(200)).all()
    items = []; used = 0; skipped = 0
    for row in rows:
        if row.scope != 'character' and row.scope_ref.get('session') != current_ref:
            continue
        if row.scope == 'branch' and row.scope_ref.get('branch', {}).get('id') not in path:
            continue
        if memory_issue(session, soul, row):
            skipped += 1; continue
        citation = f'[memory:{row.uid}]'
        rendered = citation + ' ' + row.content
        cost = len(rendered) + (1 if items else 0)
        if used + cost > max_chars or len(items) >= limit:
            skipped += 1; continue
        used += cost
        items.append({'uid': row.uid, 'id': row.id, 'citation': citation, 'content': row.content,
                      'source': row.source, 'scope': row.scope, 'revision': row.revision,
                      'reason': '用户固定' if row.pinned else '关键词匹配' if q else '重要度与更新时间',
                      'rendered': rendered})
    return {'items': items, 'chars': used, 'max_chars': max_chars, 'skipped': skipped,
            'candidate_limit': 200, 'context': '\n'.join(x['rendered'] for x in items),
            'sent_to_ai': False, 'notice': '仅本地召回预览；尚未接入聊天请求，不会自动发送给模型。'}
