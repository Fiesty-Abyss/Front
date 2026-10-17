"""v0.6.2 图表画布：增删改查、校验、导入导出、复制、预览图、检索与统计。"""

import io

from PIL import Image


def flow(n=3):
    nodes = [{"id": f"n{i}", "type": "shape", "position": {"x": i * 200, "y": 0}, "data": {"label": f"【示例】步骤{i}", "shape": "rect"}} for i in range(n)]
    edges = [{"id": f"e{i}", "source": f"n{i}", "target": f"n{i + 1}", "label": "然后" if i == 0 else None} for i in range(n - 1)]
    return {"nodes": nodes, "edges": edges, "viewport": {"x": 0, "y": 0, "zoom": 1}}


def png(color=(120, 90, 200)):
    buf = io.BytesIO()
    Image.new("RGB", (640, 360), color).save(buf, "PNG")
    return buf.getvalue()


def test_crud_and_list_trim(client):
    d = client.post("/api/diagrams", json={"title": "【示例】灯塔节剧情流程", "kind": "flowchart", "data": flow()}).json()
    assert d["nodes"] == 3 and d["edges"] == 2 and d["data"]["viewport"]["zoom"] == 1
    listed = client.get("/api/diagrams").json()["items"]
    assert listed[0]["id"] == d["id"] and listed[0]["data"] is None and listed[0]["nodes"] == 3  # 列表不带画布数据
    full = client.get(f"/api/diagrams/{d['id']}").json()
    assert [n["id"] for n in full["data"]["nodes"]] == ["n0", "n1", "n2"]
    upd = client.patch(f"/api/diagrams/{d['id']}", json={"title": "改名", "data": flow(5)}).json()
    assert upd["title"] == "改名" and upd["nodes"] == 5
    assert client.get("/api/diagrams?kind=workflow").json()["total"] == 0
    assert client.get("/api/diagrams?kind=flowchart").json()["total"] == 1
    assert client.delete(f"/api/diagrams/{d['id']}").status_code == 204
    assert client.get(f"/api/diagrams/{d['id']}").status_code == 404


def test_validation(client):
    bad_edge = flow()
    bad_edge["edges"].append({"id": "x", "source": "n0", "target": "missing"})
    assert client.post("/api/diagrams", json={"title": "x", "data": bad_edge}).status_code == 422
    dup = flow()
    dup["nodes"].append(dict(dup["nodes"][0]))
    assert client.post("/api/diagrams", json={"title": "x", "data": dup}).status_code == 422
    js = flow()
    js["nodes"][0]["data"]["link"] = "javascript:alert(1)"
    assert client.post("/api/diagrams", json={"title": "x", "data": js}).status_code == 422
    ok = flow()
    ok["nodes"][0]["data"]["link"] = "/notes/3"
    ok["nodes"][1]["data"]["link"] = "https://example.com/"
    assert client.post("/api/diagrams", json={"title": "x", "data": ok}).status_code == 201
    assert client.post("/api/diagrams", json={"title": "x", "kind": "nope"}).status_code == 422


def test_export_import_duplicate(client):
    d = client.post("/api/diagrams", json={"title": "【示例】出图工作流", "kind": "workflow", "description": "演示", "data": flow(4)}).json()
    r = client.get(f"/api/diagrams/{d['id']}/export")
    assert r.status_code == 200 and "attachment" in r.headers["content-disposition"]
    doc = r.json()
    assert doc["format"] == "front-diagram" and doc["kind"] == "workflow" and len(doc["data"]["nodes"]) == 4
    back = client.post("/api/diagrams/import", json=doc).json()
    assert back["title"] == "【示例】出图工作流" and back["kind"] == "workflow" and back["nodes"] == 4
    bare = client.post("/api/diagrams/import", json=flow(2)).json()  # Vue Flow toObject() 的结果
    assert bare["nodes"] == 2 and bare["title"] == "导入的图表"
    assert client.post("/api/diagrams/import", json={"format": "other", "data": flow()}).status_code == 422
    assert client.post("/api/diagrams/import", json={"title": "x"}).status_code == 422
    client.put(f"/api/diagrams/{d['id']}/preview", files={"file": ("p.png", png())})
    cp = client.post(f"/api/diagrams/{d['id']}/duplicate").json()
    assert cp["title"].endswith("（副本）") and cp["nodes"] == 4 and cp["id"] != d["id"]
    assert client.get(f"/api/diagrams/{cp['id']}/preview").status_code == 200  # 预览图一起复制


def test_preview(client, data_dir):
    d = client.post("/api/diagrams", json={"title": "预览", "data": flow()}).json()
    assert client.get(f"/api/diagrams/{d['id']}/preview").status_code == 404
    assert client.put(f"/api/diagrams/{d['id']}/preview", files={"file": ("p.txt", b"not an image")}).status_code == 422
    assert client.put(f"/api/diagrams/{d['id']}/preview", files={"file": ("p.png", png())}).status_code == 204
    r = client.get(f"/api/diagrams/{d['id']}/preview")
    assert r.status_code == 200 and r.headers["content-type"] == "image/webp"
    path = data_dir / "thumbs" / f"diagram-{d['id']}.webp"
    assert path.is_file()
    client.delete(f"/api/diagrams/{d['id']}")
    assert not path.exists()  # 删除图表时一起删掉预览图


def test_search_and_stats(client):
    data = flow()
    data["nodes"][1]["data"]["text"] = "林汐在第一百零八级台阶上点亮灯笼"
    data["nodes"].append({"id": "w", "type": "workflow", "position": {"x": 0, "y": 200},
                          "data": {"label": "采样器", "fields": [{"label": "步数", "value": 28}]}})
    data["edges"][0]["label"] = "雾散之后"
    client.post("/api/diagrams", json={"title": "【示例】灯塔节剧情流程", "data": data})
    for q in ("一百零八级台阶", "雾散之后", "采样器", "灯塔节剧情"):
        hits = client.get("/api/search", params={"q": q}).json()
        assert any(h["entity"] == "diagram" for h in hits), q
    stats = client.get("/api/stats").json()
    assert stats["diagrams"] == 1
    r = client.get("/api/stats/activity", params={"weeks": 1}).json()
    today = next(d for d in r["days"] if d["date"] == r["today"])
    assert today["by"].get("diagrams") == 1


def test_templates_are_valid(client):
    ts = client.get("/api/diagrams/templates").json()
    assert [t["id"] for t in ts] == ["blank", "flow", "workflow", "mind"]
    for t in ts:
        r = client.post("/api/diagrams", json={"title": t["title"], "kind": t["kind"], "data": t["data"]})
        assert r.status_code == 201, (t["id"], r.text)
    wf = next(t for t in ts if t["id"] == "workflow")["data"]
    ports = {(n["id"], f"out-{o['id']}") for n in wf["nodes"] for o in n["data"]["outputs"]} | {(n["id"], f"in-{i['id']}") for n in wf["nodes"] for i in n["data"]["inputs"]}
    for e in wf["edges"]:  # 每条连线都接在真实存在的端口上
        assert (e["source"], e["sourceHandle"]) in ports and (e["target"], e["targetHandle"]) in ports, e
