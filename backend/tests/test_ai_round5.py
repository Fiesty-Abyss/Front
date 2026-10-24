"""v0.5：AI 服务设置、流式对话与分支、世界书、小说抽取角色、语义检索、自动打标签。"""

import json
import time

import httpx
import pytest
from conftest import png_bytes
from fastapi.testclient import TestClient

from front_api.ai import lore, registry
from front_api.ai.embed import local_embed
from front_api.mock_ai import create_mock_app


@pytest.fixture
def mock_ai(client):
    """注册一个指向模拟 AI 服务的 provider，并设为对话 / 嵌入 / 视觉服务。"""
    transport = TestClient(create_mock_app(delay=0))._transport
    p = client.post("/api/ai/providers", json={
        "name": "模拟", "base_url": "http://mock-ai/v1", "api_key": "sk-test-1234567890",
        "chat_model": "mock-chat", "embedding_model": "mock-embed", "vision_model": "mock-vision",
    }).json()
    registry.transport_override[p["id"]] = transport
    client.patch("/api/settings", json={"chat_provider_id": p["id"]})
    yield p
    registry.transport_override.clear()


def wait_job(client, job_id):
    for _ in range(400):
        j = client.get(f"/api/jobs/{job_id}").json()
        if j["status"] not in ("queued", "running"):
            return j
        time.sleep(0.02)
    raise AssertionError("job timeout")


def sse(text):
    out = []
    for block in text.strip().split("\n\n"):
        lines = dict(line.split(": ", 1) for line in block.split("\n") if ": " in line)
        out.append((lines["event"], json.loads(lines["data"])))
    return out


def _card(client, **kw):
    body = {"name": "灯塔守", "first_mes": "（举灯）谁在那里？", "alternate_greetings": ["（打哈欠）又是雾季。"]}
    body.update(kw)
    return client.post("/api/cards", json=body).json()


# ---------- 设置 ----------
def test_provider_crud_masks_key(client, mock_ai):
    listed = client.get("/api/ai/providers").json()
    item = listed["items"][0]
    assert "api_key" not in item and item["api_key_set"] and item["api_key_hint"] == "sk-…7890"
    assert any(p["name"].startswith("Ollama") for p in listed["presets"])
    # 不传 api_key 不修改，传空字符串清除
    assert client.patch(f"/api/ai/providers/{item['id']}", json={"name": "改名"}).json()["api_key_set"]
    assert not client.patch(f"/api/ai/providers/{item['id']}", json={"api_key": ""}).json()["api_key_set"]
    st = client.get("/api/ai/status").json()
    assert st["available"] and st["source"] == "settings" and st["model"] == "mock-chat"
    test = client.post(f"/api/ai/providers/{item['id']}/test").json()
    assert test["ok"] and "mock-chat" in test["models"]["result"] and test["embedding"]["result"]["dim"] == 256
    assert client.get(f"/api/ai/providers/{item['id']}/models").json()["models"] == ["mock-chat", "mock-embed", "mock-vision"]
    # 删除 provider 时清掉引用它的设置
    client.delete(f"/api/ai/providers/{item['id']}")
    assert client.get("/api/settings").json()["chat_provider_id"] is None
    assert client.get("/api/ai/status").json()["source"] == "none"


def test_settings_validation(client):
    assert client.patch("/api/settings", json={"chat_provider_id": 999}).status_code == 404
    assert client.patch("/api/settings", json={"tagger_backend": "magic"}).status_code == 422
    assert client.patch("/api/settings", json={"tagger_threshold": 0.5}).json()["tagger_threshold"] == 0.5


