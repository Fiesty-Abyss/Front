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
    return added
