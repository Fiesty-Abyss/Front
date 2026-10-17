"""通过 SD WebUI（A1111 / Forge，需带 --api 启动）或 ComfyUI 的 HTTP 接口出图，并自动存进素材库。

- WebUI：POST /sdapi/v1/txt2img，返回 base64 图片 + infotext；Front 把 infotext 写回 PNG 的 parameters，
  所以入库后和手动导入的 WebUI 图一样能识别出图参数。
- ComfyUI：POST /prompt 提交 API 格式工作流，轮询 /history/{id}，从 /view 取回图片（PNG 自带 prompt / workflow）。
  可以用内置的文生图模板，也可以提交自己的 API 格式工作流，用 {{positive}} {{seed}} 这类占位符填参数。
"""

from __future__ import annotations

import base64
import io
import itertools
import json
import random
import re
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable

import httpx
from PIL import Image, PngImagePlugin

from .config import get_settings

# 测试 / 示例数据里替换成指向模拟服务的客户端
client_factory: Callable[[str, float], httpx.Client] = lambda base_url, timeout: httpx.Client(  # noqa: E731
    base_url=base_url, timeout=timeout
)
POLL_INTERVAL = 1.0

AXIS_PARAMS = {"model", "cfg", "steps", "sampler", "scheduler", "seed", "size", "clip_skip", "prompt_sr", "lora_weight"}


class BackendError(RuntimeError):
    pass


@dataclass
class Spec:
    """一张图的完整出图参数（已经套用了 XY 轴的取值）。"""

    positive: str
    negative: str = ""
    steps: int = 24
    cfg: float = 7.0
    sampler: str | None = None
    scheduler: str | None = None
    seed: int = -1
    width: int = 512
    height: int = 768
    clip_skip: int | None = None
    model_file: str | None = None  # 后端认识的模型文件名
    loras: list[dict[str, Any]] = field(default_factory=list)  # [{"file": "x.safetensors", "weight": 0.8}]

    def params(self) -> dict[str, Any]:
        out: dict[str, Any] = {"steps": self.steps, "cfg": self.cfg, "seed": self.seed, "size": f"{self.width}x{self.height}"}
        for k in ("sampler", "scheduler", "clip_skip"):
            if getattr(self, k) not in (None, ""):
                out[k] = getattr(self, k)
        if self.loras:
            out["loras"] = [f"{_stem(x['file'])}:{x['weight']}" for x in self.loras]
        return out


def _stem(name: str) -> str:
    return re.sub(r"\.(safetensors|ckpt|pt|pth|gguf)$", "", name.replace("\\", "/").split("/")[-1], flags=re.I)


def backend_url(backend: str, override: str | None = None) -> str:
    s = get_settings()
    url = override or (s.sd_webui_url if backend == "webui" else s.comfyui_url)
    if not url:
        env = "FRONT_SD_WEBUI_URL" if backend == "webui" else "FRONT_COMFYUI_URL"
        raise BackendError(f"尚未配置 {'SD WebUI' if backend == 'webui' else 'ComfyUI'} 地址，请设置 {env}（例如 "
                           f"{'http://127.0.0.1:7860' if backend == 'webui' else 'http://127.0.0.1:8188'}）后重启")
    return url.rstrip("/")


def _client(url: str, timeout: float | None = None) -> httpx.Client:
    return client_factory(url, timeout or get_settings().sd_timeout)


def _req(fn, what: str):
    try:
        r = fn()
    except httpx.HTTPError as exc:
        raise BackendError(f"{what}失败：{exc.__class__.__name__} {exc}") from exc
    if r.status_code >= 400:
        raise BackendError(f"{what}失败：HTTP {r.status_code} {r.text[:200]}")
    return r


# ---------------- SD WebUI ----------------
def webui_options(url: str) -> dict[str, Any]:
    with _client(url, 15) as c:
        opts = _req(lambda: c.get("/sdapi/v1/options"), "连接 SD WebUI").json()
        def get(path: str) -> list[Any]:
            try:
                r = c.get(path)
                return r.json() if r.status_code == 200 else []
            except httpx.HTTPError:
                return []
        return {
            "backend": "webui",
            "current_model": opts.get("sd_model_checkpoint"),
            "models": [m.get("title") or m.get("model_name") for m in get("/sdapi/v1/sd-models")],
            "samplers": [s.get("name") for s in get("/sdapi/v1/samplers")],
            "schedulers": [s.get("label") or s.get("name") for s in get("/sdapi/v1/schedulers")],
            "loras": [x.get("name") for x in get("/sdapi/v1/loras")],
        }


