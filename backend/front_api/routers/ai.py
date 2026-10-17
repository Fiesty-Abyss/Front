"""AI 接口：状态、角色扮演对话（带上下文）、世界观关系识别。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models as m
from .. import schemas as s
from ..ai import AIProvider, AIUnavailable, get_provider
from ..ai.prompts import build_relation_messages, build_roleplay_messages, parse_relations
from ..crud import get_or_404
from ..db import get_session

router = APIRouter(prefix="/api/ai", tags=["AI 接口"])


def provider_dep() -> AIProvider:
    return get_provider()


@router.get("/status")
def status(provider: AIProvider = Depends(provider_dep)) -> dict[str, Any]:
    return {
        "provider": provider.name,
        "available": provider.available(),
        "model": getattr(provider, "model", None),
        "base_url": getattr(provider, "base_url", None),
    }


# ---------- 角色扮演会话 ----------
@router.get("/sessions")
def list_sessions(card_id: int | None = None, session: Session = Depends(get_session)) -> list[dict[str, Any]]:
    stmt = select(m.ChatSession).order_by(m.ChatSession.updated_at.desc())
    if card_id is not None:
        stmt = stmt.where(m.ChatSession.card_id == card_id)
    return [
        {"id": c.id, "card_id": c.card_id, "title": c.title, "messages": len(c.messages), "updated_at": c.updated_at.isoformat()}
        for c in session.scalars(stmt).all()
    ]


@router.post("/sessions", response_model=s.ChatSessionRead, status_code=201)
def create_session(payload: s.ChatSessionCreate, session: Session = Depends(get_session)) -> Any:
    card = get_or_404(session, m.CharacterCard, payload.card_id)
    chat = m.ChatSession(card_id=card.id, title=payload.title, user_name=payload.user_name)
    if card.first_mes:
        chat.messages.append(m.ChatMessage(role="assistant", content=card.first_mes.replace("{{user}}", payload.user_name).replace("{{char}}", card.name)))
    session.add(chat)
    session.commit()
    session.refresh(chat)
    return chat


@router.get("/sessions/{session_id}", response_model=s.ChatSessionRead)
def get_chat(session_id: int, session: Session = Depends(get_session)) -> Any:
    return get_or_404(session, m.ChatSession, session_id)


@router.delete("/sessions/{session_id}", status_code=204)
def delete_chat(session_id: int, session: Session = Depends(get_session)) -> None:
    session.delete(get_or_404(session, m.ChatSession, session_id))
    session.commit()


@router.post("/sessions/{session_id}/messages", response_model=s.ChatSessionRead)
def send_message(
    session_id: int,
    payload: s.ChatSend,
    session: Session = Depends(get_session),
    provider: AIProvider = Depends(provider_dep),
) -> Any:
    chat = get_or_404(session, m.ChatSession, session_id)
    card = get_or_404(session, m.CharacterCard, chat.card_id)
    history = [{"role": msg.role, "content": msg.content} for msg in chat.messages]
    history.append({"role": "user", "content": payload.content})
    try:
        reply = provider.chat(build_roleplay_messages(card, history, chat.user_name))
    except AIUnavailable as exc:
        raise HTTPException(503, str(exc)) from exc
    chat.messages.append(m.ChatMessage(role="user", content=payload.content))
    chat.messages.append(m.ChatMessage(role="assistant", content=reply))
    session.commit()
    session.refresh(chat)
    return chat


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
