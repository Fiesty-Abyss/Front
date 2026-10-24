"""第四轮：AI 绘画工作流。模型目录扫描与哈希、Civitai 匹配、提示词片段、调用 WebUI / ComfyUI 出图、XY 网格。"""

from __future__ import annotations

import uuid
from datetime import date
from pathlib import Path
from typing import Any, Literal

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import civitai, jobs, modelscan, sdgen, sdparams, ocgeneration
from .. import models as m
from .. import schemas as s
from ..config import get_settings
from ..crud import get_or_404, make_crud_router, qp, resolve_tags
from ..db import get_session, new_session
from ..ingest import ingest, make_thumb

router = APIRouter(tags=["AI 绘画工作流"])


# ---------------- 模型目录扫描 ----------------
class ScanRequest(BaseModel):
    path: str
    recursive: bool = True
    compute_hash: bool = False


class ScanRun(ScanRequest):
    import_previews: bool = True
    update_existing: bool = False
    files: list[str] | None = None  # 只登记这些（local_path），不填则全部
    tag_ids: list[int] = []


def _scan_root(path: str) -> Path:
    root = Path(path).expanduser()
    if not root.is_dir():
        raise HTTPException(404, "文件夹不存在")
    data_dir = get_settings().data_dir.resolve()
    if root.resolve() == data_dir or data_dir in root.resolve().parents:
        raise HTTPException(422, "不能扫描 Front 自己的数据目录")
    return root


def _existing(session: Session, item: dict[str, Any]) -> m.SDModel | None:
    found = session.scalar(select(m.SDModel).where(m.SDModel.local_path == item["local_path"]))
    sha = (item.get("hashes") or {}).get("SHA256")
    if not found and sha:
        found = session.scalar(select(m.SDModel).where(func.lower(m.SDModel.sha256) == sha.lower()))
    return found


@router.post("/api/sd-models/scan")
def scan_models(req: ScanRequest, session: Session = Depends(get_session)) -> dict[str, Any]:
    """只读预览：列出文件夹里的模型文件，按目录名判断类型，读取 safetensors 元数据和旁边的说明文件。"""
    root = _scan_root(req.path)
    items = []
    counts: dict[str, int] = {}
    for p in modelscan.iter_model_files(root, req.recursive):
        it = modelscan.describe(p, root, with_hash=req.compute_hash)
        ex = _existing(session, it)
        it["existing_id"] = ex.id if ex else None
        it["civitai"] = civitai.summarize(it.pop("civitai_info")) if it.get("civitai_info") else None
        it.pop("metadata", None)
        counts[it["kind"]] = counts.get(it["kind"], 0) + 1
        items.append(it)
    return {"root": str(root), "total": len(items), "new": sum(1 for i in items if not i["existing_id"]),
            "kinds": counts, "total_size": sum(i["size"] for i in items), "items": items}


def _apply_scan_item(session: Session, mdl: m.SDModel, it: dict[str, Any], fresh: bool) -> None:
    stem = Path(it["file_name"]).stem
    summary = civitai.summarize(it["civitai_info"]) if it.get("civitai_info") else None
    fields: dict[str, Any] = {
        "name": stem, "kind": it["kind"], "base_model": it["base_model"], "file_name": it["file_name"],
        "local_path": it["local_path"], "size": it["size"], "trigger_words": it["trigger_words"], "notes": it["notes"],
    }
    if summary:
        cf = civitai.fields_from(summary)
        fields.update({k: v for k, v in cf.items() if k != "kind" or it["kind"] in ("other", "checkpoint")})
        mdl.civitai = summary
    for k, v in fields.items():
        if v is not None and (fresh or k in ("local_path", "size", "file_name") or not getattr(mdl, k)):
            setattr(mdl, k, v)
    if it.get("hashes"):
        mdl.hashes = it["hashes"]
        mdl.sha256 = it["hashes"]["SHA256"].lower()


def _import_preview(session: Session, mdl: m.SDModel, preview: str) -> None:
    p = Path(preview)
    if mdl.preview_asset_id or not p.is_file() or p.stat().st_size > 30 * 1024 * 1024:
        return
    data = p.read_bytes()
    asset, created = ingest(session, data, p.name, kind="reference", title=f"{mdl.name} · 模型预览图", source="模型目录预览图")
    mdl.preview_asset_id = asset.id
    if created:
        session.flush()
        session.info.setdefault("thumbs", []).append((asset.id, data))


