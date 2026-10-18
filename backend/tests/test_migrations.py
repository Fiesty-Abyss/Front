"""Generated pre-v0.5 chat schema; this is not a production database fixture."""

from sqlalchemy import create_engine, text

from front_api.migrate import upgrade


def test_legacy_linear_chat_upgrade_preserves_content_and_is_idempotent(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'legacy.db'}")
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE chat_sessions (id INTEGER PRIMARY KEY, title TEXT)"))
        conn.execute(text("CREATE TABLE chat_messages (id INTEGER PRIMARY KEY, session_id INTEGER, content TEXT)"))
        conn.execute(text("INSERT INTO chat_sessions VALUES (1, 'legacy'), (2, 'other')"))
        conn.execute(text("INSERT INTO chat_messages VALUES (10, 1, 'first'), (11, 1, 'second'), (20, 2, 'separate')"))
    assert set(upgrade(engine)) == {"chat_sessions.head_id", "chat_sessions.lorebook_ids", "chat_messages.parent_id", "chat_messages.meta"}
    with engine.connect() as conn:
        assert conn.execute(text("SELECT id, parent_id, content FROM chat_messages ORDER BY id")).fetchall() == [
            (10, None, "first"), (11, 10, "second"), (20, None, "separate")]
        assert conn.execute(text("SELECT head_id FROM chat_sessions ORDER BY id")).scalars().all() == [11, 20]
    assert upgrade(engine) == []
    engine.dispose()
