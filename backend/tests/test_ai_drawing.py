import hashlib
import json
import time

import httpx
import pytest
from fastapi.testclient import TestClient

from front_api import civitai, modelscan, sdgen, sdparams
from front_api.config import get_settings
from front_api.mock_sd import create_mock_app
from front_api.seed import make_sample_model_dir


def wait_job(client, job, timeout=30):
    deadline = time.time() + timeout
    while time.time() < deadline:
        j = client.get(f"/api/jobs/{job['id']}").json()
        if j["status"] not in ("queued", "running"):
            return j
        time.sleep(0.05)
    raise AssertionError(f"任务超时：{j}")


@pytest.fixture()
def mock_sd(monkeypatch, data_dir):
    mock = create_mock_app()
    monkeypatch.setattr(sdgen, "client_factory", lambda url, timeout: TestClient(mock, base_url=url))
    monkeypatch.setattr(sdgen, "POLL_INTERVAL", 0.01)
    monkeypatch.setenv("FRONT_SD_WEBUI_URL", "http://mock-webui")
    monkeypatch.setenv("FRONT_COMFYUI_URL", "http://mock-comfy/")
    get_settings.cache_clear()
    yield mock
    get_settings.cache_clear()


def test_normalize_and_diff():
    a = sdparams.normalize({"Steps": "28", "CFG scale": "6.5", "Sampler": "DPM++ 2M", "Model": "D:/m/animebase.safetensors", "Seed": "1"})
    b = sdparams.normalize({"steps": 28, "cfg": 7, "sampler": "DPM++ 2M", "model": "paintflow", "seed": 1, "width": 512, "height": 640})
    assert a == {"steps": 28, "cfg": 6.5, "sampler": "DPM++ 2M", "model": "animebase", "seed": 1}
    assert b["size"] == "512x640"
    assert sdparams.diff_keys([a, b]) == ["model", "cfg"]  # 缺失的 size 不算差异
    assert sdparams.sort_values([9, 5, 7, 5]) == [5, 7, 9]


def test_compute_hashes(tmp_path):
    p = tmp_path / "x.safetensors"
    header = json.dumps({"__metadata__": {"ss_network_module": "networks.lora"}}).encode()
    body = bytes(range(256)) * 5000
    p.write_bytes(len(header).to_bytes(8, "little") + header + body)
    h = modelscan.compute_hashes(p)
    sha = hashlib.sha256(p.read_bytes()).hexdigest().upper()
    assert h["SHA256"] == sha and h["AutoV2"] == sha[:10]
    assert h["AutoV3"] == hashlib.sha256(body).hexdigest().upper()
    raw = p.read_bytes()
    assert h["AutoV1"] == hashlib.sha256(raw[0x100000:0x110000]).hexdigest()[:8].upper()


def test_scan_model_folder(client, tmp_path):
    root = make_sample_model_dir(tmp_path / "webui")
    r = client.post("/api/sd-models/scan", json={"path": str(root)}).json()
    assert r["total"] == 6 and r["new"] == 6
    by = {i["file_name"]: i for i in r["items"]}
    ink = by["inkline_v2_example.safetensors"]
    assert ink["kind"] == "checkpoint" and ink["base_model"] == "SDXL" and ink["preview"].endswith(".preview.png")
    assert ink["civitai"]["model_name"] == "【示例】InkLine 线稿模型"
    lin = by["linxi_character_example.safetensors"]
    assert lin["kind"] == "lora" and lin["trigger_words"] == "linxi, lighthouse keeper uniform" and lin["base_model"] == "SDXL"
    assert by["inkwash_style_example.safetensors"]["kind"] == "lycoris"  # Header identifies LyCORIS despite its Lora directory.
    assert {by["sdxl_vae_example.safetensors"]["kind"], by["4x_softedge_example.pth"]["kind"], by["badhand_example.pt"]["kind"]} == {"vae", "upscaler", "embedding"}

    job = wait_job(client, client.post("/api/sd-models/scan/run", json={"path": str(root), "compute_hash": True}).json())
    assert job["status"] == "done" and len(job["result"]["created"]) == 6
    models = {x["file_name"]: x for x in client.get("/api/sd-models", params={"limit": 50}).json()["items"]}
    ink_m = models["inkline_v2_example.safetensors"]
    assert ink_m["name"] == "【示例】InkLine 线稿模型" and ink_m["version"] == "v2.0（示例）" and ink_m["trigger_words"] == "inkline, lineart"
    assert ink_m["hashes"]["AutoV2"] == ink_m["sha256"][:10].upper() and ink_m["preview_asset_id"]
    assert client.get(f"/api/assets/{ink_m['preview_asset_id']}").json()["kind"] == "reference"
    # 再扫一次：全部已登记
    again = client.post("/api/sd-models/scan", json={"path": str(root)}).json()
    assert again["new"] == 0
    job2 = wait_job(client, client.post("/api/sd-models/scan/run", json={"path": str(root)}).json())
    assert job2["result"]["skipped"] == 6
    # 不能扫 Front 自己的数据目录 / 不存在的目录
    assert client.post("/api/sd-models/scan", json={"path": str(get_settings().data_dir)}).status_code == 422
    assert client.post("/api/sd-models/scan", json={"path": str(tmp_path / "nope")}).status_code == 404

    # 单个计算哈希 + 按出图参数里的 Model hash 匹配模型
    vae = models["sdxl_vae_example.safetensors"]
    client.patch(f"/api/sd-models/{vae['id']}", json={"sha256": None})
    hashed = client.post(f"/api/sd-models/{vae['id']}/hash").json()
    assert hashed["sha256"] and hashed["hashes"]["AutoV3"]
    from front_api.db import new_session
    from front_api.routers.sd import match_model

    with new_session() as ses:
        assert match_model(ses, "something-else", ink_m["hashes"]["AutoV2"]).id == ink_m["id"]
        assert match_model(ses, None, ink_m["hashes"]["AutoV1"]).id == ink_m["id"]


