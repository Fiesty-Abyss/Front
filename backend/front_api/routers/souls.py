"""Explicit local character identities and reviewable memory, independent of chat inference."""
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import Integer, func, select, text
from sqlalchemy.orm import Session

from .. import models as m, souls as s, versions as v
from ..db import get_session
from ..search import _escape_like

router = APIRouter(prefix='/api/souls', tags=['Character Soul'])


class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid')


class CreateSoul(Strict):
    name: str = Field(min_length=1, max_length=200)
    world_id: int | None = Field(default=None, ge=1)
    notes: str = Field(default='', max_length=10000)

    @field_validator('name')
    @classmethod
    def name_required(cls, value):
        if not value.strip():
            raise ValueError('名称不能为空白')
        return value.strip()


class UpdateSoul(Strict):
    expected_revision: int = Field(ge=1)
    name: str | None = Field(default=None, min_length=1, max_length=200)
    notes: str | None = Field(default=None, max_length=10000)
    active: bool | None = None


class Link(Strict):
    kind: Literal['character', 'card', 'oc', 'voice_profile', 'live2d', 'asset', 'chat', 'lore']
    target_id: int = Field(ge=1)


class ToggleLink(Strict):
    expected_revision: int = Field(ge=1)
    active: bool


class Source(Strict):
    kind: Literal['manual', 'message', 'character', 'card', 'oc', 'voice_profile', 'live2d', 'asset', 'lore'] = 'manual'
    id: int | None = Field(default=None, ge=1)
    note: str = Field(default='', max_length=1000)


class CreateMemory(Strict):
    kind: Literal['core', 'episode', 'relationship', 'summary', 'suggestion', 'fictional_state', 'world']
    content: str = Field(min_length=1, max_length=12000)
    scope: Literal['character', 'session', 'branch'] = 'character'
    session_id: int | None = Field(default=None, ge=1)
    branch_head_id: int | None = Field(default=None, ge=1)
    source: Source = Field(default_factory=Source)
    importance: int = Field(default=50, ge=0, le=100)

    @field_validator('content')
    @classmethod
    def content_required(cls, value):
        if not value.strip():
            raise ValueError('记忆内容不能为空白')
        return value.strip()


class UpdateMemory(Strict):
    expected_revision: int = Field(ge=1)
    content: str | None = Field(default=None, min_length=1, max_length=12000)
    review: Literal['pending', 'approved', 'rejected'] | None = None
    allow_injection: bool | None = None
    conflict: bool | None = None
    conflict_note: str | None = Field(default=None, max_length=1000)
    pinned: bool | None = None
    importance: int | None = Field(default=None, ge=0, le=100)
    active: bool | None = None


class Recall(Strict):
    query: str = Field(default='', max_length=200)
    session_id: int | None = Field(default=None, ge=1)
    branch_head_id: int | None = Field(default=None, ge=1)
    limit: int = Field(default=8, ge=1, le=30)
    max_chars: int = Field(default=4000, ge=64, le=12000)


def begin(session):
    # Check and write occur in the same SQLite transaction, across windows/processes.
    session.connection().exec_driver_sql('BEGIN IMMEDIATE')


def expected(obj, revision):
    if obj.revision != revision:
        raise HTTPException(409, '记录已被其他窗口修改，请刷新后再确认')


def remember(session, obj, note):
    session.flush(); v.enable(session, obj, note)


def soul_data(session, obj):
    return {**s.columns(obj), 'diagnostic': s.scope_issue(session, obj)}


@router.get('')
def listing(q: str = Query('', max_length=200), limit: int = Query(50, ge=1, le=100),
            offset: int = Query(0, ge=0), include_inactive: bool = False, session: Session = Depends(get_session)):
    query = select(m.SoulIdentity)
    if not include_inactive:
        query = query.where(m.SoulIdentity.active.is_(True))
    if q.strip():
        query = query.where(m.SoulIdentity.name.like('%'+_escape_like(q.strip())+'%', escape='\\'))
    total = session.scalar(select(func.count()).select_from(query.subquery()))
    rows = session.scalars(query.order_by(m.SoulIdentity.updated_at.desc(), m.SoulIdentity.id.desc()).offset(offset).limit(limit))
    return {'items': [soul_data(session, x) for x in rows], 'total': total}


@router.post('', status_code=201)
def create(body: CreateSoul, session: Session = Depends(get_session)):
    begin(session)
    obj = m.SoulIdentity(name=body.name, world_ref=s.world_ref(session, body.world_id), notes=body.notes)
    session.add(obj); remember(session, obj, '创建角色身份'); session.commit()
    return soul_data(session, obj)


@router.get('/{soul_id}')
def detail(soul_id: int, session: Session = Depends(get_session)):
    obj = s.get_soul(session, soul_id)
    return {**soul_data(session, obj), 'links': [{**s.columns(x), 'diagnostic': s.link_issue(session, x)}
                                             for x in s.links_for(session, obj.id)]}


