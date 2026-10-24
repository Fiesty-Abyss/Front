"""把一个文件写入素材库：上传接口和本地文件夹批量导入共用这一套逻辑。"""

from __future__ import annotations

import hashlib
import io
import mimetypes
import os
import tempfile
import codecs
from datetime import date
from pathlib import Path
from typing import Any, BinaryIO

from PIL import Image
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import models as m
from .comfy import parse_comfy_chunks
from .config import get_settings
from .pngmeta import parse_sd_parameters, read_png_text

from .filetypes import IMAGE_EXT, KIND_BY_EXT, KNOWN_EXT, TEXT_EXT, analyze  # noqa: F401  (IMAGE_EXT 供 importer 使用)

IMPORTABLE_EXT = KNOWN_EXT
THUMB_SIZE = (480, 480)
for _ext, _mime in ((".glb", "model/gltf-binary"), (".vrm", "model/gltf-binary"), (".gltf", "model/gltf+json"), (".pmx", "application/octet-stream"),
                    (".fbx", "application/octet-stream"), (".obj", "model/obj"), (".flac", "audio/flac"), (".opus", "audio/ogg"),
                    (".m4a", "audio/mp4"), (".webm", "video/webm"), (".mkv", "video/x-matroska"), (".7z", "application/x-7z-compressed")):
    mimetypes.add_type(_mime, _ext)


def thumb_path(asset_id: int) -> Path:
    return get_settings().thumb_dir / f"{asset_id}.webp"


def write_thumb(asset_id: int, data: bytes | None) -> bool:
    if not data:
        return False
    make_thumb(asset_id, data)
    return thumb_path(asset_id).is_file()


def make_thumb(asset_id: int, data: bytes | Path) -> None:
    try:
        with Image.open(io.BytesIO(data) if isinstance(data, bytes) else data) as img:
            img.thumbnail(THUMB_SIZE)
            if img.mode not in ("RGB", "RGBA"):
                img = img.convert("RGBA")
            path = thumb_path(asset_id)
            path.parent.mkdir(parents=True, exist_ok=True)
            img.save(path, "WEBP", quality=82)
    except Exception:
        pass


def decode_text(data: bytes, *, truncated: bool = False) -> str:
    encodings = ('utf-16',) if data.startswith((b'\xff\xfe', b'\xfe\xff')) else ("utf-8-sig", "gb18030", "shift_jis", "utf-16")
    for enc in encodings:
        try:
            return codecs.getincrementaldecoder(enc)().decode(data, final=not truncated)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def image_generation_meta(data: bytes | Path) -> dict[str, Any] | None:
    """识别 AI 出图信息：SD WebUI / Forge 的 parameters，或 ComfyUI 的 prompt / workflow。"""
    chunks = read_png_text(data)
    if chunks.get("parameters"):
        parsed = parse_sd_parameters(chunks["parameters"])
        parsed["source"] = "a1111"
        return parsed
    return parse_comfy_chunks(chunks)


def find_duplicate(session: Session, sha: str) -> m.Asset | None:
    return session.scalar(select(m.Asset).where(m.Asset.sha256 == sha))


def ingest_stream(
    session: Session,
    data: BinaryIO,
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
    expected_sha: str | None = None,
) -> tuple[m.Asset, bool]:
    """返回 (素材, 是否新建)。相同内容的文件已存在时直接返回旧素材，不重复写盘。
    调用方负责 commit；缩略图在 commit 后用 make_thumb 生成。"""
    settings = get_settings()
    staging = settings.data_dir / '.staging'
    staging.mkdir(parents=True, exist_ok=True)
    digest, size = hashlib.sha256(), 0
    staged = None
    try:
        with tempfile.NamedTemporaryFile(dir=staging, delete=False) as handle:
            staged = Path(handle.name)
            while chunk := data.read(1024 * 1024):
                size += len(chunk)
                if size > settings.max_upload_mb * 1024 * 1024:
                    from fastapi import HTTPException
                    raise HTTPException(413, f'文件超过 {settings.max_upload_mb} MB')
                digest.update(chunk)
                handle.write(chunk)
            handle.flush()
            os.fsync(handle.fileno())
        sha = digest.hexdigest()
        if expected_sha is not None and sha != expected_sha:
            from fastapi import HTTPException
            raise HTTPException(409, '原文件内容与预览不一致，请重新预览')
        dup = find_duplicate(session, sha)
        if dup and dup.file_path:
            return dup, False
        ext = Path(name).suffix.lower()
        rel = Path('media') / date.today().strftime('%Y/%m') / f'{sha}{ext}'
        dest = settings.data_dir / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        if not dest.exists():
            os.replace(staged, dest)
    finally:
        if staged is not None:
            staged.unlink(missing_ok=True)

    if dup:
        dup.file_path = rel.as_posix()
        return dup, False
    return _register(session, dest, name, sha, size, rel, mime=mime, kind=kind, title=title,
                     description=description, source=source, work_date=work_date, work_id=work_id,
                     world_id=world_id, tags=tags, extra_meta=extra_meta)


