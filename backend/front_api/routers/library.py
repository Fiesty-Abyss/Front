"""标签、作品、世界观、收藏集。"""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models as m
from .. import schemas as s
from ..crud import make_crud_router, qp


def _tag_filters(stmt, request):
    if cat := qp(request, "category"):
        stmt = stmt.where(m.Tag.category == cat)
    if name := qp(request, "name"):
        stmt = stmt.where(m.Tag.name.contains(name))
    return stmt


def _tag_validate(session: Session, data: dict[str, Any]) -> None:
    if "name" in data and data["name"] is not None:
        exists = session.scalar(
            select(m.Tag).where(m.Tag.name == data["name"], m.Tag.category == data.get("category", "custom"))
        )
        if exists:
            raise HTTPException(409, f"标签已存在: {exists.category}:{exists.name} (id={exists.id})")


def _work_filters(stmt, request):
    if kind := qp(request, "kind"):
        stmt = stmt.where(m.Work.kind == kind)
    return stmt


tags = make_crud_router(
    prefix="/api/tags", model=m.Tag, create_schema=s.TagCreate, update_schema=s.TagUpdate,
    read_schema=s.TagRead, tag_name="标签", filters=_tag_filters,
    order_by=(m.Tag.category, m.Tag.name), validate=_tag_validate,
)
works = make_crud_router(
    prefix="/api/works", model=m.Work, create_schema=s.WorkCreate, update_schema=s.WorkUpdate,
    read_schema=s.WorkRead, tag_name="作品", filters=_work_filters,
)
worlds = make_crud_router(
    prefix="/api/worlds", model=m.World, create_schema=s.WorldCreate, update_schema=s.WorldUpdate,
    read_schema=s.WorldRead, tag_name="世界观",
)