@router.patch('/{soul_id}')
def update(soul_id: int, body: UpdateSoul, session: Session = Depends(get_session)):
    begin(session); obj = s.get_soul(session, soul_id); expected(obj, body.expected_revision)
    data = body.model_dump(exclude_unset=True); data.pop('expected_revision')
    if any(value is None for value in data.values()) or ('name' in data and not data['name'].strip()):
        raise HTTPException(422, '字段不能为空值或空白名称')
    for key, value in data.items():
        setattr(obj, key, value)
    obj.revision += 1; session.commit()
    return soul_data(session, obj)


@router.get('/{soul_id}/candidates')
def candidates(soul_id: int, kind: str, q: str = Query('', max_length=200),
               limit: int = Query(30, ge=1, le=50), session: Session = Depends(get_session)):
    soul = s.get_soul(session, soul_id)
    model = s.TARGETS.get(kind)
    if not model:
        raise HTTPException(422, '不支持的关联类型')
    title = next(getattr(model, key) for key in ('name', 'title', 'original_name') if hasattr(model, key))
    query = select(model.id, title.label('title'))
    if q.strip():
        query = query.where(title.like('%'+_escape_like(q.strip())+'%', escape='\\'))
    rows = session.execute(query.order_by(model.id.desc()).limit(limit))
    return {'items': [{'id': x.id, 'title': x.title or f'#{x.id}'} for x in rows],
            'notice': '仅候选；提交关联时再次校验身份与世界观范围。'}


@router.get('/{soul_id}/source-messages')
def source_messages(soul_id: int, session_id: int = Query(ge=1), head_id: int | None = Query(default=None, ge=1),
                    limit: int = Query(30, ge=1, le=50), session: Session = Depends(get_session)):
    soul = s.get_soul(session, soul_id); s.valid_link(session, soul, 'chat', session_id)
    chat = s.target(session, 'chat', session_id)
    head_id = head_id if head_id is not None else chat.head_id
    ids = s.branch_path(session, chat.id, head_id)
    rows = session.execute(select(m.ChatMessage.id, m.ChatMessage.role,
        func.substr(m.ChatMessage.content, 1, 300).label('excerpt')).where(m.ChatMessage.id.in_(ids))
        .order_by(m.ChatMessage.id.desc()).limit(limit))
    return {'head_id': head_id, 'items': [dict(x._mapping) for x in rows],
            'notice': '仅所选分支的原文片段；来源位置和完整内容指纹随记忆保存。'}


@router.post('/{soul_id}/links', status_code=201)
def link(soul_id: int, body: Link, session: Session = Depends(get_session)):
    begin(session); soul = s.get_soul(session, soul_id)
    row = s.add_link(session, soul, body.kind, body.target_id); session.commit()
    return {**s.columns(row), 'diagnostic': s.link_issue(session, row)}


@router.patch('/{soul_id}/links/{link_id}')
def toggle(soul_id: int, link_id: int, body: ToggleLink, session: Session = Depends(get_session)):
    begin(session); soul = s.get_soul(session, soul_id)
    row = session.get(m.SoulLink, link_id)
    if not row or row.soul_id != soul.id:
        raise HTTPException(404, '关联不存在')
    expected(row, body.expected_revision)
    if body.active:
        s.validate_restore(session, row, s.columns(row))
        if issue := s.scope_issue(session, soul):
            raise HTTPException(409, issue)
        # Use the same canonical conflict checks as creating a link.
        duplicate = s.add_link(session, soul, row.kind, row.target_id)
        if duplicate.id != row.id:
            raise HTTPException(409, '请使用已存在的有效关联')
    row.active = body.active; row.revision += 1; session.commit()
    return {**s.columns(row), 'diagnostic': s.link_issue(session, row)}


@router.get('/{soul_id}/memories')
def memories(soul_id: int, q: str = Query('', max_length=200), kind: str | None = None,
             review: str | None = None, include_inactive: bool = False,
             limit: int = Query(30, ge=1, le=100), offset: int = Query(0, ge=0), session: Session = Depends(get_session)):
    soul = s.get_soul(session, soul_id)
    query = select(m.SoulMemory).where(m.SoulMemory.soul_id == soul.id)
    if not include_inactive:
        query = query.where(m.SoulMemory.active.is_(True))
    if kind:
        if kind not in s.KINDS:
            raise HTTPException(422, '记忆类型不正确')
        query = query.where(m.SoulMemory.kind == kind)
    if review:
        if review not in s.REVIEWS:
            raise HTTPException(422, '审核状态不正确')
        query = query.where(m.SoulMemory.review == review)
    if q.strip():
        term = q.strip()
        if len(term) >= 3:
            ids = text('SELECT rowid FROM soul_memory_index WHERE soul_memory_index MATCH :term').bindparams(term='"'+term.replace('"','""')+'"')
        else:
            ids = text("SELECT rowid FROM soul_memory_index WHERE content LIKE :term ESCAPE '\\'").bindparams(term='%'+_escape_like(term)+'%')
        query = query.where(m.SoulMemory.id.in_(ids.columns(rowid=Integer)))
    total = session.scalar(select(func.count()).select_from(query.subquery()))
    rows = session.scalars(query.order_by(m.SoulMemory.id.desc()).offset(offset).limit(limit))
    return {'items': [s.memory_data(session, soul, x) for x in rows], 'total': total}