@router.post("/api/sd-models/scan/run")
def scan_run(req: ScanRun) -> dict[str, Any]:
    """登记扫描到的模型（后台任务）。已登记的模型按路径或 SHA256 识别，默认跳过。"""
    root = _scan_root(req.path)
    files = modelscan.iter_model_files(root, req.recursive)
    if req.files is not None:
        wanted = set(req.files)
        files = [f for f in files if str(f) in wanted]

    def work(job: jobs.Job) -> None:
        created, updated, skipped = [], [], 0
        with new_session() as session:
            tags = resolve_tags(session, req.tag_ids)
            for p in files:
                job.check()
                it = modelscan.describe(p, root, with_hash=req.compute_hash)
                ex = _existing(session, it)
                if ex and not req.update_existing:
                    skipped += 1
                    job.step(f"已登记，跳过：{p.name}")
                    continue
                mdl = ex or m.SDModel(name=p.stem)
                _apply_scan_item(session, mdl, it, fresh=ex is None)
                if not ex:
                    mdl.tags = list(tags)
                    session.add(mdl)
                session.flush()
                if req.import_previews and it.get("preview"):
                    _import_preview(session, mdl, it["preview"])
                session.commit()
                for aid, data in session.info.pop("thumbs", []):
                    make_thumb(aid, data)
                (updated if ex else created).append(mdl.id)
                job.result = {"created": created, "updated": updated, "skipped": skipped}
                job.step(p.name)
        job.result = {"created": created, "updated": updated, "skipped": skipped}

    job = jobs.start("model-scan", f"登记模型：{root.name}", len(files), work)
    return job.to_dict()


def _hash_model(session: Session, mdl: m.SDModel) -> dict[str, str]:
    if not mdl.local_path:
        raise HTTPException(422, "这个模型没有登记本地路径")
    p = Path(mdl.local_path).expanduser()
    if not p.is_file():
        raise HTTPException(404, f"找不到模型文件：{mdl.local_path}")
    hashes = modelscan.compute_hashes(p)
    mdl.hashes = hashes
    mdl.sha256 = hashes["SHA256"].lower()
    mdl.size = p.stat().st_size
    return hashes


@router.post("/api/sd-models/{model_id}/hash", response_model=s.SDModelRead)
def hash_model(model_id: int, session: Session = Depends(get_session)) -> Any:
    """计算单个模型的 SHA256 / AutoV1 / AutoV2 / AutoV3（大文件需要一些时间）。"""
    mdl = get_or_404(session, m.SDModel, model_id)
    _hash_model(session, mdl)
    session.commit()
    return mdl


class HashAll(BaseModel):
    only_missing: bool = True


@router.post("/api/sd-models/hash-all")
def hash_all(body: HashAll | None = None, session: Session = Depends(get_session)) -> dict[str, Any]:
    """后台计算所有（或缺少哈希的）已登记模型的哈希。"""
    body = body or HashAll()
    ids = [x.id for x in session.scalars(select(m.SDModel).where(m.SDModel.local_path.is_not(None)))
           if not body.only_missing or not x.sha256]

    def work(job: jobs.Job) -> None:
        with new_session() as ses:
            for mid in ids:
                mdl = ses.get(m.SDModel, mid)
                try:
                    _hash_model(ses, mdl)
                    ses.commit()
                except HTTPException as exc:
                    job.errors.append(f"{mdl.name}：{exc.detail}")
                job.step(mdl.name)

    return jobs.start("model-hash", "计算模型哈希", len(ids), work).to_dict()


# ---------------- Civitai ----------------
class CivitaiRequest(BaseModel):
    apply: bool = True
    overwrite: bool = False
    download_preview: bool = False


