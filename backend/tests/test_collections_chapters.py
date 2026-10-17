import sqlite3

from front_api.chapters import count_words, split_chapters
from front_api.config import get_settings
from front_api.main import create_app


def _assets(client, n):
    return [client.post("/api/assets", json={"title": f"a{i}"}).json()["id"] for i in range(n)]


def test_collection_order_and_cover(client):
    a, b, c, d = _assets(client, 4)
    col = client.post("/api/collections", json={"name": "C", "asset_ids": [c, a, b]}).json()
    assert [x["id"] for x in col["assets"]] == [c, a, b] and col["effective_cover_id"] == c
    col = client.put(f"/api/collections/{col['id']}/order", json={"asset_ids": [b, c]}).json()
    assert [x["id"] for x in col["assets"]] == [b, c, a]
    assert client.put(f"/api/collections/{col['id']}/order", json={"asset_ids": [d]}).status_code == 422
    col = client.post(f"/api/collections/{col['id']}/items", json={"asset_ids": [a, d]}).json()
    assert [x["id"] for x in col["assets"]] == [b, c, a, d]
    col = client.patch(f"/api/collections/{col['id']}", json={"cover_asset_id": d}).json()
    assert col["effective_cover_id"] == d
    col = client.delete(f"/api/collections/{col['id']}/items/{d}").json()
    assert col["cover_asset_id"] is None and col["effective_cover_id"] == b
    assert client.patch(f"/api/collections/{col['id']}", json={"cover_asset_id": 999}).status_code == 422


def test_collections_sorted_by_position(client):
    x = client.post("/api/collections", json={"name": "X"}).json()["id"]
    y = client.post("/api/collections", json={"name": "Y"}).json()["id"]
    client.put("/api/collections/order", json={"collection_ids": [y, x]})
    assert [c["name"] for c in client.get("/api/collections").json()["items"]] == ["Y", "X"]


def test_migration_adds_new_columns(tmp_path, monkeypatch):
    data = tmp_path / "old"
    data.mkdir()
    con = sqlite3.connect(data / "front.db")
    con.executescript(
        "CREATE TABLE assets (id INTEGER PRIMARY KEY, title VARCHAR(300));"
        "CREATE TABLE collections (id INTEGER PRIMARY KEY, name VARCHAR(200), description TEXT, work_id INTEGER, created_at DATETIME, updated_at DATETIME);"
        "CREATE TABLE collection_assets (collection_id INTEGER, asset_id INTEGER, PRIMARY KEY (collection_id, asset_id));"
        "INSERT INTO collections (id, name) VALUES (1, '旧收藏');"
    )
    con.close()
    monkeypatch.setenv("FRONT_DATA_DIR", str(data))
    get_settings.cache_clear()
    create_app()
    cols = {r[1] for r in sqlite3.connect(data / "front.db").execute("PRAGMA table_info(collections)")}
    assert {"cover_asset_id", "position"} <= cols
    get_settings.cache_clear()


NOVEL = """这是一段前言。

第一章 起风了
雾从海面升起。

第二章　灯塔
她爬上台阶。
Chapter 3 The Map
He opened the map.
尾声
完。
"""


def test_split_chapters():
    toc = split_chapters(NOVEL)
    assert [c["title"] for c in toc] == ["前言", "第一章 起风了", "第二章　灯塔", "Chapter 3 The Map", "尾声"]
    assert toc[1]["words"] == count_words("雾从海面升起。")
    assert split_chapters("没有任何标题的短文")[0]["title"] == "正文"


def test_count_words():
    assert count_words("你好 world, it's fine") == 2 + 3


def test_reader_api(client):
    nid = client.post("/api/assets", json={"title": "示例小说", "kind": "novel", "content": NOVEL}).json()["id"]
    toc = client.get(f"/api/assets/{nid}/chapters").json()
    assert len(toc["chapters"]) == 5 and toc["words"] > 0
    ch = client.get(f"/api/assets/{nid}/chapters/1").json()
    assert ch["title"] == "第一章 起风了" and ch["content"] == "雾从海面升起。"
    assert ch["prev"] == 0 and ch["next"] == 2 and ch["total"] == 5
    assert client.get(f"/api/assets/{nid}/chapters/9").status_code == 404
    md = client.post("/api/assets", json={"title": "md", "kind": "novel", "content": "# 一\n甲\n## 二\n乙"}).json()["id"]
    assert [c["title"] for c in client.get(f"/api/assets/{md}/chapters").json()["chapters"]] == ["一", "二"]
    empty = client.post("/api/assets", json={"title": "e"}).json()["id"]
    assert client.get(f"/api/assets/{empty}/chapters").status_code == 422
