"""Portable, read-only Markdown exports of the encyclopedia."""

from __future__ import annotations

import io
import posixpath
import re
from zipfile import ZIP_DEFLATED, ZipFile

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from .. import models as m
from ..crud import get_or_404
from ..db import get_session

router = APIRouter(prefix="/api/exports", tags=["数据导出"])
KINDS = {"location": "地点", "organization": "组织", "event": "事件", "item": "物品", "concept": "概念"}
GENDERS = {"male": "男", "female": "女", "other": "其他", "unknown": "未知"}


def text(value) -> str:
    """Escape generated Markdown labels; authored Markdown bodies stay untouched."""
    return re.sub(r"([\\`*_{}\[\]<>()#!|])", r"\\\1", " ".join(str(value or "").split()))


@router.get("/encyclopedia")
def encyclopedia(world_id: int | None = None, session: Session = Depends(get_session)) -> Response:
    if world_id is not None:
        get_or_404(session, m.World, world_id)
    worlds_query = select(m.World).order_by(m.World.id)
    if world_id is not None:
        worlds_query = worlds_query.where(m.World.id == world_id)
    worlds = list(session.scalars(worlds_query))
    chars_query = select(m.Character).order_by(m.Character.id)
    entries_query = select(m.WorldEntry).order_by(m.WorldEntry.kind, m.WorldEntry.sort_key, m.WorldEntry.id)
    if world_id is not None:
        chars_query = chars_query.where(m.Character.world_id == world_id)
        entries_query = entries_query.where(m.WorldEntry.world_id == world_id)
    chars = list(session.scalars(chars_query))
    entries = list(session.scalars(entries_query))
    entries.sort(key=lambda e: (e.kind, e.sort_key is None, e.sort_key or 0, e.id))
    char_ids = {c.id for c in chars}
    relations = list(session.scalars(select(m.Relation).where(or_(
        m.Relation.source_id.in_(char_ids), m.Relation.target_id.in_(char_ids)
    )).order_by(m.Relation.id)))
    # Resolve external names without exporting their full profiles or creating broken links.
    referenced = char_ids | {l.character_id for e in entries for l in e.links}
    referenced |= {r.source_id for r in relations} | {r.target_id for r in relations}
    all_chars = {c.id: c for c in session.scalars(select(m.Character).where(m.Character.id.in_(referenced)))}
    works = {w.id: w for w in session.scalars(select(m.Work))}
    appearances = list(session.scalars(select(m.Appearance).where(
        m.Appearance.character_id.in_(char_ids)).order_by(m.Appearance.id)))
    paths = {("world", w.id): f"worlds/{w.id}.md" for w in worlds}
    paths.update({("character", c.id): f"characters/{c.id}.md" for c in chars})
    paths.update({("entry", e.id): f"entries/{e.id}.md" for e in entries})

    def link(kind, obj, origin="README.md"):
        label = text(obj.name)
        target = paths.get((kind, obj.id))
        return f"[{label}]({posixpath.relpath(target, posixpath.dirname(origin) or '.')})" if target else label

    def header(obj):
        parts = [f"# {text(obj.name)}", f"Front ID：{obj.id}"]
        if obj.tags:
            parts.append("标签：" + "、".join(text(t.name) for t in obj.tags))
        if obj.summary:
            parts.extend(["## 简介", obj.summary])
        return parts

    def section(parts, title, rows):
        if rows:
            parts.extend([f"## {title}", "\n".join(f"- {row}" for row in rows)])

    docs = {}
    for w in worlds:
        path = paths["world", w.id]
        parts = header(w)
        if w.content:
            parts.extend(["## 设定正文", w.content])
        section(parts, "角色", [link("character", c, path) for c in chars if c.world_id == w.id])
        for kind, label in KINDS.items():
            section(parts, label, [link("entry", e, path) for e in entries if e.world_id == w.id and e.kind == kind])
        docs[path] = parts
    for c in chars:
        path = paths["character", c.id]
        parts = header(c)
        parts.append("性别：" + text(GENDERS.get(c.gender, c.gender)))
        if c.alias:
            parts.append("别名：" + text(c.alias))
        world = next((w for w in worlds if w.id == c.world_id), None)
        if world:
            parts.append("世界观：" + link("world", world, path))
        if c.profile:
            parts.extend(["## 角色设定", c.profile])
        apps = [a for a in appearances if a.character_id == c.id]
        rows = [f"{text(works[a.work_id].title)} · {text(a.role)}" + (f"：{text(a.note)}" if a.note else "") for a in apps if a.work_id in works]
        if c.work_id in works and not any(a.work_id == c.work_id for a in apps):
            rows.insert(0, text(works[c.work_id].title) + " · 来源作品")
        section(parts, "出场作品", rows)
        rows = []
        for r in relations:
            if c.id not in (r.source_id, r.target_id):
                continue
            source, target = all_chars.get(r.source_id), all_chars.get(r.target_id)
            if source is None or target is None:
                continue
            status = "已确认" if r.confirmed else ("AI 待确认" if r.ai_suggested else "待确认")
            rows.append(f"{link('character', source, path)} {'↔' if r.bidirectional else '→'} {link('character', target, path)} · {text(r.kind)}（{status}）" + (f"：{text(r.description)}" if r.description else ""))
        section(parts, "角色关系", rows)
        section(parts, "相关条目", [link("entry", e, path) + (f" · {text(l.role)}" if l.role else "") for e in entries for l in e.links if l.character_id == c.id])
        docs[path] = parts
    for e in entries:
        path = paths["entry", e.id]
        parts = header(e)
        parts.append("类型：" + KINDS.get(e.kind, text(e.kind)))
        world = next(w for w in worlds if w.id == e.world_id)
        parts.append("世界观：" + link("world", world, path))
        parent = session.get(m.WorldEntry, e.parent_id) if e.parent_id else None
        if parent:
            parts.append(("发生地点：" if e.kind == "event" else "上级条目：") + link("entry", parent, path))
        if e.date_label:
            parts.append("时间：" + text(e.date_label))
        if e.sort_key is not None:
            parts.append(f"时间排序值：{e.sort_key}")
        if e.content:
            parts.extend(["## 正文", e.content])
        section(parts, "相关角色", [link("character", all_chars[l.character_id], path) + (f" · {text(l.role)}" if l.role else "") for l in e.links if l.character_id in all_chars])
        docs[path] = parts
    index = ["# Front 百科导出", "范围：" + (text(worlds[0].name) if world_id is not None else "全部百科"),
             f"世界观 {len(worlds)} · 角色 {len(chars)} · 条目 {len(entries)}",
             "这是用于离线阅读的 Markdown 文本导出，不是可还原的整库备份。图片、模型、笔记、角色卡、对话与 API Key 不包含在内。正文按原文保留，其中的 [[站内链接]]、素材引用和网址不会转换或下载。未保存的编辑不包含在内。",
             "文件名使用 Front ID，重名和特殊字符不会覆盖文件。生成的目录链接可在解压后离线打开；范围外的关联仅保留名称。"]
    section(index, "世界观", [link("world", w) for w in worlds])
    section(index, "角色", [link("character", c) for c in chars])
    section(index, "条目", [link("entry", e) for e in entries])
    docs["README.md"] = index
    buf = io.BytesIO()
    with ZipFile(buf, "w", compression=ZIP_DEFLATED) as archive:
        for path, parts in docs.items():
            archive.writestr(path, "\n\n".join(parts).rstrip() + "\n")
    filename = f"front-encyclopedia-world-{world_id}.zip" if world_id is not None else "front-encyclopedia.zip"
    return Response(buf.getvalue(), media_type="application/zip", headers={
        "Content-Disposition": f'attachment; filename="{filename}"', "Cache-Control": "no-store",
    })
