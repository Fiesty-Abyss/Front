"""AI 接口：状态、角色扮演对话（流式输出、重新生成、编辑、分支、世界书注入）、世界观关系识别。"""

from __future__ import annotations

import json
import threading
import uuid
from collections.abc import Iterator
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models as m
from .. import schemas as s
from ..ai import AIProvider, AIUnavailable
from ..ai import lore as lore_mod
from ..ai import registry
from ..ai.prompts import build_relation_messages, build_roleplay_messages, parse_relations
from ..crud import get_or_404
from ..db import get_session, new_session

router = APIRouter(prefix="/api/ai", tags=["AI 接口"])

# 正在进行的流式生成：token -> 停止标记
_running: dict[str, threading.Event] = {}


def provider_dep(session: Session = Depends(get_session)) -> AIProvider:
    return registry.chat_provider(session)


@router.get("/status")
def status(session: Session = Depends(get_session), provider: AIProvider = Depends(provider_dep)) -> dict[str, Any]:
    st = registry.get_all(session)
    return {
        "provider": provider.name,
        "available": provider.available(),
        "model": getattr(provider, "model", None),
        "base_url": getattr(provider, "base_url", None),
        "label": getattr(provider, "label", None),
        "source": registry.chat_source(session),
        "embedding_backend": st["embedding_backend"],
        "tagger_backend": st["tagger_backend"],
        "user_name": st["user_name"],
    }


# ---------- 消息树 ----------
def _index(chat: m.ChatSession) -> tuple[dict[int, m.ChatMessage], dict[int | None, list[m.ChatMessage]]]:
    by_id = {msg.id: msg for msg in chat.messages}
    children: dict[int | None, list[m.ChatMessage]] = {}
    for msg in chat.messages:
        parent = msg.parent_id if msg.parent_id in by_id else None
        children.setdefault(parent, []).append(msg)
    for lst in children.values():
        lst.sort(key=lambda x: x.id)
    return by_id, children


def path_to(chat: m.ChatSession, mid: int | None) -> list[m.ChatMessage]:
    by_id, _ = _index(chat)
    out: list[m.ChatMessage] = []
    seen: set[int] = set()
    cur = by_id.get(mid) if mid is not None else None
    while cur is not None and cur.id not in seen:
        seen.add(cur.id)
        out.append(cur)
        cur = by_id.get(cur.parent_id) if cur.parent_id is not None else None
    return list(reversed(out))


def deepest_leaf(chat: m.ChatSession, mid: int) -> int:
    """沿着“最新的子消息”一直走到底：切换分支时显示该分支最近一次的对话。"""
    _, children = _index(chat)
    cur = mid
    for _ in range(10000):
        kids = children.get(cur)
        if not kids:
            return cur
        cur = kids[-1].id
    return cur


def serialize(chat: m.ChatSession) -> dict[str, Any]:
    _, children = _index(chat)
    head = chat.head_id
    if head is None and chat.messages:
        head = deepest_leaf(chat, children[None][-1].id) if children.get(None) else chat.messages[-1].id
    path = path_to(chat, head)
    messages = []
    for msg in path:
        parent = msg.parent_id if any(x.id == msg.parent_id for x in chat.messages) else None
        messages.append({
            "id": msg.id, "role": msg.role, "content": msg.content, "created_at": msg.created_at,
            "parent_id": msg.parent_id, "meta": msg.meta or {}, "sibling_ids": [x.id for x in children.get(parent, [])],
        })
    return {
        "id": chat.id, "card_id": chat.card_id, "title": chat.title, "user_name": chat.user_name, "head_id": head,
        "lorebook_ids": list(chat.lorebook_ids or []), "total_messages": len(chat.messages), "messages": messages,
        "created_at": chat.created_at, "updated_at": chat.updated_at,
    }


def _fill(text: str, card: m.CharacterCard, user: str) -> str:
    return (text or "").replace("{{user}}", user).replace("{{char}}", card.name)


def books_for(session: Session, chat: m.ChatSession, card: m.CharacterCard) -> list[m.Lorebook]:
    """对话使用的世界书：角色卡自带的 + 角色所在世界观的 + 会话里额外选择的。"""
    ids: list[int] = []
    if card.lorebook_id:
        ids.append(card.lorebook_id)
    if card.character_id:
        char = session.get(m.Character, card.character_id)
        if char and char.world_id:
            ids += list(session.scalars(select(m.Lorebook.id).where(m.Lorebook.world_id == char.world_id)).all())
    ids += [int(i) for i in chat.lorebook_ids or []]
    books = []
    for i in dict.fromkeys(ids):
        book = session.get(m.Lorebook, i)
        if book is not None:
            books.append(book)
    return books