def _civitai_match(session: Session, mdl: m.SDModel, req: CivitaiRequest) -> dict[str, Any]:
    if not mdl.sha256:
        _hash_model(session, mdl)
    try:
        info = civitai.lookup(mdl.sha256)
    except civitai.CivitaiDisabled as exc:
        raise HTTPException(403, str(exc)) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(502, f"连接 Civitai 失败：{exc}") from exc
    if not info:
        mdl.civitai = {"not_found": True, "hash": mdl.sha256}
        session.commit()
        return {"found": False, "model": s.SDModelRead.model_validate(mdl).model_dump(mode="json")}
    summary = civitai.summarize(info)
    mdl.civitai = summary
    changed: list[str] = []
    if req.apply:
        for k, v in civitai.fields_from(summary).items():
            if req.overwrite or not getattr(mdl, k) or (k == "name" and mdl.name == Path(mdl.file_name or "").stem):
                if getattr(mdl, k) != v:
                    setattr(mdl, k, v)
                    changed.append(k)
    if req.download_preview and summary["image_urls"] and not mdl.preview_asset_id:
        try:
            data = civitai.download_image(summary["image_urls"][0])
            asset, created = ingest(session, data, "civitai_preview.png", kind="reference",
                                    title=f"{mdl.name} · Civitai 预览图", source=summary["url"])
            mdl.preview_asset_id = asset.id
            session.commit()
            if created:
                make_thumb(asset.id, data)
            changed.append("preview_asset_id")
        except (httpx.HTTPError, ValueError) as exc:
            summary["preview_error"] = str(exc)
    session.commit()
    return {"found": True, "changed": changed, "civitai": summary,
            "model": s.SDModelRead.model_validate(mdl).model_dump(mode="json")}


@router.post("/api/sd-models/{model_id}/civitai")
def civitai_match(model_id: int, body: CivitaiRequest | None = None, session: Session = Depends(get_session)) -> dict[str, Any]:
    """联网按 SHA256 查询 Civitai，取回模型名、版本、底模、触发词、链接（可选下载预览图）。
    默认只填空字段；overwrite=true 时覆盖。设置 FRONT_CIVITAI=off 可关闭。"""
    return _civitai_match(session, get_or_404(session, m.SDModel, model_id), body or CivitaiRequest())


@router.post("/api/sd-models/civitai-all")
def civitai_all(body: CivitaiRequest | None = None, session: Session = Depends(get_session)) -> dict[str, Any]:
    """后台为所有还没匹配过的模型查询 Civitai。"""
    if not get_settings().civitai_enabled:
        raise HTTPException(403, "Civitai 匹配已关闭（FRONT_CIVITAI=off）")
    body = body or CivitaiRequest()
    ids = [x.id for x in session.scalars(select(m.SDModel)) if not (x.civitai or {}).get("version_id") and (x.sha256 or x.local_path)]

    def work(job: jobs.Job) -> None:
        found = 0
        with new_session() as ses:
            for mid in ids:
                mdl = ses.get(m.SDModel, mid)
                try:
                    found += bool(_civitai_match(ses, mdl, body)["found"])
                except HTTPException as exc:
                    job.errors.append(f"{mdl.name}：{exc.detail}")
                job.result = {"found": found}
                job.step(mdl.name)

    return jobs.start("civitai", "匹配 Civitai", len(ids), work).to_dict()


# ---------------- 提示词片段 ----------------
def _snippet_filters(stmt, request):
    if cat := qp(request, "category"):
        stmt = stmt.where(m.PromptSnippet.category.in_(cat.split(",")))
    return stmt


snippets = make_crud_router(
    prefix="/api/prompt-snippets", model=m.PromptSnippet, create_schema=s.SnippetCreate,
    update_schema=s.SnippetUpdate, read_schema=s.SnippetRead, tag_name="提示词片段",
    filters=_snippet_filters, order_by=(m.PromptSnippet.category, m.PromptSnippet.position, m.PromptSnippet.title),
)


class ComposeItem(BaseModel):
    id: int
    weight: float = 1.0


class ComposeRequest(BaseModel):
    base_positive: str = ""
    base_negative: str = ""
    items: list[ComposeItem] = []


def _weighted(text: str, weight: float) -> str:
    text = text.strip().strip(",").strip()
    if not text or abs(weight - 1.0) < 1e-6:
        return text
    return f"({text}:{weight:g})"


