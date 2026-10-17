from datetime import date, timedelta
from pathlib import Path

from front_api.routers import quicksearch

REPO = Path(__file__).resolve().parents[2]
# 资源 / 下载站不能出现在默认站点或 README 里（用户可以自己添加）
EXCLUDED = ["touchgal", "kungal", "moyu.moe", "mikiacg", "galgamex", "hikarinagi", "jiuliacg", "shionlib", "galzy",
            "acgnet", "sakugal", "cycity", "sharotto", "GalSites", "civitai.red", "藏经阁"]


def test_activity_heatmap(client):
    assert client.post("/api/assets", json={"title": "旧稿", "kind": "drawing", "work_date": (date.today() - timedelta(days=3)).isoformat()}).status_code in (200, 201)
    client.post("/api/characters", json={"name": "今天的角色"})
    r = client.get("/api/stats/activity", params={"weeks": 4}).json()
    assert r["weeks"] == 4 and len(r["days"]) % 7 in range(7)
    assert date.fromisoformat(r["start"]).weekday() == 0
    today = next(d for d in r["days"] if d["date"] == r["today"])
    assert today["by"].get("characters") == 1
    assert r["streak"] >= 1 and r["total"] >= 1 and r["max"] >= 1
    assert client.get("/api/stats/activity", params={"weeks": 0}).status_code == 422


def test_quick_search_defaults_and_links(client):
    sites = client.get("/api/quick-search/sites").json()["sites"]
    names = {s["name"] for s in sites}
    assert {"Bangumi 游戏", "VNDB", "月幕 Galgame", "2DFan", "萌娘百科", "Civitai"} <= names
    blob = repr(sites).lower()
    assert not [x for x in EXCLUDED if x.lower() in blob]

    links = client.get("/api/quick-search", params={"q": "林 汐&?", "kind": "character"}).json()
    by = {x["id"]: x for x in links}
    assert "bangumi-crt" in by and "vndb" not in by  # 只给角色用的站点
    assert by["bangumi-crt"]["url"] == "https://bgm.tv/mono_search/%E6%9E%97%20%E6%B1%90%26%3F?cat=crt"
    # 官网条目只在关键词匹配时出现，并且是主页链接
    assert "summer-pockets" not in {x["id"] for x in client.get("/api/quick-search", params={"q": "樱色回廊", "kind": "work"}).json()}
    sp = {x["id"]: x for x in client.get("/api/quick-search", params={"q": "Summer Pockets REFLECTION BLUE", "kind": "work"}).json()}["summer-pockets"]
    assert sp["url"] == "https://summerpockets.com/" and sp["search"] is False
    assert client.get("/api/quick-search", params={"q": "  "}).status_code == 422
    assert client.get("/api/quick-search", params={"q": "x", "kind": "nope"}).status_code == 422


def test_quick_search_edit_validate_reset(client):
    mine = {"id": "my", "name": "我的站", "url": "https://example.org/find?s={q}&lang=zh", "kinds": ["model"]}
    r = client.put("/api/quick-search/sites", json={"sites": [mine]})
    assert r.status_code == 200 and r.json()["sites"][0]["enabled"] is True
    links = client.get("/api/quick-search", params={"q": "ink line", "kind": "model"}).json()
    assert links == [{"id": "my", "name": "我的站", "url": "https://example.org/find?s=ink%20line&lang=zh", "search": True, "host": "example.org"}]
    assert client.get("/api/quick-search", params={"q": "x", "kind": "work"}).json() == []
    for bad in ({**mine, "url": "javascript:alert(1)"}, {**mine, "url": "ftp://x.org/{q}"}, {**mine, "kinds": ["bad"]}, {**mine, "name": ""}):
        assert client.put("/api/quick-search/sites", json={"sites": [bad]}).status_code == 422
    assert client.put("/api/quick-search/sites", json={"sites": [mine, mine]}).status_code == 422
    assert len(client.post("/api/quick-search/sites/reset").json()["sites"]) == len(quicksearch.DEFAULT_SITES)


def test_readme_has_no_resource_sites():
    text = (REPO / "README.md").read_text(encoding="utf-8").lower()
    assert not [x for x in EXCLUDED if x.lower() in text]
