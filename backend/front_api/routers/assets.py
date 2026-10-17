"""素材库：上传、按日期/类型/标签/作品筛选、全文检索、缩略图、时间线。"""

from __future__ import annotations

import hashlib
from datetime import date
from pathlib import Path
from typing import Any
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response
from sqlalchemy import extract, func, select
from sqlalchemy.orm import Session

from .. import models as m
from .. import schemas as s
from ..config import get_settings
from ..crud import get_or_404, make_crud_router, qp, resolve_tags
from ..db import get_session
from ..chapters import chapter_text, split_chapters
from ..ingest import find_duplicate, ingest, make_thumb, thumb_path
from ..pngmeta import read_png_text


def _filters(stmt, request):
    if kind := qp(request, "kind"):
        stmt = stmt.where(m.Asset.kind.in_(kind.split(",")))
    if work := qp(request, "work_id"):
        stmt = stmt.where(m.Asset.work_id == int(work))
    if world := qp(request, "world_id"):
        stmt = stmt.where(m.Asset.world_id == int(world))
    if dfrom := qp(request, "date_from"):
        stmt = stmt.where(m.Asset.work_date >= date.fromisoformat(dfrom))
    if dto := qp(request, "date_to"):
        stmt = stmt.where(m.Asset.work_date <= date.fromisoformat(dto))
    if year := qp(request, "year"):
        stmt = stmt.where(extract("year", m.Asset.work_date) == int(year))
    if month := qp(request, "month"):
        stmt = stmt.where(extract("month", m.Asset.work_date) == int(month))
    if (has_file := qp(request, "has_file")) is not None:
        stmt = stmt.where(m.Asset.file_path.is_not(None) if has_file == "true" else m.Asset.file_path.is_(None))
    return stmt


router = make_crud_router(
    prefix="/api/assets", model=m.Asset, create_schema=s.AssetCreate, update_schema=s.AssetUpdate,
    read_schema=s.AssetRead, tag_name="素材库", filters=_filters,
    order_by=(m.Asset.work_date.desc().nulls_last(), m.Asset.id.desc()),
)

files = APIRouter(prefix="/api/assets", tags=["素材库"])


def _thumb_path(asset_id: int) -> Path:
    return thumb_path(asset_id)


def _make_thumb(asset_id: int, data: bytes) -> None:
    make_thumb(asset_id, data)


@files.get("/stats/timeline")
def timeline(session: Session = Depends(get_session)) -> list[dict[str, Any]]:
    """按 年-月 × 类型 统计素材数量，用于时间线/日期分类导航。"""
    ym = func.strftime("%Y-%m", m.Asset.work_date)
    rows = session.execute(
        select(ym.label("ym"), m.Asset.kind, func.count()).group_by("ym", m.Asset.kind).order_by(ym.desc())
    ).all()
    return [{"month": r[0] or "未标日期", "kind": r[1], "count": r[2]} for r in rows]


@files.post("/upload", response_model=s.AssetRead, status_code=201)
async def upload(
    file: UploadFile = File(...),
    title: str | None = Form(None),
    kind: str | None = Form(None),
    description: str | None = Form(None),
    source: str | None = Form(None),
    work_date: date | None = Form(None),
    work_id: int | None = Form(None),
    world_id: int | None = Form(None),
    tag_ids: str | None = Form(None),
    session: Session = Depends(get_session),
) -> Any:
    settings = get_settings()
    data = await file.read()
    if len(data) > settings.max_upload_mb * 1024 * 1024:
        raise HTTPException(413, f"文件超过 {settings.max_upload_mb} MB")
    dup = find_duplicate(session, hashlib.sha256(data).hexdigest())
    if dup:
        raise HTTPException(409, {"message": "相同文件已存在", "asset_id": dup.id})
    tags = resolve_tags(session, [int(x) for x in tag_ids.split(",") if x.strip()]) if tag_ids else None
    asset, _ = ingest(
        session, data, file.filename or "upload", mime=file.content_type, kind=kind or None, title=title,
        description=description, source=source, work_date=work_date, work_id=work_id, world_id=world_id, tags=tags,
    )
    session.commit()
    session.refresh(asset)
    if asset.width:
        make_thumb(asset.id, data)
    return asset


def _file_of(asset: m.Asset) -> Path:
    if not asset.file_path:
        raise HTTPException(404, "该素材没有文件")
    root = get_settings().data_dir.resolve()
    path = (root / asset.file_path).resolve()
    if root not in path.parents or not path.is_file():
        raise HTTPException(404, "文件不存在")
    return path


