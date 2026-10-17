import pytest


def test_health(client):
    assert client.get("/api/health").json()["ok"] is True


@pytest.mark.parametrize(
    "path,payload,patch",
    [
        ("/api/tags", {"name": "女", "category": "gender"}, {"color": "#f6a"}),
        ("/api/works", {"title": "示例作品", "kind": "galgame"}, {"year": 2026}),
        ("/api/worlds", {"name": "示例世界", "summary": "s"}, {"content": "正文"}),
        ("/api/characters", {"name": "示例角色", "gender": "female"}, {"alias": "别名"}),
        ("/api/prompts", {"title": "示例提示词", "positive": "1girl"}, {"negative": "lowres"}),
        ("/api/sd-models", {"name": "示例模型", "kind": "lora"}, {"base_model": "SDXL"}),
        ("/api/cards", {"name": "示例卡"}, {"first_mes": "你好"}),
        ("/api/assets", {"title": "示例文章", "kind": "novel", "content": "第一章"}, {"title": "改名"}),
        ("/api/collections", {"name": "示例收藏"}, {"description": "d"}),
    ],
)
def test_crud_roundtrip(client, path, payload, patch):
    r = client.post(path, json=payload)
    assert r.status_code == 201, r.text
    obj = r.json()
    oid = obj["id"]
    assert client.get(f"{path}/{oid}").status_code == 200
    listed = client.get(path).json()
    assert listed["total"] == 1 and listed["items"][0]["id"] == oid
    r = client.patch(f"{path}/{oid}", json=patch)
    assert r.status_code == 200, r.text
    for k, v in patch.items():
        assert r.json()[k] == v
    assert client.delete(f"{path}/{oid}").status_code == 204
    assert client.get(f"{path}/{oid}").status_code == 404


def test_duplicate_tag_conflict(client):
    client.post("/api/tags", json={"name": "游戏", "category": "medium"})
    assert client.post("/api/tags", json={"name": "游戏", "category": "medium"}).status_code == 409
    # 同名不同分类允许
    assert client.post("/api/tags", json={"name": "游戏", "category": "custom"}).status_code == 201


def test_character_facets(client):
    girl = client.post("/api/tags", json={"name": "女", "category": "gender"}).json()["id"]
    game = client.post("/api/tags", json={"name": "游戏", "category": "medium"}).json()["id"]
    anime = client.post("/api/tags", json={"name": "动漫", "category": "medium"}).json()["id"]
    client.post("/api/characters", json={"name": "甲", "gender": "female", "tag_ids": [girl, game]})
    client.post("/api/characters", json={"name": "乙", "gender": "female", "tag_ids": [girl, anime]})
    client.post("/api/characters", json={"name": "丙", "gender": "male", "tag_ids": [game]})
    assert client.get("/api/characters", params={"tag": [girl, game]}).json()["total"] == 1
    assert client.get("/api/characters", params={"tag": [game]}).json()["total"] == 2
    assert client.get("/api/characters", params={"gender": "male"}).json()["total"] == 1


def test_unknown_tag_rejected(client):
    assert client.post("/api/characters", json={"name": "x", "tag_ids": [999]}).status_code == 422


def test_relations_and_graph(client):
    w = client.post("/api/worlds", json={"name": "W"}).json()["id"]
    a = client.post("/api/characters", json={"name": "A", "world_id": w}).json()["id"]
    b = client.post("/api/characters", json={"name": "B", "world_id": w}).json()["id"]
    other = client.post("/api/characters", json={"name": "C"}).json()["id"]
    assert client.post("/api/relations", json={"source_id": a, "target_id": a, "kind": "自己"}).status_code == 422
    assert client.post("/api/relations", json={"source_id": a, "target_id": 999, "kind": "x"}).status_code == 422
    assert client.post("/api/relations", json={"source_id": a, "target_id": b, "kind": "青梅竹马"}).status_code == 201
    client.post("/api/relations", json={"source_id": a, "target_id": other, "kind": "路人"})
    g = client.get("/api/graph", params={"world_id": w}).json()
    assert {n["name"] for n in g["nodes"]} == {"A", "B"}
    assert [e["kind"] for e in g["edges"]] == ["青梅竹马"]
    # 删除角色时关系级联删除
    client.delete(f"/api/characters/{b}")
    assert client.get("/api/relations", params={"character_id": a}).json()["total"] == 1


def test_prompt_compare(client):
    p = client.post("/api/prompts", json={"title": "P", "positive": "1girl, garden"}).json()["id"]
    m1 = client.post("/api/sd-models", json={"name": "M1"}).json()["id"]
    m2 = client.post("/api/sd-models", json={"name": "M2"}).json()["id"]
    a1 = client.post("/api/assets", json={"title": "i1", "kind": "ai_image"}).json()["id"]
    a2 = client.post("/api/assets", json={"title": "i2", "kind": "ai_image"}).json()["id"]
    client.post("/api/generations", json={"prompt_id": p, "model_id": m1, "asset_id": a1, "params": {"seed": 1}})
    client.post("/api/generations", json={"prompt_id": p, "model_id": m2, "asset_id": a2, "params": {"seed": 1}})
    cmp = client.get(f"/api/prompts/{p}/compare").json()
    assert sorted(g["model"]["name"] for g in cmp["groups"]) == ["M1", "M2"]


def test_collection_assets(client):
    a = client.post("/api/assets", json={"title": "a"}).json()["id"]
    c = client.post("/api/collections", json={"name": "c", "asset_ids": [a]}).json()
    assert [x["id"] for x in c["assets"]] == [a]
