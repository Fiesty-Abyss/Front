"""AI 服务与功能设置：对话、嵌入（语义检索）、自动打标签各自用哪个服务。"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from .. import models as m
from .provider import AIProvider, NullProvider, OpenAICompatibleProvider, env_provider

DEFAULTS: dict[str, Any] = {
    "chat_provider_id": None,        # None = 使用环境变量
    "embedding_backend": "local",    # local / provider
    "embedding_provider_id": None,
    "tagger_backend": "off",         # off / webui / vision
    "vision_provider_id": None,
    "tagger_threshold": 0.35,
    "tagger_model": "wd14-vit-v2-git",
    "user_name": "User",
}

# 只允许测试替换：provider_id -> transport
transport_override: dict[int, Any] = {}


def get_all(session: Session) -> dict[str, Any]:
    out = dict(DEFAULTS)
    for row in session.query(m.AppSetting).all():
        if row.key in DEFAULTS:
            out[row.key] = row.value
    return out


def get(session: Session, key: str) -> Any:
    row = session.get(m.AppSetting, key)
    return row.value if row is not None else DEFAULTS.get(key)


def put(session: Session, values: dict[str, Any]) -> dict[str, Any]:
    for key, value in values.items():
        if key not in DEFAULTS:
            continue
        row = session.get(m.AppSetting, key)
        if row is None:
            session.add(m.AppSetting(key=key, value=value))
        else:
            row.value = value
    session.commit()
    return get_all(session)


def from_config(cfg: m.AIProviderConfig) -> OpenAICompatibleProvider:
    return OpenAICompatibleProvider(
        cfg.base_url, cfg.chat_model, cfg.api_key, timeout=cfg.timeout or 120.0, label=cfg.name,
        embedding_model=cfg.embedding_model, vision_model=cfg.vision_model,
        temperature=cfg.temperature if cfg.temperature is not None else 0.8, max_tokens=cfg.max_tokens,
        provider_id=cfg.id, transport=transport_override.get(cfg.id),
    )


def _by_setting(session: Session, key: str) -> OpenAICompatibleProvider | None:
    pid = get(session, key)
    if pid:
        cfg = session.get(m.AIProviderConfig, int(pid))
        if cfg is not None:
            return from_config(cfg)
    return None


def chat_provider(session: Session) -> AIProvider:
    p = _by_setting(session, "chat_provider_id")
    if p is not None and p.model:
        return p
    return env_provider() or NullProvider()


def chat_source(session: Session) -> str:
    p = _by_setting(session, "chat_provider_id")
    if p is not None and p.model:
        return "settings"
    return "env" if env_provider() else "none"


def embedding_provider(session: Session) -> OpenAICompatibleProvider | None:
    return _by_setting(session, "embedding_provider_id")


def vision_provider(session: Session) -> AIProvider:
    return _by_setting(session, "vision_provider_id") or NullProvider()
