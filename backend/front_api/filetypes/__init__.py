"""识别各种文件并提取元数据 / 缩略图 / 可检索的文字。

analyze(path, name) 返回 Analysis：素材类型、写入 asset.meta["file"] 的元数据、缩略图字节、正文（用于全文检索）。
全部是纯读取：不执行文件里的任何内容，压缩包也不会解压到磁盘。所有解析失败都安静地降级为“只有文件信息”。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import archive, audio, code, docs, live2d, model3d, video

IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"}
TEXT_EXT = {".txt", ".md", ".markdown"}

KIND_BY_EXT: dict[str, str] = {}
for _ext in model3d.EXT:
    KIND_BY_EXT[_ext] = "model3d"
for _ext in audio.EXT:
    KIND_BY_EXT[_ext] = "audio"
for _ext in video.EXT:
    KIND_BY_EXT[_ext] = "video"
KIND_BY_EXT[".pdf"] = "pdf"
for _ext in docs.OFFICE_EXT:
    KIND_BY_EXT[_ext] = "document"
for _ext in archive.EXT:
    KIND_BY_EXT[_ext] = "archive"
for _ext in code.EXT:
    KIND_BY_EXT[_ext] = "code"
for _ext in live2d.EXT:
    KIND_BY_EXT[_ext] = "live2d"

FILE_KINDS = ("model3d", "live2d", "audio", "video", "pdf", "document", "archive", "code")
KNOWN_EXT = IMAGE_EXT | TEXT_EXT | set(KIND_BY_EXT)


@dataclass
class Analysis:
    kind: str | None = None
    meta: dict[str, Any] = field(default_factory=dict)
    thumb: bytes | None = None
    content: str | None = None
    title: str | None = None


def analyze(path: Path, name: str) -> Analysis:
    ext = Path(name).suffix.lower()
    kind = KIND_BY_EXT.get(ext)
    out = Analysis(kind=kind)
    try:
        if ext == ".zip":
            bundle = archive.detect_bundle(path)
            if bundle:
                out.kind = bundle["kind"]
                handler = live2d.analyze_zip if bundle["kind"] == "live2d" else model3d.analyze_zip
                handler(path, bundle, out)
                return _finish(out, ext)
        if kind == "model3d":
            model3d.analyze(path, ext, out)
        elif kind == "live2d":
            live2d.analyze_single(path, ext, out)
        elif kind == "audio":
            audio.analyze(path, out)
        elif kind == "video":
            video.analyze(path, out)
        elif kind == "pdf":
            docs.analyze_pdf(path, out)
        elif kind == "document":
            docs.analyze_office(path, ext, out)
        elif kind == "archive":
            archive.analyze(path, ext, out)
        elif kind == "code":
            code.analyze(path, ext, out)
    except Exception as exc:  # 坏文件 / 不支持的变体：保留基本信息
        out.meta["error"] = f"{type(exc).__name__}: {exc}"[:300]
    return _finish(out, ext)


def _finish(out: Analysis, ext: str) -> Analysis:
    out.meta.setdefault("ext", ext.lstrip("."))
    out.meta["thumb"] = bool(out.thumb)
    if out.content and len(out.content) > 400_000:
        out.content = out.content[:400_000]
    return out
