"""PNG 文本块读写：SD WebUI 出图参数（parameters）与 SillyTavern 角色卡（chara / ccv3）。"""

from __future__ import annotations

import base64
import io
import json
import re
from typing import Any

from PIL import Image, PngImagePlugin


def read_png_text(data: bytes) -> dict[str, str]:
    try:
        with Image.open(io.BytesIO(data)) as img:
            if img.format != "PNG":
                return {}
            info = dict(getattr(img, "text", {}) or {})
            return {k: v for k, v in info.items() if isinstance(v, str)}
    except Exception:
        return {}


_PARAM_RE = re.compile(r"\s*([\w ]+?):\s*(\"(?:[^\"\\]|\\.)*\"|[^,]+)(?:,|$)")


def parse_sd_parameters(text: str) -> dict[str, Any]:
    """解析 A1111 / Forge / SD.Next 写进 PNG 的 parameters 文本。"""
    lines = text.strip().split("\n")
    if not lines:
        return {}
    settings_line = ""
    if re.search(r"\bSteps:\s*\d+", lines[-1]):
        settings_line = lines.pop()
    positive: list[str] = []
    negative: list[str] = []
    target = positive
    for line in lines:
        if line.startswith("Negative prompt:"):
            target = negative
            line = line[len("Negative prompt:"):].strip()
        target.append(line)
    params: dict[str, str] = {}
    for key, value in _PARAM_RE.findall(settings_line):
        params[key.strip()] = value.strip().strip('"')
    return {
        "prompt": "\n".join(positive).strip(),
        "negative_prompt": "\n".join(negative).strip(),
        "params": params,
    }


# ---------------- Character Card ----------------
CARD_FIELDS = [
    "name",
    "description",
    "personality",
    "scenario",
    "first_mes",
    "mes_example",
    "creator_notes",
    "system_prompt",
    "post_history_instructions",
    "alternate_greetings",
    "tags",
    "creator",
    "character_version",
    "extensions",
]


def card_to_v2(card: Any) -> dict[str, Any]:
    data = {f: getattr(card, "card_tags" if f == "tags" else f) for f in CARD_FIELDS}
    data["alternate_greetings"] = list(data["alternate_greetings"] or [])
    data["tags"] = list(data["tags"] or [])
    data["extensions"] = dict(data["extensions"] or {})
    return {"spec": "chara_card_v2", "spec_version": "2.0", "data": data}


def v2_to_fields(payload: dict[str, Any]) -> dict[str, Any]:
    """接受 V1（扁平字段）、V2（chara_card_v2）、V3（chara_card_v3）JSON。"""
    if not isinstance(payload, dict):
        raise ValueError("角色卡 JSON 必须是对象")
    data = payload.get("data") if payload.get("spec") in ("chara_card_v2", "chara_card_v3") else payload
    if not isinstance(data, dict) or not data.get("name"):
        raise ValueError("角色卡缺少 name 字段")
    out: dict[str, Any] = {}
    for f in CARD_FIELDS:
        if f not in data:
            continue
        key = "card_tags" if f == "tags" else f
        out[key] = data[f]
    # V1 字段名兼容
    if "char_persona" in data and not out.get("personality"):
        out["personality"] = data["char_persona"]
    if "world_scenario" in data and not out.get("scenario"):
        out["scenario"] = data["world_scenario"]
    if "char_greeting" in data and not out.get("first_mes"):
        out["first_mes"] = data["char_greeting"]
    if "example_dialogue" in data and not out.get("mes_example"):
        out["mes_example"] = data["example_dialogue"]
    for key in ("alternate_greetings", "card_tags"):
        if key in out and not isinstance(out[key], list):
            out[key] = []
    if "extensions" in out and not isinstance(out["extensions"], dict):
        out["extensions"] = {}
    for key, value in list(out.items()):
        if value is None:
            out.pop(key)
    return out


def read_card_png(data: bytes) -> dict[str, Any]:
    chunks = read_png_text(data)
    raw = chunks.get("ccv3") or chunks.get("chara")
    if not raw:
        raise ValueError("PNG 中没有找到角色卡数据（chara / ccv3 文本块）")
    try:
        return json.loads(base64.b64decode(raw).decode("utf-8"))
    except Exception as exc:  # noqa: BLE001
        raise ValueError(f"角色卡数据无法解码: {exc}") from exc


def placeholder_avatar(name: str, size: tuple[int, int] = (400, 600)) -> Image.Image:
    """没有头像时生成纯色占位图（只含渐变与首字母，不含任何第三方素材）。"""
    from PIL import ImageDraw

    img = Image.new("RGB", size, (40, 44, 70))
    draw = ImageDraw.Draw(img)
    for y in range(size[1]):
        t = y / size[1]
        draw.line([(0, y), (size[0], y)], fill=(int(60 + 120 * t), int(70 + 40 * t), int(140 - 40 * t)))
    return img


def write_card_png(card_json: dict[str, Any], base_image: bytes | None) -> bytes:
    if base_image:
        img = Image.open(io.BytesIO(base_image))
        img.load()
    else:
        img = placeholder_avatar(card_json.get("data", {}).get("name", "?"))
    if img.mode not in ("RGB", "RGBA"):
        img = img.convert("RGBA")
    info = PngImagePlugin.PngInfo()
    encoded = base64.b64encode(json.dumps(card_json, ensure_ascii=False).encode("utf-8")).decode("ascii")
    info.add_text("chara", encoded)
    out = io.BytesIO()
    img.save(out, format="PNG", pnginfo=info)
    return out.getvalue()
