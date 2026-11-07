"""Actual source processes and generated migration/media; no native GUI or installer claim."""
import hashlib
import io
import json
import os
from pathlib import Path
import queue
import sqlite3
import subprocess
import sys
import threading
import time

import httpx
from PIL import Image


class ProgressSidecar:
    def __init__(self, folder):
        env = {k: v for k, v in os.environ.items() if not k.startswith('FRONT_')}
        env['PYTHONPATH'] = os.pathsep.join(str(Path(p).resolve()) for p in sys.path if p)
        self.process = subprocess.Popen([getattr(sys, '_base_executable', sys.executable), '-m', 'front_api.desktop',
            '--data-dir', str(folder), '--startup-events'], env=env, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True,
            creationflags=0x08000000 if os.name == 'nt' else 0)
        self.events = []
        self.lines = queue.Queue()
        def collect():
            for line in self.process.stdout:
                self.lines.put(line)
        threading.Thread(target=collect, daemon=True).start()
        self.ready = None
    def wait(self):
        deadline = time.monotonic() + 30
        try:
            for _ in range(100):
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError('startup_progress_deadline')
                line = self.lines.get(timeout=remaining)
                assert len(line.encode()) <= 4096
                value = json.loads(line)
                if 'phase' in value:
                    assert set(value) == {'phase', 'done', 'total'}
                    self.events.append(value)
                else:
                    self.ready = value
                    return value
            raise AssertionError('too_many_generated_startup_messages')
        except Exception:
            self.close(); raise
    def client(self):
        assert self.ready['pid'] == self.process.pid
        return httpx.Client(base_url=f"http://127.0.0.1:{self.ready['port']}", trust_env=False, timeout=15,
            headers={'Authorization': 'Bearer ' + self.ready['token']})
    def stop(self, client):
        assert client.post('/_desktop/shutdown').status_code == 200
        self.process.wait(timeout=15)
        assert self.process.returncode == 0
    def close(self):
        if self.process.poll() is None:
            self.process.kill(); self.process.wait(timeout=15)
        self.process.stdout.close()


def test_real_startup_phases_backup_restore_and_failure_do_not_expose_paths(tmp_path):
    folder = tmp_path / 'generated private-name path & 中文'
    first = ProgressSidecar(folder)
    try:
        first.wait()
        assert [e['phase'] for e in first.events] == ['checking_data', 'checking_database', 'initializing_database', 'starting_service']
        with first.client() as client:
            client.post('/api/worlds', json={'name': 'Generated startup world'}).raise_for_status()
            body = io.BytesIO(); Image.new('RGB', (16, 16), (100, 70, 150)).save(body, 'PNG')
            asset = client.post('/api/assets/upload', files={'file': ('generated-private-name.png', body.getvalue(), 'image/png')})
            asset.raise_for_status(); media = folder / asset.json()['file_path']
            digest = hashlib.sha256(media.read_bytes()).hexdigest()
            first.stop(client)
    finally:
        first.close()
    with sqlite3.connect(folder / 'front.db') as db:
        db.execute('DROP TABLE sd_model_profiles')
    second = ProgressSidecar(folder)
    try:
        second.wait()
        phases = [e['phase'] for e in second.events]
        assert {'backup', 'verify_backup', 'restore', 'migrating', 'starting_service'} <= set(phases)
        assert phases.index('backup') < phases.index('restore') < phases.index('migrating')
        assert 'private-name' not in json.dumps(second.events)
        with second.client() as client:
            assert client.get('/api/worlds').json()['total'] == 1
            assert hashlib.sha256(media.read_bytes()).hexdigest() == digest
            second.stop(client)
        assert second.ready['token'] not in (folder / 'logs/desktop.log').read_text(encoding='utf-8')
        assert list((folder / 'backups').glob('full-*/manifest.json'))
        assert list((folder / 'restores').glob('*/front.db'))
    finally:
        second.close()
    with sqlite3.connect(folder / 'front.db') as db:
        db.execute('CREATE TABLE generated_future_format(id INTEGER)')
    rejected = ProgressSidecar(folder)
    try:
        assert rejected.wait() == {'error': 'database_incompatible_or_damaged'}
        rejected.process.wait(timeout=15)
        assert rejected.process.returncode == 1
        assert all('private-name' not in json.dumps(e) for e in rejected.events)
    finally:
        rejected.close()
