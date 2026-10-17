"""世界书：增删改查、条目、命中测试、导入导出（Character Card V2 / SillyTavern）、从世界观生成。"""

from __future__ import annotations

import json
import re
from typing import Any
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import models as m
from .. import schemas as s
from ..ai import lore as lore_mod
from ..crud import get_or_404
from ..db import get_session

router = APIRouter(tags=["世界书"])


def _read(book: m.Lorebook) -> dict[str, Any]:
    return s.LorebookRead.model_validate(book).model_dump(mode="json")


def create_book(session: Session, data: dict[str, Any]) -> m.Lorebook:
    entries = data.pop("entries", [])
    if data.get("world_id") is not None:
        get_or_404(session, m.World, data["world_id"])
    book = m.Lorebook(**data)
    for e in entries:
        book.entries.append(m.LoreEntry(**e))
    session.add(book)
    session.flush()
    return book


@router.get("/api/lorebooks")
def list_books(world_id: int | None = None, session: Session = Depends(get_session)) -> dict[str, Any]:
    stmt = select(m.Lorebook).order_by(m.Lorebook.id.desc())
    if world_id is not None:
        stmt = stmt.where(m.Lorebook.world_id == world_id)
    cards = dict(session.execute(select(m.CharacterCard.lorebook_id, func.count()).where(m.CharacterCard.lorebook_id.is_not(None))
                                 .group_by(m.CharacterCard.lorebook_id)).all())
    items = []
    for b in session.scalars(stmt).all():
        items.append({"id": b.id, "name": b.name, "description": b.description, "world_id": b.world_id,
                      "entries": len(b.entries), "enabled": sum(1 for e in b.entries if e.enabled),
                      "cards": cards.get(b.id, 0), "updated_at": b.updated_at.isoformat()})
    return {"items": items, "total": len(items)}


@router.post("/api/lorebooks", status_code=201)
def create(payload: s.LorebookCreate, session: Session = Depends(get_session)) -> dict[str, Any]:
    book = create_book(session, payload.model_dump())
    session.commit()
    session.refresh(book)
    return _read(book)


@router.get("/api/lorebooks/{book_id}")
def get_book(book_id: int, session: Session = Depends(get_session)) -> dict[str, Any]:
    return _read(get_or_404(session, m.Lorebook, book_id))


@router.patch("/api/lorebooks/{book_id}")
def update_book(book_id: int, payload: s.LorebookUpdate, session: Session = Depends(get_session)) -> dict[str, Any]:
    book = get_or_404(session, m.Lorebook, book_id)
    data = payload.model_dump(exclude_unset=True)
    if data.get("world_id") is not None:
        get_or_404(session, m.World, data["world_id"])
    for k, v in data.items():
        setattr(book, k, v)
    session.commit()
    session.refresh(book)
    return _read(book)


@router.delete("/api/lorebooks/{book_id}", status_code=204)
def delete_book(book_id: int, session: Session = Depends(get_session)) -> Response:
    session.delete(get_or_404(session, m.Lorebook, book_id))
    for chat in session.scalars(select(m.ChatSession)).all():
        if book_id in (chat.lorebook_ids or []):
            chat.lorebook_ids = [i for i in chat.lorebook_ids if i != book_id]
    session.commit()
    return Response(status_code=204)


@router.post("/api/lorebooks/{book_id}/entries", status_code=201)
def add_entry(book_id: int, payload: s.LoreEntryCreate, session: Session = Depends(get_session)) -> dict[str, Any]:
    book = get_or_404(session, m.Lorebook, book_id)
    entry = m.LoreEntry(lorebook_id=book.id, **payload.model_dump())
    session.add(entry)
    session.commit()
    session.refresh(entry)
    return s.LoreEntryRead.model_validate(entry).model_dump(mode="json")


@router.patch("/api/lore-entries/{entry_id}")
def update_entry(entry_id: int, payload: s.LoreEntryUpdate, session: Session = Depends(get_session)) -> dict[str, Any]:
    entry = get_or_404(session, m.LoreEntry, entry_id)
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(entry, k, v)
    session.commit()
    session.refresh(entry)
    return s.LoreEntryRead.model_validate(entry).model_dump(mode="json")


