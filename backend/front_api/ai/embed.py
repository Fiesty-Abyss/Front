"""语义检索：把每个条目（素材、角色、世界观、条目、提示词……）转成向量，按余弦相似度排序。

两种向量来源：
- provider：设置页里选的 AI 服务的 /embeddings 接口（例如 Ollama 的 bge-m3、nomic-embed-text，
  或 OpenAI text-embedding-3-small）。这是真正的语义向量，推荐使用。
- local：内置的字符 n-gram 哈希向量，不需要任何模型、离线可用，但它只能找到“用词相近”的内容，
  不理解同义词，算是近似的模糊检索。
"""

from __future__ import annotations

import hashlib
import math
import re
from array import array
from collections import Counter
from collections.abc import Callable, Iterator
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from .. import models as m
from ..search import SPEC
from . import registry

LOCAL_MODEL = "local:ngram-512"
LOCAL_DIM = 512
MAX_CHARS = 2000
CJK = re.compile(r"[\u3040-\u30ff\u3400-\u9fff\uf900-\ufaff\uac00-\ud7af]+")
WORD = re.compile(r"[a-z0-9]+")


def _features(textv: str) -> Counter:
    t = textv.casefold()
    feats: Counter = Counter()
    for run in CJK.findall(t):
        feats.update(run)
        feats.update(run[i:i + 2] for i in range(len(run) - 1))
    for w in WORD.findall(t):
        feats[w] += 1
        if len(w) > 4:
            feats.update("#" + w[i:i + 4] for i in range(len(w) - 3))
    return feats


def local_embed(texts: list[str], dim: int = LOCAL_DIM) -> list[list[float]]:
    out = []
    for textv in texts:
        vec = [0.0] * dim
        for feat, tf in _features(textv).items():
            h = hashlib.blake2b(feat.encode(), digest_size=8).digest()
            idx = int.from_bytes(h[:4], "little") % dim
            sign = 1.0 if h[4] & 1 else -1.0
            vec[idx] += sign * (1.0 + math.log(tf))
        norm = math.sqrt(sum(x * x for x in vec)) or 1.0
        out.append([x / norm for x in vec])
    return out


def _normalize(vec: list[float]) -> list[float]:
    norm = math.sqrt(sum(x * x for x in vec)) or 1.0
    return [x / norm for x in vec]


def embedder(session: Session) -> tuple[str, Callable[[list[str]], list[list[float]]]]:
    if registry.get(session, "embedding_backend") == "provider":
        p = registry.embedding_provider(session)
        if p is None or not p.embedding_model:
            from .provider import AIUnavailable
            raise AIUnavailable("语义检索设为使用 AI 服务，但还没有选择带嵌入模型的服务（设置页 → 语义检索）")
        return f"p{p.provider_id}:{p.embedding_model}", lambda texts: [_normalize(v) for v in p.embed(texts)]
    return LOCAL_MODEL, local_embed


def entity_texts(session: Session) -> Iterator[tuple[str, int, str]]:
    for cls, (entity, title_fn, body_fn) in SPEC.items():
        for obj in session.scalars(select(cls)).all():
            body = body_fn(obj) or ""
            yield entity, obj.id, f"{title_fn(obj) or ''}\n{body}"[:MAX_CHARS]


def _hash(textv: str) -> str:
    return hashlib.sha256(textv.encode()).hexdigest()


def index(session: Session, job: Any = None, batch: int = 32) -> dict[str, int]:
    model, fn = embedder(session)
    existing = {(e.entity, e.entity_id): e for e in session.scalars(select(m.Embedding).where(m.Embedding.model == model)).all()}
    todo, seen = [], set()
    for entity, eid, textv in entity_texts(session):
        seen.add((entity, eid))
        h = _hash(textv)
        cur = existing.get((entity, eid))
        if cur is None or cur.text_hash != h:
            todo.append((entity, eid, textv, h))
    removed = 0
    for key, row in existing.items():
        if key not in seen:
            session.delete(row)
            removed += 1
    if job is not None:
        job.total = len(todo)
    for i in range(0, len(todo), batch):
        part = todo[i:i + batch]
        vectors = fn([t[2] for t in part])
        for (entity, eid, _textv, h), vec in zip(part, vectors):
            blob = array("f", vec).tobytes()
            row = existing.get((entity, eid))
            if row is None:
                session.add(m.Embedding(entity=entity, entity_id=eid, model=model, dim=len(vec), vector=blob, text_hash=h))
            else:
                row.vector, row.dim, row.text_hash = blob, len(vec), h
            if job is not None:
                job.step(f"{entity} #{eid}")
        session.commit()
    session.commit()
    return {"indexed": len(todo), "removed": removed, "total": len(seen), "model": model}