# ---------- 对话：流式、重新生成、编辑、分支 ----------
def test_streaming_chat_and_branches(client, mock_ai):
    card = _card(client)
    chat = client.post("/api/ai/sessions", json={"card_id": card["id"], "user_name": "旅人"}).json()
    greet = chat["messages"][0]
    assert len(greet["sibling_ids"]) == 2  # 开场白 + 备选开场白
    r = client.post(f"/api/ai/sessions/{chat['id']}/generate", json={"content": "灯塔为什么亮着"})
    assert r.headers["content-type"].startswith("text/event-stream")
    events = sse(r.text)
    assert events[0][0] == "start" and events[-1][0] == "done"
    deltas = "".join(d["text"] for e, d in events if e == "delta")
    sess = events[-1][1]["session"]
    assert sess["messages"][-1]["content"] == deltas and deltas.startswith("【模拟回复】")
    assert [m["role"] for m in sess["messages"]] == ["assistant", "user", "assistant"]
    first_reply = sess["messages"][-1]

    # 重新生成：同一个 parent 下多一个兄弟
    events = sse(client.post(f"/api/ai/sessions/{chat['id']}/generate", json={"regenerate_id": first_reply["id"]}).text)
    sess = events[-1][1]["session"]
    assert sess["messages"][-1]["sibling_ids"] == [first_reply["id"], sess["messages"][-1]["id"]]
    assert sess["messages"][-1]["meta"]["regenerated_from"] == first_reply["id"]

    # 切回第一个回复
    sess = client.post(f"/api/ai/sessions/{chat['id']}/select", json={"message_id": first_reply["id"]}).json()
    assert sess["messages"][-1]["id"] == first_reply["id"]

    # 编辑用户消息：另开分支，原分支保留
    user_msg = sess["messages"][1]
    events = sse(client.post(f"/api/ai/sessions/{chat['id']}/generate", json={"edit_id": user_msg["id"], "content": "你叫什么名字"}).text)
    sess = events[-1][1]["session"]
    assert sess["messages"][1]["content"] == "你叫什么名字" and len(sess["messages"][1]["sibling_ids"]) == 2
    assert sess["total_messages"] == 2 + 1 + 2 + 2

    # 切换开场白分支：该分支下没有回复
    sess = client.post(f"/api/ai/sessions/{chat['id']}/select", json={"message_id": greet["sibling_ids"][1]}).json()
    assert len(sess["messages"]) == 1 and sess["messages"][0]["content"] == "（打哈欠）又是雾季。"

    # 删除第一个开场白及其全部后续
    sess = client.delete(f"/api/ai/messages/{greet['id']}").json()
    assert sess["total_messages"] == 1

    # 直接修改内容
    sess = client.patch(f"/api/ai/messages/{sess['messages'][0]['id']}", json={"content": "改过的开场白"}).json()
    assert sess["messages"][0]["content"] == "改过的开场白" and sess["messages"][0]["meta"]["edited"]

    assert client.post(f"/api/ai/sessions/{chat['id']}/generate", json={"regenerate_id": sess["messages"][0]["id"] + 999}).status_code == 404
    assert client.post(f"/api/ai/sessions/{chat['id']}/generate", json={"edit_id": sess["messages"][0]["id"], "content": "x"}).status_code == 422


def test_non_stream_and_legacy_endpoint(client, mock_ai):
    card = _card(client, alternate_greetings=[])
    chat = client.post("/api/ai/sessions", json={"card_id": card["id"]}).json()
    sess = client.post(f"/api/ai/sessions/{chat['id']}/generate", json={"content": "你好", "stream": False}).json()
    assert sess["messages"][-1]["role"] == "assistant"
    sess = client.post(f"/api/ai/sessions/{chat['id']}/messages", json={"content": "再见"}).json()
    assert len(sess["messages"]) == 5
    listing = client.get("/api/ai/sessions").json()
    assert listing[0]["messages"] == 5 and listing[0]["last"].startswith("【模拟回复】")


