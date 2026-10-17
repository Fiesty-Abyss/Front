"""v0.6.3 galgame 游戏库：三个来源的解析、混合模式补全与回退、覆盖字段、封面、角色导入、批量添加。"""

import httpx
import pytest
from fastapi.testclient import TestClient

from front_api import mock_galgame
from front_api.galgame import meta
from front_api.galgame import sources as src


@pytest.fixture()
def mock(monkeypatch):
    app = mock_galgame.create_mock_app()
    for name, path in (("BANGUMI", "bangumi"), ("VNDB", "vndb"), ("YMGAL", "ymgal")):
        monkeypatch.setenv(f"FRONT_{name}_API", f"http://mockgal/{path}")
    monkeypatch.setattr(src, "client_factory", lambda: TestClient(app, base_url="http://mockgal"))
    src._ymgal_token.update(token=None, exp=0, base=None)
    yield app
    src._ymgal_token.update(token=None, exp=0, base=None)


def _broken(source):
    """让某一个来源连不上，其余照常。"""
    app = mock_galgame.create_mock_app()

    class C(TestClient):
        def request(self, method, url, **kw):
            if f"/{source}/" in str(url):
                raise httpx.ConnectError("down")
            return super().request(method, url, **kw)

    return lambda: C(app, base_url="http://mockgal")


def test_sources_normalize(mock):
    b = src.bangumi_search("樱色回廊")
    assert b[0]["sid"] == "900001" and b[0]["title"] == "【示例】樱色回廊" and b[0]["score"] == 7.9
    d = src.bangumi_detail("900001")
    assert d["developer"] == "示例工作室" and "樱回" in d["aliases"] and d["platforms"] == ["PC", "Nintendo Switch"]
    assert d["characters"][0]["role"] == "main" and d["characters"][0]["cv"] == "示例声优 A"
    v = src.vndb_detail("v90002")
    assert v["title_cn"] == "【示例】雾港夜想曲" and v["score"] == 8.56 and v["length_minutes"] == 2700
    assert v["platforms"] == ["Windows"] and v["characters"][0]["cv"] == "示例声优 D"
    y = src.ymgal_detail("80001")
    assert y["developer"] == "示例工作室" and y["has_chinese"] and y["characters"][0]["cv"] == "示例声优 A"
    assert src.vndb_detail("v99999") is None and src.ymgal_detail("1") is None
    with pytest.raises(src.SourceError):
        src.vndb_detail("../etc")


def test_ymgal_token_refresh(mock):
    src._ymgal_token.update(token="stale", exp=10**12, base="http://mockgal/ymgal")
    assert src.ymgal_search("雾港")[0]["sid"] == "80002"  # 旧令牌 401 → 自动重新获取
    assert src._ymgal_token["token"] == "mock-token"


def test_mixed_match_and_merge(mock):
    cfg = {**meta.DEFAULTS, "order": ["bangumi", "ymgal", "vndb"]}
    r = meta.fetch({"bangumi": "900002"}, cfg)
    assert r["matched"]["vndb"]["sid"] == "v90002" and r["matched"]["ymgal"]["sid"] == "80002"
    mg = r["merged"]
    assert set(mg["sources"]) == {"bangumi", "vndb", "ymgal"}
    assert mg["title"] == "【示例】雾港夜想曲" and mg["original"] == "【示例】霧港ノクターン"
    assert mg["description"].startswith("【示例】雾季")  # 中文简介优先
    assert mg["sources"]["vndb"]["length_minutes"] == 2700 and mg["sources"]["bangumi"]["rank"] == 233
    # 星屑邮局在月幕没有：只合并有的来源
    r = meta.fetch({"vndb": "v90003"}, cfg)
    assert set(r["merged"]["sources"]) == {"bangumi", "vndb"} and r["matched"]["ymgal"] == {"none": True}


