"""Append-only chat model selections; never store or silently fall back credentials."""
import hashlib
import json
from urllib.parse import urlsplit

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from . import models as m
from .ai import registry


class Selection(BaseModel):
    model_config = ConfigDict(extra='forbid')
    provider_id: int = Field(ge=1, le=2**63-1)
    model: str = Field(min_length=1, max_length=200)
    temperature: float = Field(default=.8, ge=0, le=2, allow_inf_nan=False)
    max_tokens: int = Field(default=2048, ge=1, le=32768)
    context_characters: int = Field(default=32000, ge=1024, le=250000)
    expected: str = Field(pattern=r'^[a-f0-9]{64}$')


def latest(session, chat):
    return session.scalar(select(m.ChatModelSelection).where(m.ChatModelSelection.session_id == chat.id).order_by(m.ChatModelSelection.id.desc()).limit(1))


def identity(value):
    return value.replace(tzinfo=None).isoformat()


def state(session, chat):
    row = latest(session, chat)
    expected = hashlib.sha256(json.dumps({'session_id': chat.id, 'identity': identity(chat.created_at), 'selection_id': row.id if row else None}, sort_keys=True).encode()).hexdigest()
    return {'expected': expected, 'selection': output(row) if row else None}


def output(row):
    return {'id': row.id, 'snapshot': row.snapshot, 'created_at': identity(row.created_at)}


def address(value):
    try:
        parts = urlsplit(value)
        _ = parts.port
    except ValueError:
        raise HTTPException(422, '服务地址或端口无效，请先修正设置') from None
    if parts.scheme not in ('http', 'https') or not parts.hostname or parts.username or parts.password or parts.query or parts.fragment:
        raise HTTPException(422, '服务地址必须是没有内嵌凭据或查询参数的HTTP(S)地址')
    return value.rstrip('/')


def choose(session, chat, body):
    if state(session, chat)['expected'] != body.expected:
        raise HTTPException(409, '会话模型已被其他窗口切换，请重新载入并核对')
    cfg = session.get(m.AIProviderConfig, body.provider_id)
    if not cfg or not body.model.strip():
        raise HTTPException(422, '请选择现有文本服务和非空模型名称')
    endpoint = address(cfg.base_url)
    row = m.ChatModelSelection(session_id=chat.id, snapshot={
        'schema': 1, 'provider_id': cfg.id, 'provider_identity': identity(cfg.created_at),
        'provider_name': cfg.name, 'base_url': endpoint, 'model': body.model.strip(),
        'temperature': body.temperature, 'max_tokens': body.max_tokens,
        'context_characters': body.context_characters, 'timeout': min(cfg.timeout or 60, 60)})
    session.add(row)
    session.commit()
    return state(session, chat)


def resolve(session, chat, fallback):
    row = latest(session, chat)
    if row is None:
        return fallback, None
    snap = row.snapshot
    if snap.get('schema') != 1:
        raise HTTPException(409, '会话使用较新模型配置格式，请使用兼容版本')
    cfg = session.get(m.AIProviderConfig, snap['provider_id'])
    if not cfg or identity(cfg.created_at) != snap['provider_identity'] or address(cfg.base_url) != snap['base_url']:
        raise HTTPException(409, '会话绑定服务已删除、替换或改变地址；请明确重新选择，不自动切到其他服务')
    provider = registry.from_config(cfg)
    provider.model, provider.temperature, provider.max_tokens = snap['model'], snap['temperature'], snap['max_tokens']
    provider.timeout = snap['timeout']
    return provider, output(row)


def bound_context(messages, limit):
    """Preserve all instructions + latest turn; remove oldest turns, never stored text."""
    result = list(messages)
    last_turn = max((i for i, msg in enumerate(result) if msg['role'] != 'system'), default=-1)
    mandatory = sum(len(msg['content']) for i, msg in enumerate(result) if msg['role'] == 'system' or i == last_turn)
    if mandatory > limit:
        raise HTTPException(422, '角色设定、世界书与最新消息超过上下文字数预算；请缩小内容或明确增加预算，不静默截断人设')
    total = sum(len(msg['content']) for msg in result)
    keep = []
    dropped = 0
    for i, msg in enumerate(result):
        if total > limit and msg['role'] != 'system' and i != last_turn:
            total -= len(msg['content'])
            dropped += 1
        else:
            keep.append(msg)
    return keep, {'characters': total, 'limit': limit, 'dropped_turns': dropped, 'unit': 'characters-not-tokens'}
