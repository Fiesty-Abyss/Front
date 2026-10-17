"""模拟的 SD WebUI / ComfyUI 接口，只用于开发、测试和示例截图（没有显卡也能把出图流程跑通）。
它不会真的画图：返回的是程序生成的几何占位图，图上标着“模拟出图”。

    python -m front_api.mock_sd --port 7861
    FRONT_SD_WEBUI_URL=http://127.0.0.1:7861 FRONT_COMFYUI_URL=http://127.0.0.1:7861 python -m front_api
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import uuid
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import Response

from .comfy import parse_api_prompt
from .sdgen import _stem

MODELS = ["animebase_xl_example.safetensors", "paintflow15_example.safetensors", "inkline_v2_example.safetensors"]
LORAS = ["watercolor_lora_example.safetensors"]
SAMPLERS = ["Euler a", "Euler", "DPM++ 2M", "DPM++ SDE", "DDIM"]
SCHEDULERS = ["Automatic", "Karras", "Exponential", "SGM Uniform"]
COMFY_SAMPLERS = ["euler", "euler_ancestral", "dpmpp_2m", "dpmpp_sde", "ddim"]
COMFY_SCHEDULERS = ["normal", "karras", "exponential", "sgm_uniform"]

PALETTES = [((40, 60, 130), (150, 180, 240)), ((120, 50, 90), (250, 180, 150)), ((30, 100, 80), (200, 230, 160)),
            ((90, 60, 140), (230, 190, 250)), ((130, 90, 30), (250, 220, 140))]
MOODS = [("night", ((18, 26, 60), (70, 90, 160))), ("夜", ((18, 26, 60), (70, 90, 160))),
         ("sunset", ((120, 50, 40), (250, 170, 90))), ("dawn", ((90, 80, 130), (250, 200, 210))),
         ("rain", ((40, 60, 70), (120, 150, 160)))]


def render(model: str, prompt: str, cfg: float, seed: int, steps: int, width: int, height: int,
           text_chunks: dict[str, str] | None = None) -> bytes:
    from .seed import placeholder

    h = int(hashlib.md5(_stem(model).encode()).hexdigest()[:6], 16)
    base, bottom = PALETTES[h % len(PALETTES)]
    top = base
    for key, pal in MOODS:
        if key in prompt.lower():
            top = tuple((a + b) // 2 for a, b in zip(pal[0], base))
            bottom = pal[1]
            break
    shift = int((cfg - 7) * 14)  # CFG 越高颜色越浓，网格里一眼能看出差别
    top = tuple(max(0, min(255, c + shift)) for c in top)
    bottom = tuple(max(0, min(255, c - shift)) for c in bottom)
    scale = min(1.0, 768 / max(width, height))
    size = (max(64, int(width * scale)), max(64, int(height * scale)))
    label = f"{_stem(model).split('_')[0][:12]} · CFG {cfg:g}"
    return placeholder(label, (top, bottom), seed % 100000 + steps, size=size, text_chunks=text_chunks, badge="模拟出图")


def create_mock_app() -> FastAPI:
    app = FastAPI(title="Front 模拟 SD 接口（仅用于开发与示例）")
    state: dict[str, Any] = {"current": MODELS[0], "history": {}, "files": {}}

    # ---------- SD WebUI ----------
    @app.get("/sdapi/v1/options")
    def options() -> dict[str, Any]:
        return {"sd_model_checkpoint": f"{state['current']} [mock]"}

    @app.get("/sdapi/v1/sd-models")
    def sd_models() -> list[dict[str, Any]]:
        return [{"title": f"{m} [mock]", "model_name": _stem(m), "filename": f"/mock/models/Stable-diffusion/{m}"} for m in MODELS]

    @app.get("/sdapi/v1/samplers")
    def samplers() -> list[dict[str, Any]]:
        return [{"name": s} for s in SAMPLERS]

    @app.get("/sdapi/v1/schedulers")
    def schedulers() -> list[dict[str, Any]]:
        return [{"name": s.lower(), "label": s} for s in SCHEDULERS]

    @app.get("/sdapi/v1/loras")
    def loras() -> list[dict[str, Any]]:
        return [{"name": _stem(x), "path": f"/mock/models/Lora/{x}"} for x in LORAS]

    @app.post("/sdapi/v1/txt2img")
    def txt2img(body: dict[str, Any]) -> dict[str, Any]:
        model = (body.get("override_settings") or {}).get("sd_model_checkpoint") or state["current"]
        model = _stem(model.split(" [")[0])
        seed = int(body.get("seed", -1))
        seed = seed if seed >= 0 else 12345
        cfg = float(body.get("cfg_scale", 7))
        steps = int(body.get("steps", 20))
        w, h = int(body.get("width", 512)), int(body.get("height", 512))
        png = render(model, body.get("prompt", ""), cfg, seed, steps, w, h)
        infotext = (f"{body.get('prompt', '')}\nNegative prompt: {body.get('negative_prompt', '')}\n"
                    f"Steps: {steps}, Sampler: {body.get('sampler_name', 'Euler a')}, CFG scale: {cfg:g}, Seed: {seed}, "
                    f"Size: {w}x{h}, Model hash: {hashlib.sha256(model.encode()).hexdigest()[:10]}, Model: {model}")
        info = {"infotexts": [infotext], "all_seeds": [seed], "seed": seed, "sd_model_name": model}
        return {"images": [base64.b64encode(png).decode()], "parameters": body, "info": json.dumps(info, ensure_ascii=False)}

    # ---------- ComfyUI ----------
    @app.get("/system_stats")
    def system_stats() -> dict[str, Any]:
        return {"system": {"os": "mock", "comfyui_version": "mock"}, "devices": []}

    @app.get("/object_info/{node}")
    def object_info(node: str) -> dict[str, Any]:
        table = {
            "CheckpointLoaderSimple": {"ckpt_name": [MODELS]},
            "KSampler": {"sampler_name": [COMFY_SAMPLERS], "scheduler": [COMFY_SCHEDULERS]},
            "LoraLoader": {"lora_name": [LORAS]},
        }
        if node not in table:
            raise HTTPException(404)
        return {node: {"input": {"required": table[node]}}}

    @app.post("/prompt")
    async def prompt(request: Request) -> dict[str, Any]:
        body = await request.json()
        graph = body.get("prompt") or {}
        parsed = parse_api_prompt(graph)
        p = parsed["params"]
        w, h = (int(v) for v in (p.get("Size") or "512x512").split("x"))
        png = render(parsed["models"][0] if parsed["models"] else MODELS[0], parsed["prompt"], float(p.get("CFG scale", 7)),
                     int(p.get("Seed", 1)), int(p.get("Steps", 20)), w, h, text_chunks={"prompt": json.dumps(graph)})
        pid = uuid.uuid4().hex
        name = f"Front_{len(state['files']) + 1:05d}_.png"
        state["files"][name] = png
        save_node = next((k for k, v in graph.items() if v.get("class_type") == "SaveImage"), "9")
        state["history"][pid] = {"status": {"status_str": "success", "completed": True},
                                 "outputs": {save_node: {"images": [{"filename": name, "subfolder": "", "type": "output"}]}}}
        return {"prompt_id": pid, "number": len(state["history"])}

    @app.get("/history/{pid}")
    def history(pid: str) -> dict[str, Any]:
        return {pid: state["history"][pid]} if pid in state["history"] else {}

    @app.get("/view")
    def view(filename: str, subfolder: str = "", type: str = "output") -> Response:
        if filename not in state["files"]:
            raise HTTPException(404)
        return Response(state["files"][filename], media_type="image/png")

    @app.post("/tagger/v1/interrogate")
    def interrogate(body: dict[str, Any]) -> dict[str, Any]:
        """模拟 wd14-tagger 扩展：只看颜色与长宽比，不是真正的识别。"""
        import base64
        import io

        from PIL import Image

        with Image.open(io.BytesIO(base64.b64decode(body.get("image", "")))) as im:
            w, h = im.size
            r, g, b = im.convert("RGB").resize((1, 1)).getpixel((0, 0))
        tags = {"placeholder": 0.99, "no_humans": 0.62}
        if h > w * 1.1:
            tags["portrait"] = 0.71
        elif w > h * 1.1:
            tags["scenery"] = 0.83
        tags["blue_theme" if b >= r else "orange_theme"] = 0.55
        if max(r, g, b) < 90:
            tags["night"] = 0.47
        threshold = float(body.get("threshold", 0.35))
        return {"caption": {"tag": {k: v for k, v in tags.items() if v >= threshold}, "rating": {"general": 0.98}}}

    return app


def main() -> None:
    import uvicorn

    ap = argparse.ArgumentParser(description="Front 模拟 SD WebUI / ComfyUI 接口（仅用于开发与示例）")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=7861)
    args = ap.parse_args()
    uvicorn.run(create_mock_app(), host=args.host, port=args.port)


if __name__ == "__main__":
    main()
