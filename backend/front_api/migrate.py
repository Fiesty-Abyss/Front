"""极简的就地迁移：create_all 只建新表，不会给旧表加列。
这里在启动时补齐新版本增加的列，老用户升级后数据库无需手动处理。"""

from __future__ import annotations

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

# (表, 列, 列定义)
COLUMNS: list[tuple[str, str, str]] = [
    # v0.2.0
    ("collection_assets", "position", "INTEGER NOT NULL DEFAULT 0"),
    ("collections", "cover_asset_id", "INTEGER REFERENCES assets(id) ON DELETE SET NULL"),
    ("collections", "position", "INTEGER NOT NULL DEFAULT 0"),
    # v0.3.0
    ("tags", "aliases", "JSON NOT NULL DEFAULT '[]'"),
    ("tags", "parent_id", "INTEGER REFERENCES tags(id) ON DELETE SET NULL"),
    # v0.4.0
    ("sd_models", "hashes", "JSON NOT NULL DEFAULT '{}'"),
    ("sd_models", "civitai", "JSON NOT NULL DEFAULT '{}'"),
    ("generations", "batch", "VARCHAR(40)"),
    ("generations", "xy", "JSON NOT NULL DEFAULT '{}'"),
    # v0.5.0
    ("chat_sessions", "head_id", "INTEGER"),
    ("chat_sessions", "lorebook_ids", "JSON NOT NULL DEFAULT '[]'"),
    ("chat_messages", "parent_id", "INTEGER"),
    ("chat_messages", "meta", "JSON NOT NULL DEFAULT '{}'"),
    ("character_cards", "lorebook_id", "INTEGER REFERENCES lorebooks(id) ON DELETE SET NULL"),
]


def upgrade(engine: Engine) -> list[str]:
    insp = inspect(engine)
    added: list[str] = []
    with engine.begin() as conn:
        for table, column, ddl in COLUMNS:
            if not insp.has_table(table):
                continue
            existing = {c["name"] for c in insp.get_columns(table)}
            if column not in existing:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}"))
                added.append(f"{table}.{column}")
        if "chat_messages.parent_id" in added:
            _link_linear_chats(conn)
        # A rebuildable index only: no row, history or source-file changes.
        # Measured 100k-record world queries otherwise scan the date index.
        if insp.has_table("assets") and {"world_id", "work_date", "id"} <= {
            c["name"] for c in inspect(conn).get_columns("assets")
        }:
            if "ix_assets_world_date_id" not in {i["name"] for i in inspect(conn).get_indexes("assets")}:
                conn.execute(text("CREATE INDEX ix_assets_world_date_id ON assets(world_id, work_date, id)"))
                added.append("index:ix_assets_world_date_id")
    return added


def _link_linear_chats(conn) -> None:
    """v0.5 之前的对话是线性的：把每条消息的上一条设为 parent，最后一条设为 head。"""
    rows = conn.execute(text("SELECT id, session_id FROM chat_messages ORDER BY session_id, id")).fetchall()
    last: dict[int, int] = {}
    for mid, sid in rows:
        if sid in last:
            conn.execute(text("UPDATE chat_messages SET parent_id=:p WHERE id=:i"), {"p": last[sid], "i": mid})
        last[sid] = mid
    for sid, mid in last.items():
        conn.execute(text("UPDATE chat_sessions SET head_id=:h WHERE id=:s"), {"h": mid, "s": sid})
