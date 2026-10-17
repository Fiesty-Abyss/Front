from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, Query
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
        "notes": count(m.Note),
        "diagrams": count(m.Diagram),
        "galgames": count(m.Galgame),
        "worlds": count(m.World),
        "works": count(m.Work),
        "relations": count(m.Relation),
        "prompts": count(m.Prompt),
        "sd_models": count(m.SDModel),
        "cards": count(m.CharacterCard),
        "collections": count(m.Collection),
        "tags": count(m.Tag),
    }


ACTIVITY_SOURCES: dict[str, type] = {
    "characters": m.Character, "world_entries": m.WorldEntry, "prompts": m.Prompt, "generations": m.Generation,
    "chat": m.ChatMessage, "cards": m.CharacterCard, "lore": m.LoreEntry, "notes": m.Note, "diagrams": m.Diagram, "galgames": m.Galgame,
}


def _local_day(dt: datetime | None) -> date | None:
    if dt is None:
        return None
    if dt.tzinfo is None:  # SQLite 读回来的是不带时区的 UTC
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone().date()


@router.get("/stats/activity")
def activity(weeks: int = Query(26, ge=1, le=104), session: Session = Depends(get_session)) -> dict[str, Any]:
    """创作活跃度：按本机时区的“天”统计入库与编辑记录（素材优先用创作日期 work_date）。"""
    today = datetime.now().astimezone().date()
    start = today - timedelta(days=today.weekday() + 7 * (weeks - 1))  # 从周一开始，整周对齐
    per_day: dict[date, Counter] = defaultdict(Counter)
    for work_date, created in session.execute(select(m.Asset.work_date, m.Asset.created_at)):
        d = work_date or _local_day(created)
        if d and start <= d <= today:
            per_day[d]["assets"] += 1
    for key, model in ACTIVITY_SOURCES.items():
        for (created,) in session.execute(select(model.created_at)):
            d = _local_day(created)
            if d and start <= d <= today:
                per_day[d][key] += 1
    days = []
    cur = start
    while cur <= today:
        c = per_day.get(cur, Counter())
        days.append({"date": cur.isoformat(), "count": sum(c.values()), "by": dict(c)})
        cur += timedelta(days=1)
    streak = 0
    probe = today if per_day.get(today) else today - timedelta(days=1)
    while per_day.get(probe):
        streak += 1
        probe -= timedelta(days=1)
    total = sum(d["count"] for d in days)
    return {"start": start.isoformat(), "today": today.isoformat(), "weeks": weeks, "days": days, "total": total,
            "active_days": sum(1 for d in days if d["count"]), "streak": streak,
            "max": max((d["count"] for d in days), default=0)}


@router.get("/search")
def global_search(q: str, entity: str | None = None, limit: int = 50, session: Session = Depends(get_session)) -> list[dict[str, Any]]:
    return search(session, q, entity=entity, limit=min(limit, 200))


@router.post("/search/rebuild")
def rebuild_index(session: Session = Depends(get_session)) -> dict[str, int]:
    return {"indexed": rebuild(session)}