def compose_prompt(base_pos: str, base_neg: str, parts: list[tuple[str, str | None, float]]) -> dict[str, str]:
    """按顺序拼接片段，逗号分隔、去掉重复的词（不区分大小写）。权重 ≠ 1 时整段包成 (片段:权重)。"""
    def join(chunks: list[str]) -> str:
        seen: set[str] = set()
        out: list[str] = []
        for chunk in chunks:
            if chunk.startswith("(") and chunk.endswith(")"):
                if chunk.lower() not in seen:
                    seen.add(chunk.lower())
                    out.append(chunk)
                continue
            for tok in sdparams.tokens(chunk):
                if tok.lower() not in seen:
                    seen.add(tok.lower())
                    out.append(tok)
        return ", ".join(out)
    pos = [base_pos] + [_weighted(p, w) for p, _, w in parts]
    neg = [base_neg] + [n for _, n, _ in parts if n]
    return {"positive": join([x for x in pos if x]), "negative": join([x for x in neg if x])}


@router.post("/api/prompt-snippets/compose")
def compose(body: ComposeRequest, session: Session = Depends(get_session)) -> dict[str, str]:
    """把若干片段（可带权重）组合成完整的正向 / 反向提示词。"""
    parts = []
    for it in body.items:
        sn = get_or_404(session, m.PromptSnippet, it.id)
        parts.append((sn.positive, sn.negative, it.weight))
    return compose_prompt(body.base_positive, body.base_negative, parts)


# ---------------- 后台任务 ----------------
@router.get("/api/jobs")
def list_jobs(kind: str | None = None) -> list[dict[str, Any]]:
    return jobs.listing(kind)


@router.get("/api/jobs/{job_id}")
def get_job(job_id: str) -> dict[str, Any]:
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(404, "任务不存在或已超过历史保留数量")
    return job.to_dict()


@router.post("/api/jobs/{job_id}/cancel")
def cancel_job(job_id: str) -> dict[str, Any]:
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(404, "任务不存在")
    job.cancel_requested = True
    return job.to_dict()


# ---------------- 出图 ----------------
@router.get("/api/generate/status")
def generate_status(backend: Literal["webui", "comfyui"] | None = None) -> dict[str, Any]:
    """两个出图后端的配置与连通情况；连得上时附带可选的模型 / 采样器 / 调度器 / LoRA 列表。"""
    out: dict[str, Any] = {}
    for b in [backend] if backend else ["webui", "comfyui"]:
        try:
            url = sdgen.backend_url(b)
        except sdgen.BackendError as exc:
            out[b] = {"configured": False, "ok": False, "error": str(exc)}
            continue
        try:
            opts = sdgen.webui_options(url) if b == "webui" else sdgen.comfy_options(url)
            out[b] = {"configured": True, "ok": True, "url": url, "options": opts}
        except sdgen.BackendError as exc:
            out[b] = {"configured": True, "ok": False, "url": url, "error": str(exc)}
    return out


class Axis(BaseModel):
    param: str
    values: list[Any] = Field(min_length=1, max_length=20)
    search: str | None = None  # prompt_sr：要被替换的词，默认取第一个值


class LoraPick(BaseModel):
    model_id: int
    weight: float = 0.8


class GenerateRequest(BaseModel):
    backend: Literal["webui", "comfyui"] = "webui"
    prompt_id: int | None = None
    title: str | None = None
    positive: str = ""
    negative: str = ""
    steps: int = Field(default=24, ge=1, le=150)
    cfg: float = Field(default=7.0, ge=0, le=30)
    sampler: str | None = None
    scheduler: str | None = None
    seed: int = -1
    width: int = Field(default=512, ge=64, le=4096)
    height: int = Field(default=768, ge=64, le=4096)
    clip_skip: int | None = None
    model_ids: list[int] = []
    loras: list[LoraPick] = []
    x: Axis | None = None
    y: Axis | None = None
    count: int = Field(default=1, ge=1, le=8)
    tag_ids: list[int] = []
    world_id: int | None = None
    collection_id: int | None = None
    collection_name: str | None = None
    workflow: dict[str, Any] | None = None
    save_prompt: bool = True
    oc_profile_id: int | None = None
    oc_design_id: str | None = None
    oc_expected_version: int | None = Field(default=None,ge=1)


MAX_IMAGES = 100


def _model_label(mdl: m.SDModel | None) -> str:
    return mdl.name if mdl else "当前模型"