def build_context(session: Session, chat: m.ChatSession, card: m.CharacterCard, history: list[m.ChatMessage]) -> tuple[list[dict], dict]:
    turns = [{"role": msg.role, "content": msg.content} for msg in history if msg.role in ("user", "assistant", "system")]
    activated = lore_mod.activate(books_for(session, chat, card), [t["content"] for t in turns])
    messages = build_roleplay_messages(card, turns, chat.user_name, lore=lore_mod.split_positions(activated["active"]))
    return messages, activated


# ---------- 会话 ----------
@router.get("/sessions")
def list_sessions(card_id: int | None = None, session: Session = Depends(get_session)) -> list[dict[str, Any]]:
    stmt = select(m.ChatSession).order_by(m.ChatSession.updated_at.desc())
    if card_id is not None:
        stmt = stmt.where(m.ChatSession.card_id == card_id)
    out = []
    for c in session.scalars(stmt).all():
        path = path_to(c, c.head_id)
        last = path[-1].content[:60] if path else ""
        out.append({"id": c.id, "card_id": c.card_id, "title": c.title, "messages": len(path), "total_messages": len(c.messages),
                    "last": last, "updated_at": c.updated_at.isoformat()})
    return out


@router.post("/sessions", response_model=s.ChatSessionRead, status_code=201)
def create_session(payload: s.ChatSessionCreate, session: Session = Depends(get_session)) -> Any:
    card = get_or_404(session, m.CharacterCard, payload.card_id)
    chat = m.ChatSession(card_id=card.id, title=payload.title, user_name=payload.user_name)
    session.add(chat)
    session.flush()
    greetings = [g for g in [card.first_mes, *(card.alternate_greetings or [])] if g]
    first = None
    for i, g in enumerate(greetings):  # 开场白与备选开场白互为兄弟分支，可左右切换
        msg = m.ChatMessage(session_id=chat.id, role="assistant", content=_fill(g, card, payload.user_name),
                            meta={"greeting": i})
        session.add(msg)
        session.flush()
        first = first or msg
    chat.head_id = first.id if first else None
    session.commit()
    session.refresh(chat)
    return serialize(chat)


@router.get("/sessions/{session_id}", response_model=s.ChatSessionRead)
def get_chat(session_id: int, session: Session = Depends(get_session)) -> Any:
    return serialize(get_or_404(session, m.ChatSession, session_id))


@router.patch("/sessions/{session_id}", response_model=s.ChatSessionRead)
def update_chat(session_id: int, payload: s.ChatSessionUpdate, session: Session = Depends(get_session)) -> Any:
    chat = get_or_404(session, m.ChatSession, session_id)
    data = payload.model_dump(exclude_unset=True)
    if "lorebook_ids" in data:
        for i in data["lorebook_ids"] or []:
            get_or_404(session, m.Lorebook, i)
        data["lorebook_ids"] = list(dict.fromkeys(data["lorebook_ids"] or []))
    for k, v in data.items():
        setattr(chat, k, v)
    session.commit()
    session.refresh(chat)
    return serialize(chat)


@router.delete("/sessions/{session_id}", status_code=204)
def delete_chat(session_id: int, session: Session = Depends(get_session)) -> None:
    session.delete(get_or_404(session, m.ChatSession, session_id))
    session.commit()


@router.post("/sessions/{session_id}/select", response_model=s.ChatSessionRead)
def select_branch(session_id: int, payload: s.ChatSelect, session: Session = Depends(get_session)) -> Any:
    chat = get_or_404(session, m.ChatSession, session_id)
    if not any(x.id == payload.message_id for x in chat.messages):
        raise HTTPException(404, "消息不在这个对话里")
    chat.head_id = deepest_leaf(chat, payload.message_id)
    session.commit()
    session.refresh(chat)
    return serialize(chat)


@router.get("/sessions/{session_id}/context")
def chat_context(session_id: int, session: Session = Depends(get_session)) -> dict[str, Any]:
    """查看下一次发送给模型的完整上下文与激活的世界书条目（调试用）。"""
    chat = get_or_404(session, m.ChatSession, session_id)
    card = get_or_404(session, m.CharacterCard, chat.card_id)
    messages, activated = build_context(session, chat, card, path_to(chat, chat.head_id))
    books = books_for(session, chat, card)
    return {"messages": messages, "lore": activated, "lorebooks": [{"id": b.id, "name": b.name, "world_id": b.world_id} for b in books]}