def test_search_fallback_and_errors(client, mock, monkeypatch):
    client.put("/api/galgames/meta/settings", json={"mode": "bangumi"}).raise_for_status()
    # 夏日方程式不在 Bangumi：单一来源模式回退到下一个来源
    r = client.get("/api/galgames/meta/search", params={"q": "夏日方程式"}).json()
    assert r["order"][0] == "bangumi" and r["used"] and r["used"][0] != "bangumi"
    client.put("/api/galgames/meta/settings", json={"mode": "mixed"}).raise_for_status()
    monkeypatch.setattr(src, "client_factory", _broken("vndb"))
    r = client.get("/api/galgames/meta/search", params={"q": "樱色回廊"}).json()
    assert r["results"]["vndb"]["ok"] is False and "VNDB" in r["results"]["vndb"]["error"]
    assert r["results"]["bangumi"]["items"] and r["results"]["ymgal"]["items"]


def test_settings_validation(client):
    s = client.get("/api/galgames/meta/settings").json()
    assert s["mode"] == "mixed" and s["order"] == ["bangumi", "ymgal", "vndb"] and s["has_bangumi_token"] is False
    r = client.put("/api/galgames/meta/settings", json={"bangumi_token": "secret", "order": ["vndb", "bangumi", "ymgal"]}).json()
    assert r["has_bangumi_token"] and "bangumi_token" not in r and r["order"][0] == "vndb"
    assert client.put("/api/galgames/meta/settings", json={"order": ["vndb", "vndb"]}).status_code == 422
    assert client.put("/api/galgames/meta/settings", json={"enabled": {"bangumi": False, "vndb": False, "ymgal": False}}).status_code == 422
    assert client.put("/api/galgames/meta/settings", json={"mode": "steam"}).status_code == 422


def test_add_from_meta_full(client, mock):
    g = client.post("/api/galgames/from-meta", json={"picks": {"bangumi": "900001"}, "status": "playing",
                                                     "import_characters": True}).json()
    assert g["status"] == "playing" and g["has_cover"] and g["work_id"]
    assert set(g["sources"]) == {"bangumi", "vndb", "ymgal"} and g["overrides"] == []
    work = client.get(f"/api/works/{g['work_id']}").json()
    assert work["kind"] == "galgame" and work["year"] == 2025 and work["publisher"] == "示例工作室"
    chars = client.get("/api/characters", params={"work_id": g["work_id"]}).json()["items"]
    assert {c["name"] for c in chars} >= {"樱井 遥", "白石 凛"}
    again = client.post(f"/api/galgames/{g['id']}/import-characters", json={}).json()
    assert again["created"] == [] and len(again["skipped"]) == 3
    cover = client.get(f"/api/galgames/{g['id']}/cover")
    assert cover.status_code == 200 and cover.headers["content-type"] == "image/webp"
    # 已在库里的搜索结果有标记
    r = client.get("/api/galgames/meta/search", params={"q": "樱色回廊"}).json()
    assert r["results"]["bangumi"]["items"][0]["in_library"] == g["id"]
    # 删除时封面文件一起删除
    client.delete(f"/api/galgames/{g['id']}").raise_for_status()
    assert client.get(f"/api/galgames/{g['id']}/cover").status_code == 404


def test_overrides_survive_refresh(client, mock):
    g = client.post("/api/galgames/from-meta", json={"picks": {"vndb": "v90002"}, "work": None, "save_cover": False}).json()
    assert g["work_id"] is None and not g["has_cover"]
    client.patch(f"/api/galgames/{g['id']}", json={"title": "我的雾港", "status": "finished", "my_rating": 9}).raise_for_status()
    g2 = client.get(f"/api/galgames/{g['id']}").json()
    assert g2["overrides"] == ["title"]  # 状态 / 评分不算元数据覆盖
    g3 = client.post(f"/api/galgames/{g['id']}/refresh", json={}).json()
    assert g3["title"] == "我的雾港" and g3["my_rating"] == 9
    g4 = client.post(f"/api/galgames/{g['id']}/refresh", json={"reset_overrides": True}).json()
    assert g4["title"] == "【示例】雾港夜想曲" and g4["overrides"] == []
    # 解除关联 + 手动重新匹配
    g5 = client.delete(f"/api/galgames/{g['id']}/sources/ymgal").json()
    assert "ymgal" not in g5["sources"]
    g6 = client.post(f"/api/galgames/{g['id']}/match", json={"source": "ymgal", "sid": "80002"}).json()
    assert g6["sources"]["ymgal"]["id"] == "80002" and g6["has_cover"]
    assert client.post(f"/api/galgames/{g['id']}/match", json={"source": "vndb", "sid": "v99999"}).status_code == 502


