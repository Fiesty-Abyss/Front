"""角色百科、关系网。"""

from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from .. import models as m
from .. import schemas as s
from ..crud import make_crud_router, qp
from ..db import get_session


def _char_filters(stmt, request):
    if gender := qp(request, "gender"):
        stmt = stmt.where(m.Character.gender == gender)
    if world := qp(request, "world_id"):
        stmt = stmt.where(m.Character.world_id == int(world))
    if work := qp(request, "work_id"):
        stmt = stmt.where(m.Character.work_id == int(work))
    return stmt


def _rel_filters(stmt, request):
    if cid := qp(request, "character_id"):
        cid_i = int(cid)
        stmt = stmt.where(or_(m.Relation.source_id == cid_i, m.Relation.target_id == cid_i))
    if (confirmed := qp(request, "confirmed")) is not None:
        stmt = stmt.where(m.Relation.confirmed == (confirmed.lower() in ("1", "true", "yes")))
    return stmt


def _rel_validate(session: Session, data: dict[str, Any]) -> None:
    for key in ("source_id", "target_id"):
        if data.get(key) is not None and session.get(m.Character, data[key]) is None:
            raise HTTPException(422, f"角色 {data[key]} 不存在")
    if data.get("source_id") is not None and data.get("source_id") == data.get("target_id"):
        raise HTTPException(422, "关系的两端不能是同一个角色")


characters = make_crud_router(
    prefix="/api/characters", model=m.Character, create_schema=s.CharacterCreate,
    update_schema=s.CharacterUpdate, read_schema=s.CharacterRead, tag_name="角色百科",
    filters=_char_filters, order_by=m.Character.name,
)
relations = make_crud_router(
    prefix="/api/relations", model=m.Relation, create_schema=s.RelationCreate,
    update_schema=s.RelationUpdate, read_schema=s.RelationRead, tag_name="关系网",
    filters=_rel_filters, validate=_rel_validate,
)

graph = APIRouter(prefix="/api/graph", tags=["关系网"])


def _scope(world_id: int | None) -> str:
    return f"world:{world_id}" if world_id is not None else "all"


def build_graph(session: Session, world_id: int | None, include_unconfirmed: bool = True, kinds: list[str] | None = None) -> dict[str, Any]:
    cstmt = select(m.Character)
    if world_id is not None:
        cstmt = cstmt.where(m.Character.world_id == world_id)
    chars = session.scalars(cstmt).all()
    ids = {c.id for c in chars}
    rstmt = select(m.Relation).where(m.Relation.source_id.in_(ids), m.Relation.target_id.in_(ids))
    if not include_unconfirmed:
        rstmt = rstmt.where(m.Relation.confirmed.is_(True))
    all_rels = session.scalars(rstmt).all()
    kind_counts = Counter(r.kind for r in all_rels)
    rels = [r for r in all_rels if not kinds or r.kind in kinds]
    layout = session.scalar(select(m.GraphLayout).where(m.GraphLayout.scope == _scope(world_id)))
    return {
        "scope": _scope(world_id),
        "nodes": [
            {
                "id": c.id,
                "name": c.name,
                "gender": c.gender,
                "world_id": c.world_id,
                "avatar_asset_id": c.avatar_asset_id,
                "tags": [t.name for t in c.tags],
            }
            for c in chars
        ],
        "edges": [
            {
                "id": r.id,
                "source": r.source_id,
                "target": r.target_id,
                "kind": r.kind,
                "description": r.description,
                "bidirectional": r.bidirectional,
                "ai_suggested": r.ai_suggested,
                "confirmed": r.confirmed,
            }
            for r in rels
        ],
        "kinds": [{"kind": k, "count": n} for k, n in kind_counts.most_common()],
        "layout": {
            "positions": layout.positions if layout else {},
            "kind_colors": layout.kind_colors if layout else {},
            "saved_at": layout.updated_at.isoformat() if layout else None,
        },
    }


@graph.get("")
def relation_graph(
    world_id: int | None = None,
    include_unconfirmed: bool = True,
    kinds: str | None = None,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """返回关系网的节点与边、关系类型统计和已保存的布局。kinds 用逗号分隔，只显示这些关系类型。"""
    return build_graph(session, world_id, include_unconfirmed, [k for k in (kinds or "").split(",") if k] or None)


class LayoutIn(BaseModel):
    world_id: int | None = None
    positions: dict[str, dict[str, float]] | None = None
    kind_colors: dict[str, str] | None = None


@graph.put("/layout")
def save_layout(body: LayoutIn, session: Session = Depends(get_session)) -> dict[str, Any]:
    """保存节点位置与关系类型配色（只更新传入的部分）。"""
    scope = _scope(body.world_id)
    layout = session.scalar(select(m.GraphLayout).where(m.GraphLayout.scope == scope))
    if layout is None:
        layout = m.GraphLayout(scope=scope, positions={}, kind_colors={})
        session.add(layout)
    if body.positions is not None:
        layout.positions = {str(k): {"x": float(v.get("x", 0)), "y": float(v.get("y", 0))} for k, v in body.positions.items()}
    if body.kind_colors is not None:
        layout.kind_colors = {k: v for k, v in body.kind_colors.items() if v}
    session.commit()
    return {"scope": scope, "positions": len(layout.positions), "kind_colors": layout.kind_colors}


@graph.delete("/layout", status_code=204)
def reset_layout(world_id: int | None = None, session: Session = Depends(get_session)) -> Response:
    layout = session.scalar(select(m.GraphLayout).where(m.GraphLayout.scope == _scope(world_id)))
    if layout:
        layout.positions = {}
        session.commit()
    return Response(status_code=204)


@graph.get("/export")
def export_graph(world_id: int | None = None, session: Session = Depends(get_session)) -> Response:
    """导出关系网 JSON（节点、边、布局），便于备份或在其他工具中使用。"""
    data = build_graph(session, world_id)
    data["exported_at"] = datetime.now(timezone.utc).isoformat()
    name = f"front-graph-{data['scope'].replace(':', '-')}.json"
    return Response(json.dumps(data, ensure_ascii=False, indent=2), media_type="application/json",
                    headers={"Content-Disposition": f'attachment; filename="{name}"'})
