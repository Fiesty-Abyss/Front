"""图片自动打标签（可选，默认关闭）。两种后端：

- webui：SD WebUI 的 WD14 Tagger 扩展（stable-diffusion-webui-wd14-tagger）提供的
  POST /tagger/v1/interrogate 接口，完全在本机运行。
- vision：设置页里选的 AI 服务的视觉模型（例如 Ollama 的 qwen2.5vl、llava，或 GPT-4o 等）。

识别出的标签按名称和别名匹配已有标签（下划线视为空格、不分大小写）。可以给标签加
danbooru 风格的别名（例如给「女」加别名 1girl），让识别结果自动对上你自己的标签体系。
"""

from __future__ import annotations

import base64
import io
import json
import re
from typing import Any

import httpx
from PIL import Image
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models as m
from ..config import get_settings
from . import registry
from .provider import AIUnavailable

TASK_MARK = "[FRONT_TASK:tag_image]"


def client_factory(base_url: str, timeout: float) -> httpx.Client:
    return httpx.Client(base_url=base_url, timeout=timeout)


def norm(name: str) -> str:
    return re.sub(r"\s+", " ", (name or "").replace("_", " ")).strip().casefold()


def image_bytes(session: Session, asset: m.Asset, max_side: int = 768) -> bytes:
    if not asset.file_path or not asset.width:
        raise ValueError("这个素材不是图片")
    path = get_settings().data_dir / asset.file_path
    with Image.open(path) as im:
        im = im.convert("RGB")
        im.thumbnail((max_side, max_side))
        buf = io.BytesIO()
        im.save(buf, "PNG")
        return buf.getvalue()


def webui_tags(png: bytes, threshold: float, model: str) -> list[tuple[str, float]]:
    url = get_settings().sd_webui_url
    if not url:
        raise AIUnavailable("自动打标签设为 WebUI Tagger，但没有设置 FRONT_SD_WEBUI_URL")
    try:
        with client_factory(url, 120.0) as client:
            r = client.post("/tagger/v1/interrogate", json={"image": base64.b64encode(png).decode(), "model": model,
                                                             "threshold": threshold})
            r.raise_for_status()
            data = r.json()
    except httpx.HTTPError as exc:
        raise AIUnavailable(f"WebUI Tagger 调用失败（需要安装 wd14-tagger 扩展并以 --api 启动）: {exc}") from exc
    caption = data.get("caption", data)
    if isinstance(caption, dict) and isinstance(caption.get("tag"), dict):  # 新版扩展：{"tag": {...}, "rating": {...}}
        caption = caption["tag"]
    tags = [(str(k), float(v)) for k, v in (caption or {}).items() if isinstance(v, (int, float))]
    return sorted([t for t in tags if t[1] >= threshold], key=lambda t: -t[1])


def vision_prompt(candidates: list[str]) -> str:
    cand = "、".join(candidates[:150])
    return (
        f"{TASK_MARK}\n给这张图片打标签。优先从候选标签里选，也可以补充 danbooru 风格的英文标签。"
        '只输出 JSON：{"tags":[{"name":"标签","score":0.0到1.0的把握}]}，最多 20 个。\n候选标签：' + cand
    )


def parse_vision(textv: str) -> list[tuple[str, float]]:
    match = re.search(r"\{.*\}|\[.*\]", textv or "", re.S)
    if not match:
        return []
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        return []
    items = data.get("tags") if isinstance(data, dict) else data
    out = []
    for it in items if isinstance(items, list) else []:
        if isinstance(it, str):
            out.append((it, 0.8))
        elif isinstance(it, dict) and it.get("name"):
            try:
                out.append((str(it["name"]), max(0.0, min(1.0, float(it.get("score", 0.8))))))
            except (TypeError, ValueError):
                out.append((str(it["name"]), 0.8))
    return out


def tag_lookup(session: Session) -> dict[str, m.Tag]:
    out: dict[str, m.Tag] = {}
    for tag in session.scalars(select(m.Tag)).all():
        for name in [tag.name, *(tag.aliases or [])]:
            out.setdefault(norm(name), tag)
    return out


def suggest(session: Session, asset: m.Asset) -> dict[str, Any]:
    settings = registry.get_all(session)
    backend = settings["tagger_backend"]
    if backend == "off":
        raise AIUnavailable("自动打标签未开启（设置页 → 自动打标签）")
    png = image_bytes(session, asset)
    lookup = tag_lookup(session)
    threshold = float(settings["tagger_threshold"] or 0.35)
    if backend == "webui":
        raw = webui_tags(png, threshold, settings["tagger_model"])
    else:
        provider = registry.vision_provider(session)
        names = sorted({t.name for t in lookup.values()})
        raw = parse_vision(provider.vision(vision_prompt(names), png))
    seen: set[str] = set()
    suggestions = []
    for name, score in raw:
        key = norm(name)
        if not key or key in seen:
            continue
        seen.add(key)
        tag = lookup.get(key)
        suggestions.append({
            "name": name, "score": round(score, 3),
            "tag": {"id": tag.id, "name": tag.name, "category": tag.category, "color": tag.color} if tag else None,
            "applied": bool(tag and tag in asset.tags),
        })
    return {"backend": backend, "threshold": threshold, "suggestions": suggestions}