def a1111_infotext(spec: Spec, model_name: str | None, seed: int) -> str:
    settings = [f"Steps: {spec.steps}", f"Sampler: {spec.sampler or 'Euler a'}"]
    if spec.scheduler:
        settings.append(f"Schedule type: {spec.scheduler}")
    settings += [f"CFG scale: {spec.cfg}", f"Seed: {seed}", f"Size: {spec.width}x{spec.height}"]
    if model_name:
        settings.append(f"Model: {model_name}")
    if spec.clip_skip:
        settings.append(f"Clip skip: {spec.clip_skip}")
    text = _with_loras(spec)
    if spec.negative:
        text += f"\nNegative prompt: {spec.negative}"
    return text + "\n" + ", ".join(settings)


def _with_loras(spec: Spec) -> str:
    tags = "".join(f" <lora:{_stem(x['file'])}:{x['weight']}>" for x in spec.loras)
    return spec.positive + tags


def embed_parameters(png: bytes, text: str) -> bytes:
    with Image.open(io.BytesIO(png)) as img:
        info = PngImagePlugin.PngInfo()
        for k, v in (img.info or {}).items():
            if isinstance(v, str) and k != "parameters":
                info.add_text(k, v)
        info.add_text("parameters", text)
        buf = io.BytesIO()
        img.save(buf, format="PNG", pnginfo=info)
        return buf.getvalue()


def webui_txt2img(url: str, spec: Spec) -> list[tuple[bytes, int]]:
    payload: dict[str, Any] = {
        "prompt": _with_loras(spec), "negative_prompt": spec.negative, "steps": spec.steps, "cfg_scale": spec.cfg,
        "seed": spec.seed, "width": spec.width, "height": spec.height, "batch_size": 1, "n_iter": 1,
        "override_settings_restore_afterwards": True, "override_settings": {},
    }
    if spec.sampler:
        payload["sampler_name"] = spec.sampler
    if spec.scheduler:
        payload["scheduler"] = spec.scheduler
    if spec.model_file:
        payload["override_settings"]["sd_model_checkpoint"] = _stem(spec.model_file)
    if spec.clip_skip:
        payload["override_settings"]["CLIP_stop_at_last_layers"] = spec.clip_skip
    with _client(url) as c:
        data = _req(lambda: c.post("/sdapi/v1/txt2img", json=payload), "SD WebUI 出图").json()
    try:
        info = json.loads(data.get("info") or "{}")
    except json.JSONDecodeError:
        info = {}
    infotexts = info.get("infotexts") or []
    seeds = info.get("all_seeds") or [info.get("seed", spec.seed)]
    out = []
    for i, b64 in enumerate(data.get("images") or []):
        png = base64.b64decode(b64.split(",", 1)[-1])
        seed = seeds[i] if i < len(seeds) else spec.seed
        text = infotexts[i] if i < len(infotexts) else a1111_infotext(spec, info.get("sd_model_name") or (spec.model_file and _stem(spec.model_file)), seed)
        out.append((embed_parameters(png, text), seed))
    if not out:
        raise BackendError("SD WebUI 没有返回图片")
    return out


# ---------------- ComfyUI ----------------
def comfy_options(url: str) -> dict[str, Any]:
    with _client(url, 15) as c:
        _req(lambda: c.get("/system_stats"), "连接 ComfyUI")
        def choices(node: str, inp: str) -> list[str]:
            try:
                r = c.get(f"/object_info/{node}")
                spec = r.json()[node]["input"]["required"][inp]
                return list(spec[0]) if isinstance(spec[0], list) else []
            except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError):
                return []
        return {
            "backend": "comfyui",
            "current_model": None,
            "models": choices("CheckpointLoaderSimple", "ckpt_name"),
            "samplers": choices("KSampler", "sampler_name"),
            "schedulers": choices("KSampler", "scheduler"),
            "loras": choices("LoraLoader", "lora_name"),
        }


def comfy_graph(spec: Spec) -> dict[str, Any]:
    """内置的文生图模板：Checkpoint →（LoRA 串联）→ CLIP 编码 → KSampler → VAE 解码 → 保存。"""
    g: dict[str, Any] = {
        "4": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": spec.model_file or ""}},
        "5": {"class_type": "EmptyLatentImage", "inputs": {"width": spec.width, "height": spec.height, "batch_size": 1}},
    }
    model_ref, clip_ref = ["4", 0], ["4", 1]
    for i, lora in enumerate(spec.loras):
        nid = str(20 + i)
        g[nid] = {"class_type": "LoraLoader", "inputs": {"lora_name": lora["file"], "strength_model": lora["weight"],
                                                          "strength_clip": lora["weight"], "model": model_ref, "clip": clip_ref}}
        model_ref, clip_ref = [nid, 0], [nid, 1]
    if spec.clip_skip:
        g["11"] = {"class_type": "CLIPSetLastLayer", "inputs": {"stop_at_clip_layer": -abs(spec.clip_skip), "clip": clip_ref}}
        clip_ref = ["11", 0]
    g["6"] = {"class_type": "CLIPTextEncode", "inputs": {"text": spec.positive, "clip": clip_ref}}
    g["7"] = {"class_type": "CLIPTextEncode", "inputs": {"text": spec.negative, "clip": clip_ref}}
    g["3"] = {"class_type": "KSampler", "inputs": {
        "seed": spec.seed, "steps": spec.steps, "cfg": spec.cfg, "sampler_name": spec.sampler or "euler",
        "scheduler": spec.scheduler or "normal", "denoise": 1.0, "model": model_ref,
        "positive": ["6", 0], "negative": ["7", 0], "latent_image": ["5", 0]}}
    g["8"] = {"class_type": "VAEDecode", "inputs": {"samples": ["3", 0], "vae": ["4", 2]}}
    g["9"] = {"class_type": "SaveImage", "inputs": {"images": ["8", 0], "filename_prefix": "Front"}}
    return g


