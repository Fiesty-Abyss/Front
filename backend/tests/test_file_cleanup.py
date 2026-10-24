from front_api import models as m
from front_api.db import new_session


def uploaded(client, data_dir):
    response = client.post("/api/assets/upload", files={"file": ("safe.txt", b"rollback-safe-fixture")})
    assert response.status_code == 201
    asset = response.json()
    return asset["id"], data_dir / asset["file_path"]


def test_failed_delete_preserves_file_and_record(client, data_dir):
    aid, path = uploaded(client, data_dir)
    with new_session() as session:
        session.delete(session.get(m.Asset, aid))
        session.flush()
        assert path.exists()
        session.rollback()
        assert session.get(m.Asset, aid) is not None
        session.commit()
    assert path.read_bytes() == b"rollback-safe-fixture"


def test_committed_delete_cleans_managed_file(client, data_dir):
    aid, path = uploaded(client, data_dir)
    assert client.delete(f"/api/assets/{aid}").status_code == 204
    assert not path.exists()


def test_detach_file_uses_same_post_commit_cleanup(client, data_dir):
    aid, path = uploaded(client, data_dir)
    assert client.delete(f"/api/assets/{aid}/file").status_code == 204
    assert not path.exists()
    assert client.get(f"/api/assets/{aid}").json()["file_path"] is None


def test_savepoint_commit_does_not_delete_before_outer_commit(client, data_dir):
    aid, path = uploaded(client, data_dir)
    with new_session() as session:
        with session.begin_nested():
            session.delete(session.get(m.Asset, aid))
            session.flush()
        assert path.exists()
        session.rollback()
    assert path.exists()


def test_savepoint_rollback_does_not_schedule_a_later_delete(client, data_dir):
    aid, path = uploaded(client, data_dir)
    with new_session() as session:
        nested = session.begin_nested()
        session.delete(session.get(m.Asset, aid))
        session.flush()
        nested.rollback()
        session.commit()
    assert path.exists()


def test_closed_session_cannot_carry_deletes_into_another_transaction(client, data_dir):
    aid, path = uploaded(client, data_dir)
    session = new_session()
    try:
        session.delete(session.get(m.Asset, aid))
        session.flush()
        session.close()
        assert session.get(m.Asset, aid) is not None
        session.commit()
        assert path.exists()
    finally:
        session.close()


def test_cleanup_never_removes_files_outside_data_directory(client, data_dir, tmp_path):
    aid, _ = uploaded(client, data_dir)
    outside = tmp_path / "original.txt"
    outside.write_text("preserve original", encoding="utf-8")
    with new_session() as session:
        session.get(m.Asset, aid).file_path = "../original.txt"
        session.commit()
    assert client.delete(f"/api/assets/{aid}").status_code == 204
    assert outside.read_text(encoding="utf-8") == "preserve original"
