from conftest import png_bytes


def test_fulltext_search_cjk(client):
    client.post("/api/worlds", json={"name": "群星彼岸", "content": "漂浮在云海之上的学园都市"})
    client.post("/api/assets", json={"title": "短篇", "kind": "novel", "content": "她在雨夜的车站等待"})
    hits = client.get("/api/search", params={"q": "学园都市"}).json()
    assert hits and hits[0]["entity"] == "world"
    # 两个字的查询走 LIKE 回退
    assert client.get("/api/search", params={"q": "雨夜"}).json()[0]["entity"] == "asset"
    assert client.get("/api/assets", params={"q": "车站等待"}).json()["total"] == 1
    assert client.get("/api/search", params={"q": '"; DROP'}).json() == []


def test_upload_image_and_thumb(client, data_dir):
    r = client.post(
        "/api/assets/upload",
        files={"file": ("my.png", png_bytes(), "image/png")},
        data={"title": "我的画", "work_date": "2026-03-04"},
    )
    assert r.status_code == 201, r.text
    a = r.json()
    assert a["kind"] == "drawing" and (a["width"], a["height"]) == (64, 48)
    assert (data_dir / a["file_path"]).is_file()
    assert client.get(f"/api/assets/{a['id']}/file").content[:4] == b"\x89PNG"
    assert client.get(f"/api/assets/{a['id']}/thumb").headers["content-type"] == "image/webp"
    # 重复上传被拒
    dup = client.post("/api/assets/upload", files={"file": ("x.png", png_bytes(), "image/png")})
    assert dup.status_code == 409
    # 日期筛选
    assert client.get("/api/assets", params={"year": 2026, "month": 3}).json()["total"] == 1
    assert client.get("/api/assets", params={"date_from": "2026-04-01"}).json()["total"] == 0
    tl = client.get("/api/assets/stats/timeline").json()
    assert tl == [{"month": "2026-03", "kind": "drawing", "count": 1}]
    # 删除条目时文件一并清理
    client.delete(f"/api/assets/{a['id']}")
    assert not (data_dir / a["file_path"]).exists()


def test_upload_sd_png_extracts_parameters(client):
    params = (
        "masterpiece, 1girl, cherry blossoms\n"
        "Negative prompt: lowres, bad hands\n"
        "Steps: 28, Sampler: DPM++ 2M Karras, CFG scale: 7, Seed: 1234, Size: 512x768, Model: exampleModel"
    )
    r = client.post(
        "/api/assets/upload",
        files={"file": ("gen.png", png_bytes(color=(1, 2, 3), text={"parameters": params}), "image/png")},
    )
    a = r.json()
    assert a["kind"] == "ai_image"
    sd = a["meta"]["sd"]
    assert sd["prompt"] == "masterpiece, 1girl, cherry blossoms"
    assert sd["negative_prompt"] == "lowres, bad hands"
    assert sd["params"]["Seed"] == "1234" and sd["params"]["Model"] == "exampleModel"
    assert client.get("/api/search", params={"q": "cherry blossoms"}).json()[0]["id"] == a["id"]


def test_upload_novel_text(client):
    body = "第一章 起风了\n这是一篇示例小说。".encode("gb18030")
    a = client.post("/api/assets/upload", files={"file": ("novel.txt", body, "text/plain")}).json()
    assert a["kind"] == "novel" and "起风了" in a["content"]
