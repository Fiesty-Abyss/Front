"""Immutable chapter plans over bounded, read-only source text."""
from pathlib import Path
import zipfile

from fastapi import HTTPException
from sqlalchemy import select

from . import models as m
from .chapters import split_chapters, fingerprint
from .config import get_settings
from .ingest import decode_text

MAX_SOURCE = 32 * 1024 * 1024


def source_text(asset):
    ext = Path(asset.original_name or '').suffix.lower()
    use_file = (asset.meta or {}).get('text_truncated') or ext == '.epub'
    if use_file and asset.file_path:
        root = get_settings().data_dir.resolve()
        path = (root / asset.file_path).resolve()
        if not path.is_relative_to(root) or not path.is_file():
            raise HTTPException(409, '小说原文件已失效；不能使用截断预览代替全文')
        if path.stat().st_size > MAX_SOURCE:
            raise HTTPException(413, '章节整理全文限 32 MiB，请分卷；原文件保留')
        if ext == '.epub':
            from .filetypes.docs import _epub
            try:
                with zipfile.ZipFile(path) as archive:
                    if sum(i.file_size for i in archive.infolist() if i.filename.lower().endswith(('.html', '.xhtml', '.htm', '.opf', '.xml'))) > MAX_SOURCE:
                        raise HTTPException(413, 'EPUB 解压正文超过 32 MiB，请分卷')
                    _, text, info = _epub(archive, strict=True)
                    if info.get('chapters', 0) > 400:
                        raise HTTPException(413, 'EPUB 超过 400 个正文条目，请分卷')
            except (zipfile.BadZipFile, KeyError, ValueError):
                raise HTTPException(422, 'EPUB 无法完整读取') from None
        else:
            text = decode_text(path.read_bytes())
    else:
        text = asset.content or ''
    if not text.strip():
        raise HTTPException(422, '该素材没有可读取正文')
    if len(text.encode('utf-8')) > MAX_SOURCE:
        raise HTTPException(413, '章节整理全文限 32 MiB，请分卷')
    return text


def current(session, asset_id):
    return session.scalar(select(m.ChapterRevision).where(m.ChapterRevision.asset_id == asset_id).order_by(m.ChapterRevision.id.desc()).limit(1))


def plan(session, asset_id, text):
    revision = current(session, asset_id)
    digest = fingerprint(text)
    toc = revision.chapters if revision and revision.text_hash == digest else split_chapters(text)
    if len(toc) > 5000:
        raise HTTPException(413, '识别目录超过 5000 项，请分卷或清理大量非章节标题')
    return toc, revision, digest
