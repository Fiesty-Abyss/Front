"""本地文件夹批量导入、galgame CG 识别与 CG 档案。

Front 是自托管的：这里的“本地路径”指运行 Front 的这台电脑上的路径。文件会被复制进数据目录，
原文件不会被修改或删除。"""

from __future__ import annotations

import io
import os
import zipfile
from collections import Counter
from datetime import date, datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from PIL import Image
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models as m
from .. import schemas as s
from ..cg import CGItem, group_cgs, groups_to_json, natural_key
from ..config import get_settings
from ..crud import get_or_404, resolve_tags
from ..db import get_session
from ..ingest import IMAGE_EXT, IMPORTABLE_EXT, ingest, make_thumb

MAX_FILES = 5000
MAX_BUNDLE = 512 * 1024 * 1024


def bundle_kind(filenames: list[str]) -> str | None:
    """一个文件夹是不是“一整个模型”：Live2D（model3.json / model.json + .moc）、PMX、带外部文件的 glTF、OBJ + MTL。
    是的话整个文件夹打包成一个素材，贴图和动作跟着模型走。"""
    low = [n.lower() for n in filenames]
    if any(n.endswith(".model3.json") for n in low) or (any(n.endswith(".moc") for n in low) and any(n.endswith(".json") and "model" in n for n in low)):
        return "live2d"
    if any(n.endswith((".pmx", ".gltf")) for n in low) or (any(n.endswith(".obj") for n in low) and any(n.endswith(".mtl") for n in low)):
        return "model3d"
    return None


def zip_dir(path: Path) -> bytes:
    buf = io.BytesIO()
    total = 0
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for fp in sorted(path.rglob("*")):
            if fp.is_file() and not fp.name.startswith("."):
                total += fp.stat().st_size
                if total > MAX_BUNDLE:
                    raise OSError(f"模型文件夹超过 {MAX_BUNDLE >> 20} MB")
                z.write(fp, fp.relative_to(path).as_posix())
    return buf.getvalue()
router = APIRouter(tags=["批量导入 / CG"])


class ScanRequest(BaseModel):
    path: str
    recursive: bool = True
    cg_mode: bool = False


class RunRequest(ScanRequest):
    kind: str | None = None
    work_id: int | None = None
    new_work_title: str | None = Field(default=None, max_length=200)
    world_id: int | None = None
    tag_ids: list[int] = []
    use_mtime: bool = True
    title_prefix: str | None = Field(default=None, max_length=100)


def _resolve_dir(path: str) -> Path:
    p = Path(path).expanduser()
    if not p.is_dir():
        raise HTTPException(404, f"文件夹不存在: {path}")
    data_dir = get_settings().data_dir.resolve()
    rp = p.resolve()
    if rp == data_dir or data_dir in rp.parents:
        raise HTTPException(422, "不能从 Front 自己的数据目录导入")
    return p


def scan_files(root: Path, recursive: bool) -> tuple[list[Path], int]:
    files: list[Path] = []
    unsupported = 0
    walker = os.walk(root) if recursive else [(str(root), [], [e.name for e in root.iterdir() if e.is_file()])]
    for dirpath, dirnames, filenames in walker:
        dirnames[:] = sorted(d for d in dirnames if not d.startswith("."))
        if recursive and bundle_kind(filenames):
            files.append(Path(dirpath))  # 整个文件夹作为一个模型包
            dirnames[:] = []
            continue
        for name in filenames:
            if name.startswith("."):
                continue
            fp = Path(dirpath) / name
            if fp.suffix.lower() in IMPORTABLE_EXT:
                files.append(fp)
                if len(files) > MAX_FILES:
                    raise HTTPException(422, f"文件过多（超过 {MAX_FILES} 个），请分批导入子文件夹")
            else:
                unsupported += 1
    files.sort(key=lambda f: natural_key(str(f.relative_to(root))))
    return files, unsupported


def _label(root: Path, fp: Path) -> str:
    rel = fp.relative_to(root).as_posix()
    return (rel if rel != "." else fp.name) + "/" if fp.is_dir() else rel


def _image_size(fp: Path) -> tuple[int | None, int | None]:
    try:
        with Image.open(fp) as img:  # 只读文件头
            return img.size
    except Exception:
        return None, None


def _cg_items(root: Path, files: list[Path]) -> list[CGItem]:
    items = []
    for f in files:
        if f.is_file() and f.suffix.lower() in IMAGE_EXT:
            w, h = _image_size(f)
            items.append(CGItem(name=f.name, width=w, height=h, ref=str(f.relative_to(root))))
    return items


@router.post("/api/import/scan")
def scan(req: ScanRequest) -> dict[str, Any]:
    """预览：列出将要导入的文件；CG 模式下给出差分分组结果。不写入任何数据。"""
    root = _resolve_dir(req.path)
    files, unsupported = scan_files(root, req.recursive)
    exts = Counter("模型文件夹" if f.is_dir() else f.suffix.lower() for f in files)
    result: dict[str, Any] = {
        "path": str(root),
        "folder_name": root.name,
        "total": len(files),
        "unsupported": unsupported,
        "by_ext": dict(exts),
        "total_size": sum(sum(x.stat().st_size for x in f.rglob("*") if x.is_file()) if f.is_dir() else f.stat().st_size for f in files),
        "files": [_label(root, f) for f in files[:300]],
        "bundles": [_label(root, f) for f in files if f.is_dir()][:100],
    }
    if req.cg_mode:
        groups = group_cgs(_cg_items(root, files))
        result["cg_groups"] = groups_to_json(groups)
    return result


