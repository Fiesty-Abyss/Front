"""SD 模型库、提示词库、出图记录与“同一提示词 × 不同模型”风格对比。"""

from __future__ import annotations

import hashlib
import json
import struct
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models as m
from .. import schemas as s
from ..crud import get_or_404, make_crud_router, qp
from ..db import get_session

MODEL_EXT = {".safetensors", ".ckpt", ".pt", ".pth", ".bin", ".gguf"}


def _model_filters(stmt, request):
    if kind := qp(request, "kind"):
        stmt = stmt.where(m.SDModel.kind == kind)
    if base := qp(request, "base_model"):
        stmt = stmt.where(m.SDModel.base_model == base)
    return stmt


def _gen_filters(stmt, request):
    if pid := qp(request, "prompt_id"):
        stmt = stmt.where(m.Generation.prompt_id == int(pid))
    if mid := qp(request, "model_id"):
        stmt = stmt.where(m.Generation.model_id == int(mid))
    return stmt


models = make_crud_router(
    prefix="/api/sd-models", model=m.SDModel, create_schema=s.SDModelCreate,
    update_schema=s.SDModelUpdate, read_schema=s.SDModelRead, tag_name="SD 模型库",
    filters=_model_filters, order_by=m.SDModel.name,
)
prompts = make_crud_router(
    prefix="/api/prompts", model=m.Prompt, create_schema=s.PromptCreate,
    update_schema=s.PromptUpdate, read_schema=s.PromptRead, tag_name="提示词库",
)
generations = make_crud_router(
    prefix="/api/generations", model=m.Generation, create_schema=s.GenerationCreate,
    update_schema=s.GenerationUpdate, read_schema=s.GenerationRead, tag_name="出图记录",
    filters=_gen_filters,
)

extra = APIRouter(tags=["SD 模型库"])


@extra.get("/api/prompts/{prompt_id}/compare")
def compare(prompt_id: int, session: Session = Depends(get_session)) -> dict[str, Any]:
    """同一提示词在不同模型下的出图，按模型分组。"""
    prompt = get_or_404(session, m.Prompt, prompt_id)
    gens = session.scalars(select(m.Generation).where(m.Generation.prompt_id == prompt_id)).all()
    groups: dict[int | None, dict[str, Any]] = {}
    for g in gens:
        model = session.get(m.SDModel, g.model_id) if g.model_id else None
        asset = session.get(m.Asset, g.asset_id) if g.asset_id else None
        key = g.model_id
        group = groups.setdefault(
            key,
            {
                "model": s.SDModelRead.model_validate(model).model_dump(mode="json") if model else None,
                "items": [],
            },
        )
        group["items"].append(
            {
                "generation_id": g.id,
                "params": g.params,
                "notes": g.notes,
                "asset": s.AssetRead.model_validate(asset).model_dump(mode="json") if asset else None,
            }
        )
    return {
        "prompt": s.PromptRead.model_validate(prompt).model_dump(mode="json"),
        "groups": list(groups.values()),
    }


class InspectRequest(BaseModel):
    path: str
    compute_hash: bool = False