def test_stream_error_keeps_user_message(client):
    def handler(req):
        return httpx.Response(500, text="boom")

    p = client.post("/api/ai/providers", json={"name": "坏", "base_url": "http://bad/v1", "chat_model": "x"}).json()
    registry.transport_override[p["id"]] = httpx.MockTransport(handler)
    try:
        client.patch("/api/settings", json={"chat_provider_id": p["id"]})
        card = _card(client)
        chat = client.post("/api/ai/sessions", json={"card_id": card["id"]}).json()
        events = sse(client.post(f"/api/ai/sessions/{chat['id']}/generate", json={"content": "在吗"}).text)
        assert events[-1][0] == "error" and "500" in events[-1][1]["detail"]
        sess = client.get(f"/api/ai/sessions/{chat['id']}").json()
        assert sess["messages"][-1]["content"] == "在吗"
        # 用户消息已保存：服务恢复后可以不带 content 直接让 AI 接着回复
    finally:
        registry.transport_override.clear()


def test_stream_parser_handles_sse_and_json():
    from front_api.ai import OpenAICompatibleProvider

    def handler(req):
        body = json.loads(req.content)
        if body["model"] == "sse":
            chunks = [{"choices": [{"delta": {"content": "你"}}]}, {"choices": [{"delta": {}}]}, {"choices": [{"delta": {"content": "好"}}]}]
            text = "".join(f"data: {json.dumps(c)}\n\n" for c in chunks) + ": keep-alive\n\ndata: [DONE]\n\n"
            return httpx.Response(200, text=text, headers={"content-type": "text/event-stream"})
        return httpx.Response(200, json={"choices": [{"message": {"content": "整段"}}]})

    t = httpx.MockTransport(handler)
    assert "".join(OpenAICompatibleProvider("http://x/v1", "sse", transport=t).stream([])) == "你好"
    assert "".join(OpenAICompatibleProvider("http://x/v1", "json", transport=t).stream([])) == "整段"


# ---------- 世界书 ----------
def test_lore_activation_rules():
    book = {"id": 1, "name": "b", "scan_depth": 2, "token_budget": 1000, "recursive": False, "entries": [
        {"id": 1, "keys": ["灯塔"], "content": "灯塔在港口北侧。", "insertion_order": 20},
        {"id": 2, "keys": ["cat"], "content": "猫的设定", "insertion_order": 10},
        {"id": 3, "keys": ["/雾+季/"], "content": "雾季持续三个月。"},
        {"id": 4, "keys": ["学院"], "secondary_keys": ["夜晚"], "selective": True, "content": "学院夜晚禁止外出。"},
        {"id": 5, "constant": True, "keys": [], "content": "世界基调：安静。", "insertion_order": 0},
        {"id": 6, "keys": ["守望会"], "content": "守望会负责灯塔。", "enabled": False},
        {"id": 7, "keys": ["港口北侧"], "content": "北侧有旧仓库。"},
    ]}
    ids = lambda res: [r["entry_id"] for r in res["active"]]  # noqa: E731
    assert ids(lore.activate([book], ["很久以前", "灯塔亮了", "category 页面"])) == [5, 1]  # 只扫描最近两条；cat 不匹配 category
    assert set(ids(lore.activate([book], ["雾雾季来了", "学院"]))) == {5, 3}  # 正则；selective 缺次关键词
    assert 4 in ids(lore.activate([book], ["学院的夜晚"]))
    assert 7 in ids(lore.activate([dict(book, recursive=True)], ["灯塔"]))  # 递归：条目内容再触发
    small = dict(book, token_budget=12)
    res = lore.activate([small], ["灯塔", "雾季"])
    assert 5 in ids(res) and res["skipped"]  # 常驻优先，其余超预算被跳过
    assert lore.estimate_tokens("灯塔 abcd") == 4