def test_cover_host_guard(client, mock):
    g = client.post("/api/galgames", json={"title": "手动条目"}).json()
    assert client.post(f"/api/galgames/{g['id']}/cover").status_code == 502  # 没有封面地址
    from conftest import png_bytes

    r = client.put(f"/api/galgames/{g['id']}/cover", files={"file": ("c.png", png_bytes(), "image/png")})
    assert r.status_code == 200 and r.json()["has_cover"]
    assert client.put(f"/api/galgames/{g['id']}/cover", files={"file": ("c.txt", b"hello", "text/plain")}).status_code == 422
    from front_api.routers.galgames import _allowed_image_host

    assert _allowed_image_host("https://lain.bgm.tv/pic/cover/x.jpg") and _allowed_image_host("https://t.vndb.org/cv/1.jpg")
    assert _allowed_image_host("http://mockgal/img/cover/x.png")
    assert not _allowed_image_host("http://169.254.169.254/latest") and not _allowed_image_host("file:///etc/passwd")
    assert not _allowed_image_host("https://evil-bgm.tv/x.png")


def test_quick_add_list_filters_stats(client, mock):
    out = [client.post("/api/galgames/quick-add", json={"title": t, "status": st}).json()
           for t, st in (("樱色回廊", "finished"), ("雾港夜想曲", "playing"), ("白夜图书馆", "wishlist"), ("一个不存在的游戏", "wishlist"))]
    assert [o["status"] for o in out] == ["matched", "matched", "matched", "unmatched"]
    assert client.post("/api/galgames/quick-add", json={"title": "樱色回廊"}).json()["status"] == "exists"
    client.patch(f"/api/galgames/{out[0]['id']}", json={"play_minutes": 1500, "my_rating": 8}).raise_for_status()
    lst = lambda **p: client.get("/api/galgames", params=p).json()  # noqa: E731
    assert lst(status="playing")["total"] == 1
    assert lst(source="none")["items"][0]["title"] == "一个不存在的游戏"
    assert lst(source="ymgal")["total"] == 3 and lst(nsfw="1")["items"][0]["title"] == "【示例】白夜图书馆"
    assert lst(sort="rating")["items"][0]["id"] == out[0]["id"]
    assert lst(sort="title")["total"] == 4 and lst()["items"][0]["characters"] is None
    assert lst(q="霧港")["items"][0]["id"] == out[1]["id"]  # 别名 / 原名可搜
    st = client.get("/api/galgames/stats/summary").json()
    assert st["total"] == 4 and st["by_status"]["finished"] == {"count": 1, "minutes": 1500} and st["rated"] == 8
    assert any(d["name"] == "雾灯社" for d in st["developers"])
    cg = client.get(f"/api/galgames/{out[0]['id']}/cg").json()
    assert cg["work_id"] and cg["count"] == 0
    assert client.get("/api/stats").json()["galgames"] == 4
    assert any(r["entity"] == "galgame" for r in client.get("/api/search", params={"q": "雾港"}).json())


