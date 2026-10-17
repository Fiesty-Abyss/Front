"""设置页：AI 服务（OpenAI 兼容）增删改查、连接测试、模型列表，以及各功能使用哪个服务。"""

from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models as m
from .. import schemas as s
from ..ai import AIUnavailable, registry
from ..ai.provider import env_provider
from ..crud import get_or_404
from ..db import get_session

router = APIRouter(tags=["设置"])

PRESETS = [
    {"name": "Ollama（本机）", "base_url": "http://127.0.0.1:11434/v1", "chat_model": "qwen2.5:14b",
     "embedding_model": "bge-m3", "vision_model": "qwen2.5vl:7b", "needs_key": False},
    {"name": "LM Studio（本机）", "base_url": "http://127.0.0.1:1234/v1", "chat_model": "", "embedding_model": "",
     "vision_model": "", "needs_key": False},
    {"name": "OpenAI", "base_url": "https://api.openai.com/v1", "chat_model": "gpt-4o-mini",
     "embedding_model": "text-embedding-3-small", "vision_model": "gpt-4o-mini", "needs_key": True},
    {"name": "DeepSeek", "base_url": "https://api.deepseek.com/v1", "chat_model": "deepseek-chat", "embedding_model": "",
     "vision_model": "", "needs_key": True},
    {"name": "OpenRouter", "base_url": "https://openrouter.ai/api/v1", "chat_model": "", "embedding_model": "",
     "vision_model": "", "needs_key": True},
]


def _read(cfg: m.AIProviderConfig) -> dict[str, Any]:
    return s.ProviderRead.model_validate(cfg).model_dump(mode="json")


@router.get("/api/ai/providers")
def list_providers(session: Session = Depends(get_session)) -> dict[str, Any]:
    rows = session.scalars(select(m.AIProviderConfig).order_by(m.AIProviderConfig.id)).all()
    env = env_provider()
    return {
        "items": [_read(r) for r in rows],
        "env": {"base_url": env.base_url, "model": env.model} if env else None,
        "presets": PRESETS,
    }


@router.post("/api/ai/providers", status_code=201)
def create_provider(payload: s.ProviderCreate, session: Session = Depends(get_session)) -> dict[str, Any]:
    data = payload.model_dump()
    data["api_key"] = (data.get("api_key") or "").strip() or None
    data["base_url"] = data["base_url"].strip().rstrip("/")
    cfg = m.AIProviderConfig(**data)
    session.add(cfg)
    session.commit()
    session.refresh(cfg)
    return _read(cfg)


@router.get("/api/ai/providers/{pid}")
def get_provider_cfg(pid: int, session: Session = Depends(get_session)) -> dict[str, Any]:
    return _read(get_or_404(session, m.AIProviderConfig, pid))


@router.patch("/api/ai/providers/{pid}")
def update_provider(pid: int, payload: s.ProviderUpdate, session: Session = Depends(get_session)) -> dict[str, Any]:
    cfg = get_or_404(session, m.AIProviderConfig, pid)
    data = payload.model_dump(exclude_unset=True)
    if "api_key" in data:
        key = data.pop("api_key")
        if key is not None:
            cfg.api_key = key.strip() or None
    if data.get("base_url"):
        data["base_url"] = data["base_url"].strip().rstrip("/")
    for k, v in data.items():
        setattr(cfg, k, v)
    session.commit()
    session.refresh(cfg)
    return _read(cfg)


@router.delete("/api/ai/providers/{pid}", status_code=204)
def delete_provider(pid: int, session: Session = Depends(get_session)) -> Response:
    cfg = get_or_404(session, m.AIProviderConfig, pid)
    session.delete(cfg)
    changes = {k: None for k in ("chat_provider_id", "embedding_provider_id", "vision_provider_id") if registry.get(session, k) == pid}
    session.commit()
    if changes:
        registry.put(session, changes)
    return Response(status_code=204)


@router.get("/api/ai/providers/{pid}/models")
def provider_models(pid: int, session: Session = Depends(get_session)) -> dict[str, Any]:
    p = registry.from_config(get_or_404(session, m.AIProviderConfig, pid))
    try:
        return {"models": p.list_models()}
    except AIUnavailable as exc:
        raise HTTPException(502, str(exc)) from exc


@router.post("/api/ai/providers/{pid}/test")
def test_provider(pid: int, session: Session = Depends(get_session)) -> dict[str, Any]:
    """依次测试：模型列表、对话、嵌入（各自可选）。不会抛错，结果逐项返回。"""
    cfg = get_or_404(session, m.AIProviderConfig, pid)
    p = registry.from_config(cfg)
    out: dict[str, Any] = {"ok": True}

    def run(name: str, fn) -> None:
        t0 = time.perf_counter()
        try:
            out[name] = {"ok": True, "result": fn(), "ms": round((time.perf_counter() - t0) * 1000)}
        except AIUnavailable as exc:
            out[name] = {"ok": False, "error": str(exc), "ms": round((time.perf_counter() - t0) * 1000)}
            out["ok"] = False

    run("models", lambda: p.list_models()[:50])
    if cfg.chat_model:
        run("chat", lambda: p.chat([{"role": "user", "content": "请只回复：连接成功"}], temperature=0, max_tokens=32)[:200])
    if cfg.embedding_model:
        run("embedding", lambda: {"dim": len(p.embed(["测试"])[0])})
    return out


@router.get("/api/settings")
def get_settings_api(session: Session = Depends(get_session)) -> dict[str, Any]:
    return registry.get_all(session)


@router.patch("/api/settings")
def update_settings(payload: s.SettingsUpdate, session: Session = Depends(get_session)) -> dict[str, Any]:
    data = payload.model_dump(exclude_unset=True)
    for key in ("chat_provider_id", "embedding_provider_id", "vision_provider_id"):
        if data.get(key) is not None:
            get_or_404(session, m.AIProviderConfig, data[key])
    return registry.put(session, data)