@router.post("/api/generate")
def generate(req: GenerateRequest, session: Session = Depends(get_session)) -> dict[str, Any]:
    """提交一次出图任务（后台运行）。多个模型 / XY 轴会展开成网格，每张图自动入库并记录为一次出图，
    同一次任务共享批次号，可在提示词页按网格查看。"""
    batch = uuid.uuid4().hex[:12]
    oc_batch = ocgeneration.prepare(session,req,batch)
    if req.workflow and len(__import__('json').dumps(req.workflow).encode())>1024*1024:raise HTTPException(413,'工作流超过1MiB')
    url = None
    try:
        url = sdgen.backend_url(req.backend)
    except sdgen.BackendError as exc:
        raise HTTPException(503, str(exc)) from exc
    x, y = req.x, req.y
    if not x and len(req.model_ids) > 1:
        x = Axis(param="model", values=list(req.model_ids))
    for ax in (x, y):
        if ax and ax.param not in sdgen.AXIS_PARAMS:
            raise HTTPException(422, f"不支持的 XY 轴：{ax.param}，可选 {', '.join(sorted(sdgen.AXIS_PARAMS))}")
        if ax and ax.param == "prompt_sr" and not ax.search:
            ax.search = str(ax.values[0])
    model_ids = set(req.model_ids) | {int(v) for ax in (x, y) if ax and ax.param == "model" for v in ax.values}
    mdls = {i: get_or_404(session, m.SDModel, i) for i in model_ids}
    if any(mdl.kind!='checkpoint' for mdl in mdls.values()):raise HTTPException(422,'Checkpoint请选择对应模型类型')
    loras = [(get_or_404(session, m.SDModel, lp.model_id), lp.weight) for lp in req.loras]
    for mdl, _ in loras:
        if mdl.kind not in ('lora','lycoris'):raise HTTPException(422,'LoRA请选择LoRA或LyCORIS档案')
        if not mdl.file_name:
            raise HTTPException(422, f"LoRA「{mdl.name}」没有登记文件名")
    cells = sdgen.axis_cells(x.model_dump() if x else None, y.model_dump() if y else None)
    total = len(cells) * req.count
    if total > MAX_IMAGES:
        raise HTTPException(422, f"一次最多出 {MAX_IMAGES} 张，当前组合是 {total} 张")

    prompt = get_or_404(session, m.Prompt, req.prompt_id) if req.prompt_id else None
    positive = req.positive or (prompt.positive if prompt else "")
    if not positive.strip():
        raise HTTPException(422, "正向提示词不能为空")
    negative = req.negative or ((prompt.negative or "") if prompt and not req.positive else "")
    if not prompt and req.save_prompt:
        prompt = session.scalar(select(m.Prompt).where(m.Prompt.positive == positive))
        if not prompt:
            prompt = m.Prompt(title=req.title or (positive[:40] + ("…" if len(positive) > 40 else "")), positive=positive,
                              negative=negative or None, notes="由 Front 出图时创建",
                              params={"steps": req.steps, "cfg": req.cfg, "sampler": req.sampler, "size": f"{req.width}x{req.height}"})
            session.add(prompt)
    collection_id = req.collection_id
    if req.collection_name:
        col = m.Collection(name=req.collection_name, description="Front 出图任务自动创建")
        session.add(col)
        session.flush()
        collection_id = col.id
    elif collection_id:
        get_or_404(session, m.Collection, collection_id)
    session.commit()
    prompt_id = prompt.id if prompt else None
    prompt_title = (prompt.title if prompt else req.title) or "出图"
    base_seed = sdgen.resolve_seed(req.seed)
    fixed_model = mdls.get(req.model_ids[0]) if len(req.model_ids) == 1 else None

    def axis_label(ax: Axis | None, v: Any) -> dict[str, Any] | None:
        if not ax or v is None:
            return None
        label = _model_label(mdls[int(v)]) if ax.param == "model" else str(v)
        return {"param": ax.param, "value": v, "label": label}

    def work(job: jobs.Job) -> None:
        items: list[dict[str, Any]] = []
        job.result = {"batch": batch, "prompt_id": prompt_id, "collection_id": collection_id, "items": items}
        with new_session() as ses:
            tags = resolve_tags(ses, req.tag_ids)
            n = 0
            for yv, xv in cells:
                for i in range(req.count):
                    job.check()
                    model = fixed_model
                    for ax, v in ((x, xv), (y, yv)):
                        if ax and ax.param == "model" and v is not None:
                            model = mdls[int(v)]
                    spec = sdgen.Spec(positive=positive, negative=negative, steps=req.steps, cfg=req.cfg, sampler=req.sampler,
                                      scheduler=req.scheduler, seed=base_seed + i, width=req.width, height=req.height,
                                      clip_skip=req.clip_skip, model_file=model.file_name if model else None,
                                      loras=[{"file": lm.file_name, "weight": w, "name": lm.name} for lm, w in loras])
                    for ax, v in ((x, xv), (y, yv)):
                        sdgen.apply_axis(spec, positive, ax.param if ax else None, v, ax.search if ax else None)
                    xy = {k: lab for k, lab in (("x", axis_label(x, xv)), ("y", axis_label(y, yv))) if lab}
                    label = " · ".join(f"{sdparams.LABELS.get(a['param'], a['param'])} {a['label']}" for a in xy.values() if a["param"] != "model")
                    try:
                        images = (sdgen.webui_txt2img(url, spec) if req.backend == "webui"
                                  else sdgen.comfy_txt2img(url, spec, req.workflow))
                    except sdgen.BackendError as exc:
                        job.errors.append(str(exc))
                        job.step(f"失败：{exc}")
                        continue
                    for png, used_seed in images:
                        job.check()
                        n += 1
                        title = f"{prompt_title} × {_model_label(model)}" + (f" · {label}" if label else "")
                        asset, created = ingest(ses, png, f"front_{batch}_{n:03d}.png", kind="ai_image", title=title,
                                                source=f"Front 出图 · {'SD WebUI' if req.backend == 'webui' else 'ComfyUI'}",
                                                work_date=date.today(), world_id=req.world_id, tags=tags,
                                                extra_meta={"generation": {"backend": req.backend, "batch": batch}})
                        ses.flush()
                        params = {**spec.params(), "seed": used_seed, "model": _model_label(model) if model else None,
                                  "prompt": spec.positive, "negative": spec.negative, "backend": req.backend, "checkpoint_snapshot": {"id":model.id,"name":model.name,"sha256":model.sha256,"file":model.file_name} if model else None, "lora_snapshots":[{"id":lm.id,"name":lm.name,"file":lm.file_name,"sha256":lm.sha256,"weight":spec.loras[j]["weight"]} for j,(lm,_) in enumerate(loras)], "workflow": (sdgen.fill_workflow(req.workflow,spec) if req.workflow else sdgen.comfy_graph(spec)) if req.backend=="comfyui" else None}
                        gen = m.Generation(prompt_id=prompt_id, model_id=model.id if model else None, asset_id=asset.id,
                                           params={k: v for k, v in params.items() if v is not None}, batch=batch, xy=xy)
                        ses.add(gen);ses.flush()
                        ocgeneration.attach_output(ses,batch,asset,gen,job)
                        if collection_id:
                            exists = ses.execute(select(m.collection_assets.c.asset_id).where(
                                m.collection_assets.c.collection_id == collection_id, m.collection_assets.c.asset_id == asset.id)).first()
                            if not exists:
                                pos = ses.scalar(select(func.coalesce(func.max(m.collection_assets.c.position), -1)).where(
                                    m.collection_assets.c.collection_id == collection_id)) + 1
                                ses.execute(m.collection_assets.insert().values(collection_id=collection_id, asset_id=asset.id, position=pos))
                        ses.commit()
                        if created:
                            make_thumb(asset.id, png)
                        items.append({"generation_id": gen.id, "asset_id": asset.id, "title": title, "xy": xy, "seed": used_seed})
                    job.step(f"已完成 {len(items)} 张")
        if not items and job.errors:
            raise RuntimeError(job.errors[-1])

    job = jobs.start("generate", f"出图：{prompt_title}（{total} 张）", total, work)
    ocgeneration.bind_job(session,batch,job)
    out = job.to_dict()
    out["batch"] = batch
    out["prompt_id"] = prompt_id
    return out


