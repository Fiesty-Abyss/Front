"""PDF（pypdfium2，Apache-2.0 / BSD-3）与 Office / OpenDocument 文档（只读 zip 里的 XML，不需要 Office）。"""

from __future__ import annotations

import io
import re
import zipfile
import posixpath
from html import unescape
from urllib.parse import unquote
from pathlib import Path
from typing import TYPE_CHECKING, Any
from xml.etree import ElementTree as ET

from .util import clean, is_image, text

if TYPE_CHECKING:
    from . import Analysis

OFFICE_EXT = {".docx", ".xlsx", ".pptx", ".doc", ".xls", ".ppt", ".odt", ".ods", ".odp", ".rtf", ".epub"}
PREVIEW_CHARS = 30_000


def render_pdf_page(path: Path, index: int, width: int = 1100) -> bytes:
    import pypdfium2 as pdfium

    pdf = pdfium.PdfDocument(str(path))
    try:
        page = pdf[index]
        scale = width / max(page.get_width(), 1)
        img = page.render(scale=min(scale, 4)).to_pil()
        buf = io.BytesIO()
        img.convert("RGB").save(buf, "WEBP", quality=85)
        return buf.getvalue()
    finally:
        pdf.close()


def analyze_pdf(path: Path, out: Analysis) -> None:
    import pypdfium2 as pdfium

    pdf = pdfium.PdfDocument(str(path))
    try:
        meta = pdf.get_metadata_dict()
        n = len(pdf)
        w, h = pdf[0].get_size() if n else (0, 0)
        out.meta.update(clean({
            "pages": n, "title": text(meta.get("Title")), "author": text(meta.get("Author")),
            "subject": text(meta.get("Subject")), "creator": text(meta.get("Creator")), "producer": text(meta.get("Producer")),
            "created": _pdf_date(meta.get("CreationDate")), "page_size": f"{w * 25.4 / 72:.0f}×{h * 25.4 / 72:.0f} mm" if w else None,
        }))
        if meta.get("Title"):
            out.title = text(meta["Title"], 200)
        parts = []
        for i in range(min(n, 200)):
            tp = pdf[i].get_textpage()
            parts.append(tp.get_text_range())
            tp.close()
            if sum(map(len, parts)) > 400_000:
                break
        out.content = "\n\n".join(parts).replace("\r\n", "\n").strip() or None
    finally:
        pdf.close()
    if out.meta.get("pages"):
        out.thumb = render_pdf_page(path, 0, 480)


def _pdf_date(v: str | None) -> str | None:
    m = re.match(r"D:(\d{4})(\d{2})?(\d{2})?", v or "")
    return "-".join(x for x in m.groups() if x) if m else None


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


MAX_ENTRY = 64 * 1024 * 1024  # 防止压缩炸弹：单个条目解压后超过 64 MB 就不读


def _read(z: zipfile.ZipFile, name: str) -> bytes:
    if z.getinfo(name).file_size > MAX_ENTRY:
        raise KeyError(name)
    return z.read(name)


def _xml(z: zipfile.ZipFile, name: str) -> ET.Element | None:
    try:
        return ET.fromstring(_read(z, name))
    except (KeyError, ET.ParseError):
        return None


def _core_props(z: zipfile.ZipFile) -> dict[str, Any]:
    out: dict[str, Any] = {}
    root = _xml(z, "docProps/core.xml")
    for el in root if root is not None else []:
        k = _local(el.tag)
        if k in ("title", "creator", "lastModifiedBy", "created", "modified", "subject", "description") and el.text:
            out[{"creator": "author", "lastModifiedBy": "last_modified_by"}.get(k, k)] = el.text.strip()[:300]
    app = _xml(z, "docProps/app.xml")
    for el in app if app is not None else []:
        k = _local(el.tag)
        if k in ("Application", "Pages", "Words", "Slides", "Characters") and el.text:
            out[k.lower()] = int(el.text) if el.text.isdigit() else el.text.strip()[:100]
    return out


