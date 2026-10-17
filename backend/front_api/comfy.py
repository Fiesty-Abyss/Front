"""ComfyUI 出图信息解析。

ComfyUI 保存的 PNG 里有两个文本块：
- ``prompt``：API 格式，``{节点id: {"class_type": ..., "inputs": {...}}}``，输入里的连线写作 ``[节点id, 输出序号]``；
- ``workflow``：界面格式，``{"nodes": [{"type": ..., "widgets_values": [...]}], "links": [...]}``。

优先解析 ``prompt``（可以沿连线准确找到正/反向提示词），没有时退回 ``workflow`` 的粗略解析。
"""

from __future__ import annotations

import json
from typing import Any

SAMPLERS = {"KSampler", "KSamplerAdvanced", "SamplerCustom", "SamplerCustomAdvanced"}
CKPT_LOADERS = {
    "CheckpointLoaderSimple": "ckpt_name",
    "CheckpointLoader": "ckpt_name",
    "ImageOnlyCheckpointLoader": "ckpt_name",
    "UNETLoader": "unet_name",
    "UnetLoaderGGUF": "unet_name",
}
LORA_LOADERS = {"LoraLoader", "LoraLoaderModelOnly"}
LATENTS = {"EmptyLatentImage", "EmptySD3LatentImage", "EmptyHunyuanLatentVideo"}
TEXT_KEYS = ("text", "text_g", "text_l", "string", "value", "prompt")


def _is_link(v: Any) -> bool:
    return isinstance(v, list) and len(v) == 2 and isinstance(v[0], (str, int)) and isinstance(v[1], int)


class _Graph:
    def __init__(self, nodes: dict[str, Any]):
        self.nodes = {str(k): v for k, v in nodes.items() if isinstance(v, dict)}

    def node(self, ref: Any) -> dict[str, Any] | None:
        return self.nodes.get(str(ref[0])) if _is_link(ref) else None

    def value(self, v: Any, depth: int = 0) -> Any:
        """把一个输入解析成具体值：常量直接返回，连线则追到源节点取 text/value 等。"""
        if depth > 12:
            return None
        if not _is_link(v):
            return v
        src = self.node(v)
        if not src:
            return None
        inputs = src.get("inputs", {})
        for key in TEXT_KEYS + ("seed", "noise_seed", "int", "float"):
            if key in inputs:
                return self.value(inputs[key], depth + 1)
        return None

    def texts(self, ref: Any, depth: int = 0) -> list[str]:
        """沿条件（conditioning）连线收集所有提示词文本，支持 Combine / Concat / SetArea 等中间节点。"""
        if depth > 12:
            return []
        src = self.node(ref)
        if not src:
            return []
        inputs = src.get("inputs", {})
        out: list[str] = []
        found_text = False
        for key in TEXT_KEYS:
            if key in inputs:
                val = self.value(inputs[key], depth + 1)
                if isinstance(val, str) and val.strip() and val.strip() not in out:
                    out.append(val.strip())
                    found_text = True
        if not found_text:
            for key, val in inputs.items():
                if _is_link(val) and key not in ("clip", "model", "vae", "image", "mask"):
                    for t in self.texts(val, depth + 1):
                        if t not in out:
                            out.append(t)
        return out

    def by_type(self, types: set[str] | dict[str, str]) -> list[tuple[str, dict[str, Any]]]:
        return [(k, n) for k, n in self.nodes.items() if n.get("class_type") in types]


