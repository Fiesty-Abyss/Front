"""素材库：上传、按日期/类型/标签/作品筛选、全文检索、缩略图、时间线。"""

from __future__ import annotations

import hashlib
import io
import mimetypes
from datetime import date
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from PIL import Image
from sqlalchemy import extract, func, select
from sqlalchemy.orm import Session

from .. import models as m
from .. import schemas as s
from ..config import get_settings
from ..crud import get_or_404, make_crud_router, qp, resolve_tags
from ..db import get_session
from ..pngmeta import parse_sd_parameters, read_png_text

TEXT_EXT = {".txt", ".md", ".markdown"}
THUMB_SIZE = (480, 480)


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
    return get_settings().thumb_dir / f"{asset_id}.webp"


def _make_thumb(asset_id: int, data: bytes) -> None:
    try:
        with Image.open(io.BytesIO(data)) as img:
            img.thumbnail(THUMB_SIZE)
            if img.mode not in ("RGB", "RGBA"):
                img = img.convert("RGBA")
            path = _thumb_path(asset_id)
            path.parent.mkdir(parents=True, exist_ok=True)
            img.save(path, "WEBP", quality=82)
    except Exception:
        pass


def _decode_text(data: bytes) -> str:
    for enc in ("utf-8-sig", "gb18030", "shift_jis", "utf-16"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


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
    sha = hashlib.sha256(data).hexdigest()
    dup = session.scalar(select(m.Asset).where(m.Asset.sha256 == sha))
    if dup:
        raise HTTPException(409, {"message": "相同文件已存在", "asset_id": dup.id})

    name = file.filename or "upload"
    ext = Path(name).suffix.lower()
    mime = file.content_type or mimetypes.guess_type(name)[0] or "application/octet-stream"
    asset = m.Asset(
        title=title or Path(name).stem,
        description=description,
        source=source,
        work_date=work_date or date.today(),
        work_id=work_id,
        world_id=world_id,
        original_name=name,
        mime=mime,
        size=len(data),
        sha256=sha,
        meta={},
    )
    if tag_ids:
        asset.tags = resolve_tags(session, [int(x) for x in tag_ids.split(",") if x.strip()])

    if ext in TEXT_EXT or mime.startswith("text/"):
        asset.kind = kind or "novel"
        asset.content = _decode_text(data)
    else:
        asset.kind = kind or "other"
        try:
            with Image.open(io.BytesIO(data)) as img:
                asset.width, asset.height = img.size
            if not kind:
                asset.kind = "drawing"
        except Exception:
            pass
        params_text = read_png_text(data).get("parameters")
        if params_text:
            parsed = parse_sd_parameters(params_text)
            asset.meta = {"sd": parsed, "prompt": parsed.get("prompt")}
            if not kind:
                asset.kind = "ai_image"

    rel = Path("media") / date.today().strftime("%Y/%m") / f"{sha[:20]}{ext}"
    dest = settings.data_dir / rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)
    asset.file_path = rel.as_posix()

    session.add(asset)
    session.commit()
    session.refresh(asset)
    if asset.width:
        _make_thumb(asset.id, data)
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