def _odf_props(z: zipfile.ZipFile) -> dict[str, Any]:
    out: dict[str, Any] = {}
    root = _xml(z, "meta.xml")
    if root is None:
        return out
    for el in root.iter():
        k = _local(el.tag)
        if k in ("title", "initial-creator", "creator", "creation-date", "generator") and el.text:
            out[{"initial-creator": "author", "creation-date": "created", "generator": "application"}.get(k, k)] = el.text[:300]
        if k == "document-statistic":
            for a, v in el.attrib.items():
                if _local(a) in ("page-count", "word-count"):
                    out[_local(a).split("-")[0] + "s"] = int(v)
    return out


def _docx(z: zipfile.ZipFile) -> tuple[list[dict[str, str]], str]:
    root = _xml(z, "word/document.xml")
    blocks: list[dict[str, str]] = []
    if root is None:
        return blocks, ""
    for p in root.iter():
        if _local(p.tag) != "p":
            continue
        style = next((v for el in p.iter() if _local(el.tag) == "pStyle" for k, v in el.attrib.items() if _local(k) == "val"), "")
        t = "".join(el.text or "" for el in p.iter() if _local(el.tag) == "t")
        if not t.strip():
            continue
        lvl = re.search(r"(?:Heading|标题|heading)\s*(\d)", style)
        blocks.append({"type": f"h{lvl.group(1)}" if lvl else ("title" if style.lower() == "title" else "p"), "text": t})
    return blocks, "\n".join(b["text"] for b in blocks)


def _pptx(z: zipfile.ZipFile) -> tuple[list[dict[str, Any]], str]:
    names = sorted((n for n in z.namelist() if re.fullmatch(r"ppt/slides/slide\d+\.xml", n)), key=lambda n: int(re.findall(r"\d+", n)[-1]))
    slides = []
    for n in names:
        root = _xml(z, n)
        paras = []
        for p in root.iter() if root is not None else []:
            if _local(p.tag) == "p":
                t = "".join(el.text or "" for el in p.iter() if _local(el.tag) == "t").strip()
                if t:
                    paras.append(t)
        slides.append({"title": paras[0] if paras else "", "lines": paras[1:12]})
    return slides, "\n\n".join("\n".join([s["title"], *s["lines"]]) for s in slides)


def _xlsx(z: zipfile.ZipFile) -> tuple[dict[str, Any], str]:
    shared: list[str] = []
    ss = _xml(z, "xl/sharedStrings.xml")
    for si in ss if ss is not None else []:
        shared.append("".join(el.text or "" for el in si.iter() if _local(el.tag) == "t"))
    wb = _xml(z, "xl/workbook.xml")
    sheets = [el.attrib.get("name", "") for el in (wb.iter() if wb is not None else []) if _local(el.tag) == "sheet"]
    rows: list[list[str]] = []
    first = _xml(z, "xl/worksheets/sheet1.xml")
    for r in first.iter() if first is not None else []:
        if _local(r.tag) != "row" or len(rows) >= 40:
            continue
        row: list[str] = []
        for c in r:
            if _local(c.tag) != "c":
                continue
            col = re.match(r"[A-Z]+", c.attrib.get("r", "A"))
            idx = 0
            for ch in col.group(0) if col else "A":
                idx = idx * 26 + ord(ch) - 64
            while len(row) < idx - 1:
                row.append("")
            v = next((el.text for el in c.iter() if _local(el.tag) in ("v", "t")), "") or ""
            if c.attrib.get("t") == "s" and v.isdigit() and int(v) < len(shared):
                v = shared[int(v)]
            row.append(v[:80])
        rows.append(row[:16])
    return {"sheets": sheets, "rows": rows}, "\n".join(shared[:20000])


def _odf_text(z: zipfile.ZipFile) -> tuple[list[dict[str, str]], str]:
    root = _xml(z, "content.xml")
    blocks: list[dict[str, str]] = []
    for el in root.iter() if root is not None else []:
        k = _local(el.tag)
        if k in ("p", "h"):
            t = "".join(el.itertext()).strip()
            if t:
                lvl = next((v for a, v in el.attrib.items() if _local(a) == "outline-level"), "1")
                blocks.append({"type": f"h{lvl}" if k == "h" else "p", "text": t})
    return blocks, "\n".join(b["text"] for b in blocks)


