"""素材库：上传、按日期/类型/标签/作品筛选、全文检索、缩略图、时间线。"""

from __future__ import annotations

import hashlib
import mimetypes
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
from ..filetypes import FILE_KINDS, KIND_BY_EXT, analyze
from ..filetypes.archive import read_entry
from ..filetypes.docs import render_pdf_page
from ..filetypes.util import is_image
from ..ingest import find_duplicate, ingest, make_thumb, thumb_path, write_thumb
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


def _trim(d: dict[str, Any]) -> dict[str, Any]:
    """列表里不带大段的文件正文 / 预览（PDF、代码、压缩包目录），打开详情时再取。"""
    f = (d.get("meta") or {}).get("file")
    if f:
        d["content"] = None
        d["meta"] = {**d["meta"], "file": {k: v for k, v in f.items() if k not in ("preview", "entries", "motion_files", "material_names", "textures")}}
    return d


router = make_crud_router(
    list_trim=_trim,
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
def get_file(asset_id: int, inline: bool = False, session: Session = Depends(get_session)) -> FileResponse:
    """inline=1 时在浏览器里直接打开（PDF、音视频）；支持 Range，音视频可以拖动进度。"""
    asset = get_or_404(session, m.Asset, asset_id)
    return FileResponse(_file_of(asset), media_type=asset.mime, filename=asset.original_name,
                        content_disposition_type="inline" if inline else "attachment")


@files.get("/{asset_id}/entry/{entry:path}")
def get_entry(asset_id: int, entry: str, session: Session = Depends(get_session)) -> Response:
    """读取模型包（zip）里的单个文件，供浏览器里的 3D / Live2D 预览加载贴图、动作等。只读，不解压到磁盘。"""
    asset = get_or_404(session, m.Asset, asset_id)
    path = _file_of(asset)
    if not ((asset.meta or {}).get("file") or {}).get("bundle") and (asset.meta or {}).get("file", {}).get("format") != "zip":
        raise HTTPException(404, "这个素材不是压缩包")
    try:
        data = read_entry(path, entry)
    except KeyError:
        raise HTTPException(404, f"包里没有 {entry}") from None
    except ValueError as exc:
        raise HTTPException(413, str(exc)) from None
    mime = mimetypes.guess_type(entry)[0] or "application/octet-stream"
    return Response(data, media_type=mime, headers={"Cache-Control": "private, max-age=3600"})


@files.get("/{asset_id}/pdf/{page}")
def pdf_page(asset_id: int, page: int, width: int = 1100, session: Session = Depends(get_session)) -> Response:
    """把 PDF 的某一页渲染成图片（页码从 1 开始）。"""
    asset = get_or_404(session, m.Asset, asset_id)
    pages = ((asset.meta or {}).get("file") or {}).get("pages") or 0
    if asset.kind != "pdf" or not 1 <= page <= pages:
        raise HTTPException(404, "没有这一页")
    data = render_pdf_page(_file_of(asset), page - 1, max(200, min(width, 2400)))
    return Response(data, media_type="image/webp", headers={"Cache-Control": "private, max-age=86400"})


@files.put("/{asset_id}/thumb", response_model=s.AssetRead)
async def set_thumb(asset_id: int, file: UploadFile = File(...), session: Session = Depends(get_session)) -> Any:
    """用浏览器里截下的画面做封面（3D 模型预览里的“设为封面”）。"""
    asset = get_or_404(session, m.Asset, asset_id)
    data = await file.read()
    if len(data) > 8 * 1024 * 1024 or not is_image(data) or not write_thumb(asset.id, data):
        raise HTTPException(422, "封面必须是 8 MB 以内的图片")
    meta = dict(asset.meta or {})
    meta["file"] = {**(meta.get("file") or {}), "thumb": True, "custom_thumb": True}
    asset.meta = meta
    session.commit()
    session.refresh(asset)
    return asset


def reanalyze_asset(asset: m.Asset) -> bool:
    name = asset.original_name or asset.file_path or ""
    ext = Path(name).suffix.lower()
    if not asset.file_path or not (ext in KIND_BY_EXT or ext == ".zip"):
        return False
    info = analyze(_file_of(asset), name)
    meta = dict(asset.meta or {})
    custom = (meta.get("file") or {}).get("custom_thumb")
    meta["file"] = {**info.meta, **({"thumb": True, "custom_thumb": True} if custom else {})}
    asset.meta = meta
    if info.kind and asset.kind in ("other", "material", "reference", "drawing", "cg", "novel", *FILE_KINDS):
        asset.kind = info.kind
    if info.content:
        asset.content = info.content
    if info.thumb and not custom:
        write_thumb(asset.id, info.thumb)
    return True


@files.post("/{asset_id}/reanalyze", response_model=s.AssetRead)
def reanalyze_one(asset_id: int, session: Session = Depends(get_session)) -> Any:
    asset = get_or_404(session, m.Asset, asset_id)
    if not reanalyze_asset(asset):
        raise HTTPException(422, "这个文件类型没有可提取的信息")
    session.commit()
    session.refresh(asset)
    return asset


@files.post("/reanalyze")
def reanalyze_missing(session: Session = Depends(get_session)) -> dict[str, Any]:
    """给旧版本导入、还没有文件信息的素材补上识别结果（例如 v0.5 导入的压缩包、音频）。"""
    done = 0
    for asset in session.scalars(select(m.Asset).where(m.Asset.file_path.is_not(None), m.Asset.width.is_(None))).all():
        if not ((asset.meta or {}).get("file")) and reanalyze_asset(asset):
            done += 1
            if done % 20 == 0:
                session.commit()
    session.commit()
    return {"updated": done}


@files.get("/{asset_id}/thumb")
def get_thumb(asset_id: int, session: Session = Depends(get_session)) -> FileResponse:
    asset = get_or_404(session, m.Asset, asset_id)
    thumb = _thumb_path(asset_id)
    if not thumb.is_file():
        path = _file_of(asset)
        if asset.width:
            _make_thumb(asset_id, path.read_bytes())
        elif ((asset.meta or {}).get("file") or {}).get("thumb"):
            name = asset.original_name or path.name
            write_thumb(asset_id, analyze(path, name).thumb)
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
