"""角色百科、关系网。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
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


@graph.get("")
def relation_graph(world_id: int | None = None, include_unconfirmed: bool = True, session: Session = Depends(get_session)) -> dict[str, Any]:
    """返回关系网的节点与边，前端直接用来画图。"""
    cstmt = select(m.Character)
    if world_id is not None:
        cstmt = cstmt.where(m.Character.world_id == world_id)
    chars = session.scalars(cstmt).all()
    ids = {c.id for c in chars}
    rstmt = select(m.Relation).where(m.Relation.source_id.in_(ids), m.Relation.target_id.in_(ids))
    if not include_unconfirmed:
        rstmt = rstmt.where(m.Relation.confirmed.is_(True))
    rels = session.scalars(rstmt).all()
    return {
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
    }