def test_civitai_match(client, monkeypatch, tmp_path):
    p = tmp_path / "m.safetensors"
    p.write_bytes(b"\x02\x00\x00\x00\x00\x00\x00\x00{}" + b"x" * 100)
    mid = client.post("/api/sd-models", json={"name": "m", "kind": "other", "file_name": "m.safetensors", "local_path": str(p)}).json()["id"]
    sha = hashlib.sha256(p.read_bytes()).hexdigest()
    calls = []

    def handler(req: httpx.Request):
        calls.append(str(req.url))
        if req.url.path.endswith(sha):
            return httpx.Response(200, json={"id": 22, "modelId": 11, "name": "v1", "baseModel": "Pony", "trainedWords": ["foo"],
                                             "model": {"name": "Remote Model", "type": "LORA"},
                                             "images": [{"url": "https://image.civitai.com/a.png", "nsfwLevel": 1}]})
        if req.url.host == "image.civitai.com":
            from conftest import png_bytes
            return httpx.Response(200, content=png_bytes())
        return httpx.Response(404, json={"error": "not found"})

    monkeypatch.setattr(civitai, "client_factory", lambda: httpx.Client(transport=httpx.MockTransport(handler)))
    r = client.post(f"/api/sd-models/{mid}/civitai", json={"download_preview": True}).json()
    assert r["found"] and calls[0].endswith(f"/model-versions/by-hash/{sha}")
    mdl = r["model"]
    assert mdl["name"] == "m" or mdl["name"] == "Remote Model"
    assert mdl["kind"] == "other"  # 已有值默认不覆盖
    assert mdl["base_model"] == "Pony" and mdl["trigger_words"] == "foo" and mdl["source_url"] == "https://civitai.com/models/11?modelVersionId=22"
    assert mdl["preview_asset_id"] and mdl["civitai"]["version_id"] == 22
    r2 = client.post(f"/api/sd-models/{mid}/civitai", json={"overwrite": True}).json()
    assert r2["model"]["kind"] == "lora" and r2["model"]["name"] == "Remote Model"
    # 找不到
    p2 = tmp_path / "n.safetensors"
    p2.write_bytes(b"\x02\x00\x00\x00\x00\x00\x00\x00{}zz")
    nid = client.post("/api/sd-models", json={"name": "n", "local_path": str(p2)}).json()["id"]
    assert client.post(f"/api/sd-models/{nid}/civitai").json()["found"] is False
    # 关闭开关
    monkeypatch.setenv("FRONT_CIVITAI", "off")
    get_settings.cache_clear()
    assert client.post(f"/api/sd-models/{nid}/civitai").status_code == 403
    get_settings.cache_clear()
    # 只允许下载 Civitai 图床的图片
    with pytest.raises(ValueError):
        civitai.download_image("http://127.0.0.1/evil.png")