def read_safetensors_metadata(path: Path) -> dict[str, Any]:
    with path.open("rb") as fh:
        head = fh.read(8)
        if len(head) < 8:
            return {}
        (length,) = struct.unpack("<Q", head)
        if length > 100 * 1024 * 1024:
            return {}
        try:
            header = json.loads(fh.read(length))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return {}
    meta = header.get("__metadata__") or {}
    return {k: v for k, v in meta.items() if isinstance(v, str) and len(v) < 4000}


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(4 * 1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def guess_base_model(meta: dict[str, Any]) -> str | None:
    raw = (meta.get("ss_base_model_version") or meta.get("modelspec.architecture") or "").lower()
    if not raw:
        return None
    for needle, label in (("flux", "Flux"), ("sdxl", "SDXL"), ("xl", "SDXL"), ("v2", "SD2"), ("sd_v1", "SD1.5"), ("v1", "SD1.5"), ("sd3", "SD3")):
        if needle in raw:
            return label
    return raw


@extra.post("/api/sd-models/inspect")
def inspect_model_file(req: InspectRequest) -> dict[str, Any]:
    """读取本机模型文件的信息（文件名、大小、safetensors 元数据、可选 SHA256）。
    Front 是自托管的，这里读取的是运行 Front 的这台电脑上的文件，文件不会被复制或上传。"""
    path = Path(req.path).expanduser()
    if path.suffix.lower() not in MODEL_EXT:
        raise HTTPException(422, f"只支持模型文件: {', '.join(sorted(MODEL_EXT))}")
    if not path.is_file():
        raise HTTPException(404, "文件不存在")
    meta = read_safetensors_metadata(path) if path.suffix.lower() == ".safetensors" else {}
    return {
        "file_name": path.name,
        "local_path": str(path),
        "size": path.stat().st_size,
        "sha256": sha256_file(path) if req.compute_hash else None,
        "base_model": guess_base_model(meta),
        "metadata": meta,
    }


class FromAsset(BaseModel):
    prompt_id: int | None = None
    title: str | None = None


def _stem(name: str) -> str:
    return Path(name.replace("\\", "/")).stem.lower()


def match_model(session: Session, model_name: str | None) -> m.SDModel | None:
    """按出图参数里的模型名（可能带路径、扩展名、或 "名字 [hash]"）匹配已登记的模型。"""
    if not model_name:
        return None
    key = _stem(model_name.split(" [")[0])
    for mdl in session.scalars(select(m.SDModel)).all():
        for cand in (mdl.file_name, mdl.local_path, mdl.name):
            if cand and _stem(cand) == key:
                return mdl
    return None


@extra.post("/api/prompts/from-asset/{asset_id}")
def prompt_from_asset(asset_id: int, body: FromAsset | None = None, session: Session = Depends(get_session)) -> dict[str, Any]:
    """把 AI 图里的出图参数存进提示词库，并记录一次出图（提示词 × 模型 → 图片）。
    正向提示词完全相同的已有提示词会被复用，所以多张同提示词、不同模型的图会自动汇集到同一个对比视图。"""
    body = body or FromAsset()
    asset = get_or_404(session, m.Asset, asset_id)
    sd = (asset.meta or {}).get("sd")
    if not sd or not sd.get("prompt"):
        raise HTTPException(422, "这张图没有可识别的出图参数")
    params = dict(sd.get("params") or {})
    if body.prompt_id:
        prompt = get_or_404(session, m.Prompt, body.prompt_id)
    else:
        prompt = session.scalar(select(m.Prompt).where(m.Prompt.positive == sd["prompt"]))
    reused = prompt is not None
    if prompt is None:
        prompt = m.Prompt(
            title=body.title or (sd["prompt"][:40] + ("…" if len(sd["prompt"]) > 40 else "")),
            positive=sd["prompt"],
            negative=sd.get("negative_prompt") or None,
            params={k: v for k, v in params.items() if k not in ("Model", "Model hash", "Seed")},
            notes=f"从素材 #{asset.id} 导入（{sd.get('source', 'sd')}）",
        )
        session.add(prompt)
        session.flush()
    model = match_model(session, params.get("Model"))
    existing = session.scalar(select(m.Generation).where(m.Generation.prompt_id == prompt.id, m.Generation.asset_id == asset.id))
    gen = existing or m.Generation(prompt_id=prompt.id, asset_id=asset.id)
    gen.model_id = model.id if model else gen.model_id
    gen.params = params
    if not existing:
        gen.notes = None if model else f"未匹配到已登记模型：{params.get('Model') or '未知'}"
        session.add(gen)
    session.commit()
    return {"prompt_id": prompt.id, "reused_prompt": reused, "generation_id": gen.id, "model_id": gen.model_id}
