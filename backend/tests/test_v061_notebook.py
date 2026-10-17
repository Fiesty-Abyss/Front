import io
import shutil
import zipfile

import pytest
from PIL import Image

import samples as S


def up(client, name, data, **form):
    r = client.post("/api/assets/upload", files={"file": (name, data)}, data=form)
    assert r.status_code == 201, r.text
    return r.json()


def test_model_files(client):
    a = up(client, "lighthouse.glb", S.glb(*S.gltf_lighthouse()), kind="drawing")
    f = a["meta"]["file"]
    assert a["kind"] == "model3d" and f["format"] == "glTF 二进制" and f["triangles"] == 288 and f["materials"] == 6
    assert a["width"] is None  # 不是图片，不能被当成图片显示

    v = up(client, "keeper.vrm", S.glb(*S.gltf_lighthouse("1.0", S.png(size=(96, 96)))))
    vm = v["meta"]["file"]["vrm_meta"]
    assert v["title"].startswith("【示例】灯塔守望者") and vm["vrm"] == "1.0" and vm["allow_redistribution"] is False
    assert vm["commercial_usage"] == "personalNonProfit" and v["meta"]["file"]["thumb"] is True
    assert client.get(f"/api/assets/{v['id']}/thumb").status_code == 200

    p = up(client, "lantern.zip", S.pmx_zip())
    pf = p["meta"]["file"]
    assert p["kind"] == "model3d" and pf["bundle"] and pf["main"] == "灯笼/【示例】灯笼.pmx"
    assert pf["model_name"] == "【示例】灯笼" and pf["triangles"] == 8 and pf["bones"] == 1 and pf["missing"] == []
    r = client.get(f"/api/assets/{p['id']}/entry/灯笼/tex/lantern.png")
    assert r.status_code == 200 and r.headers["content-type"] == "image/png"
    assert client.get(f"/api/assets/{p['id']}/entry/灯笼/TEX/Lantern.PNG").status_code == 200  # 大小写不敏感
    assert client.get(f"/api/assets/{p['id']}/entry/..%2F..%2Fetc%2Fpasswd").status_code == 404
    assert client.get(f"/api/assets/{a['id']}/entry/x").status_code == 404  # 不是压缩包

    o = up(client, "lighthouse.obj", S.obj_lighthouse())
    assert o["meta"]["file"]["faces"] == 192 and "mtl" in o["meta"]["file"]["note"]
    fbx = up(client, "x.fbx", b"Kaydara FBX Binary  \x00\x1a\x00" + (7400).to_bytes(4, "little") + b"\0" * 40)
    assert fbx["meta"]["file"]["fbx_version"] == "7.4"
    bad = up(client, "broken.glb", b"not a model at all")
    assert bad["kind"] == "model3d" and "error" in bad["meta"]["file"]  # 坏文件也能入库，只是没有详细信息


def test_custom_thumb(client):
    a = up(client, "lighthouse.glb", S.glb(*S.gltf_lighthouse()))
    assert client.get(f"/api/assets/{a['id']}/thumb").status_code == 404
    shot = S.png((20, 30, 60), (400, 300))
    r = client.put(f"/api/assets/{a['id']}/thumb", files={"file": ("snap.png", shot)})
    assert r.status_code == 200 and r.json()["meta"]["file"]["custom_thumb"]
    assert client.get(f"/api/assets/{a['id']}/thumb").status_code == 200
    assert client.put(f"/api/assets/{a['id']}/thumb", files={"file": ("x.png", b"nope")}).status_code == 422
    # 重新识别不会覆盖手动设置的封面
    assert client.post(f"/api/assets/{a['id']}/reanalyze").json()["meta"]["file"]["custom_thumb"]