def parse_api_prompt(nodes: dict[str, Any]) -> dict[str, Any]:
    g = _Graph(nodes)
    params: dict[str, Any] = {}
    positive: list[str] = []
    negative: list[str] = []

    samplers = g.by_type(SAMPLERS)
    if samplers:
        _, s = sorted(samplers, key=lambda kv: kv[0])[0]
        inp = s.get("inputs", {})
        positive = g.texts(inp.get("positive"))
        negative = g.texts(inp.get("negative"))
        if not positive and _is_link(inp.get("guider")):
            guider = g.node(inp["guider"]) or {}
            positive = g.texts(guider.get("inputs", {}).get("conditioning") or guider.get("inputs", {}).get("positive"))
            negative = g.texts(guider.get("inputs", {}).get("negative"))
        for src, dst in (("seed", "Seed"), ("noise_seed", "Seed"), ("steps", "Steps"), ("cfg", "CFG scale"),
                         ("sampler_name", "Sampler"), ("scheduler", "Scheduler"), ("denoise", "Denoise")):
            if src in inp and dst not in params:
                val = g.value(inp[src])
                if val is not None:
                    params[dst] = val
    for _, n in g.by_type(LATENTS):
        inp = n.get("inputs", {})
        w, h = g.value(inp.get("width")), g.value(inp.get("height"))
        if w and h:
            params["Size"] = f"{w}x{h}"
            break
    models = []
    for _, n in g.by_type(CKPT_LOADERS):
        name = g.value(n.get("inputs", {}).get(CKPT_LOADERS[n["class_type"]]))
        if isinstance(name, str):
            models.append(name)
    if models:
        params["Model"] = models[0]
    loras = []
    for _, n in g.by_type(LORA_LOADERS):
        inp = n.get("inputs", {})
        name = g.value(inp.get("lora_name"))
        if isinstance(name, str):
            loras.append({"name": name, "strength": g.value(inp.get("strength_model"))})
    return {
        "source": "comfyui",
        "prompt": "\n".join(positive),
        "negative_prompt": "\n".join(negative),
        "params": {k: str(v) for k, v in params.items()},
        "models": models,
        "loras": loras,
        "node_count": len(g.nodes),
        "node_types": sorted({n.get("class_type", "?") for n in g.nodes.values()}),
    }


def parse_ui_workflow(wf: dict[str, Any]) -> dict[str, Any]:
    """界面格式只能粗略解析：不沿连线判断正反向，按出现顺序列出文本。"""
    nodes = wf.get("nodes") or []
    texts, models, loras, params = [], [], [], {}
    for n in nodes:
        t, wv = n.get("type"), n.get("widgets_values") or []
        if not isinstance(wv, list):
            continue
        if t and t.startswith("CLIPTextEncode") and wv and isinstance(wv[0], str):
            texts.append(wv[0].strip())
        elif t in CKPT_LOADERS and wv and isinstance(wv[0], str):
            models.append(wv[0])
        elif t in LORA_LOADERS and wv and isinstance(wv[0], str):
            loras.append({"name": wv[0], "strength": wv[1] if len(wv) > 1 else None})
        elif t == "KSampler" and len(wv) >= 7 and not params:
            params = {"Seed": wv[0], "Steps": wv[2], "CFG scale": wv[3], "Sampler": wv[4], "Scheduler": wv[5], "Denoise": wv[6]}
        elif t in LATENTS and len(wv) >= 2 and "Size" not in params:
            params["Size"] = f"{wv[0]}x{wv[1]}"
    if models:
        params["Model"] = models[0]
    return {
        "source": "comfyui-workflow",
        "prompt": texts[0] if texts else "",
        "negative_prompt": texts[1] if len(texts) > 1 else "",
        "params": {k: str(v) for k, v in params.items()},
        "models": models,
        "loras": loras,
        "node_count": len(nodes),
        "node_types": sorted({n.get("type", "?") for n in nodes}),
    }


def parse_comfy_chunks(chunks: dict[str, str]) -> dict[str, Any] | None:
    for key, parser in (("prompt", parse_api_prompt), ("workflow", parse_ui_workflow)):
        raw = chunks.get(key)
        if not raw:
            continue
        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            continue
        if isinstance(data, dict) and data:
            try:
                result = parser(data)
            except Exception:  # noqa: BLE001 - 第三方节点千奇百怪，解析失败不影响入库
                continue
            result["has_workflow"] = "workflow" in chunks
            return result
    return None