def status(session: Session) -> dict[str, Any]:
    backend = registry.get(session, "embedding_backend")
    try:
        model, _ = embedder(session)
        error = None
    except Exception as exc:  # noqa: BLE001
        model, error = None, str(exc)
    total = sum(1 for _ in entity_texts(session))
    indexed = session.query(m.Embedding).filter(m.Embedding.model == model).count() if model else 0
    return {"backend": backend, "model": model, "indexed": indexed, "total": total, "error": error}


def _load(session: Session, model: str, entity: str | None) -> list[tuple[str, int, array]]:
    stmt = select(m.Embedding.entity, m.Embedding.entity_id, m.Embedding.vector).where(m.Embedding.model == model)
    if entity:
        stmt = stmt.where(m.Embedding.entity == entity)
    rows = []
    for ent, eid, blob in session.execute(stmt).all():
        vec = array("f")
        vec.frombytes(blob)
        rows.append((ent, eid, vec))
    return rows


def _rank(rows, qvec: list[float], limit: int, exclude: tuple[str, int] | None = None) -> list[tuple[str, int, float]]:
    scored = []
    for ent, eid, vec in rows:
        if exclude == (ent, eid) or len(vec) != len(qvec):
            continue
        scored.append((ent, eid, sum(a * b for a, b in zip(vec, qvec))))
    scored.sort(key=lambda r: -r[2])
    return scored[:limit]


def _decorate(session: Session, hits: list[tuple[str, int, float]]) -> list[dict[str, Any]]:
    out = []
    for ent, eid, score in hits:
        row = session.connection().execute(
            text("SELECT title, substr(body, 1, 120) FROM search_index WHERE entity=:e AND entity_id=:i"), {"e": ent, "i": eid}
        ).fetchone()
        if row is None:
            continue
        out.append({"entity": ent, "id": eid, "title": row[0], "snippet": row[1], "score": round(float(score), 4)})
    return out


def query(session: Session, q: str, entity: str | None = None, limit: int = 20, auto_index: bool = True) -> list[dict[str, Any]]:
    q = (q or "").strip()
    if not q:
        return []
    model, fn = embedder(session)
    if auto_index and model == LOCAL_MODEL:
        index(session)  # 本地向量很便宜：查询前顺手补齐新增 / 修改过的条目
    qvec = fn([q])[0]
    return _decorate(session, _rank(_load(session, model, entity), qvec, limit))


def similar(session: Session, entity: str, entity_id: int, limit: int = 10) -> list[dict[str, Any]]:
    model, _ = embedder(session)
    row = session.scalar(select(m.Embedding).where(m.Embedding.model == model, m.Embedding.entity == entity,
                                                   m.Embedding.entity_id == entity_id))
    if row is None:
        return []
    vec = array("f")
    vec.frombytes(row.vector)
    return _decorate(session, _rank(_load(session, model, None), list(vec), limit, exclude=(entity, entity_id)))


def hybrid(keyword_hits: list[dict[str, Any]], semantic_hits: list[dict[str, Any]], limit: int = 30, k: int = 60) -> list[dict[str, Any]]:
    """倒数排名融合（RRF）：两边的排名各贡献 1/(k+rank)。"""
    scores: dict[tuple[str, int], float] = {}
    info: dict[tuple[str, int], dict[str, Any]] = {}
    for source, hits in (("keyword", keyword_hits), ("semantic", semantic_hits)):
        for rank, h in enumerate(hits):
            key = (h["entity"], h["id"])
            scores[key] = scores.get(key, 0.0) + 1.0 / (k + rank + 1)
            cur = info.setdefault(key, dict(h, sources=[]))
            cur["sources"].append(source)
            if source == "semantic":
                cur["score"] = h.get("score")
    ordered = sorted(scores, key=lambda key: -scores[key])[:limit]
    return [dict(info[key], rrf=round(scores[key], 5)) for key in ordered]
