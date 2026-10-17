"""角色卡：在线编辑、导入（JSON / PNG）、导出（V2 JSON / 嵌入 PNG）。"""

from __future__ import annotations

import json
import re
from typing import Any
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import Response
from sqlalchemy.orm import Session

from .. import models as m
from .. import schemas as s
from ..config import get_settings
from ..crud import get_or_404, make_crud_router
from ..db import get_session
from ..pngmeta import card_to_v2, read_card_png, v2_to_fields, write_card_png

router = make_crud_router(
    prefix="/api/cards", model=m.CharacterCard, create_schema=s.CardCreate,
    update_schema=s.CardUpdate, read_schema=s.CardRead, tag_name="角色卡",
)
io_router = APIRouter(prefix="/api/cards", tags=["角色卡"])


def _filename(name: str, ext: str) -> str:
    safe = re.sub(r'[\\/:*?"<>|]+', "_", name).strip() or "card"
    return f"{safe}.{ext}"


def _disposition(name: str) -> str:
    return f"attachment; filename=card; filename*=UTF-8''{quote(name)}"


@io_router.post("/import", response_model=s.CardRead, status_code=201)
async def import_card(file: UploadFile = File(...), session: Session = Depends(get_session)) -> Any:
    data = await file.read()
    try:
        if data[:8] == b"\x89PNG\r\n\x1a\n":
            payload = read_card_png(data)
        else:
            payload = json.loads(data.decode("utf-8-sig"))
        fields = v2_to_fields(payload)
    except (ValueError, UnicodeDecodeError) as exc:
        raise HTTPException(422, str(exc)) from exc
    card = m.CharacterCard(**fields)
    session.add(card)
    session.commit()
    session.refresh(card)
    return card


@io_router.get("/{card_id}/export.json")
def export_json(card_id: int, session: Session = Depends(get_session)) -> Response:
    card = get_or_404(session, m.CharacterCard, card_id)
    body = json.dumps(card_to_v2(card), ensure_ascii=False, indent=2)
    return Response(
        body,
        media_type="application/json",
        headers={"Content-Disposition": _disposition(_filename(card.name, "json"))},
    )


@io_router.get("/{card_id}/export.png")
def export_png(card_id: int, session: Session = Depends(get_session)) -> Response:
    card = get_or_404(session, m.CharacterCard, card_id)
    base: bytes | None = None
    if card.avatar_asset_id:
        asset = session.get(m.Asset, card.avatar_asset_id)
        if asset and asset.file_path and asset.width:
            path = get_settings().data_dir / asset.file_path
            if path.is_file():
                base = path.read_bytes()
    png = write_card_png(card_to_v2(card), base)
    return Response(
        png,
        media_type="image/png",
        headers={"Content-Disposition": _disposition(_filename(card.name, "png"))},
    )


@io_router.post("/from-character/{character_id}", response_model=s.CardRead, status_code=201)
def card_from_character(character_id: int, session: Session = Depends(get_session)) -> Any:
    """用百科里的角色条目生成一张角色卡草稿。"""
    char = get_or_404(session, m.Character, character_id)
    world = session.get(m.World, char.world_id) if char.world_id else None
    card = m.CharacterCard(
        name=char.name,
        description="\n\n".join(x for x in (char.summary, char.profile) if x),
        scenario=(world.summary or "") if world else "",
        card_tags=[t.name for t in char.tags],
        character_id=char.id,
        avatar_asset_id=char.avatar_asset_id,
        creator_notes="由 Front 角色百科生成",
    )
    session.add(card)
    session.commit()
    session.refresh(card)
    return card
