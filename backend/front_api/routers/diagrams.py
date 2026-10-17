"""图表画布：流程图 / 节点工作流。节点和连线按 Vue Flow 的结构保存，可导入导出 JSON，预览图由前端生成后上传。"""

from __future__ import annotations

import json
import re
from typing import Any
from urllib.parse import quote

from fastapi import APIRouter, Body, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response
from sqlalchemy import event
from sqlalchemy.orm import Session

from .. import models as m
from .. import schemas as s
from ..config import get_settings
from ..crud import get_or_404, make_crud_router, qp
from ..db import get_session
from ..filetypes.util import is_image

FORMAT = "front-diagram"
MAX_NODES = 5000
MAX_EDGES = 10000
MAX_BYTES = 8 * 1024 * 1024
LINK_RE = re.compile(r"^/(assets\?open=\d+|notes/\d+|characters/\d+|worlds\?id=\d+|works\?id=\d+|diagrams/\d+)$")


def normalize(data: dict[str, Any] | None) -> dict[str, Any]:
    """检查并整理画布数据：节点 id 唯一、连线两端都存在、数量与大小有上限。"""
    data = data or {}
    nodes, edges = data.get("nodes") or [], data.get("edges") or []
    if not isinstance(nodes, list) or not isinstance(edges, list):
        raise HTTPException(422, "nodes / edges 必须是列表")
    if len(nodes) > MAX_NODES or len(edges) > MAX_EDGES:
        raise HTTPException(422, f"节点最多 {MAX_NODES} 个、连线最多 {MAX_EDGES} 条")
    ids: set[str] = set()
    for n in nodes:
        if not isinstance(n, dict) or not n.get("id"):
            raise HTTPException(422, "每个节点都需要 id")
        nid = str(n["id"])
        if nid in ids:
            raise HTTPException(422, f"节点 id 重复：{nid}")
        ids.add(nid)
        pos = n.get("position") or {}
        try:
            n["position"] = {"x": float(pos.get("x", 0)), "y": float(pos.get("y", 0))}
        except (TypeError, ValueError):
            raise HTTPException(422, f"节点 {nid} 的位置无效") from None
        link = ((n.get("data") or {}).get("link") or "").strip()
        if link and not (LINK_RE.match(link) or link.startswith(("http://", "https://"))):
            raise HTTPException(422, f"节点 {nid} 的链接只能是 Front 内部页面或 http(s) 网址")
    eids: set[str] = set()
    for e in edges:
        if not isinstance(e, dict) or str(e.get("source")) not in ids or str(e.get("target")) not in ids:
            raise HTTPException(422, "连线的两端必须是已有节点")
        e["id"] = str(e.get("id") or f"e{e['source']}-{e['target']}-{len(eids)}")
        if e["id"] in eids:
            raise HTTPException(422, f"连线 id 重复：{e['id']}")
        eids.add(e["id"])
    out = {"nodes": nodes, "edges": edges}
    vp = data.get("viewport")
    if isinstance(vp, dict):
        out["viewport"] = {k: float(vp[k]) for k in ("x", "y", "zoom") if isinstance(vp.get(k), int | float)}
    if len(json.dumps(out, ensure_ascii=False).encode()) > MAX_BYTES:
        raise HTTPException(422, "图表太大（超过 8 MB）")
    return out


def _validate(session: Session, data: dict[str, Any], *_: Any) -> None:
    if data.get("data") is not None:
        data["data"] = normalize(data["data"])


def _filters(stmt, request):
    if kind := qp(request, "kind"):
        stmt = stmt.where(m.Diagram.kind == kind)
    if work := qp(request, "work_id"):
        stmt = stmt.where(m.Diagram.work_id == int(work))
    return stmt


def _trim(d: dict[str, Any]) -> dict[str, Any]:
    d["data"] = None
    return d


crud = make_crud_router(
    prefix="/api/diagrams", model=m.Diagram, create_schema=s.DiagramCreate, update_schema=s.DiagramUpdate,
    read_schema=s.DiagramRead, tag_name="图表画布", filters=_filters, validate=_validate, list_trim=_trim,
    order_by=(m.Diagram.pinned.desc(), m.Diagram.updated_at.desc()),
)
extra = APIRouter(prefix="/api/diagrams", tags=["图表画布"])


