import json

from conftest import png_bytes

from front_api.comfy import parse_api_prompt, parse_ui_workflow

API_PROMPT = {
    "3": {"class_type": "KSampler", "inputs": {"seed": 42, "steps": 30, "cfg": 5.5, "sampler_name": "euler_ancestral", "scheduler": "normal", "denoise": 1, "model": ["10", 0], "positive": ["11", 0], "negative": ["7", 0], "latent_image": ["5", 0]}},
    "4": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "SDXL/exampleXL_v2.safetensors"}},
    "5": {"class_type": "EmptyLatentImage", "inputs": {"width": 832, "height": 1216, "batch_size": 1}},
    "6": {"class_type": "CLIPTextEncode", "inputs": {"text": ["12", 0], "clip": ["10", 1]}},
    "7": {"class_type": "CLIPTextEncode", "inputs": {"text": "lowres, watermark", "clip": ["10", 1]}},
    "8": {"class_type": "CLIPTextEncode", "inputs": {"text": "soft lighting", "clip": ["10", 1]}},
    "10": {"class_type": "LoraLoader", "inputs": {"lora_name": "watercolor.safetensors", "strength_model": 0.8, "strength_clip": 0.8, "model": ["4", 0], "clip": ["4", 1]}},
    "11": {"class_type": "ConditioningCombine", "inputs": {"conditioning_1": ["6", 0], "conditioning_2": ["8", 0]}},
    "12": {"class_type": "PrimitiveString", "inputs": {"value": "1girl, lighthouse"}},
}
UI_WORKFLOW = {"nodes": [
    {"id": 4, "type": "CheckpointLoaderSimple", "widgets_values": ["exampleXL_v2.safetensors"]},
    {"id": 6, "type": "CLIPTextEncode", "widgets_values": ["1girl, lighthouse"]},
    {"id": 7, "type": "CLIPTextEncode", "widgets_values": ["lowres"]},
    {"id": 3, "type": "KSampler", "widgets_values": [42, "fixed", 30, 5.5, "euler", "normal", 1]},
    {"id": 5, "type": "EmptyLatentImage", "widgets_values": [832, 1216, 1]},
], "links": []}


def test_parse_api_prompt_follows_links():
    r = parse_api_prompt(API_PROMPT)
    assert r["prompt"] == "1girl, lighthouse\nsoft lighting"
    assert r["negative_prompt"] == "lowres, watermark"
    assert r["params"] == {"Seed": "42", "Steps": "30", "CFG scale": "5.5", "Sampler": "euler_ancestral", "Scheduler": "normal", "Denoise": "1", "Size": "832x1216", "Model": "SDXL/exampleXL_v2.safetensors"}
    assert r["loras"] == [{"name": "watercolor.safetensors", "strength": 0.8}]


def test_parse_ui_workflow():
    r = parse_ui_workflow(UI_WORKFLOW)
    assert r["prompt"] == "1girl, lighthouse" and r["negative_prompt"] == "lowres"
    assert r["params"]["Steps"] == "30" and r["params"]["Size"] == "832x1216"


def _comfy_png(color=(5, 5, 5), prompt=API_PROMPT):
    return png_bytes(color=color, text={"prompt": json.dumps(prompt), "workflow": json.dumps(UI_WORKFLOW)})


def test_upload_comfy_png_and_download_workflow(client):
    a = client.post("/api/assets/upload", files={"file": ("comfy_0001.png", _comfy_png(), "image/png")}).json()
    assert a["kind"] == "ai_image" and a["meta"]["sd"]["source"] == "comfyui"
    assert a["meta"]["sd"]["has_workflow"] is True
    wf = client.get(f"/api/assets/{a['id']}/workflow")
    assert wf.status_code == 200 and wf.json()["nodes"][0]["type"] == "CheckpointLoaderSimple"
    plain = client.post("/api/assets/upload", files={"file": ("p.png", png_bytes(), "image/png")}).json()
    assert client.get(f"/api/assets/{plain['id']}/workflow").status_code == 404


def test_broken_comfy_json_is_ignored(client):
    data = png_bytes(text={"prompt": "{not json"})
    a = client.post("/api/assets/upload", files={"file": ("x.png", data, "image/png")}).json()
    assert a["kind"] == "drawing"


def test_prompt_from_assets_builds_comparison(client):
    m1 = client.post("/api/sd-models", json={"name": "Example XL", "file_name": "exampleXL_v2.safetensors"}).json()["id"]
    other = json.loads(json.dumps(API_PROMPT))
    other["4"]["inputs"]["ckpt_name"] = "paint15.ckpt"
    a1 = client.post("/api/assets/upload", files={"file": ("a.png", _comfy_png((1, 1, 1)), "image/png")}).json()["id"]
    a2 = client.post("/api/assets/upload", files={"file": ("b.png", _comfy_png((2, 2, 2), other), "image/png")}).json()["id"]
    r1 = client.post(f"/api/prompts/from-asset/{a1}").json()
    r2 = client.post(f"/api/prompts/from-asset/{a2}").json()
    assert r1["model_id"] == m1 and not r1["reused_prompt"]
    assert r2["prompt_id"] == r1["prompt_id"] and r2["reused_prompt"] and r2["model_id"] is None
    cmp = client.get(f"/api/prompts/{r1['prompt_id']}/compare").json()
    assert len(cmp["groups"]) == 2
    p = client.get(f"/api/prompts/{r1['prompt_id']}").json()
    assert p["negative"] == "lowres, watermark" and "Seed" not in p["params"]
    # 重复调用不会产生重复的出图记录
    client.post(f"/api/prompts/from-asset/{a1}")
    assert client.get("/api/generations", params={"prompt_id": r1["prompt_id"]}).json()["total"] == 2
    plain = client.post("/api/assets", json={"title": "t"}).json()["id"]
    assert client.post(f"/api/prompts/from-asset/{plain}").status_code == 422