# ---------------- 对比：XY 网格 ----------------
def gen_norm(session: Session, g: m.Generation, cache: dict[int, m.SDModel | None]) -> dict[str, Any]:
    norm = sdparams.normalize(g.params)
    norm.pop("backend", None)
    for metadata in ('checkpoint_snapshot','lora_snapshots','workflow'):
        norm.pop(metadata,None)
    if g.model_id:
        if g.model_id not in cache:
            cache[g.model_id] = session.get(m.SDModel, g.model_id)
        if cache[g.model_id]:
            norm["model"] = cache[g.model_id].name
    for ax in (g.xy or {}).values():
        if ax.get("param") in ("prompt_sr", "lora_weight"):
            norm[ax["param"]] = ax.get("value")
    return norm


@router.get("/api/prompts/{prompt_id}/batches")
def prompt_batches(prompt_id: int, session: Session = Depends(get_session)) -> list[dict[str, Any]]:
    """这个提示词的出图批次（每次 Front 出图任务一个批次）。"""
    get_or_404(session, m.Prompt, prompt_id)
    rows = session.execute(
        select(m.Generation.batch, func.count(), func.min(m.Generation.created_at))
        .where(m.Generation.prompt_id == prompt_id, m.Generation.batch.is_not(None))
        .group_by(m.Generation.batch).order_by(func.min(m.Generation.created_at).desc())
    ).all()
    out = []
    for batch, n, created in rows:
        first = session.scalar(select(m.Generation).where(m.Generation.batch == batch).limit(1))
        axes = {k: v.get("param") for k, v in (first.xy or {}).items()} if first else {}
        out.append({"batch": batch, "count": n, "created_at": created.isoformat() if created else None, "axes": axes})
    return out