def preview_path(diagram_id: int):
    return get_settings().thumb_dir / f"diagram-{diagram_id}.webp"


def _export(d: m.Diagram) -> dict[str, Any]:
    return {"format": FORMAT, "version": 1, "title": d.title, "kind": d.kind, "description": d.description, "data": d.data}


@extra.get("/{diagram_id}/export")
def export(diagram_id: int, session: Session = Depends(get_session)) -> Response:
    d = get_or_404(session, m.Diagram, diagram_id)
    body = json.dumps(_export(d), ensure_ascii=False, indent=2)
    name = quote(f"{d.title}.diagram.json")
    return Response(body, media_type="application/json",
                    headers={"Content-Disposition": f"attachment; filename=diagram.json; filename*=UTF-8''{name}"})


@extra.post("/import", response_model=s.DiagramRead, status_code=201)
def import_diagram(body: dict[str, Any] = Body(...), session: Session = Depends(get_session)) -> Any:
    """导入 Front 导出的图表 JSON，也接受 Vue Flow `toObject()` 的结果（只有 nodes / edges / viewport）。"""
    if body.get("format") not in (None, FORMAT):
        raise HTTPException(422, "不是 Front 图表文件")
    data = body.get("data") if "data" in body else body
    if not isinstance(data, dict) or "nodes" not in data:
        raise HTTPException(422, "缺少 nodes")
    kind = body.get("kind") if body.get("kind") in ("flowchart", "workflow", "mindmap", "other") else "flowchart"
    d = m.Diagram(title=str(body.get("title") or "导入的图表")[:200], kind=kind, description=body.get("description"), data=normalize(data))
    session.add(d)
    session.commit()
    return d


@extra.post("/{diagram_id}/duplicate", response_model=s.DiagramRead, status_code=201)
def duplicate(diagram_id: int, session: Session = Depends(get_session)) -> Any:
    src = get_or_404(session, m.Diagram, diagram_id)
    d = m.Diagram(title=f"{src.title}（副本）"[:200], kind=src.kind, description=src.description, data=json.loads(json.dumps(src.data)),
                  work_id=src.work_id, world_id=src.world_id, tags=list(src.tags))
    session.add(d)
    session.commit()
    if preview_path(src.id).is_file():
        preview_path(d.id).write_bytes(preview_path(src.id).read_bytes())
    return d


@extra.put("/{diagram_id}/preview", status_code=204)
async def set_preview(diagram_id: int, file: UploadFile = File(...), session: Session = Depends(get_session)) -> Response:
    """前端用 html-to-image 渲染的缩略图。"""
    get_or_404(session, m.Diagram, diagram_id)
    data = await file.read()
    if len(data) > 8 * 1024 * 1024 or not is_image(data):
        raise HTTPException(422, "预览图必须是图片")
    from PIL import Image
    import io

    with Image.open(io.BytesIO(data)) as im:
        im.thumbnail((800, 520))
        path = preview_path(diagram_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        im.convert("RGBA").save(path, "WEBP", quality=85)
    return Response(status_code=204)


@extra.get("/{diagram_id}/preview")
def get_preview(diagram_id: int, session: Session = Depends(get_session)) -> FileResponse:
    get_or_404(session, m.Diagram, diagram_id)
    path = preview_path(diagram_id)
    if not path.is_file():
        raise HTTPException(404, "还没有预览图")
    return FileResponse(path, media_type="image/webp")


@extra.delete("/{diagram_id}/preview", status_code=204)
def drop_preview(diagram_id: int) -> Response:
    preview_path(diagram_id).unlink(missing_ok=True)
    return Response(status_code=204)


@event.listens_for(m.Diagram, "after_delete")
def _drop_preview_file(_mapper: Any, _conn: Any, target: m.Diagram) -> None:
    preview_path(target.id).unlink(missing_ok=True)