def test_live2d_bundle(client):
    a = up(client, "sample_live2d.zip", S.live2d_zip(version=5))
    f = a["meta"]["file"]
    assert a["kind"] == "live2d" and f["cubism"] == "Cubism 5.0（moc3 v5）"
    assert f["motions"] == {"Idle": 2, "TapBody": 1} and f["expressions"] == ["微笑", "惊讶"]
    assert f["textures"][0] == {"path": "sample_live2d/sample.2048/texture_00.png", "size": "256×256"}
    assert f["physics"] and f["groups"] == {"EyeBlink": 2, "LipSync": 1} and f["missing"] == [] and f["thumb"]
    single = up(client, "x.moc3", b"MOC3\x03" + b"\0" * 20)
    assert single["kind"] == "live2d" and single["meta"]["file"]["cubism"].startswith("Cubism 4.0")


def test_documents_and_pdf(client):
    d = up(client, "plan.docx", S.docx("【示例】雾港设定集", [("Heading1", "第一章 灯塔"), ("", "灯塔守望者的女儿林汐。")]))
    assert d["kind"] == "document" and d["title"] == "【示例】雾港设定集" and d["meta"]["file"]["preview"][0] == {"type": "h1", "text": "第一章 灯塔"}
    assert d["meta"]["file"]["thumb"] and "林汐" in d["content"]
    x = up(client, "cast.xlsx", S.xlsx("角色表", [["名字", "年龄"], ["林汐", 17]]))
    assert x["meta"]["file"]["preview"] == {"sheets": ["角色表", "备注"], "rows": [["名字", "年龄"], ["林汐", "17"]]}
    p = up(client, "deck.pptx", S.pptx("演示", [["封面", "副标题"], ["第二页", "要点"]]))
    assert p["meta"]["file"]["slides"] == 2 and p["meta"]["file"]["preview"][1] == {"title": "第二页", "lines": ["要点"]}
    old = up(client, "old.doc", b"\xd0\xcf\x11\xe0" + b"\0" * 100)
    assert old["kind"] == "document" and "旧版" in old["meta"]["file"]["note"]

    pdf = up(client, "notes.pdf", S.pdf("Lighthouse Notes", ["Fog harbor page one", "Page two"]))
    f = pdf["meta"]["file"]
    assert pdf["kind"] == "pdf" and f["pages"] == 2 and f["author"] == "Front sample generator" and f["created"] == "2026-10-17"
    assert "Fog harbor" in pdf["content"]
    r = client.get(f"/api/assets/{pdf['id']}/pdf/2", params={"width": 300})
    assert r.status_code == 200 and Image.open(io.BytesIO(r.content)).width == 300
    assert client.get(f"/api/assets/{pdf['id']}/pdf/3").status_code == 404
    inline = client.get(f"/api/assets/{pdf['id']}/file", params={"inline": 1})
    assert inline.headers["content-disposition"].startswith("inline")
    # PDF 里的文字可以被全文检索搜到
    hits = client.get("/api/search", params={"q": "Fog harbor"}).json()
    assert any(h["entity"] == "asset" and h["id"] == pdf["id"] for h in hits), hits


def test_audio_archive_code(client):
    w = up(client, "melody.wav", S.wav(1.5))
    assert w["kind"] == "audio" and w["meta"]["file"]["duration"] == 1.5 and w["meta"]["file"]["samplerate"] == 22050
    r = client.get(f"/api/assets/{w['id']}/file", headers={"Range": "bytes=0-99"})
    assert r.status_code == 206 and len(r.content) == 100  # 播放器可以拖动进度

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("cg/ev01.png", S.png((90, 120, 200), (64, 48)))
        z.writestr("readme.txt", "示例")
        z.writestr("__MACOSX/._ev01.png", "junk")
    a = up(client, "pack.zip", buf.getvalue())
    f = a["meta"]["file"]
    assert a["kind"] == "archive" and f["count"] == 2 and f["by_ext"] == {"png": 1, "txt": 1} and f["thumb"]
    assert client.get(f"/api/assets/{a['id']}/entry/readme.txt").content.decode() == "示例"
    sz = up(client, "x.7z", b"7z\xbc\xaf\x27\x1c" + b"\0" * 30)
    assert sz["meta"]["file"]["format"] == "7z"

    c = up(client, "script.rpy", 'label start:\n    l "灯塔的台阶一共一百零八级。"\n'.encode())
    assert c["kind"] == "code" and c["meta"]["file"]["label"] == "Ren'Py 脚本" and "一百零八级" in c["content"]


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="需要 ffmpeg")
def test_video_probe(client, tmp_path):
    import subprocess
    out = tmp_path / "clip.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=c=0x9a6ad0:s=160x90:d=1", "-pix_fmt", "yuv420p", str(out)], check=True)
    v = up(client, "clip.mp4", out.read_bytes())
    f = v["meta"]["file"]
    assert v["kind"] == "video" and f["resolution"] == "160×90" and f["video_codec"] == "h264" and f["thumb"] and f["playable"]