@router.get("/api/prompts/{prompt_id}/xy")
def prompt_xy(prompt_id: int, x: str | None = None, y: str | None = None, batch: str | None = None,
              session: Session = Depends(get_session)) -> dict[str, Any]:
    """把这个提示词的出图按任意两个参数排成 XY 网格（不限于 Front 自己出的图，导入的图同样可以）。
    不指定 x / y 时：有批次就用批次的轴，否则取前两个取值不同的参数。"""
    prompt = get_or_404(session, m.Prompt, prompt_id)
    stmt = select(m.Generation).where(m.Generation.prompt_id == prompt_id)
    if batch:
        stmt = stmt.where(m.Generation.batch == batch)
    gens = session.scalars(stmt.order_by(m.Generation.id)).all()
    cache: dict[int, m.SDModel | None] = {}
    rows = [(g, gen_norm(session, g, cache)) for g in gens]
    axes = sdparams.diff_keys([n for _, n in rows])
    from_batch = bool(batch and gens and not x and (gens[0].xy or {}).get("x"))
    if from_batch:
        xy = gens[0].xy or {}
        x = xy["x"].get("param")
        y = y or (xy.get("y") or {}).get("param")
    x = x or (axes[0] if axes else None)
    if not from_batch:
        y = y or (next((a for a in axes if a != x), None))
    if y == x:
        y = None
    xs = sdparams.sort_values([n.get(x) for _, n in rows]) if x else [None]
    ys = sdparams.sort_values([n.get(y) for _, n in rows]) if y else [None]
    cells: list[list[list[dict[str, Any]]]] = [[[] for _ in xs] for _ in ys]
    assets = {a.id: a for a in session.scalars(select(m.Asset).where(m.Asset.id.in_([g.asset_id for g in gens if g.asset_id])))}
    for g, n in rows:
        a = assets.get(g.asset_id)
        xi = xs.index(n.get(x)) if x else 0
        yi = ys.index(n.get(y)) if y else 0
        cells[yi][xi].append({"generation_id": g.id, "params": n,
                              "asset": {"id": a.id, "title": a.title, "width": a.width, "height": a.height} if a else None})
    return {
        "prompt": {"id": prompt.id, "title": prompt.title},
        "batch": batch, "x": x, "y": y,
        "x_values": [sdparams.value_label(v) for v in xs], "y_values": [sdparams.value_label(v) for v in ys],
        "cells": cells, "axes": [{"key": k, "label": sdparams.LABELS.get(k, k)} for k in axes], "count": len(gens),
    }