@router.delete("/api/lore-entries/{entry_id}", status_code=204)
def delete_entry(entry_id: int, session: Session = Depends(get_session)) -> Response:
    session.delete(get_or_404(session, m.LoreEntry, entry_id))
    session.commit()
    return Response(status_code=204)


@router.post("/api/lorebooks/{book_id}/test")
def test_book(book_id: int, payload: s.LoreTest, session: Session = Depends(get_session)) -> dict[str, Any]:
    """把一段文字当作最近的对话，看看会激活哪些条目。"""
    book = get_or_404(session, m.Lorebook, book_id)
    return lore_mod.activate([book], [payload.text])


@router.post("/api/lorebooks/import", status_code=201)
async def import_book(file: UploadFile = File(...), session: Session = Depends(get_session)) -> dict[str, Any]:
    raw = await file.read()
    try:
        if raw[:8] == b"\x89PNG\r\n\x1a\n":
            from ..pngmeta import read_card_png
            payload = read_card_png(raw)
        else:
            payload = json.loads(raw.decode("utf-8-sig"))
        data = lore_mod.book_from_json(payload)
    except (ValueError, UnicodeDecodeError) as exc:
        raise HTTPException(422, str(exc)) from exc
    book = create_book(session, data)
    session.commit()
    session.refresh(book)
    return _read(book)


@router.get("/api/lorebooks/{book_id}/export")
def export_book(book_id: int, format: str = "v2", session: Session = Depends(get_session)) -> Response:
    book = get_or_404(session, m.Lorebook, book_id)
    body = lore_mod.book_to_st(book) if format == "st" else lore_mod.book_to_v2(book)
    name = re.sub(r'[\\/:*?"<>|]+', "_", book.name).strip() or "lorebook"
    return Response(json.dumps(body, ensure_ascii=False, indent=2), media_type="application/json",
                    headers={"Content-Disposition": f"attachment; filename=lorebook.json; filename*=UTF-8''{quote(name + '.json')}"})


@router.post("/api/lorebooks/from-world/{world_id}", status_code=201)
def from_world(world_id: int, session: Session = Depends(get_session)) -> dict[str, Any]:
    """用世界观百科生成世界书：角色（名字 + 别名为关键词）和地点 / 组织 / 物品 / 概念 / 事件条目。"""
    world = get_or_404(session, m.World, world_id)
    entries: list[dict[str, Any]] = []
    if world.summary:
        entries.append({"title": f"世界观 · {world.name}", "keys": [world.name], "content": world.summary, "constant": True,
                        "insertion_order": 0, "priority": 100})
    kind_label = {"location": "地点", "organization": "组织", "event": "事件", "item": "物品", "concept": "概念"}
    order = 10
    for c in session.scalars(select(m.Character).where(m.Character.world_id == world_id).order_by(m.Character.id)).all():
        keys = [c.name] + [a.strip() for a in re.split(r"[、,，/]", c.alias or "") if a.strip()]
        content = c.summary or (c.profile or "")[:300]
        if content:
            entries.append({"title": f"角色 · {c.name}", "keys": keys, "content": f"{c.name}：{content}", "insertion_order": order})
            order += 10
    for e in session.scalars(select(m.WorldEntry).where(m.WorldEntry.world_id == world_id).order_by(m.WorldEntry.id)).all():
        content = e.summary or (e.content or "")[:300]
        if not content:
            continue
        prefix = f"{e.date_label}，" if e.kind == "event" and e.date_label else ""
        entries.append({"title": f"{kind_label.get(e.kind, e.kind)} · {e.name}", "keys": [e.name],
                        "content": f"{e.name}（{kind_label.get(e.kind, e.kind)}）：{prefix}{content}", "insertion_order": order})
        order += 10
    if not entries:
        raise HTTPException(422, "这个世界观还没有可用的简介、角色或条目")
    book = create_book(session, {"name": f"{world.name} 世界书", "description": "由世界观百科自动生成，可继续编辑",
                                 "world_id": world.id, "entries": entries})
    session.commit()
    session.refresh(book)
    return _read(book)
