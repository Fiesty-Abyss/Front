"""可选的 Civitai 元数据匹配：按模型哈希查询 https://civitai.com/api/v1/model-versions/by-hash/<hash>。
只在用户点击“匹配 Civitai”时联网；设置 FRONT_CIVITAI=off 可完全关闭。本地的 .civitai.info 不需要联网。"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable

import httpx

from .config import get_settings

API = "https://civitai.com/api/v1"
IMAGE_HOSTS = ("image.civitai.com", "imagecache.civitai.com")

TYPE_MAP = {
    "checkpoint": "checkpoint", "lora": "lora", "locon": "lycoris", "lycoris": "lycoris", "dora": "lora",
    "textualinversion": "embedding", "vae": "vae", "controlnet": "controlnet", "upscaler": "upscaler",
    "hypernetwork": "hypernetwork",
}

# 测试时替换成 httpx.MockTransport 的工厂
client_factory: Callable[[], httpx.Client] = lambda: httpx.Client(timeout=20, follow_redirects=True)  # noqa: E731


class CivitaiDisabled(RuntimeError):
    pass


def base_model_label(raw: str | None) -> str | None:
    if not raw:
        return None
    r = raw.lower()
    for needle, label in (("flux", "Flux"), ("pony", "Pony"), ("illustrious", "Illustrious"), ("sdxl", "SDXL"),
                          ("sd 3", "SD3"), ("sd 2", "SD2"), ("sd 1", "SD1.5")):
        if needle in r:
            return label
    return raw


def summarize(info: dict[str, Any]) -> dict[str, Any]:
    """把 Civitai 的 model-version 响应（或 .civitai.info）精简成要保存的字段。"""
    model = info.get("model") or {}
    images = [i.get("url") for i in info.get("images") or [] if i.get("url") and not i.get("nsfw") and (i.get("nsfwLevel") or 1) <= 1]
    mid, vid = info.get("modelId"), info.get("id")
    return {
        "model_id": mid,
        "version_id": vid,
        "model_name": model.get("name"),
        "version_name": info.get("name"),
        "type": model.get("type"),
        "base_model": info.get("baseModel"),
        "trained_words": [w for w in info.get("trainedWords") or [] if isinstance(w, str)],
        "url": f"https://civitai.com/models/{mid}?modelVersionId={vid}" if mid and vid else None,
        "image_urls": images[:4],
        "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


def fields_from(summary: dict[str, Any]) -> dict[str, Any]:
    """Civitai 信息 → SDModel 字段。"""
    out: dict[str, Any] = {}
    if summary.get("model_name"):
        out["name"] = summary["model_name"]
    if summary.get("version_name"):
        out["version"] = summary["version_name"][:60]
    if (t := TYPE_MAP.get((summary.get("type") or "").lower())):
        out["kind"] = t
    if (b := base_model_label(summary.get("base_model"))):
        out["base_model"] = b
    if summary.get("trained_words"):
        out["trigger_words"] = ", ".join(summary["trained_words"])
    if summary.get("url"):
        out["source_url"] = summary["url"]
    return out


def lookup(hash_value: str) -> dict[str, Any] | None:
    """按哈希查询。找不到返回 None；网络错误抛 httpx.HTTPError。"""
    settings = get_settings()
    if not settings.civitai_enabled:
        raise CivitaiDisabled("Civitai 匹配已关闭（FRONT_CIVITAI=off）")
    headers = {"Authorization": f"Bearer {settings.civitai_api_key}"} if settings.civitai_api_key else {}
    with client_factory() as client:
        r = client.get(f"{API}/model-versions/by-hash/{hash_value}", headers=headers)
        if r.status_code == 404:
            return None
        r.raise_for_status()
        return r.json()


def download_image(url: str) -> bytes:
    host = httpx.URL(url).host
    if host not in IMAGE_HOSTS:
        raise ValueError("只下载 Civitai 图床上的预览图")
    with client_factory() as client:
        r = client.get(url)
        r.raise_for_status()
        if len(r.content) > 20 * 1024 * 1024:
            raise ValueError("预览图过大")
        return r.content