@files.get("/{asset_id}/file")
def get_file(asset_id: int, session: Session = Depends(get_session)) -> FileResponse:
    asset = get_or_404(session, m.Asset, asset_id)
    return FileResponse(_file_of(asset), media_type=asset.mime, filename=asset.original_name)


@files.get("/{asset_id}/thumb")
def get_thumb(asset_id: int, session: Session = Depends(get_session)) -> FileResponse:
    asset = get_or_404(session, m.Asset, asset_id)
    thumb = _thumb_path(asset_id)
    if not thumb.is_file():
        path = _file_of(asset)
        _make_thumb(asset_id, path.read_bytes())
    if not thumb.is_file():
        raise HTTPException(404, "无法生成缩略图")
    return FileResponse(thumb, media_type="image/webp")


@files.delete("/{asset_id}/file", status_code=204)
def delete_file(asset_id: int, session: Session = Depends(get_session)) -> None:
    """删除素材的文件（保留条目）。删除整个条目请用 DELETE /api/assets/{id}。"""
    asset = get_or_404(session, m.Asset, asset_id)
    _remove_files(session, asset)
    asset.file_path = None
    session.commit()


def _remove_files(session: Session, asset: m.Asset) -> None:
    if asset.file_path:
        others = session.scalar(
            select(func.count()).where(m.Asset.file_path == asset.file_path, m.Asset.id != asset.id)
        )
        if not others:
            (get_settings().data_dir / asset.file_path).unlink(missing_ok=True)
    _thumb_path(asset.id).unlink(missing_ok=True)


def install_delete_hook() -> None:
    """删除素材条目时同时清理磁盘上的文件和缩略图。"""
    from sqlalchemy import event

    @event.listens_for(m.Asset, "after_delete")
    def _after_delete(_mapper, _conn, target: m.Asset) -> None:
        if target.file_path:
            path = get_settings().data_dir / target.file_path
            # after_delete 内不再查询；同哈希文件不会重复入库，因此路径唯一
            path.unlink(missing_ok=True)
        _thumb_path(target.id).unlink(missing_ok=True)


# ---------------- 小说：章节与阅读 ----------------
def _novel_text(session: Session, asset_id: int) -> tuple[m.Asset, str]:
    asset = get_or_404(session, m.Asset, asset_id)
    if not asset.content:
        raise HTTPException(422, "该素材没有正文")
    return asset, asset.content


@files.get("/{asset_id}/chapters")
def chapters(asset_id: int, session: Session = Depends(get_session)) -> dict[str, Any]:
    """目录：自动识别“第X章 / Chapter N / Markdown 标题 / 序章 尾声”等。"""
    asset, text = _novel_text(session, asset_id)
    toc = split_chapters(text)
    return {
        "asset_id": asset.id,
        "title": asset.title,
        "words": sum(c["words"] for c in toc),
        "chapters": [{k: c[k] for k in ("index", "title", "words")} for c in toc],
    }


@files.get("/{asset_id}/chapters/{index}")
def chapter(asset_id: int, index: int, session: Session = Depends(get_session)) -> dict[str, Any]:
    asset, text = _novel_text(session, asset_id)
    toc = split_chapters(text)
    if not 0 <= index < len(toc):
        raise HTTPException(404, "章节不存在")
    ch = toc[index]
    return {
        "asset_id": asset.id,
        "book_title": asset.title,
        "index": index,
        "total": len(toc),
        "title": ch["title"],
        "words": ch["words"],
        "content": chapter_text(text, ch),
        "prev": index - 1 if index > 0 else None,
        "next": index + 1 if index + 1 < len(toc) else None,
    }


# ---------------- AI 图：原始工作流 ----------------
@files.get("/{asset_id}/workflow")
def workflow(asset_id: int, session: Session = Depends(get_session)) -> Response:
    """下载 PNG 里内嵌的 ComfyUI 工作流（可直接拖回 ComfyUI）。"""
    asset = get_or_404(session, m.Asset, asset_id)
    chunks = read_png_text(_file_of(asset).read_bytes())
    raw = chunks.get("workflow") or chunks.get("prompt")
    if not raw:
        raise HTTPException(404, "这张图里没有 ComfyUI 工作流")
    name = Path(asset.original_name or f"asset-{asset.id}").stem + ".workflow.json"
    return Response(raw, media_type="application/json", headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(name)}"})
