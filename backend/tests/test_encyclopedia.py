import json


def _world(client, name="W"):
    return client.post("/api/worlds", json={"name": name}).json()["id"]


def _char(client, name, **kw):
    return client.post("/api/characters", json={"name": name, **kw}).json()["id"]


def test_world_entries_hierarchy_and_links(client):
    w = _world(client)
    a = _char(client, "甲", world_id=w)
    city = client.post("/api/world-entries", json={"world_id": w, "kind": "location", "name": "雾港市"}).json()
    port = client.post("/api/world-entries", json={"world_id": w, "kind": "location", "name": "旧港区", "parent_id": city["id"]}).json()
    assert port["parent_id"] == city["id"]
    # 不能成环、不能跨世界观
    assert client.patch(f"/api/world-entries/{city['id']}", json={"parent_id": port["id"]}).status_code == 422
    assert client.patch(f"/api/world-entries/{city['id']}", json={"parent_id": city["id"]}).status_code == 422
    w2 = _world(client, "W2")
    assert client.post("/api/world-entries", json={"world_id": w2, "name": "x", "parent_id": city["id"]}).status_code == 422
    org = client.post("/api/world-entries", json={"world_id": w, "kind": "organization", "name": "学生会",
                                                  "characters": [{"character_id": a, "role": "会长"}]}).json()
    assert org["links"] == [{"character_id": a, "role": "会长"}]
    org = client.patch(f"/api/world-entries/{org['id']}", json={"characters": [{"character_id": a, "role": "前会长"}]}).json()
    assert org["links"] == [{"character_id": a, "role": "前会长"}]
    assert client.post("/api/world-entries", json={"world_id": w, "name": "y", "characters": [{"character_id": 999}]}).status_code == 422
    assert client.get("/api/world-entries", params={"world_id": w, "kind": "location"}).json()["total"] == 2
    assert client.get("/api/world-entries", params={"parent_id": "root", "kind": "location"}).json()["total"] == 1
    assert client.get("/api/world-entries", params={"character_id": a}).json()["total"] == 1
    assert client.get("/api/search", params={"q": "学生会", "entity": "world_entry"}).json()[0]["id"] == org["id"]
    # 删除世界观会级联删除条目
    client.delete(f"/api/worlds/{w}")
    assert client.get("/api/world-entries").json()["total"] == 0


def test_timeline_sorted(client):
    w = _world(client)
    a = _char(client, "甲", world_id=w)
    place = client.post("/api/world-entries", json={"world_id": w, "kind": "location", "name": "灯塔"}).json()["id"]
    for name, key in [("后来", 20), ("未定", None), ("最初", 1)]:
        client.post("/api/world-entries", json={"world_id": w, "kind": "event", "name": name, "sort_key": key,
                                                "parent_id": place, "characters": [{"character_id": a, "role": "主角"}]})
    tl = client.get(f"/api/worlds/{w}/timeline").json()
    assert [e["name"] for e in tl] == ["最初", "后来", "未定"]
    assert tl[0]["place"]["name"] == "灯塔" and tl[0]["characters"][0]["role"] == "主角"


def test_character_detail(client):
    w = _world(client)
    work = client.post("/api/works", json={"title": "作品A"}).json()["id"]
    work2 = client.post("/api/works", json={"title": "作品B"}).json()["id"]
    a = _char(client, "甲", world_id=w, work_id=work)
    b = _char(client, "乙", world_id=w)
    client.post("/api/relations", json={"source_id": b, "target_id": a, "kind": "姐妹"})
    assert client.post("/api/appearances", json={"character_id": a, "work_id": work2, "role": "客串"}).status_code == 201
    assert client.post("/api/appearances", json={"character_id": a, "work_id": work2}).status_code == 409
    imgs = [client.post("/api/assets", json={"title": f"i{i}"}).json()["id"] for i in range(3)]
    assert client.put(f"/api/characters/{a}/gallery", json={"asset_ids": [imgs[2], imgs[0]]}).json() == [imgs[2], imgs[0]]
    assert client.post(f"/api/characters/{a}/gallery", json={"asset_ids": [imgs[1], imgs[0]]}).json() == [imgs[2], imgs[0], imgs[1]]
    assert client.delete(f"/api/characters/{a}/gallery/{imgs[0]}").json() == [imgs[2], imgs[1]]
    client.post("/api/world-entries", json={"world_id": w, "kind": "organization", "name": "守望会", "characters": [{"character_id": a, "role": "成员"}]})
    client.post(f"/api/cards/from-character/{a}")
    d = client.get(f"/api/characters/{a}/detail").json()
    assert d["world"]["id"] == w
    assert [g["id"] for g in d["gallery"]] == [imgs[2], imgs[1]]
    assert [(x["work"]["title"], x["role"]) for x in d["appearances"]] == [("作品A", "来源作品"), ("作品B", "客串")]
    assert d["relations"][0]["other"]["name"] == "乙" and d["relations"][0]["direction"] == "in"
    assert d["entries"]["organization"][0]["role"] == "成员"
    assert len(d["cards"]) == 1
    wc = client.get(f"/api/works/{work2}/characters").json()
    assert wc == [{"id": a, "name": "甲", "gender": "unknown", "avatar_asset_id": None, "role": "客串"}]


