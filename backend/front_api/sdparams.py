"""出图参数的统一表示：SD WebUI、ComfyUI 和 Front 自己发起的出图，参数名各不相同，
这里统一成同一套小写键，方便做参数差异高亮和 XY 网格。"""

from __future__ import annotations

import re
from typing import Any

# 统一后的键 → 中文名（前端展示用，顺序即展示顺序）
LABELS: dict[str, str] = {
    "model": "模型",
    "sampler": "采样器",
    "scheduler": "调度器",
    "steps": "步数",
    "cfg": "CFG",
    "seed": "种子",
    "size": "尺寸",
    "clip_skip": "Clip skip",
    "denoise": "重绘幅度",
    "vae": "VAE",
    "loras": "LoRA",
    "prompt_sr": "提示词替换",
}

_ALIASES: dict[str, str] = {
    "model": "model", "checkpoint": "model", "ckpt": "model", "sd_model_checkpoint": "model",
    "sampler": "sampler", "sampler_name": "sampler",
    "schedule type": "scheduler", "scheduler": "scheduler",
    "steps": "steps",
    "cfg scale": "cfg", "cfg": "cfg", "cfg_scale": "cfg",
    "seed": "seed",
    "size": "size",
    "clip skip": "clip_skip", "clip_skip": "clip_skip",
    "denoising strength": "denoise", "denoise": "denoise",
    "vae": "vae",
    "loras": "loras",
    "prompt_sr": "prompt_sr",
}


def _num(v: Any) -> Any:
    if isinstance(v, bool) or not isinstance(v, (str, int, float)):
        return v
    if isinstance(v, (int, float)):
        return int(v) if float(v).is_integer() else float(v)
    t = v.strip()
    if re.fullmatch(r"-?\d+", t):
        return int(t)
    if re.fullmatch(r"-?\d+\.\d+", t):
        f = float(t)
        return int(f) if f.is_integer() else f
    return t


def normalize(params: dict[str, Any] | None) -> dict[str, Any]:
    """把任意来源的参数字典转成统一键。未知键原样保留（小写），以下划线开头的内部键丢弃。"""
    out: dict[str, Any] = {}
    p = dict(params or {})
    w, h = p.pop("width", None), p.pop("height", None)
    for key, value in p.items():
        if key.startswith("_") or key in ("prompt", "negative_prompt", "negative"):
            continue
        k = _ALIASES.get(key.lower(), key.lower().replace(" ", "_"))
        if k == "model" and isinstance(value, str):
            value = re.sub(r"\.(safetensors|ckpt|pt|pth|gguf)$", "", value.replace("\\", "/").split("/")[-1], flags=re.I)
        out.setdefault(k, _num(value))
    if w and h and "size" not in out:
        out["size"] = f"{int(w)}x{int(h)}"
    return out


def value_label(v: Any) -> str:
    if v is None:
        return "—"
    if isinstance(v, list):
        return ", ".join(value_label(x) for x in v)
    if isinstance(v, dict):
        return ", ".join(f"{k}:{x}" for k, x in v.items())
    return str(v)


def diff_keys(rows: list[dict[str, Any]]) -> list[str]:
    """在多组参数里取值不同的键。缺失的值视为“未知”，不算差异（导入的旧图常常只记录了部分参数）。"""
    keys: list[str] = []
    seen = {k for r in rows for k in r}
    for k in [*LABELS, *sorted(seen - set(LABELS))]:
        if k not in seen:
            continue
        values = {value_label(r[k]) for r in rows if r.get(k) is not None}
        if len(values) > 1:
            keys.append(k)
    return keys


def sort_values(values: list[Any]) -> list[Any]:
    uniq: list[Any] = []
    for v in values:
        if v not in uniq:
            uniq.append(v)
    if all(isinstance(v, (int, float)) for v in uniq):
        return sorted(uniq)
    return uniq


def tokens(prompt: str) -> list[str]:
    return [t.strip() for t in re.split(r"[,\n]", prompt or "") if t.strip()]