def test_lorebook_api_and_chat_injection(client, mock_ai):
    w = client.post("/api/worlds", json={"name": "雾港", "summary": "终年多雾的港口城市"}).json()["id"]
    ch = client.post("/api/characters", json={"name": "林汐", "alias": "汐", "summary": "灯塔看守", "world_id": w}).json()["id"]
    client.post("/api/world-entries", json={"world_id": w, "kind": "location", "name": "旧书店", "summary": "坡道尽头的书店"})
    book = client.post(f"/api/lorebooks/from-world/{w}").json()
    titles = [e["title"] for e in book["entries"]]
    assert titles[0] == "世界观 · 雾港" and book["entries"][0]["constant"] and "角色 · 林汐" in titles and "地点 · 旧书店" in titles
    assert next(e for e in book["entries"] if e["title"] == "角色 · 林汐")["keys"] == ["林汐", "汐"]
    e = client.post(f"/api/lorebooks/{book['id']}/entries", json={"keys": ["灯塔节"], "content": "灯塔节在雾季最后一天。", "title": "灯塔节"}).json()
    assert client.patch(f"/api/lore-entries/{e['id']}", json={"position": "after_char"}).json()["position"] == "after_char"
    res = client.post(f"/api/lorebooks/{book['id']}/test", json={"text": "明天就是灯塔节了"}).json()
    assert [r["title"] for r in res["active"]] == ["世界观 · 雾港", "灯塔节"]
    # 世界观的世界书自动用于该世界观角色的角色卡对话
    card = client.post(f"/api/cards/from-character/{ch}").json()
    chat = client.post("/api/ai/sessions", json={"card_id": card["id"], "user_name": "旅人"}).json()
    events = sse(client.post(f"/api/ai/sessions/{chat['id']}/generate", json={"content": "去旧书店吧"}).text)
    assert {x["title"] for x in events[0][1]["lore"]} == {"世界观 · 雾港", "地点 · 旧书店"}
    reply = events[-1][1]["session"]["messages"][-1]
    assert "世界书" in reply["content"] and reply["meta"]["lore"]
    ctx = client.get(f"/api/ai/sessions/{chat['id']}/context").json()
    assert "【世界书】" in ctx["messages"][0]["content"] and ctx["lorebooks"][0]["id"] == book["id"]
    # 会话额外挂一本世界书
    other = client.post("/api/lorebooks", json={"name": "额外", "entries": [{"keys": ["猫"], "content": "港口有很多猫。"}]}).json()
    assert client.patch(f"/api/ai/sessions/{chat['id']}", json={"lorebook_ids": [other["id"]]}).json()["lorebook_ids"] == [other["id"]]
    assert client.patch(f"/api/ai/sessions/{chat['id']}", json={"lorebook_ids": [999]}).status_code == 404
    listed = client.get("/api/lorebooks").json()["items"]
    assert {b["name"] for b in listed} == {"雾港 世界书", "额外"}
    client.delete(f"/api/lorebooks/{other['id']}")
    assert client.get(f"/api/ai/sessions/{chat['id']}").json()["lorebook_ids"] == []


def test_lorebook_import_export_formats(client):
    st = {"entries": {"0": {"uid": 0, "key": ["雾港"], "keysecondary": [], "comment": "城市", "content": "雾港是港口城市。",
                            "constant": False, "selective": False, "order": 5, "position": 1, "disable": False}}}
    book = client.post("/api/lorebooks/import", files={"file": ("w.json", json.dumps(st).encode(), "application/json")}).json()
    e = book["entries"][0]
    assert e["title"] == "城市" and e["position"] == "after_char" and e["insertion_order"] == 5
    v2 = client.get(f"/api/lorebooks/{book['id']}/export").json()
    assert v2["entries"][0]["keys"] == ["雾港"] and v2["entries"][0]["position"] == "after_char"
    back = client.get(f"/api/lorebooks/{book['id']}/export?format=st").json()
    assert back["entries"]["0"]["key"] == ["雾港"] and back["entries"]["0"]["position"] == 1
    assert client.post("/api/lorebooks/import", files={"file": ("x.json", b"{}", "application/json")}).status_code == 422