def test_offline_switch(client, mock, monkeypatch):
    monkeypatch.setenv("FRONT_GALGAME", "off")
    r = client.get("/api/galgames/meta/search", params={"q": "樱色回廊"}).json()
    assert all(not v["ok"] and "关闭" in v["error"] for v in r["results"].values())
    assert client.get("/api/galgames/meta/settings").json()["online"] is False
    assert client.post("/api/galgames/meta/preview", json={"picks": {"bangumi": "900001"}}).status_code == 502


def test_seed_galgames(client):
    from front_api.seed import seed

    out = seed(client)["galgames"]
    sakura = client.get(f"/api/galgames/{out['sakura']}").json()
    assert sakura["status"] == "finished" and sakura["has_cover"] and sakura["pinned"]
    assert set(sakura["sources"]) == {"bangumi", "vndb", "ymgal"}
    assert client.get(f"/api/works/{sakura['work_id']}").json()["title"] == "【示例】樱色回廊"
    assert client.get(f"/api/galgames/{out['sakura']}/cg").json()["count"] > 0  # 挂上了已有的 CG 档案
    fog = client.get(f"/api/galgames/{out['fog']}").json()
    assert fog["work_id"] and client.get("/api/characters", params={"work_id": fog["work_id"]}).json()["total"] == 3
    assert client.get(f"/api/galgames/{out['unmatched']}").json()["sources"] == {}
    assert client.get(f"/api/galgames/{out['night']}").json()["nsfw"] is True


def test_plays_bulk_export_unplayed(client, mock):
    from datetime import date, timedelta

    g = client.post("/api/galgames", json={"title": "记录测试", "status": "unplayed"}).json()
    today = date.today().isoformat()
    r = client.post(f"/api/galgames/{g['id']}/plays", json={"played_on": today, "minutes": 90, "note": "第一章"}).json()
    assert r["play_minutes"] == 90 and r["status"] == "playing"
    old = (date.today() - timedelta(days=40)).isoformat()
    client.post(f"/api/galgames/{g['id']}/plays", json={"played_on": old, "minutes": 30}).raise_for_status()
    assert client.post(f"/api/galgames/{g['id']}/plays", json={"played_on": "x", "minutes": 5}).status_code == 422
    assert client.post(f"/api/galgames/{g['id']}/plays", json={"played_on": today, "minutes": 0}).status_code == 422
    plays = client.get(f"/api/galgames/{g['id']}/plays").json()
    assert [p["minutes"] for p in plays] == [90, 30]
    gg = client.get(f"/api/galgames/{g['id']}").json()
    assert gg["play_minutes"] == 120 and gg["started_on"] == old
    s = client.get("/api/galgames/plays/summary").json()
    assert s["today"] == 90 and s["month"] >= 90 and s["by_day"][old] == 30 and s["recent"][0]["title"] == "记录测试"
    client.delete(f"/api/galgames/plays/{plays[1]['id']}").raise_for_status()
    assert client.get(f"/api/galgames/{g['id']}").json()["play_minutes"] == 90
    # 批量
    h = client.post("/api/galgames", json={"title": "批量二"}).json()
    assert client.post("/api/galgames/bulk", json={"ids": [g["id"], h["id"]], "status": "shelved"}).json()["count"] == 2
    assert client.get("/api/galgames", params={"status": "shelved"}).json()["total"] == 2
    # 导出
    j = client.get("/api/galgames/export/file", params={"format": "json"})
    assert j.json()["format"] == "front-galgames" and len(j.json()["items"]) == 2
    c = client.get("/api/galgames/export/file", params={"format": "csv"})
    assert c.content.startswith(b"\xef\xbb\xbf") and "记录测试" in c.content.decode("utf-8-sig")
    client.post("/api/galgames/bulk", json={"ids": [g["id"], h["id"]], "delete": True}).raise_for_status()
    assert client.get("/api/galgames").json()["total"] == 0
    # 一键模式：相似度不够也直接用第一条
    r = client.post("/api/galgames/quick-add", json={"title": "钟楼的月夜", "accept_first": True}).json()
    assert r["status"] == "matched" and "月下钟楼" in r["title"]