def _epub(z: zipfile.ZipFile, *, strict: bool = False) -> tuple[list[dict[str, str]], str, dict[str, Any]]:
    meta: dict[str, Any] = {}
    opf_name = next((n for n in z.namelist() if n.endswith(".opf")), None)
    order: list[str] = []
    if opf_name:
        root = _xml(z, opf_name)
        base = opf_name.rsplit("/", 1)[0] + "/" if "/" in opf_name else ""
        items = {}
        for el in root.iter() if root is not None else []:
            k = _local(el.tag)
            if k in ("title", "creator", "language", "publisher") and el.text:
                meta.setdefault({"creator": "author"}.get(k, k), el.text.strip()[:200])
            if k == "item":
                items[el.attrib.get("id")] = posixpath.normpath(base + unquote(el.attrib.get("href", "").split('#')[0]))
            if k == "itemref" and el.attrib.get("idref") in items:
                order.append(items[el.attrib["idref"]])
    if strict and (not order or len(order) > 400):
        raise ValueError('EPUB 无可读取 spine 或超过 400 条')
    texts = []
    for n in order[:400]:
        try:
            html = _read(z, n).decode("utf-8", errors="replace")
        except KeyError:
            if strict:
                raise ValueError('EPUB 正文引用缺失或超限') from None
            continue
        texts.append(unescape(re.sub(r"\s+\n", "\n", re.sub(r"<[^>]+>", "", re.sub(r"</(p|h\d|div|br)>", "\n", html))).strip()))
    body = "\n\n".join(t for t in texts if t)
    meta["chapters"] = len(order)
    return [{"type": "p", "text": p} for p in body.split("\n") if p.strip()][:300], body, meta


def analyze_office(path: Path, ext: str, out: Analysis) -> None:
    if ext in (".doc", ".xls", ".ppt", ".rtf"):
        out.meta["note"] = "旧版二进制 / RTF 格式只记录文件信息，另存为 docx / xlsx / pptx 后可以预览"
        return
    with zipfile.ZipFile(path) as z:
        props = _odf_props(z) if ext.startswith(".od") else _core_props(z)
        preview: Any = None
        body = ""
        if ext == ".docx":
            preview, body = _docx(z)
            out.meta["format"] = "Word 文档"
        elif ext == ".pptx":
            preview, body = _pptx(z)
            props["slides"] = len(preview)
            out.meta["format"] = "PowerPoint 演示文稿"
        elif ext == ".xlsx":
            preview, body = _xlsx(z)
            out.meta["format"] = "Excel 工作簿"
        elif ext in (".odt", ".odp", ".ods"):
            preview, body = _odf_text(z)
            out.meta["format"] = {".odt": "OpenDocument 文本", ".odp": "OpenDocument 演示", ".ods": "OpenDocument 表格"}[ext]
        elif ext == ".epub":
            preview, body, extra = _epub(z)
            props.update(extra)
            out.meta["format"] = "EPUB 电子书"
        for name in ("docProps/thumbnail.jpeg", "docProps/thumbnail.png", "Thumbnails/thumbnail.png"):
            try:
                data = _read(z, name)
            except KeyError:
                continue
            if is_image(data):
                out.thumb = data
                break
        if ext == ".epub" and not out.thumb:
            cover = next((n for n in z.namelist() if re.search(r"cover\.(jpe?g|png)$", n, re.I)), None)
            data = _read(z, cover) if cover else None
            if data and is_image(data):
                out.thumb = data
    out.meta.update(clean(props))
    if props.get("title"):
        out.title = text(props["title"], 200)
    out.content = body or None
    out.meta["preview"] = _trim(preview)


def _trim(preview: Any) -> Any:
    """预览只保留前 3 万字左右，完整文字在 content 里。"""
    if isinstance(preview, list):
        kept, n = [], 0
        for b in preview:
            n += len(str(b))
            if n > PREVIEW_CHARS:
                break
            kept.append(b)
        return kept
    return preview
