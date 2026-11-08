"""Generated SQLite/fault injection only; no personal databases."""
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
from contextlib import closing

import pytest
from front_api import database_diagnostics as dd,backups


def hash_file(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def test_good_and_future_structure_are_not_corruption(client,data_dir):
    path=data_dir/'front.db'
    assert dd.inspect_database(path).code=='ok'
    with closing(sqlite3.connect(path)) as db,db:db.execute('CREATE TABLE private_future_table(id INTEGER)')
    before=hash_file(path)
    result=dd.inspect_database(path)
    assert result.code=='database_schema_incompatible' and result.metrics['integrity_ok']
    assert result.metrics['unknown_tables']==1
    assert 'private_future_table' not in json.dumps(result.metrics)
    assert hash_file(path)==before


def test_unknown_column_is_reported_without_its_name(client,data_dir):
    path=data_dir/'front.db'
    with closing(sqlite3.connect(path)) as db,db:db.execute('ALTER TABLE assets ADD COLUMN secret_custom_field TEXT')
    result=dd.inspect_database(path)
    assert result.code=='database_schema_incompatible' and result.metrics['unknown_columns']==1
    assert 'secret_custom_field' not in json.dumps(result.metrics)


def test_missing_and_non_front_and_damaged_are_distinct(tmp_path):
    missing=tmp_path/'missing-parent'/'front.db'
    result=dd.inspect_database(missing)
    assert result.code in ('database_unreadable','database_check_failed')
    assert not missing.parent.exists()
    with pytest.raises(sqlite3.DatabaseError):backups.schema_issues(missing)
    assert not missing.exists()
    other=tmp_path/'other.db'
    with closing(sqlite3.connect(other)) as db,db:db.execute('CREATE TABLE personal_table(id INTEGER)')
    assert dd.inspect_database(other).code=='database_not_front'
    bad=tmp_path/'damaged.db';bad.write_bytes(b'generated deliberate invalid SQLite bytes')
    before=bad.read_bytes()
    result=dd.inspect_database(bad)
    assert result.code in ('database_damaged','database_check_failed')
    assert bad.read_bytes()==before


def test_foreign_key_findings_are_not_deleted_or_called_corruption(client,data_dir):
    path=data_dir/'front.db'
    asset=client.post('/api/assets',json={'title':'generated orphan','kind':'other'}).json()
    with closing(sqlite3.connect(path)) as db,db:
        db.execute('UPDATE assets SET world_id=987654 WHERE id=?',(asset['id'],))
    result=dd.inspect_database(path)
    assert result.code=='database_foreign_key_issues' and result.metrics['integrity_ok']
    with closing(sqlite3.connect(path)) as db:
        assert db.execute('SELECT world_id FROM assets').fetchone()[0]==987654


def test_real_sqlite_exclusive_lock_is_not_corruption(tmp_path):
    from sqlalchemy import create_engine
    from front_api.db import Base
    path=tmp_path/'locked.db'
    engine=create_engine('sqlite:///'+str(path));Base.metadata.create_all(engine);engine.dispose()
    with closing(sqlite3.connect(path)) as locked:
        locked.execute('BEGIN EXCLUSIVE')
        assert dd.inspect_database(path).code in ('database_locked','database_check_failed')
        locked.rollback()
    assert dd.inspect_database(path).code=='ok'


def test_unmigratable_missing_fields_stop_but_known_additive_fields_are_supported(client,data_dir,tmp_path):
    with closing(sqlite3.connect(data_dir/'front.db')) as db,db:
        for action in ('insert','update','delete'):db.execute('DROP TRIGGER collection_revision_'+action)
        db.execute('ALTER TABLE collections DROP COLUMN members_revision')
    assert dd.inspect_database(data_dir/'front.db').code=='ok'
    partial=tmp_path/'partial.db'
    with closing(sqlite3.connect(partial)) as db,db:
        for name in ('assets','worlds','characters'):db.execute(f'CREATE TABLE {name}(id INTEGER)')
    result=dd.inspect_database(partial)
    assert result.code=='database_schema_incompatible' and result.metrics['unmigratable_columns']>0


@pytest.mark.parametrize('primary,expected',[(11,'database_damaged'),(26,'database_damaged'),(5,'database_locked'),
    (6,'database_locked'),(3,'database_access_denied'),(8,'database_access_denied'),(23,'database_access_denied'),
    (14,'database_unreadable'),(10,'database_unreadable'),(1,'database_check_failed')])
def test_structured_errors_never_publish_exception_body(primary,expected):
    error=sqlite3.DatabaseError('private path and password must not be published')
    error.sqlite_errorcode=primary|(2<<8)
    assert dd.sqlite_failure(error)==expected
    assert dd.sqlite_failure(sqlite3.DatabaseError('database is locked private data'))=='database_check_failed'


def test_permission_error_fault_injection_does_not_create_file(tmp_path,monkeypatch):
    def denied(*args,**kwargs):raise PermissionError('private OS details')
    with monkeypatch.context() as patch:
        patch.setattr(dd.sqlite3,'connect',denied)
        assert dd.inspect_database(tmp_path/'missing.db').code=='database_access_denied'
    assert list(tmp_path.iterdir())==[]


def test_diagnostic_cli_does_not_initialize_or_log_private_path(tmp_path):
    root=tmp_path/'never-created'
    env={**os.environ,'PYTHONPATH':os.pathsep.join(str(Path(p).resolve()) for p in sys.path if p)}
    process=subprocess.run([sys.executable,'-m','front_api.desktop','--data-dir',str(root),'--diagnose-data'],env=env,
        capture_output=True,text=True,timeout=15)
    assert process.returncode==1
    result=json.loads(process.stdout)
    assert result['code'] in ('database_unreadable','database_check_failed')
    assert str(root) not in process.stdout+process.stderr and not root.exists()
