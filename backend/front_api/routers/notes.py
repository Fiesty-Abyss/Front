"""超级笔记本：笔记的增删改查、树形目录、引用关系。"""

from __future__ import annotations

import re
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models as m
from .. import schemas as s
from ..crud import get_or_404, make_crud_router, qp
from ..db import get_session


def _filters(stmt, request):
    if (parent := qp(request, "parent_id")) is not None:
        stmt = stmt.where(m.Note.parent_id.is_(None) if parent in ("", "root") else m.Note.parent_id == int(parent))
    if work := qp(request, "work_id"):
        stmt = stmt.where(m.Note.work_id == int(work))
    return stmt


crud = make_crud_router(
    prefix="/api/notes", model=m.Note, create_schema=s.NoteCreate, update_schema=s.NoteUpdate, read_schema=s.NoteRead,
    tag_name="笔记本", filters=_filters, order_by=(m.Note.pinned.desc(), m.Note.position, m.Note.updated_at.desc()),
)
extra = APIRouter(prefix="/api/notes", tags=["笔记本"])
ASSET_REF = re.compile(r"/api/assets/(\d+)/|asset:(\d+)|/assets\?open=(\d+)")
NOTE_REF = re.compile(r"/notes/(\d+)")


@extra.get("/tree")
def tree(session: Session = Depends(get_session)) -> list[dict[str, Any]]:
    """侧栏目录：只返回标题等轻量字段，前端自己组装成树。"""
    rows = session.execute(select(m.Note.id, m.Note.title, m.Note.icon, m.Note.parent_id, m.Note.pinned, m.Note.position, m.Note.updated_at)
                           .order_by(m.Note.pinned.desc(), m.Note.position, m.Note.updated_at.desc())).all()
    return [{"id": r.id, "title": r.title, "icon": r.icon, "parent_id": r.parent_id, "pinned": r.pinned, "position": r.position,
             "updated_at": r.updated_at.isoformat() if r.updated_at else None} for r in rows]


@extra.post("/{note_id}/move")
def move(note_id: int, body: dict[str, Any], session: Session = Depends(get_session)) -> dict[str, Any]:
    note = get_or_404(session, m.Note, note_id)
    parent = body.get("parent_id")
    if parent is not None:
        p = get_or_404(session, m.Note, int(parent))
        while p is not None:  # 不能移到自己的子孙下面
            if p.id == note.id:
                raise HTTPException(422, "不能把笔记移到它自己的子页面里")
            p = session.get(m.Note, p.parent_id) if p.parent_id else None
    note.parent_id = parent
    if "position" in body:
        note.position = int(body["position"])
    session.commit()
    return {"id": note.id, "parent_id": note.parent_id, "position": note.position}


@extra.get("/{note_id}/refs")
def refs(note_id: int, session: Session = Depends(get_session)) -> dict[str, Any]:
    """这页笔记引用了哪些素材 / 笔记，以及哪些笔记引用了它（反向链接）。"""
    note = get_or_404(session, m.Note, note_id)
    asset_ids = sorted({int(x) for g in ASSET_REF.findall(note.content or "") for x in g if x})
    assets = session.scalars(select(m.Asset).where(m.Asset.id.in_(asset_ids))).all() if asset_ids else []
    back = [n for n in session.scalars(select(m.Note).where(m.Note.content.contains(f"/notes/{note_id}"))).all()
            if n.id != note_id and note_id in {int(x) for x in NOTE_REF.findall(n.content or "")}]
    def brief(a: m.Asset) -> dict[str, Any]:
        f = (a.meta or {}).get("file") or {}
        return {"id": a.id, "title": a.title, "kind": a.kind, "width": a.width, "updated_at": a.updated_at,
                "meta": {"file": {k: f[k] for k in ("thumb", "custom_thumb", "ext") if k in f}}}
    return {"assets": [brief(a) for a in assets],
            "backlinks": [{"id": n.id, "title": n.title, "icon": n.icon} for n in back]}