def test_card_character_book_roundtrip(client):
    card_json = {"spec": "chara_card_v2", "spec_version": "2.0", "data": {"name": "带书角色", "description": "d",
                 "character_book": {"name": "", "entries": [{"keys": ["钥匙"], "content": "钥匙在灯塔顶层。", "enabled": True,
                                                             "insertion_order": 1, "extensions": {}}]}}}
    card = client.post("/api/cards/import", files={"file": ("c.json", json.dumps(card_json).encode(), "application/json")}).json()
    assert card["lorebook_id"]
    book = client.get(f"/api/lorebooks/{card['lorebook_id']}").json()
    assert book["name"] == "带书角色 的世界书" and book["entries"][0]["keys"] == ["钥匙"]
    exported = client.get(f"/api/cards/{card['id']}/export.json").json()
    assert exported["data"]["character_book"]["entries"][0]["content"] == "钥匙在灯塔顶层。"
    png = client.get(f"/api/cards/{card['id']}/export.png").content
    again = client.post("/api/cards/import", files={"file": ("c.png", png, "image/png")}).json()
    assert again["lorebook_id"] and again["lorebook_id"] != card["lorebook_id"]


# ---------- 小说抽取角色 ----------
NOVEL = """第一章 雾季
林汐正爬上灯塔的台阶，她把提灯挂在栏杆上。
第二章 书店
沈既白把旧地图搬到柜台上，他笑了笑。沈小满趴在柜台另一侧写作业，她头也不抬。
"""


def test_extract_characters_and_apply(client, mock_ai):
    w = client.post("/api/worlds", json={"name": "雾港"}).json()["id"]
    existing = client.post("/api/characters", json={"name": "林汐", "world_id": w}).json()["id"]
    female = client.post("/api/tags", json={"name": "女", "category": "gender"}).json()["id"]
    asset = client.post("/api/assets", json={"title": "短篇", "kind": "novel", "content": NOVEL}).json()["id"]
    job = client.post("/api/ai/extract/characters", json={"asset_id": asset, "world_id": w, "chunk_size": 500}).json()
    job = wait_job(client, job["id"])
    assert job["status"] == "done", job
    chars = {c["name"]: c for c in job["result"]["characters"]}
    assert set(chars) == {"林汐", "沈既白", "沈小满"}
    assert chars["林汐"]["existing_id"] == existing and chars["沈小满"]["gender"] == "female"
    picked = [chars["沈既白"], chars["沈小满"], chars["林汐"]]
    res = client.post("/api/ai/extract/apply", json={"characters": picked, "world_id": w, "source": "短篇"}).json()
    assert len(res["created"]) == 2 and res["updated"] == [] and res["relations"] == 1
    xiaoman = client.get(f"/api/characters/{res['created'][1]}").json()
    assert xiaoman["gender"] == "female" and [t["id"] for t in xiaoman["tags"]] == [female] and "短篇" in xiaoman["profile"]
    rel = client.get("/api/relations").json()["items"][0]
    assert rel["ai_suggested"] and not rel["confirmed"]
    # 已存在的角色可以选择补充信息
    res = client.post("/api/ai/extract/apply", json={"characters": [chars["林汐"]], "world_id": w, "update_existing": True}).json()
    assert res["updated"] == [existing] and client.get(f"/api/characters/{existing}").json()["summary"]


def test_extract_requires_text_and_provider(client):
    asset = client.post("/api/assets", json={"title": "空", "kind": "novel", "content": ""}).json()["id"]
    assert client.post("/api/ai/extract/characters", json={"asset_id": asset}).status_code == 422
    assert client.post("/api/ai/extract/characters", json={"text": NOVEL}).status_code == 503


def test_chunking_and_parsing():
    from front_api.ai.extract import chunk_text, merge, parse

    text = "第一章 甲\n" + "啊" * 900 + "\n第二章 乙\n短\n第三章 丙\n" + "嗯。" * 700
    chunks = chunk_text(text, 1000)
    assert all(len(c) <= 1000 for c in chunks) and "".join(chunks).count("啊") == 900
    items = parse('好的：{"characters":[{"name":"甲","aliases":"小甲、阿甲","gender":"男"},{"name":""}]}')
    assert items == [{"name": "甲", "aliases": ["小甲", "阿甲"], "gender": "male", "summary": "", "traits": [], "appearance": "", "relations": []}]
    acc = merge([], items)
    merge(acc, [{"name": "小甲", "aliases": [], "gender": "unknown", "summary": "更长的简介", "traits": ["勇敢"], "appearance": "", "relations": []}])
    assert len(acc) == 2 and acc[0]['name'] == '甲' and acc[1]['name'] == '小甲'
    merge(acc, [{"name":"甲","aliases":[],"gender":"unknown","summary":"明确同名观察","traits":[],"appearance":"","relations":[]}])
    assert acc[0]['mentions']==2 and acc[0]['summary']=='明确同名观察'
    assert parse("不是 JSON") == []


