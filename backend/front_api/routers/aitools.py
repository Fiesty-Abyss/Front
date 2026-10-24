"""AI 工具：从小说抽取角色、语义检索、图片自动打标签。耗时操作都是后台任务（/api/jobs）。"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import jobs
from .. import models as m
from .. import schemas as s
from ..ai import AIProvider, AIUnavailable, registry
from ..ai import embed as embed_mod
from ..ai import extract as extract_mod
from ..ai import tagger as tagger_mod
from ..crud import get_or_404, resolve_tags
from ..db import get_session, new_session
from ..search import search as keyword_search
from .ai import provider_dep

router = APIRouter(tags=["AI 工具"])


# ---------- 从小说抽取角色 ----------
def _known(session: Session, world_id: int | None) -> dict[str, int]:
    # Unscoped extraction may see only unscoped characters, never every world.
    stmt = select(m.Character).where(m.Character.world_id == world_id)
    out: dict[str, int] = {}
    for c in session.scalars(stmt).all():
        out[c.name] = c.id
        for a in (c.alias or "").replace("，", ",").replace("、", ",").split(","):
            if a.strip():
                out.setdefault(a.strip(), c.id)
    return out


@router.post("/api/ai/extract/characters", status_code=202)
def extract_characters(payload: s.ExtractRequest, session: Session = Depends(get_session),
                       provider: AIProvider = Depends(provider_dep)) -> dict[str, Any]:
    if payload.chapter_revision is not None:
        from ..extractionreview import start
        return start(payload,session,provider)
    if payload.world_id is not None:
        get_or_404(session, m.World, payload.world_id)
    if payload.asset_id is not None:
        asset = get_or_404(session, m.Asset, payload.asset_id)
        if asset.world_id is not None and asset.world_id != payload.world_id:
            raise HTTPException(422, '小说与选定世界观不一致，请明确选择小说所属世界观')
        text, source = asset.content or "", asset.title
    else:
        text, source = payload.text or "", "粘贴的文本"
    if not text.strip():
        raise HTTPException(422, "没有可分析的正文（请选择一篇小说或粘贴文本）")
    if not provider.available():
        try:
            provider.chat([])
        except AIUnavailable as exc:
            raise HTTPException(503, str(exc)) from exc
    chunks = extract_mod.chunk_text(text, payload.chunk_size)[: payload.max_chunks]
    known = _known(session, payload.world_id)
    exact_known: dict[str,list[int]] = {}
    for character in session.scalars(select(m.Character).where(m.Character.world_id == payload.world_id)):
        exact_known.setdefault(character.name,[]).append(character.id)

    def work(job: jobs.Job) -> None:
        acc: list[dict[str, Any]] = []
        for i, chunk in enumerate(chunks):
            job.check()
            names = list(dict.fromkeys([*known, *(c["name"] for c in acc)]))
            try:
                reply = provider.chat(extract_mod.build_messages(chunk, names), temperature=0.1)
                extract_mod.merge(acc, extract_mod.parse(reply))
            except AIUnavailable as exc:
                job.errors.append(f"第 {i + 1} 段：{exc}")
            job.step(f"第 {i + 1} / {len(chunks)} 段，已找到 {len(acc)} 个角色")
            job.result = {"characters": acc, "source": source}
        for c in acc:
            matches=exact_known.get(c['name'],[])
            c['existing_id']=matches[0] if len(matches)==1 else None
        acc.sort(key=lambda c: -c.get("mentions", 1))
        job.result = {"characters": acc, "source": source, "chunks": len(chunks)}

    job = jobs.start("extract", f"抽取角色：{source}", len(chunks), work)
    return job.to_dict()


@router.post("/api/ai/extract/apply")
def extract_apply(payload: s.ExtractApply, session: Session = Depends(get_session)) -> dict[str, Any]:
    result=apply_characters(payload,session)
    session.commit()
    return result


def apply_characters(payload: s.ExtractApply, session: Session) -> dict[str, Any]:
    """把（人工勾选、修改过的）抽取结果写进角色百科；关系以“AI 待确认”写入关系网。"""
    if payload.world_id is not None:
        get_or_404(session, m.World, payload.world_id)
    if payload.work_id is not None:
        get_or_404(session, m.Work, payload.work_id)
    # Validate all selected IDs before applying any part of an edited AI batch.
    for character in payload.characters:
        if character.existing_id is not None:
            existing = get_or_404(session, m.Character, character.existing_id)
            if existing.world_id != payload.world_id:
                raise HTTPException(422, '选中的已有角色不属于本次世界观；请重新审核匹配')
    tags = resolve_tags(session, payload.tag_ids)
    gender_tags = {t.name: t for t in session.scalars(select(m.Tag).where(m.Tag.category == "gender")).all()}
    by_name: dict[str, m.Character] = {}
    for name, cid in _known(session, payload.world_id).items():
        by_name[name] = session.get(m.Character, cid)
    created, updated = [], []
    for c in payload.characters:
        data = c.model_dump()
        data["source"] = payload.source
        existing = session.get(m.Character, c.existing_id) if c.existing_id else None
        if existing is None:
            same=list(session.scalars(select(m.Character).where(m.Character.world_id==payload.world_id,m.Character.name==c.name)))
            if len(same)>1:raise HTTPException(409,'存在多个同名人物，请明确审核要关联的角色ID')
            if same:existing=same[0]
        if existing is not None:
            if payload.update_existing:
                if not existing.summary and c.summary:
                    existing.summary = c.summary
                extra = extract_mod.profile_markdown(data)
                if extra and extra not in (existing.profile or ""):
                    existing.profile = ((existing.profile or "") + "\n\n" + extra).strip()
                aliases = [a for a in c.aliases if a not in (existing.alias or "")]
                if aliases:
                    existing.alias = "、".join(x for x in [existing.alias, *aliases] if x)
                updated.append(existing.id)
            char = existing
        else:
            char_tags = list(tags)
            gt = gender_tags.get({"male": "男", "female": "女"}.get(c.gender, ""))
            if gt is not None and gt not in char_tags:
                char_tags.append(gt)
            char = m.Character(name=c.name, alias="、".join(c.aliases) or None, gender=c.gender, summary=c.summary or None,
                               profile=extract_mod.profile_markdown(data) or None, world_id=payload.world_id,
                               work_id=payload.work_id, tags=char_tags)
            session.add(char)
            session.flush()
            created.append(char.id)
        for n in [c.name, *c.aliases]:
            by_name.setdefault(n, char)
    rel_count = 0
    if payload.relations:
        existing_rel = {(r.source_id, r.target_id, r.kind) for r in session.scalars(select(m.Relation)).all()}
        for c in payload.characters:
            src = by_name.get(c.name)
            for r in c.relations:
                dst = by_name.get(r.target)
                if src is None or dst is None or src.id == dst.id:
                    continue
                key = (src.id, dst.id, r.kind)
                if key in existing_rel or (dst.id, src.id, r.kind) in existing_rel:
                    continue
                existing_rel.add(key)
                session.add(m.Relation(source_id=src.id, target_id=dst.id, kind=r.kind[:60], description=r.evidence or None,
                                       ai_suggested=True, confirmed=False))
                rel_count += 1
    return {"created": created, "updated": updated, "relations": rel_count}


# ---------- 语义检索 ----------
@router.get("/api/search/semantic")
def semantic_search(q: str, entity: str | None = None, mode: str = Query("semantic", pattern="^(semantic|hybrid)$"),
                    limit: int = Query(20, ge=1, le=100), session: Session = Depends(get_session)) -> dict[str, Any]:
    try:
        hits = embed_mod.query(session, q, entity=entity, limit=limit if mode == "semantic" else 50)
    except AIUnavailable as exc:
        raise HTTPException(503, str(exc)) from exc
    if mode == "hybrid":
        hits = embed_mod.hybrid(keyword_search(session, q, entity=entity, limit=50), hits, limit=limit)
    return {"items": hits, "mode": mode, "model": embed_mod.embedder(session)[0]}


@router.get("/api/search/similar")
def similar_items(entity: str, id: int, limit: int = Query(10, ge=1, le=50), session: Session = Depends(get_session)) -> dict[str, Any]:
    try:
        return {"items": embed_mod.similar(session, entity, id, limit)}
    except AIUnavailable as exc:
        raise HTTPException(503, str(exc)) from exc


@router.get("/api/search/semantic/status")
def semantic_status(session: Session = Depends(get_session)) -> dict[str, Any]:
    return embed_mod.status(session)


@router.post("/api/search/semantic/index", status_code=202)
def semantic_index(session: Session = Depends(get_session)) -> dict[str, Any]:
    try:
        embed_mod.embedder(session)
    except AIUnavailable as exc:
        raise HTTPException(503, str(exc)) from exc

    def work(job: jobs.Job) -> None:
        with new_session() as db:
            job.result = embed_mod.index(db, job)

    return jobs.start("embed", "更新语义索引", 0, work).to_dict()


# ---------- 自动打标签 ----------
@router.get("/api/ai/tagger/status")
def tagger_status(session: Session = Depends(get_session)) -> dict[str, Any]:
    st = registry.get_all(session)
    return {"backend": st["tagger_backend"], "threshold": st["tagger_threshold"], "model": st["tagger_model"],
            "enabled": st["tagger_backend"] != "off"}


@router.post("/api/ai/tagger/assets/{asset_id}")
def tagger_suggest(asset_id: int, session: Session = Depends(get_session)) -> dict[str, Any]:
    asset = get_or_404(session, m.Asset, asset_id)
    try:
        return tagger_mod.suggest(session, asset)
    except AIUnavailable as exc:
        raise HTTPException(503, str(exc)) from exc
    except (ValueError, OSError) as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("/api/ai/tagger/run", status_code=202)
def tagger_run(payload: s.TaggerRun, session: Session = Depends(get_session)) -> dict[str, Any]:
    """批量识别：把把握度 ≥ min_score 且能对上已有标签的结果打上（apply），原始结果记在素材的 meta.auto_tags。"""
    if registry.get(session, "tagger_backend") == "off":
        raise HTTPException(503, "自动打标签未开启（设置页 → 自动打标签）")
    stmt = select(m.Asset.id).where(m.Asset.width.is_not(None)).order_by(m.Asset.id)
    if payload.asset_ids:
        stmt = stmt.where(m.Asset.id.in_(payload.asset_ids))
    elif payload.only_untagged:
        stmt = stmt.where(~m.Asset.tags.any())
    ids = list(session.scalars(stmt.limit(payload.limit)).all())

    def work(job: jobs.Job) -> None:
        applied = 0
        with new_session() as db:
            for aid in ids:
                job.check()
                asset = db.get(m.Asset, aid)
                try:
                    res = tagger_mod.suggest(db, asset)
                except (AIUnavailable, ValueError, OSError) as exc:
                    job.errors.append(f"#{aid}：{exc}")
                    job.step()
                    continue
                meta = dict(asset.meta or {})
                meta["auto_tags"] = {"backend": res["backend"], "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                                     "tags": [[x["name"], x["score"]] for x in res["suggestions"]]}
                asset.meta = meta
                if payload.apply:
                    for sug in res["suggestions"]:
                        if sug["tag"] and sug["score"] >= payload.min_score and not sug["applied"]:
                            tag = db.get(m.Tag, sug["tag"]["id"])
                            if tag not in asset.tags:
                                asset.tags.append(tag)
                                applied += 1
                db.commit()
                job.step(asset.title)
        job.result = {"assets": len(ids), "applied": applied}

    return jobs.start("tagger", f"自动打标签（{len(ids)} 张）", len(ids), work).to_dict()