def fill_workflow(template: dict[str, Any], spec: Spec) -> dict[str, Any]:
    """自定义 API 格式工作流：把 "{{positive}}" "{{seed}}" 这类占位符替换成实际参数。"""
    text = json.dumps(template, ensure_ascii=False)
    values: dict[str, Any] = {
        "positive": spec.positive, "negative": spec.negative, "seed": spec.seed, "steps": spec.steps, "cfg": spec.cfg,
        "width": spec.width, "height": spec.height, "sampler": spec.sampler or "euler", "scheduler": spec.scheduler or "normal",
        "model": spec.model_file or "",
    }
    for k, v in values.items():
        if isinstance(v, (int, float)):
            text = text.replace(f'"{{{{{k}}}}}"', json.dumps(v))
        text = text.replace(f"{{{{{k}}}}}", json.dumps(str(v), ensure_ascii=False)[1:-1])
    return json.loads(text)


def comfy_txt2img(url: str, spec: Spec, workflow: dict[str, Any] | None = None) -> list[tuple[bytes, int]]:
    graph = fill_workflow(workflow, spec) if workflow else comfy_graph(spec)
    timeout = get_settings().sd_timeout
    with _client(url) as c:
        pid = _req(lambda: c.post("/prompt", json={"prompt": graph, "client_id": uuid.uuid4().hex}), "提交 ComfyUI 工作流").json().get("prompt_id")
        if not pid:
            raise BackendError("ComfyUI 没有返回 prompt_id")
        deadline = time.monotonic() + timeout
        outputs: dict[str, Any] | None = None
        while time.monotonic() < deadline:
            hist = _req(lambda: c.get(f"/history/{pid}"), "查询 ComfyUI 进度").json()
            entry = hist.get(pid)
            if entry:
                status = entry.get("status") or {}
                if status.get("status_str") == "error":
                    raise BackendError("ComfyUI 执行出错，请在 ComfyUI 界面查看日志")
                if entry.get("outputs"):
                    outputs = entry["outputs"]
                    break
            time.sleep(POLL_INTERVAL)
        if outputs is None:
            raise BackendError(f"ComfyUI 出图超时（{timeout:.0f} 秒）")
        images = []
        for node_out in outputs.values():
            for img in node_out.get("images") or []:
                if img.get("type") == "temp":
                    continue
                r = _req(lambda img=img: c.get("/view", params={"filename": img["filename"], "subfolder": img.get("subfolder", ""), "type": img.get("type", "output")}), "下载 ComfyUI 图片")
                images.append((r.content, spec.seed))
    if not images:
        raise BackendError("ComfyUI 没有输出图片（工作流里需要 SaveImage 节点）")
    return images


# ---------------- XY 网格 ----------------
def axis_cells(x: dict[str, Any] | None, y: dict[str, Any] | None) -> list[tuple[Any, Any]]:
    xs = (x or {}).get("values") or [None]
    ys = (y or {}).get("values") or [None]
    return list(itertools.product(ys, xs))


def apply_axis(spec: Spec, base_positive: str, param: str | None, value: Any, search: str | None) -> None:
    """把一个轴的取值套到 spec 上（model 轴在外面处理，因为要查模型表）。"""
    if not param or value is None or param == "model":
        return
    if param == "prompt_sr":
        if search:
            spec.positive = spec.positive.replace(search, str(value))
    elif param in ("cfg",):
        spec.cfg = float(value)
    elif param in ("steps", "seed", "clip_skip"):
        setattr(spec, param, int(value))
    elif param in ("sampler", "scheduler"):
        setattr(spec, param, str(value))
    elif param == "size":
        w, h = str(value).lower().split("x")
        spec.width, spec.height = int(w), int(h)
    elif param == "lora_weight":
        for lora in spec.loras:
            lora["weight"] = float(value)


def resolve_seed(seed: int | None) -> int:
    return random.randint(0, 2**32 - 1) if seed is None or seed < 0 else seed