# ---------- 语义检索 ----------
def test_semantic_search_local_and_hybrid(client):
    client.post("/api/characters", json={"name": "林汐", "summary": "在雾港守护灯塔的少女，夜里提着灯巡视海岸"})
    client.post("/api/characters", json={"name": "陆鸣", "summary": "学生会长，擅长制定计划"})
    client.post("/api/prompts", json={"title": "雾夜", "positive": "lighthouse, sea fog, night"})
    st = client.get("/api/search/semantic/status").json()
    assert st["backend"] == "local" and st["indexed"] == 0 and st["total"] == 3
    hits = client.get("/api/search/semantic", params={"q": "守护海岸灯塔的人"}).json()["items"]
    assert hits[0]["title"] == "林汐" and hits[0]["score"] > hits[1]["score"]
    assert client.get("/api/search/semantic/status").json()["indexed"] == 3  # 本地向量查询时自动补齐
    hyb = client.get("/api/search/semantic", params={"q": "灯塔", "mode": "hybrid"}).json()["items"]
    assert hyb[0]["title"] == "林汐" and set(hyb[0]["sources"]) == {"keyword", "semantic"}
    only = client.get("/api/search/semantic", params={"q": "fog", "entity": "prompt"}).json()["items"]
    assert [h["entity"] for h in only] == ["prompt"]
    sim = client.get("/api/search/similar", params={"entity": "character", "id": hits[0]["id"]}).json()["items"]
    assert sim and all(h["id"] != hits[0]["id"] or h["entity"] != "character" for h in sim)
    # 修改后重新索引只处理变化的条目
    client.patch(f"/api/characters/{hits[0]['id']}", json={"summary": "改了"})
    job = wait_job(client, client.post("/api/search/semantic/index").json()["id"])
    assert job["result"]["indexed"] == 1


def test_semantic_search_with_provider_embeddings(client, mock_ai):
    client.post("/api/characters", json={"name": "林汐", "summary": "灯塔看守"})
    client.patch("/api/settings", json={"embedding_backend": "provider"})
    assert client.get("/api/search/semantic", params={"q": "灯塔"}).status_code == 503  # 还没选嵌入服务
    client.patch("/api/settings", json={"embedding_provider_id": mock_ai["id"]})
    job = wait_job(client, client.post("/api/search/semantic/index").json()["id"])
    assert job["status"] == "done" and job["result"]["model"] == f"p{mock_ai['id']}:mock-embed"
    hits = client.get("/api/search/semantic", params={"q": "灯塔看守"}).json()
    assert hits["items"][0]["title"] == "林汐" and hits["model"].endswith("mock-embed")


def test_local_embed_is_normalized():
    v = local_embed(["雾港的灯塔", ""])
    assert abs(sum(x * x for x in v[0]) - 1) < 1e-6 and len(v[0]) == 512


# ---------- 自动打标签 ----------
def _upload(client, size=(64, 96)):
    return client.post("/api/assets/upload", files={"file": ("a.png", png_bytes(color=(30, 40, 160), size=size), "image/png")},
                       data={"kind": "drawing"}).json()["id"]