def regroup_work(session: Session, work_id: int) -> list[dict[str, Any]]:
    """对某作品下全部 CG 重新识别差分分组，结果写入 asset.meta["cg"]。"""
    assets = session.scalars(select(m.Asset).where(m.Asset.work_id == work_id, m.Asset.kind == "cg")).all()
    items = [CGItem(name=a.original_name or a.title, width=a.width, height=a.height, ref=a.id) for a in assets]
    groups = group_cgs(items)
    by_id = {a.id: a for a in assets}
    for gi, g in enumerate(groups):
        for vi, it in enumerate(g.items):
            a = by_id[it.ref]
            a.meta = {**(a.meta or {}), "cg": {"group": g.key, "variant": it.variant, "group_order": gi, "order": vi}}
    session.commit()
    return groups_to_json(groups)


@router.post("/api/import/run")
def run(req: RunRequest, session: Session = Depends(get_session)) -> dict[str, Any]:
    root = _resolve_dir(req.path)
    files, _ = scan_files(root, req.recursive)
    settings = get_settings()
    tags = resolve_tags(session, req.tag_ids)
    work_id = req.work_id
    if work_id is not None:
        get_or_404(session, m.Work, work_id)
    elif req.new_work_title:
        work = m.Work(title=req.new_work_title.strip(), kind="galgame" if req.cg_mode else "other")
        session.add(work)
        session.flush()
        work_id = work.id
    if req.cg_mode and work_id is None:
        raise HTTPException(422, "CG 模式需要选择作品或填写新作品名")

    kind = "cg" if req.cg_mode else (req.kind or None)
    prefix = req.title_prefix
    if prefix is None and req.cg_mode:
        prefix = f"{session.get(m.Work, work_id).title} "  # CG 默认标题：作品名 + 文件名
    created: list[int] = []
    duplicates: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    thumbs: list[tuple[int, Path]] = []
    for i, fp in enumerate(files):
        rel = _label(root, fp)
        try:
            if fp.is_dir():
                data, fname, stem = zip_dir(fp), f"{fp.name}.zip", fp.name
            else:
                if fp.stat().st_size > settings.max_upload_mb * 1024 * 1024:
                    errors.append({"file": rel, "error": f"超过 {settings.max_upload_mb} MB"})
                    continue
                data, fname, stem = fp.read_bytes(), fp.name, fp.stem
            wdate = date.fromtimestamp(fp.stat().st_mtime) if req.use_mtime else None
            asset, is_new = ingest(
                session, data, fname, kind=kind, work_date=wdate, title=f"{prefix}{stem}" if prefix else (stem if fp.is_dir() else None), work_id=work_id,
                world_id=req.world_id, tags=tags, source=str(fp),
                extra_meta={"import": {"folder": root.name, "relative_path": rel, "imported_at": datetime.now().isoformat(timespec="seconds")}},
            )
            if is_new:
                created.append(asset.id)
                if asset.width:
                    thumbs.append((asset.id, fp))
            else:
                duplicates.append({"file": rel, "asset_id": asset.id})
        except OSError as exc:
            errors.append({"file": rel, "error": str(exc)})
        if i % 50 == 49:
            session.commit()
    session.commit()
    for aid, fp in thumbs:
        make_thumb(aid, fp.read_bytes())
    groups = regroup_work(session, work_id) if req.cg_mode and work_id else None
    return {
        "created": len(created),
        "created_ids": created,
        "duplicates": duplicates,
        "errors": errors,
        "work_id": work_id,
        "cg_groups": len(groups) if groups is not None else None,
    }


@router.post("/api/works/{work_id}/cg/regroup")
def regroup(work_id: int, session: Session = Depends(get_session)) -> dict[str, Any]:
    get_or_404(session, m.Work, work_id)
    groups = regroup_work(session, work_id)
    return {"groups": len(groups), "items": sum(g["count"] for g in groups)}


@router.get("/api/works/{work_id}/cg")
def cg_gallery(work_id: int, session: Session = Depends(get_session)) -> dict[str, Any]:
    """CG 档案：按差分分组，组内按差分顺序排列。"""
    work = get_or_404(session, m.Work, work_id)
    assets = session.scalars(select(m.Asset).where(m.Asset.work_id == work_id, m.Asset.kind == "cg")).all()
    groups: dict[str, dict[str, Any]] = {}
    for a in assets:
        cg = (a.meta or {}).get("cg") or {}
        key = cg.get("group") or Path(a.original_name or a.title).stem
        g = groups.setdefault(key, {"key": key, "order": cg.get("group_order", 10**6), "items": []})
        g["items"].append(
            {
                "id": a.id,
                "title": a.title,
                "variant": cg.get("variant", ""),
                "order": cg.get("order", 0),
                "width": a.width,
                "height": a.height,
                "original_name": a.original_name,
            }
        )
    out = []
    for g in groups.values():
        g["items"].sort(key=lambda x: (x["order"], natural_key(x["original_name"] or x["title"])))
        first = g["items"][0]
        out.append({
            "key": g["key"], "count": len(g["items"]), "size": f"{first['width']}x{first['height']}" if first["width"] else None,
            "cover_id": first["id"], "items": g["items"], "_order": g["order"],
        })
    out.sort(key=lambda g: (g["_order"], natural_key(g["key"])))
    for g in out:
        g.pop("_order")
    return {
        "work": s.WorkRead.model_validate(work).model_dump(mode="json"),
        "groups": out,
        "total": len(assets),
    }
