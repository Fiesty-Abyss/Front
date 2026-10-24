import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import threading
import queue

import httpx
import pytest
from fastapi.testclient import TestClient

from front_api.desktop import data_lock, prepare_data, protect


def test_desktop_origin_host_cookie_and_shell_shutdown(app):
    stopped=[]
    protect(app, token='generated-test-secret', port=23456, stop=lambda:stopped.append(True))
    with TestClient(app,base_url='http://127.0.0.1:23456') as client:
        assert client.get('/api/worlds').status_code==401
        bootstrap=client.get('/_desktop/bootstrap')
        assert bootstrap.status_code==200 and 'generated-test-secret' not in bootstrap.text
        assert 'frame-ancestors' in bootstrap.headers['Content-Security-Policy']
        assert client.post('/_desktop/session',headers={'Authorization':'Bearer wrong'}).status_code==401
        bearer={'Authorization':'Bearer generated-test-secret'}
        assert client.post('/_desktop/session',headers={**bearer,'Origin':'http://evil.test'}).status_code==403
        assert client.get('/api/worlds',headers={**bearer,'Host':'evil.test'}).status_code==403
        response=client.post('/_desktop/session',headers=bearer)
        assert response.status_code==200 and 'HttpOnly' in response.headers['set-cookie']
        assert 'SameSite=strict' in response.headers['set-cookie']
        assert client.get('/api/worlds').status_code==200
        assert client.post('/_desktop/shutdown').status_code==403
        assert client.post('/_desktop/shutdown',headers=bearer).status_code==200 and stopped


def test_desktop_data_lock_and_future_schema_refused(client,data_dir):
    from front_api.config import get_settings
    with data_lock(data_dir):
        with pytest.raises(RuntimeError,match='in_use'):
            with data_lock(data_dir):pass
    with data_lock(data_dir):pass
    with sqlite3.connect(data_dir/'front.db') as db:db.execute('CREATE TABLE future_format (id INTEGER)')
    with pytest.raises(RuntimeError,match='incompatible'):
        prepare_data(get_settings())
    with sqlite3.connect(data_dir/'front.db') as db:
        assert db.execute("SELECT name FROM sqlite_master WHERE name='future_format'").fetchone()


def test_desktop_upgrade_full_backup_before_additive_schema(client,data_dir):
    from front_api.config import get_settings
    from front_api import backups
    # Simulate the previous release lacking the new empty personal-overlay table.
    with sqlite3.connect(data_dir/'front.db') as db:db.execute('DROP TABLE sd_model_profiles')
    prepare_data(get_settings())
    packages=list((data_dir/'backups').glob('full-*'))
    assert len(packages)==1 and not backups.verify(packages[0])[1]
    assert len(list((data_dir/'restores').glob('*/front.db')))==1
    # Preparing proves migration in a separate directory; original is not migrated yet.
    with sqlite3.connect(data_dir/'front.db') as db:
        assert not db.execute("SELECT name FROM sqlite_master WHERE name='sd_model_profiles'").fetchone()


def test_source_sidecar_real_loopback_start_stop(tmp_path):
    folder=tmp_path/'isolated-desktop'
    # Windows venv python.exe is a redirector with a second PID. Invoke the actual interpreter
    # with this test environment's module paths; frozen onedir is checked separately in CI.
    env={**os.environ,'PYTHONPATH':os.pathsep.join(str(Path(p).resolve()) for p in sys.path if p)}
    process=subprocess.Popen([getattr(sys,'_base_executable',sys.executable),'-m','front_api.desktop','--data-dir',str(folder)],
        stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True,env=env)
    result=queue.Queue()
    threading.Thread(target=lambda:result.put(process.stdout.readline()),daemon=True).start()
    try:
        ready=json.loads(result.get(timeout=20))
        assert ready['pid']==process.pid and ready['port']>0
        url=f'http://127.0.0.1:{ready["port"]}'
        with httpx.Client(base_url=url,timeout=5) as c:
            assert c.get('/api/worlds').status_code==401
            bearer={'Authorization':'Bearer '+ready['token']}
            assert c.post('/api/worlds',json={'name':'Generated desktop world'},headers=bearer).status_code==201
            assert c.post('/_desktop/shutdown',headers=bearer).status_code==200
        process.wait(timeout=15)
        assert process.returncode==0
        with pytest.raises(httpx.TransportError):httpx.get(url,timeout=1)
        assert ready['token'] not in (folder/'logs/desktop.log').read_text(encoding='utf-8')
        with sqlite3.connect(folder/'front.db') as db:
            assert db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
    finally:
        if process.poll() is None:process.kill();process.wait()