def test_snippets_and_compose(client):
    a = client.post("/api/prompt-snippets", json={"title": "质量", "category": "quality", "positive": "masterpiece, best quality",
                                                  "negative": "lowres, bad hands"}).json()["id"]
    b = client.post("/api/prompt-snippets", json={"title": "水彩", "category": "style", "positive": "watercolor, soft light"}).json()["id"]
    c = client.post("/api/prompt-snippets", json={"title": "重复", "category": "style", "positive": "Best Quality, lantern"}).json()["id"]
    assert client.post("/api/prompt-snippets", json={"title": "x", "category": "nope"}).status_code == 422
    assert [x["title"] for x in client.get("/api/prompt-snippets", params={"category": "style"}).json()["items"]] == ["水彩", "重复"]
    r = client.post("/api/prompt-snippets/compose", json={"base_positive": "1girl", "base_negative": "watermark",
                                                          "items": [{"id": a}, {"id": b, "weight": 1.2}, {"id": c}]}).json()
    assert r["positive"] == "1girl, masterpiece, best quality, (watercolor, soft light:1.2), lantern"
    assert r["negative"] == "watermark, lowres, bad hands"
    assert client.get("/api/search", params={"q": "watercolor"}).json()[0]["entity"] in ("snippet",)


def _setup_models(client):
    m1 = client.post("/api/sd-models", json={"name": "AnimeBase", "file_name": "animebase_xl_example.safetensors"}).json()["id"]
    m2 = client.post("/api/sd-models", json={"name": "PaintFlow", "file_name": "paintflow15_example.safetensors"}).json()["id"]
    lora = client.post("/api/sd-models", json={"name": "Watercolor", "kind": "lora", "file_name": "watercolor_lora_example.safetensors"}).json()["id"]
    return m1, m2, lora


def test_generate_webui_xy_grid(client, mock_sd):
    st = client.get("/api/generate/status").json()
    assert st["webui"]["ok"] and "DPM++ 2M" in st["webui"]["options"]["samplers"]
    assert st["comfyui"]["ok"] and "animebase_xl_example.safetensors" in st["comfyui"]["options"]["models"]
    m1, m2, _ = _setup_models(client)
    job = client.post("/api/generate", json={
        "backend": "webui", "title": "测试网格", "positive": "1girl, lighthouse, night", "negative": "lowres",
        "steps": 20, "cfg": 7, "seed": 42, "width": 512, "height": 640, "model_ids": [m1, m2],
        "y": {"param": "cfg", "values": [5, 9]}, "collection_name": "网格收藏",
    }).json()
    done = wait_job(client, job)
    assert done["status"] == "done" and done["done"] == 4, done
    items = done["result"]["items"]
    assert len(items) == 4 and all(i["seed"] == 42 for i in items)
    asset = client.get(f"/api/assets/{items[0]['asset_id']}").json()
    assert asset["kind"] == "ai_image" and asset["meta"]["sd"]["source"] == "a1111"
    assert asset["meta"]["sd"]["params"]["CFG scale"] == "5" and asset["title"] == "测试网格 × AnimeBase · CFG 5"
    pid = done["result"]["prompt_id"]
    # XY 网格：按批次自动用任务的轴
    grid = client.get(f"/api/prompts/{pid}/xy", params={"batch": job["batch"]}).json()
    assert grid["x"] == "model" and grid["y"] == "cfg"
    assert grid["x_values"] == ["AnimeBase", "PaintFlow"] and grid["y_values"] == ["5", "9"]
    assert all(len(cell) == 1 for row in grid["cells"] for cell in row)
    assert grid["cells"][1][0][0]["params"]["cfg"] == 9 and grid["cells"][1][0][0]["params"]["model"] == "AnimeBase"
    # 换轴
    g2 = client.get(f"/api/prompts/{pid}/xy", params={"x": "cfg"}).json()
    assert g2["x"] == "cfg" and g2["y"] == "model"
    # 对比视图的差异高亮
    cmp = client.get(f"/api/prompts/{pid}/compare").json()
    assert set(cmp["diff_keys"]) == {"model", "cfg"} and cmp["common"]["steps"] == 20 and cmp["common"]["seed"] == 42
    batches = client.get(f"/api/prompts/{pid}/batches").json()
    assert batches[0]["batch"] == job["batch"] and batches[0]["count"] == 4 and batches[0]["axes"] == {"x": "model", "y": "cfg"}
    col = next(c for c in client.get("/api/collections").json()["items"] if c["name"] == "网格收藏")
    assert len(client.get(f"/api/collections/{col['id']}").json()["assets"]) == 4


