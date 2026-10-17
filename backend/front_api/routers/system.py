from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import __version__
from .. import models as m
from ..config import get_settings
from ..db import get_session
from ..search import rebuild, search

router = APIRouter(prefix="/api", tags=["系统"])


@router.get("/health")
def health() -> dict[str, Any]:
    return {"ok": True, "version": __version__}


@router.get("/stats")
def stats(session: Session = Depends(get_session)) -> dict[str, Any]:
    def count(model: type) -> int:
        return session.scalar(select(func.count()).select_from(model)) or 0

    kinds = dict(session.execute(select(m.Asset.kind, func.count()).group_by(m.Asset.kind)).all())
    return {
        "version": __version__,
        "data_dir": str(get_settings().data_dir),
        "assets": count(m.Asset),
        "asset_kinds": kinds,
        "characters": count(m.Character),
        "worlds": count(m.World),
        "works": count(m.Work),
        "relations": count(m.Relation),
        "prompts": count(m.Prompt),
        "sd_models": count(m.SDModel),
        "cards": count(m.CharacterCard),
        "collections": count(m.Collection),
        "tags": count(m.Tag),
    }


@router.get("/search")
def global_search(q: str, entity: str | None = None, limit: int = 50, session: Session = Depends(get_session)) -> list[dict[str, Any]]:
    return search(session, q, entity=entity, limit=min(limit, 200))


@router.post("/search/rebuild")
def rebuild_index(session: Session = Depends(get_session)) -> dict[str, int]:
    return {"indexed": rebuild(session)}
