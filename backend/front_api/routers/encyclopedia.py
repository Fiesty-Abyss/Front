"""百科增强：世界观条目（地点 / 组织 / 事件…）、时间线、出场作品、角色图集与角色详情。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from .. import models as m
from .. import schemas as s
from ..crud import get_or_404, make_crud_router, qp
from ..db import get_session


# ---------------- 世界观条目 ----------------
def _entry_filters(stmt, request):
    if world := qp(request, "world_id"):
        stmt = stmt.where(m.WorldEntry.world_id == int(world))
    if kind := qp(request, "kind"):
        stmt = stmt.where(m.WorldEntry.kind.in_(kind.split(",")))
    if (parent := qp(request, "parent_id")) is not None:
        stmt = stmt.where(m.WorldEntry.parent_id.is_(None) if parent == "root" else m.WorldEntry.parent_id == int(parent))
    if char := qp(request, "character_id"):
        stmt = stmt.where(m.WorldEntry.links.any(m.EntryCharacter.character_id == int(char)))
    return stmt


def _entry_validate(session: Session, data: dict[str, Any], obj_id: int | None = None) -> None:
    current = session.get(m.WorldEntry, obj_id) if obj_id is not None else None
    world_id = data.get("world_id") or (current.world_id if current else None)
    if world_id is not None and session.get(m.World, world_id) is None:
        raise HTTPException(422, f"世界观 {world_id} 不存在")
    parent_id = data.get("parent_id")
    if parent_id is not None:
        parent = session.get(m.WorldEntry, parent_id)
        if parent is None:
            raise HTTPException(422, f"上级条目 {parent_id} 不存在")
        if parent.world_id != world_id:
            raise HTTPException(422, "上级条目必须属于同一个世界观")
        # 防止成环：沿父链向上不能遇到自己
        cur, hops = parent, 0
        while cur is not None and hops < 1000:
            if obj_id is not None and cur.id == obj_id:
                raise HTTPException(422, "上级条目不能是自己或自己的下级")
            cur = session.get(m.WorldEntry, cur.parent_id) if cur.parent_id else None
            hops += 1


entries = make_crud_router(
    prefix="/api/world-entries", model=m.WorldEntry, create_schema=s.WorldEntryCreate,
    update_schema=s.WorldEntryUpdate, read_schema=s.WorldEntryRead, tag_name="世界观条目",
    filters=_entry_filters, order_by=(m.WorldEntry.kind, m.WorldEntry.sort_key, m.WorldEntry.name),
    validate=_entry_validate, validate_with_id=True,
)


# ---------------- 出场作品 ----------------
def _app_filters(stmt, request):
    if c := qp(request, "character_id"):
        stmt = stmt.where(m.Appearance.character_id == int(c))
    if w := qp(request, "work_id"):
        stmt = stmt.where(m.Appearance.work_id == int(w))
    return stmt


def _app_validate(session: Session, data: dict[str, Any]) -> None:
    if "character_id" in data and session.get(m.Character, data["character_id"]) is None:
        raise HTTPException(422, f"角色 {data['character_id']} 不存在")
    if "work_id" in data and session.get(m.Work, data["work_id"]) is None:
        raise HTTPException(422, f"作品 {data['work_id']} 不存在")
    if "character_id" in data and "work_id" in data:
        dup = session.scalar(select(m.Appearance).where(
            m.Appearance.character_id == data["character_id"], m.Appearance.work_id == data["work_id"]))
        if dup:
            raise HTTPException(409, "该角色已登记在这部作品中")


appearances = make_crud_router(
    prefix="/api/appearances", model=m.Appearance, create_schema=s.AppearanceCreate,
    update_schema=s.AppearanceUpdate, read_schema=s.AppearanceRead, tag_name="出场作品",
    filters=_app_filters, order_by=m.Appearance.id, validate=_app_validate,
)

extra = APIRouter(tags=["角色百科"])


def _brief(c: m.Character) -> dict[str, Any]:
    return {"id": c.id, "name": c.name, "gender": c.gender, "avatar_asset_id": c.avatar_asset_id}


def _asset_brief(a: m.Asset) -> dict[str, Any]:
    return {"id": a.id, "title": a.title, "kind": a.kind, "width": a.width, "height": a.height, "work_date": a.work_date.isoformat() if a.work_date else None}


@extra.get("/api/worlds/{world_id}/timeline")
def timeline(world_id: int, session: Session = Depends(get_session)) -> list[dict[str, Any]]:
    """事件时间线：按 sort_key 排序（未填排在最后），附带参与角色与发生地点。"""
    get_or_404(session, m.World, world_id)
    events = session.scalars(select(m.WorldEntry).where(m.WorldEntry.world_id == world_id, m.WorldEntry.kind == "event")).all()
    events = sorted(events, key=lambda e: (e.sort_key is None, e.sort_key or 0, e.id))
    chars = {c.id: c for c in session.scalars(select(m.Character).where(m.Character.id.in_({l.character_id for e in events for l in e.links})))}
    out = []
    for e in events:
        place = session.get(m.WorldEntry, e.parent_id) if e.parent_id else None
        out.append({
            **s.WorldEntryRead.model_validate(e).model_dump(mode="json"),
            "place": {"id": place.id, "name": place.name, "kind": place.kind} if place else None,
            "characters": [{**_brief(chars[l.character_id]), "role": l.role} for l in e.links if l.character_id in chars],
        })
    return out


# ---------------- 角色图集 ----------------
class IdList(BaseModel):
    asset_ids: list[int]


def _gallery_ids(session: Session, cid: int) -> list[int]:
    t = m.character_assets
    return list(session.scalars(select(t.c.asset_id).where(t.c.character_id == cid).order_by(t.c.position)))


def _set_gallery(session: Session, cid: int, ids: list[int]) -> list[int]:
    ordered = list(dict.fromkeys(ids))
    found = set(session.scalars(select(m.Asset.id).where(m.Asset.id.in_(ordered))))
    if missing := [i for i in ordered if i not in found]:
        raise HTTPException(422, f"素材不存在: {missing}")
    t = m.character_assets
    session.execute(t.delete().where(t.c.character_id == cid))
    if ordered:
        session.execute(t.insert(), [{"character_id": cid, "asset_id": a, "position": i} for i, a in enumerate(ordered)])
    session.commit()
    return ordered


@extra.put("/api/characters/{character_id}/gallery")
def set_gallery(character_id: int, body: IdList, session: Session = Depends(get_session)) -> list[int]:
    """整体设置角色图集（顺序即展示顺序）。"""
    get_or_404(session, m.Character, character_id)
    return _set_gallery(session, character_id, body.asset_ids)


@extra.post("/api/characters/{character_id}/gallery")
def add_gallery(character_id: int, body: IdList, session: Session = Depends(get_session)) -> list[int]:
    get_or_404(session, m.Character, character_id)
    cur = _gallery_ids(session, character_id)
    return _set_gallery(session, character_id, cur + [i for i in body.asset_ids if i not in cur])


@extra.delete("/api/characters/{character_id}/gallery/{asset_id}")
def remove_gallery(character_id: int, asset_id: int, session: Session = Depends(get_session)) -> list[int]:
    get_or_404(session, m.Character, character_id)
    return _set_gallery(session, character_id, [i for i in _gallery_ids(session, character_id) if i != asset_id])


# ---------------- 角色详情 ----------------
@extra.get("/api/characters/{character_id}/detail")
def character_detail(character_id: int, session: Session = Depends(get_session)) -> dict[str, Any]:
    """角色详情页需要的一切：基本信息、图集、出场作品、关系、所属组织 / 参与事件 / 相关地点、角色卡。"""
    c = get_or_404(session, m.Character, character_id)
    world = session.get(m.World, c.world_id) if c.world_id else None
    gallery_ids = _gallery_ids(session, c.id)
    gallery_assets = {a.id: a for a in session.scalars(select(m.Asset).where(m.Asset.id.in_(gallery_ids)))}

    apps = session.scalars(select(m.Appearance).where(m.Appearance.character_id == c.id).order_by(m.Appearance.id)).all()
    works = {w.id: w for w in session.scalars(select(m.Work).where(m.Work.id.in_({a.work_id for a in apps} | ({c.work_id} if c.work_id else set()))))}
    appearances = [{"id": a.id, "role": a.role, "note": a.note, "work": s.WorkRead.model_validate(works[a.work_id]).model_dump(mode="json")} for a in apps if a.work_id in works]
    if c.work_id and c.work_id not in {a.work_id for a in apps} and c.work_id in works:
        appearances.insert(0, {"id": None, "role": "来源作品", "note": None, "work": s.WorkRead.model_validate(works[c.work_id]).model_dump(mode="json")})

    rels = session.scalars(select(m.Relation).where(or_(m.Relation.source_id == c.id, m.Relation.target_id == c.id))).all()
    other_ids = {r.target_id if r.source_id == c.id else r.source_id for r in rels}
    others = {o.id: o for o in session.scalars(select(m.Character).where(m.Character.id.in_(other_ids)))}
    relations = []
    for r in rels:
        outgoing = r.source_id == c.id
        o = others.get(r.target_id if outgoing else r.source_id)
        if o:
            relations.append({**s.RelationRead.model_validate(r).model_dump(mode="json"), "direction": "out" if outgoing else "in", "other": _brief(o)})

    linked = session.scalars(select(m.WorldEntry).where(m.WorldEntry.links.any(m.EntryCharacter.character_id == c.id))).all()
    entries: dict[str, list[dict[str, Any]]] = {}
    for e in sorted(linked, key=lambda e: (e.sort_key is None, e.sort_key or 0, e.name)):
        role = next((l.role for l in e.links if l.character_id == c.id), None)
        entries.setdefault(e.kind, []).append({"id": e.id, "name": e.name, "summary": e.summary, "date_label": e.date_label, "role": role})

    cards = session.scalars(select(m.CharacterCard).where(m.CharacterCard.character_id == c.id)).all()
    return {
        "character": s.CharacterRead.model_validate(c).model_dump(mode="json"),
        "world": {"id": world.id, "name": world.name} if world else None,
        "gallery": [_asset_brief(gallery_assets[i]) for i in gallery_ids if i in gallery_assets],
        "appearances": appearances,
        "relations": relations,
        "entries": entries,
        "cards": [{"id": k.id, "name": k.name} for k in cards],
    }


@extra.get("/api/works/{work_id}/characters")
def work_characters(work_id: int, session: Session = Depends(get_session)) -> list[dict[str, Any]]:
    """作品的登场角色：出场登记 + 来源作品为本作的角色。"""
    get_or_404(session, m.Work, work_id)
    apps = {a.character_id: a for a in session.scalars(select(m.Appearance).where(m.Appearance.work_id == work_id))}
    chars = session.scalars(select(m.Character).where(or_(m.Character.id.in_(apps), m.Character.work_id == work_id)).order_by(m.Character.name)).all()
    return [{**_brief(ch), "role": apps[ch.id].role if ch.id in apps else "来源作品"} for ch in chars]