def test_generate_comfy_prompt_sr_and_lora(client, mock_sd):
    m1, _, lora = _setup_models(client)
    p = client.post("/api/prompts", json={"title": "灯塔", "positive": "1girl, lighthouse, night, lantern", "negative": "bad hands"}).json()["id"]
    job = client.post("/api/generate", json={
        "backend": "comfyui", "prompt_id": p, "model_ids": [m1], "loras": [{"model_id": lora, "weight": 0.6}],
        "x": {"param": "prompt_sr", "values": ["night", "sunset"]}, "seed": 7, "count": 2,
    }).json()
    done = wait_job(client, job)
    assert done["status"] == "done" and len(done["result"]["items"]) == 4
    assert sorted(i["seed"] for i in done["result"]["items"]) == [7, 7, 8, 8]
    a = client.get(f"/api/assets/{done['result']['items'][-1]['asset_id']}").json()
    sd = a["meta"]["sd"]
    assert sd["source"] == "comfyui" and "sunset" in sd["prompt"] and sd["loras"][0]["name"] == "watercolor_lora_example.safetensors"
    cmp = client.get(f"/api/prompts/{p}/compare").json()
    sunset = [i for g in cmp["groups"] for i in g["items"] if i["xy"]["x"]["value"] == "sunset"]
    assert sunset[0]["prompt_added"] == ["sunset"] and sunset[0]["prompt_removed"] == ["night"]
    grid = client.get(f"/api/prompts/{p}/xy", params={"batch": job["batch"]}).json()
    assert grid["x"] == "prompt_sr" and grid["x_values"] == ["night", "sunset"] and len(grid["cells"][0][0]) == 2
    # 自定义工作流占位符
    wf = {"1": {"class_type": "KSampler", "inputs": {"seed": "{{seed}}", "steps": "{{steps}}", "text": "{{positive}}"}}}
    filled = sdgen.fill_workflow(wf, sdgen.Spec(positive='say "hi"', seed=5, steps=9))
    assert filled["1"]["inputs"] == {"seed": 5, "steps": 9, "text": 'say "hi"'}


def test_generate_validation(client, monkeypatch, data_dir):
    for k in ("FRONT_SD_WEBUI_URL", "FRONT_COMFYUI_URL"):
        monkeypatch.delenv(k, raising=False)
    get_settings.cache_clear()
    st = client.get("/api/generate/status").json()
    assert st["webui"]["configured"] is False and "FRONT_SD_WEBUI_URL" in st["webui"]["error"]
    assert client.post("/api/generate", json={"positive": "x"}).status_code == 503
    monkeypatch.setenv("FRONT_SD_WEBUI_URL", "http://127.0.0.1:9")
    get_settings.cache_clear()
    assert client.get("/api/generate/status").json()["webui"]["ok"] is False
    assert client.post("/api/generate", json={"positive": ""}).status_code == 422
    assert client.post("/api/generate", json={"positive": "x", "x": {"param": "bogus", "values": [1]}}).status_code == 422
    big = {"positive": "x", "x": {"param": "cfg", "values": list(range(11))}, "y": {"param": "steps", "values": list(range(1, 11))}}
    assert client.post("/api/generate", json=big).status_code == 422
    # 连不上后端：任务失败并给出原因
    job = client.post("/api/generate", json={"positive": "x", "save_prompt": False}).json()
    done = wait_job(client, job)
    assert done["status"] == "error" and "失败" in done["message"]
    get_settings.cache_clear()


def test_migration_v04_columns(tmp_path, monkeypatch):
    import sqlite3

    data = tmp_path / "v03"
    data.mkdir()
    con = sqlite3.connect(data / "front.db")
    con.executescript(
        "CREATE TABLE sd_models (id INTEGER PRIMARY KEY, name VARCHAR(200), kind VARCHAR(30), base_model VARCHAR(60), version VARCHAR(60),"
        " file_name VARCHAR(300), local_path VARCHAR(1000), sha256 VARCHAR(64), size INTEGER, trigger_words TEXT, source_url VARCHAR(500),"
        " notes TEXT, preview_asset_id INTEGER, created_at DATETIME, updated_at DATETIME);"
        "INSERT INTO sd_models (id, name, kind, created_at, updated_at) VALUES (1, 'old', 'checkpoint', '2026-01-01', '2026-01-01');"
    )
    con.close()
    monkeypatch.setenv("FRONT_DATA_DIR", str(data))
    get_settings.cache_clear()
    from front_api.main import create_app

    with TestClient(create_app()) as c:
        r = c.get("/api/sd-models/1").json()
        assert r["hashes"] == {} and r["civitai"] == {}
    get_settings.cache_clear()
