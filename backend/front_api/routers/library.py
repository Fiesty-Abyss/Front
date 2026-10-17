"""标签、作品、世界观、收藏集。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import Table, or_, select, text
from sqlalchemy.orm import Session

from .. import models as m
from .. import schemas as s
from ..crud import get_or_404, make_crud_router, qp, tag_descendants
from ..db import Base, get_session
from ..search import _escape_like, rebuild


def _tag_filters(stmt, request):
    if cat := qp(request, "category"):
        stmt = stmt.where(m.Tag.category == cat)
    if name := qp(request, "name"):
        # 名称或别名包含关键字
        alias_hit = text(
            "EXISTS (SELECT 1 FROM json_each(tags.aliases) WHERE json_each.value LIKE :alias_q ESCAPE '\\')"
        ).bindparams(alias_q=f"%{_escape_like(name)}%")
        stmt = stmt.where(or_(m.Tag.name.contains(name, autoescape=True), alias_hit))
    if (parent := qp(request, "parent_id")) is not None:
        stmt = stmt.where(m.Tag.parent_id.is_(None) if parent == "root" else m.Tag.parent_id == int(parent))
    return stmt


def _clean_aliases(aliases: list[str], own_name: str | None) -> list[str]:
    out: list[str] = []
    for a in aliases:
        a = a.strip()
        if a and a != own_name and a not in out:
            out.append(a[:80])
    return out


def make_tag_validator():
    def _tag_validate(session: Session, data: dict[str, Any], obj_id: int | None = None) -> None:
        current = session.get(m.Tag, obj_id) if obj_id is not None else None
        name = data.get("name") or (current.name if current else None)
        category = data.get("category") or (current.category if current else "custom")
        if "name" in data or "category" in data:
            exists = session.scalar(select(m.Tag).where(m.Tag.name == name, m.Tag.category == category))
            if exists and exists.id != obj_id:
                raise HTTPException(409, f"标签已存在: {exists.category}:{exists.name} (id={exists.id})")
        if data.get("aliases") is not None:
            data["aliases"] = _clean_aliases(data["aliases"], name)
        parent = data.get("parent_id")
        if parent is not None:
            if session.get(m.Tag, parent) is None:
                raise HTTPException(422, f"父标签 {parent} 不存在")
            if obj_id is not None and parent in tag_descendants(session, obj_id):
                raise HTTPException(422, "父标签不能是自己或自己的子标签")

    return _tag_validate


def _work_filters(stmt, request):
    if kind := qp(request, "kind"):
        stmt = stmt.where(m.Work.kind == kind)
    return stmt


tags = make_crud_router(
    prefix="/api/tags", model=m.Tag, create_schema=s.TagCreate, update_schema=s.TagUpdate,
    read_schema=s.TagRead, tag_name="标签", filters=_tag_filters,
    order_by=(m.Tag.category, m.Tag.name), validate=make_tag_validator(), validate_with_id=True,
)
tag_extra = APIRouter(prefix="/api/tags", tags=["标签"])


class MergeRequest(BaseModel):
    into_id: int


def _tag_link_tables() -> list[Table]:
    return [t for name, t in Base.metadata.tables.items() if name.endswith("_tags") and "tag_id" in t.c]


@tag_extra.get("/usage")
def tag_usage(session: Session = Depends(get_session)) -> dict[int, dict[str, int]]:
    """每个标签的使用次数（所有类型合计）。direct 是直接打了这个标签的条目数；
    total 还包括打了它任意子标签的条目（同一条目只算一次），和按上级标签筛选时的结果一致。"""
    owners: dict[int, set[tuple[str, int]]] = {}
    for t in _tag_link_tables():
        owner = next(c for c in t.c if c.name != "tag_id")
        for tag_id, oid in session.execute(select(t.c.tag_id, owner)).all():
            owners.setdefault(tag_id, set()).add((t.name, oid))
    children: dict[int, list[int]] = {}
    ids = list(session.scalars(select(m.Tag.id)))
    for tid, pid in session.execute(select(m.Tag.id, m.Tag.parent_id)).all():
        if pid:
            children.setdefault(pid, []).append(tid)

    def family(tid: int) -> set[int]:
        out, stack = set(), [tid]
        while stack:
            cur = stack.pop()
            if cur in out:
                continue
            out.add(cur)
            stack.extend(children.get(cur, []))
        return out

    usage: dict[int, dict[str, int]] = {}
    for tid in ids:
        direct = owners.get(tid, set())
        total = set().union(*(owners.get(f, set()) for f in family(tid)))
        if direct or total:
            usage[tid] = {"direct": len(direct), "total": len(total)}
    return usage


@tag_extra.get("/tree")
def tag_tree(session: Session = Depends(get_session)) -> list[dict[str, Any]]:
    """按分类返回标签树。"""
    tags = session.scalars(select(m.Tag).order_by(m.Tag.category, m.Tag.name)).all()
    nodes = {t.id: {**s.TagRead.model_validate(t).model_dump(), "children": []} for t in tags}
    roots: list[dict[str, Any]] = []
    for t in tags:
        if t.parent_id in nodes:
            nodes[t.parent_id]["children"].append(nodes[t.id])
        else:
            roots.append(nodes[t.id])
    return roots


@tag_extra.post("/{tag_id}/merge", response_model=s.TagRead)
def merge_tag(tag_id: int, body: MergeRequest, session: Session = Depends(get_session)) -> Any:
    """把标签 tag_id 合并进 into_id：所有使用处改用目标标签，原名称与别名成为目标标签的别名，子标签移到目标下，然后删除原标签。"""
    if tag_id == body.into_id:
        raise HTTPException(422, "不能合并到自己")
    src = get_or_404(session, m.Tag, tag_id)
    dst = get_or_404(session, m.Tag, body.into_id)
    if dst.id in tag_descendants(session, src.id):
        raise HTTPException(422, "不能合并到自己的子标签")
    for t in _tag_link_tables():
        owner = next(c for c in t.c if c.name != "tag_id")
        owners_with_src = set(session.scalars(select(owner).where(t.c.tag_id == src.id)))
        owners_with_dst = set(session.scalars(select(owner).where(t.c.tag_id == dst.id)))
        to_add = owners_with_src - owners_with_dst
        if to_add:
            session.execute(t.insert(), [{owner.name: o, "tag_id": dst.id} for o in to_add])
        session.execute(t.delete().where(t.c.tag_id == src.id))
    for child in session.scalars(select(m.Tag).where(m.Tag.parent_id == src.id)):
        child.parent_id = dst.id
    dst.aliases = _clean_aliases([*(dst.aliases or []), src.name, *(src.aliases or [])], dst.name)
    session.delete(src)
    session.commit()
    session.refresh(dst)
    rebuild(session)  # 标签名出现在各条目的索引正文里
    return dst


works = make_crud_router(
    prefix="/api/works", model=m.Work, create_schema=s.WorkCreate, update_schema=s.WorkUpdate,
    read_schema=s.WorkRead, tag_name="作品", filters=_work_filters,
)
worlds = make_crud_router(
    prefix="/api/worlds", model=m.World, create_schema=s.WorldCreate, update_schema=s.WorldUpdate,
    read_schema=s.WorldRead, tag_name="世界观",
)
