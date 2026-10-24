"""Isolated startup/upgrade regression. Refuses any existing data root."""
import argparse
from contextlib import closing
import hashlib
import io
import json
import os
from pathlib import Path
import queue
import sqlite3
import subprocess
import threading
import time

import httpx
from PIL import Image


def handshake(process, timeout=45):
    output = queue.Queue()
    threading.Thread(target=lambda: output.put(process.stdout.readline()), daemon=True).start()
    try:
        line = output.get(timeout=timeout)
        return json.loads(line)
    except (queue.Empty, json.JSONDecodeError) as exc:
        raise RuntimeError('sidecar_handshake_timeout_or_invalid') from exc


class Sidecar:
    def __init__(self, command, folder, env):
        self.process = subprocess.Popen([*command, '--data-dir', str(folder)], stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, text=True, env=env, creationflags=0x08000000 if os.name == 'nt' else 0)
        self.started = time.perf_counter()
        try:
            self.ready = handshake(self.process)
            self.seconds = time.perf_counter() - self.started
        except Exception:
            self.close(); raise
        self.client = None
        if 'error' not in self.ready:
            assert self.ready['pid'] == self.process.pid
            self.url = 'http://127.0.0.1:' + str(self.ready['port'])
            self.client = httpx.Client(base_url=self.url, trust_env=False, timeout=15,
                headers={'Authorization': 'Bearer ' + self.ready['token']})
    def stop(self):
        assert self.client.post('/_desktop/shutdown').status_code == 200
        self.process.wait(timeout=20)
        assert self.process.returncode == 0
        try: httpx.get(self.url, trust_env=False, timeout=1)
        except httpx.TransportError: pass
        else: raise AssertionError('owned_port_left_open')
    def close(self):
        if self.process.poll() is None:
            self.process.kill(); self.process.wait(timeout=15)
        if getattr(self, 'client', None): self.client.close()
        if self.process.stdout: self.process.stdout.close()


def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()


def run(command, root, env, *, frozen):
    root = Path(root).resolve()
    root.mkdir(parents=True, exist_ok=False)  # Never mutate a pre-existing user/test library.
    folder = root / '中文 path & generated'
    report = {'frozen': frozen, 'clean_vm': False, 'minimal_path': frozen, 'cases': {}}
    first = Sidecar(command, folder, env)
    try:
        assert 'error' not in first.ready
        report['cases']['first_ready_seconds'] = round(first.seconds, 3)
        c = first.client
        world = c.post('/api/worlds', json={'name': 'Generated regression world'}); assert world.status_code == 201
        world_id = world.json()['id']
        image = io.BytesIO(); Image.new('RGB', (32, 32), (120, 80, 180)).save(image, 'PNG')
        asset = c.post('/api/assets/upload', files={'file': ('generated.png', image.getvalue(), 'image/png')})
        assert asset.status_code == 201
        asset_id = asset.json()['id']; original = image.getvalue()
        duplicate = Sidecar(command, folder, env)
        try:
            assert duplicate.ready == {'error': 'data_directory_in_use'}
            duplicate.process.wait(timeout=10); assert duplicate.process.returncode != 0
            assert c.get('/api/worlds').json()['total'] == 1
            report['cases']['second_instance_refused_owner_alive'] = True
        finally: duplicate.close()
        old_token = first.ready['token']
        first.stop()
    finally: first.close()
    second = Sidecar(command, folder, env)
    try:
        report['cases']['restart_ready_seconds'] = round(second.seconds, 3)
        assert second.client.get('/api/worlds').json()['items'][0]['id'] == world_id
        assert second.client.get(f'/api/assets/{asset_id}/file').content == original
        assert httpx.get(second.url+'/api/worlds', headers={'Authorization': 'Bearer '+old_token}, trust_env=False).status_code == 401
        report['cases']['restart_preserves_generated_media_and_records_rotates_session'] = True
        second.stop()
    finally: second.close()
    with closing(sqlite3.connect(folder/'front.db')) as db, db:
        db.execute('DROP TABLE sd_model_profiles')  # Deliberately old additive schema, generated data only.
    upgraded = Sidecar(command, folder, env)
    try:
        assert 'error' not in upgraded.ready
        assert upgraded.client.get('/api/worlds').json()['items'][0]['id'] == world_id
        assert upgraded.client.get(f'/api/assets/{asset_id}/file').content == original
        packages = list((folder/'backups').glob('full-*/manifest.json'))
        assert packages
        manifest = json.loads(packages[-1].read_text(encoding='utf-8'))
        assert manifest['status'] == 'complete'
        assert any(f['path'].startswith('media/') for f in manifest['files'])
        restored = list((folder/'restores').glob('*/front.db')); assert restored
        with closing(sqlite3.connect(restored[-1])) as db, db:
            assert db.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
            assert db.execute('select count(*) from worlds').fetchone()[0] == 1
        report['cases']['old_schema_full_media_backup_and_isolated_restore'] = True
        upgraded.stop()
    finally: upgraded.close()
    with closing(sqlite3.connect(folder/'front.db')) as db, db:
        assert db.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
        assert not db.execute('PRAGMA foreign_key_check').fetchall()
        db.execute('CREATE TABLE generated_future_schema (id INTEGER)')
    before = sha(folder/'front.db')
    future = Sidecar(command, folder, env)
    try:
        assert future.ready == {'error': 'database_incompatible_or_damaged'}
        future.process.wait(timeout=10); assert future.process.returncode != 0
        assert sha(folder/'front.db') == before
        report['cases']['future_schema_refused_without_rewrite'] = True
    finally: future.close()
    corrupt = root/'corrupt'; corrupt.mkdir(); (corrupt/'front.db').write_bytes(b'generated corrupt SQLite fixture')
    before = sha(corrupt/'front.db'); failed = Sidecar(command, corrupt, env)
    try:
        assert failed.ready == {'error': 'database_incompatible_or_damaged'}
        failed.process.wait(timeout=10); assert failed.process.returncode != 0
        assert sha(corrupt/'front.db') == before
        report['cases']['corrupt_database_refused_without_rewrite'] = True
    finally: failed.close()
    blocked = root/'generated-file-not-folder'; blocked.write_bytes(b'generated sentinel')
    failed = Sidecar(command, blocked, env)
    try:
        assert failed.ready == {'error': 'data_directory_unwritable'}
        failed.process.wait(timeout=10); assert failed.process.returncode != 0
        assert blocked.read_bytes() == b'generated sentinel'
        report['cases']['unusable_directory_clear_error_no_overwrite'] = True
    finally: failed.close()
    (root/'result.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    return report


if __name__ == '__main__':
    parser=argparse.ArgumentParser();parser.add_argument('binary', type=Path);parser.add_argument('new_data_root',type=Path)
    args=parser.parse_args()
    # Child gets OS essentials only, no Python/Node/Rust PATH and no AI credentials.
    keys=['SystemRoot','WINDIR','TEMP','TMP','APPDATA','LOCALAPPDATA','USERPROFILE']
    env={k:os.environ[k] for k in keys if k in os.environ}
    if os.name=='nt':env['PATH']=str(Path(os.environ['SystemRoot'])/'System32')
    print(json.dumps(run([str(args.binary.resolve())],args.new_data_root,env,frozen=True)))
