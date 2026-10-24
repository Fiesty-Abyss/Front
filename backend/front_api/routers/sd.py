"""SD 模型库、提示词库、出图记录与“同一提示词 × 不同模型”风格对比。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models as m
from .. import civitai, modelscan, sdparams
from .. import schemas as s
from ..crud import get_or_404, make_crud_router, qp
from ..db import get_session

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
    """同一提示词在不同模型下的出图，按模型分组。
    附带参数差异：diff_keys 是各张图之间取值不同的参数（前端高亮），common 是全部相同的参数；
    每张图还给出相对提示词原文多出 / 缺少的词（XY 提示词替换时会用到）。"""
    from .sdtools import gen_norm

    prompt = get_or_404(session, m.Prompt, prompt_id)
    gens = session.scalars(select(m.Generation).where(m.Generation.prompt_id == prompt_id).order_by(m.Generation.id)).all()
    cache: dict[int, m.SDModel | None] = {}
    norms = {g.id: gen_norm(session, g, cache) for g in gens}
    diff = sdparams.diff_keys(list(norms.values()))
    first = next(iter(norms.values()), {})
    common = {k: v for k, v in first.items() if k not in diff and all(k in n for n in norms.values())}
    base_tokens = sdparams.tokens(prompt.positive)
    base_lower = {t.lower() for t in base_tokens}
    groups: dict[int | None, dict[str, Any]] = {}
    for g in gens:
        model = cache.get(g.model_id) if g.model_id else None
        asset = session.get(m.Asset, g.asset_id) if g.asset_id else None
        group = groups.setdefault(
            g.model_id,
            {"model": s.SDModelRead.model_validate(model).model_dump(mode="json") if model else None, "items": []},
        )
        text = (g.params or {}).get("prompt") or prompt.positive
        toks = sdparams.tokens(text)
        lower = {t.lower() for t in toks}
        group["items"].append(
            {
                "generation_id": g.id,
                "params": g.params,
                "norm": norms[g.id],
                "batch": g.batch,
                "xy": g.xy,
                "notes": g.notes,
                "prompt_added": [t for t in toks if t.lower() not in base_lower],
                "prompt_removed": [t for t in base_tokens if t.lower() not in lower],
                "asset": s.AssetRead.model_validate(asset).model_dump(mode="json") if asset else None,
            }
        )
    return {
        "prompt": s.PromptRead.model_validate(prompt).model_dump(mode="json"),
        "groups": list(groups.values()),
        "diff_keys": diff,
        "common": common,
        "labels": sdparams.LABELS,
    }


class InspectRequest(BaseModel):
    path: str
    compute_hash: bool = False


@extra.post("/api/sd-models/inspect")
def inspect_model_file(req: InspectRequest) -> dict[str, Any]:
    """读取本机模型文件的信息（文件名、大小、类型、safetensors 元数据、说明文件，可选哈希）。
    Front 是自托管的，这里读取的是运行 Front 的这台电脑上的文件，文件不会被复制或上传。"""
    path = Path(req.path).expanduser()
    if path.suffix.lower() not in modelscan.MODEL_EXT:
        raise HTTPException(422, f"只支持模型文件: {', '.join(sorted(modelscan.MODEL_EXT))}")
    if not path.is_file():
        raise HTTPException(404, "文件不存在")
    if req.compute_hash and path.stat().st_size > 64*1024*1024:
        raise HTTPException(422, '大型模型请先登记，再使用后台哈希任务')
    info = modelscan.describe(path, path.parent, with_hash=req.compute_hash)
    info["sha256"] = info["hashes"]["SHA256"].lower() if info["hashes"] else None
    info["civitai"] = civitai.summarize(info.pop("civitai_info")) if info.get("civitai_info") else None
    return info


class FromAsset(BaseModel):
    prompt_id: int | None = None
    title: str | None = None


def _stem(name: str) -> str:
    return Path(name.replace("\\", "/")).stem.lower()


def match_model(session: Session, model_name: str | None, model_hash: str | None = None) -> m.SDModel | None:
    """按出图参数里的模型哈希（AutoV2 10 位 / AutoV1 8 位）或模型名（可能带路径、扩展名、或 "名字 [hash]"）匹配已登记的模型。"""
    all_models = session.scalars(select(m.SDModel)).all()
    if model_hash:
        h = model_hash.strip().upper()
        for mdl in all_models:
            hs = {v.upper()[: len(h)] for k, v in (mdl.hashes or {}).items() if k in ("AutoV1", "AutoV2", "SHA256")}
            if mdl.sha256:
                hs.add(mdl.sha256.upper()[: len(h)])
            if len(h) >= 8 and h in hs:
                return mdl
    if not model_name:
        return None
    key = _stem(model_name.split(" [")[0])
    for mdl in all_models:
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
    model = match_model(session, params.get("Model"), params.get("Model hash"))
    existing = session.scalar(select(m.Generation).where(m.Generation.prompt_id == prompt.id, m.Generation.asset_id == asset.id))
    gen = existing or m.Generation(prompt_id=prompt.id, asset_id=asset.id)
    gen.model_id = model.id if model else gen.model_id
    gen.params = params
    if not existing:
        gen.notes = None if model else f"未匹配到已登记模型：{params.get('Model') or '未知'}"
        session.add(gen)
    session.commit()
    return {"prompt_id": prompt.id, "reused_prompt": reused, "generation_id": gen.id, "model_id": gen.model_id}