@router.post('/{soul_id}/memories', status_code=201)
def create_memory(soul_id: int, body: CreateMemory, session: Session = Depends(get_session)):
    begin(session); soul = s.get_soul(session, soul_id)
    if issue := s.scope_issue(session, soul):
        raise HTTPException(409, issue)
    if body.source.kind != 'manual' and body.source.id is None:
        raise HTTPException(422, '来源需要明确的资料 ID')
    scope = s.memory_scope(session, soul, body.scope, body.session_id, body.branch_head_id)
    source = s.make_source(session, soul, body.source.model_dump(), body.scope, scope)
    if body.source.kind == 'message' and body.kind in ('episode', 'summary', 'fictional_state') and body.scope != 'branch':
        raise HTTPException(422, '聊天情节、摘要和虚构状态必须保留分支范围；共享事实请另行人工记录')
    if body.kind == 'core' and body.source.kind not in ('character', 'card', 'oc'):
        raise HTTPException(422, '核心设定需要已关联的正式角色来源')
    if body.kind == 'world' and body.source.kind != 'lore':
        raise HTTPException(422, '世界观记忆需要显式关联并允许使用的世界书条目')
    row = m.SoulMemory(soul_id=soul.id, kind=body.kind, content=body.content, scope=body.scope,
                       scope_ref=scope, source=source, importance=body.importance)
    session.add(row); remember(session, row, '创建待审核记忆'); session.commit()
    return s.memory_data(session, soul, row)


@router.get('/{soul_id}/memories/{memory_id}')
def memory_detail(soul_id: int, memory_id: int, session: Session = Depends(get_session)):
    soul = s.get_soul(session, soul_id)
    row = session.get(m.SoulMemory, memory_id)
    if not row or row.soul_id != soul.id:
        raise HTTPException(404, '记忆不存在')
    return s.memory_data(session, soul, row)


@router.patch('/{soul_id}/memories/{memory_id}')
def update_memory(soul_id: int, memory_id: int, body: UpdateMemory, session: Session = Depends(get_session)):
    begin(session); soul = s.get_soul(session, soul_id)
    row = session.get(m.SoulMemory, memory_id)
    if not row or row.soul_id != soul.id:
        raise HTTPException(404, '记忆不存在')
    expected(row, body.expected_revision)
    data = body.model_dump(exclude_unset=True); data.pop('expected_revision')
    if any(value is None for value in data.values()) or ('content' in data and not data['content'].strip()):
        raise HTTPException(422, '记忆字段不能为空值或空白内容')
    if data.get('review') == 'approved' or data.get('allow_injection'):
        if issue := s.memory_issue(session, soul, row):
            raise HTTPException(409, issue)
    # Text edits invalidate the old approval; approval is a separate, visible action.
    if 'content' in data and data['content'] != row.content:
        data.update(review='pending', allow_injection=False)
    for key, value in data.items():
        setattr(row, key, value)
    if row.review != 'approved' or row.conflict or not row.active:
        row.allow_injection = False
    row.revision += 1; session.commit()
    return s.memory_data(session, soul, row)


@router.post('/{soul_id}/recall')
def recall(soul_id: int, body: Recall, session: Session = Depends(get_session)):
    return s.retrieve(session, s.get_soul(session, soul_id), body.query.strip(), body.session_id,
                      body.branch_head_id, body.limit, body.max_chars)


@router.get('/{soul_id}/export')
def export(soul_id: int, after_id: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=100),
           session: Session = Depends(get_session)):
    soul = s.get_soul(session, soul_id)
    rows = session.scalars(select(m.SoulMemory).where(m.SoulMemory.soul_id == soul.id,
        m.SoulMemory.id > after_id).order_by(m.SoulMemory.id).limit(limit+1)).all()
    items = rows[:limit]
    return {'schema': 1, 'soul': soul_data(session, soul), 'links': [s.columns(x) for x in s.links_for(session, soul.id)],
            'memories': [s.memory_data(session, soul, x) for x in items],
            'next_after_id': items[-1].id if len(rows) > limit else None,
            'notice': '当前记录的分页导出；完整历史和恢复请使用完整备份。停用不等于清除历史或既有备份。'}