def test_tagger_vision_and_alias_mapping(client, mock_ai):
    aid = _upload(client)
    assert client.post(f"/api/ai/tagger/assets/{aid}").status_code == 503  # 默认关闭
    stand = client.post("/api/tags", json={"name": "立绘", "category": "type", "aliases": ["portrait"]}).json()["id"]
    blue = client.post("/api/tags", json={"name": "蓝色调", "category": "style", "aliases": ["blue_theme"]}).json()["id"]
    client.patch("/api/settings", json={"tagger_backend": "vision", "vision_provider_id": mock_ai["id"]})
    res = client.post(f"/api/ai/tagger/assets/{aid}").json()
    by = {s["name"]: s for s in res["suggestions"]}
    assert by["portrait"]["tag"]["id"] == stand and by["blue theme"]["tag"]["id"] == blue and by["placeholder (mock)"]["tag"] is None
    job = wait_job(client, client.post("/api/ai/tagger/run", json={"min_score": 0.6}).json()["id"])
    assert job["result"] == {"assets": 1, "applied": 2}
    asset = client.get(f"/api/assets/{aid}").json()
    assert {t["id"] for t in asset["tags"]} == {stand, blue} and asset["meta"]["auto_tags"]["backend"] == "vision"
    # only_untagged：已有标签的不再处理
    assert wait_job(client, client.post("/api/ai/tagger/run", json={}).json()["id"])["result"]["assets"] == 0


def test_tagger_webui_backend(client, monkeypatch):
    from front_api.ai import tagger
    from front_api.config import get_settings
    from front_api.mock_sd import create_mock_app as mock_sd_app

    monkeypatch.setenv("FRONT_SD_WEBUI_URL", "http://mock-webui")
    get_settings.cache_clear()
    monkeypatch.setattr(tagger, "client_factory", lambda url, timeout: TestClient(mock_sd_app(), base_url=url))
    try:
        scenery = client.post("/api/tags", json={"name": "场景", "category": "type", "aliases": ["scenery"]}).json()["id"]
        aid = _upload(client, size=(120, 60))
        client.patch("/api/settings", json={"tagger_backend": "webui", "tagger_threshold": 0.5})
        res = client.post(f"/api/ai/tagger/assets/{aid}").json()
        names = [s["name"] for s in res["suggestions"]]
        assert names[0] == "placeholder" and "scenery" in names and "night" not in names  # 0.47 < 阈值 0.5
        assert next(s for s in res["suggestions"] if s["name"] == "scenery")["tag"]["id"] == scenery
    finally:
        get_settings.cache_clear()


# ---------- 迁移 ----------
def test_v05_migration_links_linear_chats(tmp_path):
    from sqlalchemy import create_engine, text

    from front_api.migrate import upgrade

    eng = create_engine(f"sqlite:///{tmp_path / 'old.db'}")
    with eng.begin() as c:
        c.execute(text("CREATE TABLE lorebooks (id INTEGER PRIMARY KEY)"))
        c.execute(text("CREATE TABLE character_cards (id INTEGER PRIMARY KEY, name TEXT)"))
        c.execute(text("CREATE TABLE chat_sessions (id INTEGER PRIMARY KEY, card_id INTEGER, title TEXT, user_name TEXT)"))
        c.execute(text("CREATE TABLE chat_messages (id INTEGER PRIMARY KEY, session_id INTEGER, role TEXT, content TEXT, created_at TEXT)"))
        c.execute(text("INSERT INTO chat_sessions VALUES (1, 1, 't', 'u'), (2, 1, 't2', 'u')"))
        c.execute(text("INSERT INTO chat_messages VALUES (1,1,'assistant','a',''),(2,2,'user','x',''),(3,1,'user','b',''),(4,1,'assistant','c','')"))
    added = upgrade(eng)
    assert "chat_messages.parent_id" in added and "character_cards.lorebook_id" in added
    with eng.connect() as c:
        assert c.execute(text("SELECT id, parent_id FROM chat_messages ORDER BY id")).fetchall() == [(1, None), (2, None), (3, 1), (4, 3)]
        assert c.execute(text("SELECT id, head_id FROM chat_sessions ORDER BY id")).fetchall() == [(1, 4), (2, 2)]
