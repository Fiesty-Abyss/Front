import os
from datetime import date

import pytest
from conftest import png_bytes

from front_api.cg import CGItem, group_cgs, split_variant


@pytest.mark.parametrize(
    "stem,expected",
    [
        ("ev01a", ("ev01", "a")),
        ("EV01_B", ("EV01", "b")),
        ("ev01_02", ("ev01", "02")),
        ("cg12-3", ("cg12", "3")),
        ("ev03_diff2", ("ev03", "2")),
        ("ev03差分4", ("ev03", "4")),
        ("cg_001", None),  # 前缀不含数字：是独立 CG，不是差分
        ("title", None),
    ],
)
def test_split_variant(stem, expected):
    assert split_variant(stem) == expected


def test_group_by_name_and_resolution():
    items = [CGItem(n, 1280, 720) for n in ["ev01a.png", "ev01b.png", "ev01c.png", "ev02.png", "ev10_01.png", "ev10_02.png"]]
    items.append(CGItem("ev02a.png", 1920, 1080))  # 名字像差分但分辨率不同
    groups = {g.key: [i.name for i in g.items] for g in group_cgs(items)}
    assert groups["ev01"] == ["ev01a.png", "ev01b.png", "ev01c.png"]
    assert groups["ev10"] == ["ev10_01.png", "ev10_02.png"]
    # 同名不同分辨率拆成两组，用分辨率区分
    assert groups["ev02@1280x720"] == ["ev02.png"] and groups["ev02@1920x1080"] == ["ev02a.png"]
    # 自然排序：ev01 < ev02 < ev10
    assert list(groups)[0] == "ev01" and list(groups)[-1] == "ev10"


def test_tail_digits_need_siblings():
    items = [CGItem(n, 800, 600) for n in ["ev0101.png", "ev0102.png", "ev0201.png", "bg5000.png"]]
    groups = {g.key: [i.name for i in g.items] for g in group_cgs(items)}
    assert groups["ev01"] == ["ev0101.png", "ev0102.png"]
    assert groups["ev0201"] == ["ev0201.png"]  # 没有兄弟，不拆
    assert groups["bg5000"] == ["bg5000.png"]


def _make_cg_folder(root):
    root.mkdir(parents=True)
    specs = [("ev01a.png", (10, 20, 30)), ("ev01b.png", (11, 20, 30)), ("ev02.png", (12, 20, 30)), ("ev03_01.png", (13, 20, 30)), ("ev03_02.png", (14, 20, 30))]
    for name, color in specs:
        (root / name).write_bytes(png_bytes(color=color, size=(160, 90)))
    (root / "readme.dat").write_bytes(b"x")  # 不支持的类型会被跳过
    return root


def test_scan_preview_does_not_write(client, tmp_path):
    folder = _make_cg_folder(tmp_path / "樱色回廊")
    r = client.post("/api/import/scan", json={"path": str(folder), "cg_mode": True}).json()
    assert r["total"] == 5 and r["unsupported"] == 1 and r["folder_name"] == "樱色回廊"
    assert [g["key"] for g in r["cg_groups"]] == ["ev01", "ev02", "ev03"]
    assert client.get("/api/assets").json()["total"] == 0


def test_cg_import_creates_work_and_gallery(client, tmp_path):
    folder = _make_cg_folder(tmp_path / "game")
    ts = 1_700_000_000
    os.utime(folder / "ev01a.png", (ts, ts))
    r = client.post("/api/import/run", json={"path": str(folder), "cg_mode": True, "new_work_title": "示例游戏"}).json()
    assert r["created"] == 5 and r["cg_groups"] == 3 and not r["errors"]
    work = client.get(f"/api/works/{r['work_id']}").json()
    assert work["title"] == "示例游戏" and work["kind"] == "galgame"
    gallery = client.get(f"/api/works/{r['work_id']}/cg").json()
    assert gallery["total"] == 5
    g1 = gallery["groups"][0]
    assert g1["key"] == "ev01" and [i["variant"] for i in g1["items"]] == ["a", "b"] and g1["size"] == "160x90"
    # 使用文件修改时间作为日期
    a = client.get(f"/api/assets/{g1['items'][0]['id']}").json()
    assert a["work_date"] == date.fromtimestamp(ts).isoformat()
    assert a["meta"]["import"]["relative_path"] == "ev01a.png"
    assert a["title"] == "示例游戏 ev01a"
    # 再导入一次：全部识别为重复
    again = client.post("/api/import/run", json={"path": str(folder), "cg_mode": True, "work_id": r["work_id"]}).json()
    assert again["created"] == 0 and len(again["duplicates"]) == 5


def test_regroup_after_browser_upload(client):
    w = client.post("/api/works", json={"title": "W", "kind": "galgame"}).json()["id"]
    for i, name in enumerate(["ev05b.png", "ev05a.png"]):
        client.post("/api/assets/upload", files={"file": (name, png_bytes(color=(i, 9, 9)), "image/png")}, data={"kind": "cg", "work_id": str(w)})
    assert client.post(f"/api/works/{w}/cg/regroup").json() == {"groups": 1, "items": 2}
    items = client.get(f"/api/works/{w}/cg").json()["groups"][0]["items"]
    assert [i["variant"] for i in items] == ["a", "b"]


def test_import_guards(client, tmp_path, data_dir):
    assert client.post("/api/import/scan", json={"path": str(tmp_path / "nope")}).status_code == 404
    assert client.post("/api/import/scan", json={"path": str(data_dir)}).status_code == 422
    folder = _make_cg_folder(tmp_path / "x")
    assert client.post("/api/import/run", json={"path": str(folder), "cg_mode": True}).status_code == 422


def test_plain_folder_import_with_novel(client, tmp_path):
    folder = tmp_path / "mix"
    (folder / "sub").mkdir(parents=True)
    (folder / "a.png").write_bytes(png_bytes())
    (folder / "sub" / "story.txt").write_text("第一章 开始\n内容", encoding="utf-8")
    t = client.post("/api/tags", json={"name": "导入", "category": "custom"}).json()["id"]
    flat = client.post("/api/import/scan", json={"path": str(folder), "recursive": False}).json()
    assert flat["total"] == 1
    r = client.post("/api/import/run", json={"path": str(folder), "tag_ids": [t]}).json()
    assert r["created"] == 2
    kinds = sorted(a["kind"] for a in client.get("/api/assets", params={"tag": t}).json()["items"])
    assert kinds == ["drawing", "novel"]