def test_import_folder_bundles(client, tmp_path):
    root = tmp_path / "收藏"
    with zipfile.ZipFile(io.BytesIO(S.live2d_zip())) as z:
        z.extractall(root)
    (root / "灯笼").mkdir()
    (root / "灯笼" / "lantern.pmx").write_bytes(S.pmx_lantern())
    (root / "灯笼" / "tex").mkdir()
    (root / "灯笼" / "tex" / "lantern.png").write_bytes(S.png())
    (root / "melody.wav").write_bytes(S.wav(0.5))
    scan = client.post("/api/import/scan", json={"path": str(root)}).json()
    assert scan["total"] == 3 and sorted(scan["bundles"]) == ["sample_live2d/", "灯笼/"]
    r = client.post("/api/import/run", json={"path": str(root)}).json()
    assert r["created"] == 3 and not r["errors"]
    kinds = sorted(client.get(f"/api/assets/{i}").json()["kind"] for i in r["created_ids"])
    assert kinds == ["audio", "live2d", "model3d"]


def test_reanalyze_old_assets(client):
    a = up(client, "melody.wav", S.wav(0.5))
    client.patch(f"/api/assets/{a['id']}", json={"kind": "other"})
    assert client.post("/api/assets/reanalyze").json()["updated"] == 0  # 已有识别结果的不重复处理
    assert client.post(f"/api/assets/{a['id']}/reanalyze").json()["kind"] == "audio"


def test_notes(client):
    root = client.post("/api/notes", json={"title": "【示例】雾港创作笔记", "icon": "🗼", "content": "# 灯塔\n\n- [ ] 画台阶"}).json()
    child = client.post("/api/notes", json={"title": "灯塔节", "parent_id": root["id"], "content": f"见 [笔记](/notes/{root['id']})"}).json()
    img = up(client, "lighthouse.glb", S.glb(*S.gltf_lighthouse()))
    client.patch(f"/api/notes/{root['id']}", json={"content": f"# 灯塔\n\n[模型](/assets?open={img['id']})\n\n![图](/api/assets/{img['id']}/file)"})
    tree = client.get("/api/notes/tree").json()
    assert {(n["title"], n["parent_id"]) for n in tree} == {("【示例】雾港创作笔记", None), ("灯塔节", root["id"])}
    assert [n["title"] for n in client.get("/api/notes", params={"parent_id": "root"}).json()["items"]] == ["【示例】雾港创作笔记"]
    refs = client.get(f"/api/notes/{root['id']}/refs").json()
    assert [(a["id"], a["title"], a["kind"]) for a in refs["assets"]] == [(img["id"], img["title"], "model3d")]
    assert "file" in refs["assets"][0]["meta"]  # 带缩略图标记，前端据此显示封面
    assert refs["backlinks"] == [{"id": child["id"], "title": "灯塔节", "icon": None}]
    assert client.post(f"/api/notes/{root['id']}/move", json={"parent_id": child["id"]}).status_code == 422  # 防止成环
    assert client.post(f"/api/notes/{child['id']}/move", json={"parent_id": None}).json()["parent_id"] is None
    hits = client.get("/api/search", params={"q": "雾港创作"}).json()
    assert any(h["entity"] == "note" and h["id"] == root["id"] for h in hits), hits
    client.delete(f"/api/notes/{root['id']}")
    assert client.get(f"/api/notes/{child['id']}").status_code == 200  # 子页面已移出，不受影响