@router.patch("/messages/{message_id}", response_model=s.ChatSessionRead)
def edit_message(message_id: int, payload: s.ChatMessageUpdate, session: Session = Depends(get_session)) -> Any:
    """直接修改消息内容（不产生分支）。想保留原文另开分支，请用 generate 的 edit_id。"""
    msg = get_or_404(session, m.ChatMessage, message_id)
    msg.content = payload.content
    msg.meta = dict(msg.meta or {}, edited=True)
    session.commit()
    chat = get_or_404(session, m.ChatSession, msg.session_id)
    session.refresh(chat)
    return serialize(chat)


@router.delete("/messages/{message_id}", response_model=s.ChatSessionRead)
def delete_message(message_id: int, session: Session = Depends(get_session)) -> Any:
    """删除一条消息及其后的全部分支。"""
    msg = get_or_404(session, m.ChatMessage, message_id)
    chat = get_or_404(session, m.ChatSession, msg.session_id)
    _, children = _index(chat)
    doomed, stack = set(), [msg.id]
    while stack:
        cur = stack.pop()
        doomed.add(cur)
        stack += [c.id for c in children.get(cur, [])]
    parent = msg.parent_id
    siblings = [c.id for c in children.get(parent if parent in {x.id for x in chat.messages} else None, []) if c.id not in doomed]
    for x in list(chat.messages):
        if x.id in doomed:
            chat.messages.remove(x)
    session.flush()
    if chat.head_id in doomed or chat.head_id is None:
        if siblings:
            chat.head_id = deepest_leaf(chat, siblings[-1])
        else:
            chat.head_id = parent if parent and parent not in doomed else None
    session.commit()
    session.refresh(chat)
    return serialize(chat)


def _prepare(session: Session, chat: m.ChatSession, payload: s.ChatGenerate) -> tuple[int | None, m.ChatMessage | None]:
    """处理发送 / 编辑 / 重新生成，返回 (AI 回复要接在哪条消息后面, 新建的用户消息)。"""
    ids = {x.id for x in chat.messages}
    if payload.regenerate_id is not None:
        if payload.regenerate_id not in ids:
            raise HTTPException(404, "消息不在这个对话里")
        target = session.get(m.ChatMessage, payload.regenerate_id)
        if target.role != "assistant":
            raise HTTPException(422, "只能重新生成 AI 的回复")
        return target.parent_id, None
    if payload.edit_id is not None:
        if payload.edit_id not in ids:
            raise HTTPException(404, "消息不在这个对话里")
        target = session.get(m.ChatMessage, payload.edit_id)
        if target.role != "user" or not (payload.content or "").strip():
            raise HTTPException(422, "编辑另开分支只适用于用户消息，并且需要新内容")
        parent = target.parent_id
    elif payload.content is not None:
        if not payload.content.strip():
            raise HTTPException(422, "消息不能为空")
        parent = payload.parent_id if payload.parent_id is not None else chat.head_id
        if parent is not None and parent not in ids:
            raise HTTPException(404, "parent_id 不在这个对话里")
    else:
        if chat.head_id is None:
            raise HTTPException(422, "对话还是空的，请先发送一条消息")
        return chat.head_id, None
    user_msg = m.ChatMessage(session_id=chat.id, role="user", content=payload.content, parent_id=parent)
    session.add(user_msg)
    session.flush()
    chat.head_id = user_msg.id
    session.commit()
    session.refresh(chat)
    return user_msg.id, user_msg


def _save_reply(session_id: int, parent_id: int | None, content: str, meta: dict[str, Any]) -> dict[str, Any]:
    with new_session() as db:
        chat = db.get(m.ChatSession, session_id)
        msg = m.ChatMessage(session_id=session_id, role="assistant", content=content, parent_id=parent_id, meta=meta)
        db.add(msg)
        db.flush()
        chat.head_id = msg.id
        chat.updated_at = msg.created_at
        db.commit()
        db.refresh(chat)
        return {"message_id": msg.id, "session": json.loads(s.ChatSessionRead.model_validate(serialize(chat)).model_dump_json())}


def _sse(event: str, data: Any) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False, default=str)}\n\n"


