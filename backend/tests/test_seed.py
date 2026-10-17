from front_api.seed import seed


def test_seed_builds_full_example_library(client):
    out = seed(client)
    wid = out["world_id"]
    entries = client.get("/api/world-entries", params={"world_id": wid, "limit": 100}).json()["items"]
    kinds = {e["kind"] for e in entries}
    assert {"location", "organization", "event", "item", "concept"} <= kinds
    timeline = client.get(f"/api/worlds/{wid}/timeline").json()
    assert timeline[-1]["sort_key"] is None and timeline[0]["sort_key"] < timeline[1]["sort_key"]
    lin = next(c for c in client.get("/api/characters").json()["items"] if c["name"] == "林汐")
    detail = client.get(f"/api/characters/{lin['id']}/detail").json()
    assert len(detail["gallery"]) >= 4 and len(detail["appearances"]) == 2
    graph = client.get("/api/graph", params={"world_id": wid}).json()
    assert graph["layout"]["kind_colors"]["青梅竹马"] and any(not e["confirmed"] for e in graph["edges"])
    # 别名搜索：gal → Galgame；按父标签「游戏」筛选作品，会包含 Galgame 作品
    gal = client.get("/api/tags", params={"name": "gal"}).json()["items"]
    assert [t["name"] for t in gal] == ["Galgame"]
    game = client.get("/api/tags", params={"name": "游戏"}).json()["items"][0]
    works = client.get("/api/works", params={"tag": game["id"]}).json()["items"]
    assert [w["kind"] for w in works] == ["galgame"]


def test_seed_ai_drawing_examples(client):
    out = seed(client)
    assert len(out["batches"]) == 2
    grid = client.get(f"/api/prompts/{out['prompt_id']}/xy", params={"batch": out["batches"][0]}).json()
    assert grid["x"] == "model" and grid["y"] == "cfg" and len(grid["x_values"]) == 2 and grid["y_values"] == ["5", "7", "9"]
    sr = client.get(f"/api/prompts/{out['prompt_id']}/xy", params={"batch": out["batches"][1]}).json()
    assert sr["x_values"] == ["night", "dawn", "sunset"]
    assert client.get("/api/prompt-snippets", params={"limit": 100}).json()["total"] >= 10


def test_seed_ai_character_examples(client):
    out = seed(client)
    chat = client.get(f"/api/ai/sessions/{out['chat_id']}").json()
    roles = [m["role"] for m in chat["messages"]]
    assert roles == ["assistant", "user", "assistant", "user", "assistant", "user", "assistant"]
    assert len(chat["messages"][0]["sibling_ids"]) == 2  # 两个开场白
    assert len(chat["messages"][2]["sibling_ids"]) == 2  # 重新生成过一次
    assert len(chat["messages"][5]["sibling_ids"]) == 2  # 编辑过一次
    assert any(m["meta"].get("lore") for m in chat["messages"])
    assert chat["total_messages"] == 11
    book = client.get(f"/api/lorebooks/{out['lorebook_id']}").json()
    assert book["world_id"] == out["world_id"] and len(book["entries"]) >= 8
    assert client.get("/api/settings").json()["chat_provider_id"] is None  # 示例不会接管对话服务
    providers = client.get("/api/ai/providers").json()["items"]
    assert all(p["name"].startswith(("【示例】", "本机 Ollama")) for p in providers)