def test_graph_kinds_filter_layout_export(client):
    w = _world(client)
    a, b, c = (_char(client, n, world_id=w) for n in "ABC")
    client.post("/api/relations", json={"source_id": a, "target_id": b, "kind": "朋友"})
    client.post("/api/relations", json={"source_id": a, "target_id": c, "kind": "对手"})
    client.post("/api/relations", json={"source_id": b, "target_id": c, "kind": "朋友"})
    g = client.get("/api/graph", params={"world_id": w}).json()
    assert g["kinds"] == [{"kind": "朋友", "count": 2}, {"kind": "对手", "count": 1}]
    assert len(client.get("/api/graph", params={"world_id": w, "kinds": "对手"}).json()["edges"]) == 1
    r = client.put("/api/graph/layout", json={"world_id": w, "positions": {str(a): {"x": 10, "y": 20}}, "kind_colors": {"朋友": "#00ff00"}})
    assert r.json()["positions"] == 1
    lay = client.get("/api/graph", params={"world_id": w}).json()["layout"]
    assert lay["positions"][str(a)] == {"x": 10.0, "y": 20.0} and lay["kind_colors"] == {"朋友": "#00ff00"}
    # 只改配色时位置保留
    client.put("/api/graph/layout", json={"world_id": w, "kind_colors": {"对手": "#ff0000"}})
    lay = client.get("/api/graph", params={"world_id": w}).json()["layout"]
    assert lay["positions"] and lay["kind_colors"] == {"对手": "#ff0000"}
    exp = client.get("/api/graph/export", params={"world_id": w})
    assert "attachment" in exp.headers["content-disposition"]
    assert len(json.loads(exp.content)["edges"]) == 3
    client.delete("/api/graph/layout", params={"world_id": w})
    assert client.get("/api/graph", params={"world_id": w}).json()["layout"]["positions"] == {}
    # 全局范围与世界观范围互不影响
    assert client.get("/api/graph").json()["layout"]["kind_colors"] == {}


def test_tag_hierarchy_aliases_merge(client):
    game = client.post("/api/tags", json={"name": "游戏", "category": "medium"}).json()["id"]
    gal = client.post("/api/tags", json={"name": "Galgame", "category": "medium", "parent_id": game, "aliases": ["gal", " gal ", "Galgame", "美少女游戏"]}).json()
    assert gal["aliases"] == ["gal", "美少女游戏"]
    assert client.patch(f"/api/tags/{game}", json={"parent_id": gal["id"]}).status_code == 422  # 成环
    assert client.patch(f"/api/tags/{game}", json={"parent_id": game}).status_code == 422
    # 重命名不应误报重复
    assert client.patch(f"/api/tags/{gal['id']}", json={"name": "Galgame", "color": "#f0f"}).status_code == 200
    c1 = _char(client, "甲", tag_ids=[gal["id"]])
    _char(client, "乙", tag_ids=[game])
    # 父标签筛选包含子标签
    assert client.get("/api/characters", params={"tag": game}).json()["total"] == 2
    assert client.get("/api/characters", params={"tag": gal["id"]}).json()["total"] == 1
    # 别名可搜
    assert client.get("/api/tags", params={"name": "美少女"}).json()["items"][0]["id"] == gal["id"]
    assert client.get("/api/search", params={"q": "美少女游戏"}).json()[0]["id"] == c1
    tree = client.get("/api/tags/tree").json()
    assert tree[0]["name"] == "游戏" and tree[0]["children"][0]["name"] == "Galgame"

    # 合并：恋爱ADV → Galgame
    adv = client.post("/api/tags", json={"name": "恋爱ADV", "category": "custom", "aliases": ["ADV"]}).json()["id"]
    child = client.post("/api/tags", json={"name": "纯爱", "category": "custom", "parent_id": adv}).json()["id"]
    both = _char(client, "丙", tag_ids=[adv, gal["id"]])
    only = _char(client, "丁", tag_ids=[adv])
    a = client.post("/api/assets", json={"title": "x", "tag_ids": [adv]}).json()["id"]
    assert client.post(f"/api/tags/{adv}/merge", json={"into_id": adv}).status_code == 422
    merged = client.post(f"/api/tags/{adv}/merge", json={"into_id": gal["id"]}).json()
    assert merged["aliases"] == ["gal", "美少女游戏", "恋爱ADV", "ADV"]
    assert client.get(f"/api/tags/{adv}").status_code == 404
    assert [t["name"] for t in client.get(f"/api/characters/{both}").json()["tags"]] == ["Galgame"]
    assert [t["name"] for t in client.get(f"/api/characters/{only}").json()["tags"]] == ["Galgame"]
    assert [t["name"] for t in client.get(f"/api/assets/{a}").json()["tags"]] == ["Galgame"]
    assert client.get(f"/api/tags/{child}").json()["parent_id"] == gal["id"]
    usage = client.get("/api/tags/usage").json()
    assert usage[str(gal["id"])] == 4
    assert client.get("/api/search", params={"q": "恋爱ADV"}).json()  # 旧名作为别名仍可搜到
    # 不能合并进自己的子标签
    assert client.post(f"/api/tags/{game}/merge", json={"into_id": gal["id"]}).status_code == 422


def test_migration_adds_tag_columns(tmp_path, monkeypatch):
    import sqlite3

    from front_api.config import get_settings
    from front_api.main import create_app

    data = tmp_path / "v02"
    data.mkdir()
    con = sqlite3.connect(data / "front.db")
    con.executescript(
        "CREATE TABLE tags (id INTEGER PRIMARY KEY, name VARCHAR(80), category VARCHAR(40), color VARCHAR(16));"
        "INSERT INTO tags VALUES (1, '女', 'gender', NULL);"
    )
    con.close()
    monkeypatch.setenv("FRONT_DATA_DIR", str(data))
    get_settings.cache_clear()
    from fastapi.testclient import TestClient

    with TestClient(create_app()) as c:
        t = c.get("/api/tags/1").json()
        assert t["aliases"] == [] and t["parent_id"] is None
        assert c.patch("/api/tags/1", json={"aliases": ["女性"]}).json()["aliases"] == ["女性"]
    get_settings.cache_clear()