@router.post("/sessions/{session_id}/generate")
def generate(
    session_id: int,
    payload: s.ChatGenerate,
    session: Session = Depends(get_session),
    provider: AIProvider = Depends(provider_dep),
) -> Any:
    """流式（Server-Sent Events）生成回复。事件：start（含 token，可用于停止）/ delta / done / error。"""
    chat = get_or_404(session, m.ChatSession, session_id)
    card = get_or_404(session, m.CharacterCard, chat.card_id)
    if not provider.available():
        try:
            provider.chat([])
        except AIUnavailable as exc:
            raise HTTPException(503, str(exc)) from exc
    parent_id, user_msg = _prepare(session, chat, payload)
    messages, activated = build_context(session, chat, card, path_to(chat, parent_id))
    lore_meta = [{"entry_id": r["entry_id"], "lorebook_id": r["lorebook_id"], "title": r["title"], "reason": r["reason"]}
                 for r in activated["active"]]
    meta: dict[str, Any] = {"model": getattr(provider, "model", None), "provider": getattr(provider, "label", provider.name),
                            "lore": lore_meta}
    if payload.regenerate_id is not None:
        meta["regenerated_from"] = payload.regenerate_id

    if not payload.stream:
        try:
            reply = provider.chat(messages)
        except AIUnavailable as exc:
            raise HTTPException(503, str(exc)) from exc
        return _save_reply(chat.id, parent_id, reply, meta)["session"]

    token = uuid.uuid4().hex[:12]
    stop = threading.Event()
    _running[token] = stop
    stream_fn = getattr(provider, "stream", None)

    def events() -> Iterator[str]:
        parts: list[str] = []
        saved = False
        try:
            yield _sse("start", {"token": token, "user_message_id": user_msg.id if user_msg else None, "parent_id": parent_id,
                                 "lore": lore_meta})
            try:
                chunks = stream_fn(messages) if stream_fn else iter([provider.chat(messages)])
                for piece in chunks:
                    if stop.is_set():
                        meta["interrupted"] = True
                        break
                    parts.append(piece)
                    yield _sse("delta", {"text": piece})
            except AIUnavailable as exc:
                if parts:
                    meta["error"] = str(exc)
                    res = _save_reply(chat.id, parent_id, "".join(parts), meta)
                    saved = True
                    yield _sse("error", {"detail": str(exc), **res})
                else:
                    saved = True
                    yield _sse("error", {"detail": str(exc)})
                return
            res = _save_reply(chat.id, parent_id, "".join(parts), meta)
            saved = True
            yield _sse("done", res)
        finally:
            _running.pop(token, None)
            if not saved and parts:  # 客户端中途断开：保存已经生成的部分
                meta["interrupted"] = True
                _save_reply(chat.id, parent_id, "".join(parts), meta)

    return StreamingResponse(events(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.post("/generations/{token}/stop", status_code=204)
def stop_generation(token: str) -> None:
    ev = _running.get(token)
    if ev is None:
        raise HTTPException(404, "没有正在进行的生成")
    ev.set()


@router.post("/sessions/{session_id}/messages", response_model=s.ChatSessionRead)
def send_message(
    session_id: int,
    payload: s.ChatSend,
    session: Session = Depends(get_session),
    provider: AIProvider = Depends(provider_dep),
) -> Any:
    """非流式发送（兼容 v0.4 及更早的客户端）。"""
    return generate(session_id, s.ChatGenerate(content=payload.content, stream=False), session, provider)


# ---------- 世界观关系识别 ----------
@router.post("/worlds/{world_id}/suggest-relations")
def suggest_relations(
    world_id: int,
    session: Session = Depends(get_session),
    provider: AIProvider = Depends(provider_dep),
) -> dict[str, Any]:
    """让 AI 阅读世界观正文与角色简介，提出关系建议。
    建议以 ai_suggested=True、confirmed=False 写入，需要在关系网页面人工确认。"""
    world = get_or_404(session, m.World, world_id)
    chars = session.scalars(select(m.Character).where(m.Character.world_id == world_id)).all()
    if len(chars) < 2:
        raise HTTPException(422, "该世界观下至少需要两个角色")
    try:
        text = provider.chat(build_relation_messages(world, list(chars)), temperature=0.2)
    except AIUnavailable as exc:
        raise HTTPException(503, str(exc)) from exc
    suggestions = parse_relations(text, {c.id for c in chars})
    existing = {
        (r.source_id, r.target_id, r.kind)
        for r in session.scalars(select(m.Relation)).all()
    }
    created = []
    for sug in suggestions:
        if (sug["source_id"], sug["target_id"], sug["kind"]) in existing:
            continue
        rel = m.Relation(**sug, ai_suggested=True, confirmed=False)
        session.add(rel)
        created.append(rel)
    session.commit()
    return {"created": [s.RelationRead.model_validate(r).model_dump(mode="json") for r in created], "raw": text}
