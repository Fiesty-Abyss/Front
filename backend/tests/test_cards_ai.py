import base64
import json

from conftest import png_bytes

from front_api.routers import ai as ai_router


def _card(client, **kw):
    payload = {"name": "示例角色卡", "description": "{{char}} 是一位图书管理员", "first_mes": "你好，{{user}}。", "card_tags": ["示例"]}
    payload.update(kw)
    return client.post("/api/cards", json=payload).json()


def test_export_import_json(client):
    card = _card(client, alternate_greetings=["嗨"])
    exported = client.get(f"/api/cards/{card['id']}/export.json").json()
    assert exported["spec"] == "chara_card_v2" and exported["data"]["tags"] == ["示例"]
    r = client.post("/api/cards/import", files={"file": ("c.json", json.dumps(exported).encode(), "application/json")})
    assert r.status_code == 201 and r.json()["alternate_greetings"] == ["嗨"]


def test_export_import_png(client):
    card = _card(client)
    png = client.get(f"/api/cards/{card['id']}/export.png").content
    assert png[:8] == b"\x89PNG\r\n\x1a\n"
    r = client.post("/api/cards/import", files={"file": ("c.png", png, "image/png")})
    assert r.status_code == 201
    assert r.json()["description"] == card["description"]


def test_import_v1_and_v3(client):
    v1 = {"name": "旧卡", "char_persona": "安静", "char_greeting": "……"}
    r = client.post("/api/cards/import", files={"file": ("v1.json", json.dumps(v1).encode(), "application/json")})
    assert r.json()["personality"] == "安静" and r.json()["first_mes"] == "……"
    v3 = {"spec": "chara_card_v3", "spec_version": "3.0", "data": {"name": "新卡", "description": "d"}}
    raw = base64.b64encode(json.dumps(v3).encode()).decode()
    r = client.post("/api/cards/import", files={"file": ("v3.png", png_bytes(text={"ccv3": raw}), "image/png")})
    assert r.json()["name"] == "新卡"


def test_import_rejects_garbage(client):
    assert client.post("/api/cards/import", files={"file": ("x.png", png_bytes(), "image/png")}).status_code == 422
    assert client.post("/api/cards/import", files={"file": ("x.json", b"{}", "application/json")}).status_code == 422


def test_card_from_character(client):
    t = client.post("/api/tags", json={"name": "女", "category": "gender"}).json()["id"]
    c = client.post("/api/characters", json={"name": "角色X", "summary": "简介", "tag_ids": [t]}).json()
    card = client.post(f"/api/cards/from-character/{c['id']}").json()
    assert card["name"] == "角色X" and card["card_tags"] == ["女"] and card["character_id"] == c["id"]


def test_ai_unconfigured_returns_503(client):
    assert client.get("/api/ai/status").json()["available"] is False
    card = _card(client)
    chat = client.post("/api/ai/sessions", json={"card_id": card["id"], "user_name": "旅人"}).json()
    assert chat["messages"][0]["content"] == "你好，旅人。"
    r = client.post(f"/api/ai/sessions/{chat['id']}/messages", json={"content": "在吗"})
    assert r.status_code == 503 and "FRONT_AI_BASE_URL" in r.json()["detail"]


class FakeProvider:
    name = "fake"

    def __init__(self, reply):
        self.reply = reply
        self.calls = []

    def available(self):
        return True

    def chat(self, messages, **kw):
        self.calls.append(messages)
        return self.reply


def test_roleplay_with_fake_provider(app, client):
    fake = FakeProvider("（合上书）欢迎来到图书馆。")
    app.dependency_overrides[ai_router.provider_dep] = lambda: fake
    card = _card(client, post_history_instructions="保持简短")
    chat = client.post("/api/ai/sessions", json={"card_id": card["id"], "user_name": "旅人"}).json()
    r = client.post(f"/api/ai/sessions/{chat['id']}/messages", json={"content": "你好"})
    msgs = r.json()["messages"]
    assert [m["role"] for m in msgs] == ["assistant", "user", "assistant"]
    sent = fake.calls[0]
    assert sent[0]["role"] == "system" and "示例角色卡 是一位图书管理员" in sent[0]["content"]
    assert sent[-1] == {"role": "system", "content": "保持简短"}


def test_ai_suggest_relations(app, client):
    w = client.post("/api/worlds", json={"name": "W", "content": "A 和 B 是青梅竹马。"}).json()["id"]
    a = client.post("/api/characters", json={"name": "A", "world_id": w}).json()["id"]
    b = client.post("/api/characters", json={"name": "B", "world_id": w}).json()["id"]
    reply = json.dumps([
        {"source_id": a, "target_id": b, "kind": "青梅竹马", "description": "正文第一句"},
        {"source_id": a, "target_id": 999, "kind": "编造"},
        {"source_id": a, "target_id": a, "kind": "自环"},
    ], ensure_ascii=False)
    app.dependency_overrides[ai_router.provider_dep] = lambda: FakeProvider("好的：\n" + reply)
    created = client.post(f"/api/ai/worlds/{w}/suggest-relations").json()["created"]
    assert len(created) == 1 and created[0]["ai_suggested"] and not created[0]["confirmed"]
    # 再次识别不会重复
    assert client.post(f"/api/ai/worlds/{w}/suggest-relations").json()["created"] == []


def test_openai_compatible_provider_request():
    import httpx

    from front_api.ai import OpenAICompatibleProvider

    seen = {}

    def handler(req: httpx.Request):
        seen.update(url=str(req.url), body=json.loads(req.content), headers=req.headers)
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})

    p = OpenAICompatibleProvider("http://localhost:11434/v1/", "qwen2.5", api_key="k", transport=httpx.MockTransport(handler))
    assert p.chat([{"role": "user", "content": "hi"}]) == "ok"
    assert seen["url"] == "http://localhost:11434/v1/chat/completions"
    assert seen["body"]["model"] == "qwen2.5" and seen["headers"]["Authorization"] == "Bearer k"


def test_provider_from_env(monkeypatch):
    from front_api.ai import get_provider
    from front_api.config import get_settings

    monkeypatch.setenv("FRONT_AI_BASE_URL", "http://x/v1")
    monkeypatch.setenv("FRONT_AI_MODEL", "m")
    get_settings.cache_clear()
    assert get_provider().name == "openai-compatible"
    get_settings.cache_clear()
