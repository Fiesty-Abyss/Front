"""把一个文件写入素材库：上传接口和本地文件夹批量导入共用这一套逻辑。"""

from __future__ import annotations

import hashlib
import io
import mimetypes
from datetime import date
from pathlib import Path
from typing import Any

from PIL import Image
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import models as m
from .comfy import parse_comfy_chunks
from .config import get_settings
from .pngmeta import parse_sd_parameters, read_png_text

IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"}
TEXT_EXT = {".txt", ".md", ".markdown"}
IMPORTABLE_EXT = IMAGE_EXT | TEXT_EXT
THUMB_SIZE = (480, 480)


def thumb_path(asset_id: int) -> Path:
    return get_settings().thumb_dir / f"{asset_id}.webp"


def make_thumb(asset_id: int, data: bytes) -> None:
    try:
        with Image.open(io.BytesIO(data)) as img:
            img.thumbnail(THUMB_SIZE)
            if img.mode not in ("RGB", "RGBA"):
                img = img.convert("RGBA")
            path = thumb_path(asset_id)
            path.parent.mkdir(parents=True, exist_ok=True)
            img.save(path, "WEBP", quality=82)
    except Exception:
        pass


def decode_text(data: bytes) -> str:
    for enc in ("utf-8-sig", "gb18030", "shift_jis", "utf-16"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def image_generation_meta(data: bytes) -> dict[str, Any] | None:
    """识别 AI 出图信息：SD WebUI / Forge 的 parameters，或 ComfyUI 的 prompt / workflow。"""
    chunks = read_png_text(data)
    if chunks.get("parameters"):
        parsed = parse_sd_parameters(chunks["parameters"])
        parsed["source"] = "a1111"
        return parsed
    return parse_comfy_chunks(chunks)


def find_duplicate(session: Session, sha: str) -> m.Asset | None:
    return session.scalar(select(m.Asset).where(m.Asset.sha256 == sha))


def ingest(
    session: Session,
    data: bytes,
    name: str,
    *,
    mime: str | None = None,
    kind: str | None = None,
    title: str | None = None,
    description: str | None = None,
    source: str | None = None,
    work_date: date | None = None,
    work_id: int | None = None,
    world_id: int | None = None,
    tags: list[m.Tag] | None = None,
    extra_meta: dict[str, Any] | None = None,
) -> tuple[m.Asset, bool]:
    """返回 (素材, 是否新建)。相同内容的文件已存在时直接返回旧素材，不重复写盘。
    调用方负责 commit；缩略图在 commit 后用 make_thumb 生成。"""
    settings = get_settings()
    sha = hashlib.sha256(data).hexdigest()
    dup = find_duplicate(session, sha)
    if dup:
        return dup, False

    ext = Path(name).suffix.lower()
    mime = mime or mimetypes.guess_type(name)[0] or "application/octet-stream"
    asset = m.Asset(
        title=title or Path(name).stem,
        description=description,
        source=source,
        work_date=work_date or date.today(),
        work_id=work_id,
        world_id=world_id,
        original_name=Path(name).name,
        mime=mime,
        size=len(data),
        sha256=sha,
        meta=dict(extra_meta or {}),
    )
    if tags:
        asset.tags = list(tags)

    if ext in TEXT_EXT or mime.startswith("text/"):
        asset.kind = kind or "novel"
        asset.content = decode_text(data)
    else:
        asset.kind = kind or "other"
        try:
            with Image.open(io.BytesIO(data)) as img:
                asset.width, asset.height = img.size
            if not kind:
                asset.kind = "drawing"
        except Exception:
            pass
        gen = image_generation_meta(data) if asset.width else None
        if gen:
            asset.meta = {**asset.meta, "sd": gen, "prompt": gen.get("prompt")}
            if not kind:
                asset.kind = "ai_image"

    rel = Path("media") / date.today().strftime("%Y/%m") / f"{sha[:20]}{ext}"
    dest = settings.data_dir / rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    if not dest.exists():
        dest.write_bytes(data)
    asset.file_path = rel.as_posix()
    session.add(asset)
    session.flush()
    return asset, True
