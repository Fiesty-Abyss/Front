import io
import posixpath
import re
from zipfile import ZipFile


def create(client, resource, **data):
    result = client.post(f"/api/{resource}", json=data)
    assert result.status_code == 201, result.text
    return result.json()["id"]


def unpack(response):
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"
    assert "attachment" in response.headers["content-disposition"]
    assert response.headers["cache-control"] == "no-store"
    with ZipFile(io.BytesIO(response.content)) as archive:
        assert archive.testzip() is None
        return {name: archive.read(name).decode("utf-8") for name in archive.namelist()}


def test_empty_export_and_invalid_scope(client):
    docs = unpack(client.get("/api/exports/encyclopedia"))
    assert list(docs) == ["README.md"]
    assert "世界观 0 · 角色 0 · 条目 0" in docs["README.md"]
    assert client.get("/api/exports/encyclopedia?world_id=999").status_code == 404
    assert client.get("/api/exports/encyclopedia?world_id=no").status_code == 422


def test_export_preserves_text_metadata_and_relative_links(client):
    tag = create(client, "tags", name="原创", category="custom")
    world = create(client, "worlds", name="雾港", content="## 原始正文\n\n[[灯塔]]", tag_ids=[tag])
    work = create(client, "works", title="灯塔纪事")
    char = create(client, "characters", name="林汐", alias="小汐", gender="female", world_id=world,
                  work_id=work, summary="守望者", profile="**原样保留**\n\n- 设定", tag_ids=[tag])
    other = create(client, "characters", name="另一人", world_id=world)
    create(client, "relations", source_id=other, target_id=char, kind="师徒", description="共同守望",
           bidirectional=False, ai_suggested=True, confirmed=False)
    place = create(client, "world-entries", world_id=world, kind="location", name="灯塔")
    event = create(client, "world-entries", world_id=world, kind="event", name="初见", parent_id=place,
                   date_label="灯塔历 302 年", sort_key=0, content="事件正文",
                   characters=[{"character_id": char, "role": "目击者"}])
    docs = unpack(client.get("/api/exports/encyclopedia"))
    assert "## 原始正文\n\n[[灯塔]]" in docs[f"worlds/{world}.md"]
    profile = docs[f"characters/{char}.md"]
    for value in ["小汐", "性别：女", "原创", "守望者", "**原样保留**\n\n- 设定", "灯塔纪事", "AI 待确认", "另一人", "→", "共同守望", "目击者"]:
        assert value in profile
    event_doc = docs[f"entries/{event}.md"]
    assert f"[灯塔]({place}.md)" in event_doc
    assert "时间排序值：0" in event_doc and "灯塔历 302 年" in event_doc
    assert "事件正文" in event_doc
    for path, body in docs.items():
        for target in re.findall(r"\]\(([^)]+\.md)\)", body):
            assert posixpath.normpath(posixpath.join(posixpath.dirname(path), target)) in docs
    assert client.get(f"/api/characters/{char}").json()["profile"] == "**原样保留**\n\n- 设定"


def test_scoped_export_keeps_external_names_without_leaking_profiles(client):
    world = create(client, "worlds", name="范围内")
    outside = create(client, "worlds", name="范围外", content="不能导出的正文")
    char = create(client, "characters", name="甲", world_id=world)
    other = create(client, "characters", name="乙", world_id=outside, profile="外部角色私有设定")
    create(client, "relations", source_id=char, target_id=other, kind="朋友")
    entry = create(client, "world-entries", world_id=world, name="会馆",
                   characters=[{"character_id": other, "role": "访客"}])
    create(client, "world-entries", world_id=outside, name="隐藏地点")
    docs = unpack(client.get(f"/api/exports/encyclopedia?world_id={world}"))
    assert set(docs) == {"README.md", f"worlds/{world}.md", f"characters/{char}.md", f"entries/{entry}.md"}
    assert "乙" in docs[f"characters/{char}.md"] and "已确认" in docs[f"characters/{char}.md"]
    assert "乙 · 访客" in docs[f"entries/{entry}.md"]
    combined = "\n".join(docs.values())
    for value in ["不能导出的正文", "外部角色私有设定", "隐藏地点", f"../characters/{other}.md"]:
        assert value not in combined


def test_names_cannot_escape_archive_or_overwrite_duplicate_entries(client):
    first = create(client, "characters", name="../../CON\n[危险](x)")
    second = create(client, "characters", name="../../CON\n[危险](x)")
    docs = unpack(client.get("/api/exports/encyclopedia"))
    assert set(docs) == {"README.md", f"characters/{first}.md", f"characters/{second}.md"}
    assert r"\[危险\]\(x\)" in docs[f"characters/{first}.md"]
    assert "# ../../CON " in docs[f"characters/{first}.md"]
