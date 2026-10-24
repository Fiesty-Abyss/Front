"""Recoverable SQLite snapshots before additive schema changes. Never resets data."""
import json
import sqlite3
import uuid
from datetime import datetime, timezone
from .db import Base
from .migrate import COLUMNS


def before_schema_change(settings):
    if not settings.db_path.is_file():
        return
    with sqlite3.connect(settings.db_path) as source:
        tables = {r[0] for r in source.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        missing = sorted(set(Base.metadata.tables) - tables)
        for table, column, _ in COLUMNS:
            if table in tables and column not in {r[1] for r in source.execute(f'PRAGMA table_info("{table}")')}:
                missing.append(f'{table}.{column}')
        if not missing:
            return
        folder = settings.data_dir / 'backups' / ('pre-schema-' + uuid.uuid4().hex)
        folder.mkdir(parents=True)
        with sqlite3.connect(folder / 'front.db') as dest:
            source.backup(dest)
            if dest.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                raise RuntimeError('升级前数据库备份校验失败；停止迁移，原库保留')
        (folder / 'manifest.json').write_text(json.dumps({
            'created_at':datetime.now(timezone.utc).isoformat(), 'reason':missing,
            'scope':'front.db only; managed media and external originals are not copied',
            'restore':'Stop Front; preserve current database and WAL; restore snapshot with SQLite backup API to a separate directory first.'
        },ensure_ascii=False,indent=2),encoding='utf-8')