def _register(session, dest, name, sha, size, rel, *, mime=None, kind=None, title=None,
              description=None, source=None, work_date=None, work_id=None, world_id=None,
              tags=None, extra_meta=None):
    settings = get_settings()

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
        size=size,
        sha256=sha,
        meta=dict(extra_meta or {}),
    )
    if tags:
        asset.tags = list(tags)

    asset.file_path = rel.as_posix() if rel else None
    pending_thumb = None

    if ext in TEXT_EXT or (mime.startswith("text/") and ext not in KIND_BY_EXT):
        asset.kind = kind or "novel"
        with dest.open('rb') as handle:
            asset.content = decode_text(handle.read(4 * 1024 * 1024), truncated=size > 4 * 1024 * 1024)
        if size > 4 * 1024 * 1024:
            asset.meta = {**asset.meta, 'text_truncated': True, 'preview_note': '正文预览限制为 4 MiB，原文件完整保留'}
    elif ext in KIND_BY_EXT or ext == ".zip":
        info = analyze(dest, name)
        asset.kind = info.kind or kind or "other"  # 识别出的文件类型优先（上传表单的默认类型是给图片用的）
        asset.meta = {**asset.meta, "file": info.meta}
        asset.content = info.content
        if info.title and not title:
            asset.title = info.title[:200]
        pending_thumb = info.thumb
    else:
        asset.kind = kind or "other"
        try:
            with Image.open(dest) as img:
                asset.width, asset.height = img.size
            if not kind:
                asset.kind = "drawing"
        except Exception:
            pass
        gen = image_generation_meta(dest) if asset.width else None
        if gen:
            asset.meta = {**asset.meta, "sd": gen, "prompt": gen.get("prompt")}
            if not kind:
                asset.kind = "ai_image"

    session.add(asset)
    session.flush()
    if pending_thumb:
        write_thumb(asset.id, pending_thumb)
    return asset, True


def ingest(session: Session, data: bytes, name: str, **kwargs) -> tuple[m.Asset, bool]:
    """Compatibility entry for existing in-memory AI outputs and small fixtures."""
    return ingest_stream(session, io.BytesIO(data), name, **kwargs)


def index_file(session, path: Path, root: Path, expected_sha: str, check=lambda: None):
    from .projectpreview import stamp
    before = stamp(path)
    hasher = hashlib.sha256()
    with path.open('rb') as handle:
        while chunk := handle.read(1024 * 1024):
            check(); hasher.update(chunk)
    if stamp(path) != before or hasher.hexdigest() != expected_sha:
        from fastapi import HTTPException
        raise HTTPException(409,'原文件内容与预览不一致，请重新预览')
    asset = find_duplicate(session, expected_sha)
    if asset:
        if not asset.file_path:
            binding=session.get(m.ExternalAssetFile,asset.id)
            if binding is not None:
                old=Path(binding.path)
                if not old.is_file() or stamp(old)!=binding.stamp:
                    binding.path=str(path);binding.root=str(root);binding.stamp=before
        return asset, False
    asset, created = _register(session,path,path.name,expected_sha,before[0],None,source=str(path),work_date=date.fromtimestamp(path.stat().st_mtime))
    session.add(m.ExternalAssetFile(asset_id=asset.id,path=str(path),root=str(root),stamp=before))
    return asset, created
