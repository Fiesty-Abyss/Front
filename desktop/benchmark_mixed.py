"""Reproducible synthetic mixed-library probe; not real AI, a clean VM or TTI.

Outputs only into a NEW directory. Run with PYTHONPATH=backend from repository root.
"""
import argparse
import hashlib
import io
import json
import math
import os
from pathlib import Path
import platform
import sqlite3
import statistics
import subprocess
import sys
import threading
import time
import wave


def memory_snapshot():
    if os.name != 'nt':
        return {'available': False, 'reason': 'Windows process counters only'}
    import ctypes
    from ctypes import wintypes
    class Counters(ctypes.Structure):
        _fields_ = [('cb', wintypes.DWORD), ('PageFaultCount', wintypes.DWORD),
                    *[(key, ctypes.c_size_t) for key in ('PeakWorkingSetSize', 'WorkingSetSize', 'QuotaPeakPagedPoolUsage', 'QuotaPagedPoolUsage',
                    'QuotaPeakNonPagedPoolUsage', 'QuotaNonPagedPoolUsage', 'PagefileUsage', 'PeakPagefileUsage', 'PrivateUsage')]]
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    psapi = ctypes.WinDLL('psapi', use_last_error=True)
    kernel.GetCurrentProcess.restype = wintypes.HANDLE
    psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD]
    counter = Counters(); counter.cb = ctypes.sizeof(counter)
    if not psapi.GetProcessMemoryInfo(kernel.GetCurrentProcess(), ctypes.byref(counter), counter.cb):
        return {'available': False, 'reason': 'process memory query failed'}
    return {'available': True, 'working_set': counter.WorkingSetSize, 'peak_working_set_since_process_start': counter.PeakWorkingSetSize,
            'private_commit': counter.PrivateUsage}


def crash_worker(root):
    from front_api.jobs import Manager
    if (Path(root) / '.front-generated-benchmark').read_text() != 'front-mixed-benchmark-v1':
        raise ValueError('refuse_unmarked_worker_directory')
    manager = Manager(Path(root) / 'crash-jobs.sqlite3')
    gate = threading.Event()
    def hold(job):
        while not gate.wait(.05):
            job.check()
    for _ in range(8):
        manager.start('generated-recovery', 'Generated crash task', 1, hold)
    print(json.dumps({'ready': True, 'pid': os.getpid()}), flush=True)
    gate.wait(60)


def query(client, url, expected=None, count=5):
    samples = []
    for _ in range(count):
        started = time.perf_counter()
        response = client.get(url)
        response.raise_for_status()
        samples.append((time.perf_counter() - started) * 1000)
    value = response.json()
    if expected is not None:
        assert value['total'] == expected, (url, expected, value.get('total'))
    return {'p50_ms': round(statistics.median(samples), 3), 'max_ms': round(max(samples), 3),
            'bytes': len(response.content), 'total': value.get('total')}, value


def queue_probe(root, client):
    from fastapi import HTTPException
    from front_api.jobs import Manager
    mgr = Manager(root / 'queue-jobs.sqlite3')
    release = threading.Event()
    guard = threading.Lock()
    active, peak = 0, 0
    def work(job):
        nonlocal active, peak
        with guard:
            active += 1; peak = max(peak, active)
        try:
            while not release.wait(.01):
                job.check(); hashlib.sha256(b'generated bounded hash' * 4096).digest()
            for _ in range(3):
                hashlib.sha256(b'generated queue input' * 4096).digest()
                job.step()
        finally:
            with guard: active -= 1
    tasks = []
    try:
        for _ in range(34): tasks.append(mgr.start('generated-hash', 'Generated queue pressure', 3, work))
        try: mgr.start('generated-overflow', 'Must refuse overflow', 1, work)
        except HTTPException as exc: assert exc.status_code == 429
        else: raise AssertionError('unbounded_queue')
        tasks[-1].cancel_requested = True; mgr.save(tasks[-1])
        tasks[0].cancel_requested = True; mgr.save(tasks[0])
        under_load, _ = query(client, '/api/assets?limit=60')
        release.set()
        deadline = time.monotonic() + 30
        while any(j.status in ('queued', 'running') for j in tasks):
            if time.monotonic() > deadline: raise TimeoutError('queue_did_not_drain')
            time.sleep(.02)
        assert peak <= 2 and tasks[-1].status == tasks[0].status == 'cancelled'
        statuses = {state: sum(j.status == state for j in tasks) for state in ('done', 'cancelled', 'error')}
        assert statuses == {'done': 32, 'cancelled': 2, 'error': 0}
    finally:
        release.set(); mgr.shutdown()
    # Actually terminate a separate producer after it has persisted live work.
    command = [sys.executable, str(Path(__file__).resolve()), '--crash-worker', str(root)]
    child = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True,
        creationflags=0x08000000 if os.name == 'nt' else 0)
    try:
        import queue
        output = queue.Queue()
        threading.Thread(target=lambda: output.put(child.stdout.readline()), daemon=True).start()
        ready = json.loads(output.get(timeout=20)); assert ready['ready'] is True
        if os.name == 'nt':
            subprocess.run(['taskkill', '/PID', str(child.pid), '/T', '/F'], capture_output=True, check=True, timeout=10)
        else: child.kill()
        child.wait(timeout=10)
        recovered = Manager(root / 'crash-jobs.sqlite3')
        try:
            assert len(recovered.jobs) == 8
            assert all(j.status == 'interrupted' for j in recovered.jobs.values())
            assert recovered.executor is None  # no replay of inference or side effects
            retry = recovered.start('generated-explicit-retry', 'Generated manual retry', 1, lambda job: job.step())
            deadline = time.monotonic() + 5
            while retry.status in ('queued', 'running'):
                if time.monotonic() > deadline: raise TimeoutError('explicit_retry_stalled')
                time.sleep(.01)
            assert retry.status == 'done'
            assert sum(j.status == 'interrupted' for j in recovered.jobs.values()) == 8
        finally: recovered.shutdown()
    finally:
        if child.poll() is None: child.kill(); child.wait(timeout=10)
        child.stdout.close()
    return {'peak_active_workers': peak, 'capacity': 34, 'overflow_status': 429, 'statuses': statuses,
            'asset_query_during_backlog': under_load, 'actual_process_crash_recovered': 8,
            'recovery_policy': 'interrupted; no automatic replay; explicit new retry verified'}


def run(root, smoke):
    root = root.resolve(); root.mkdir(parents=True, exist_ok=False)
    (root / '.front-generated-benchmark').write_text('front-mixed-benchmark-v1')
    os.environ['FRONT_DATA_DIR'] = str(root / 'data'); os.environ['FRONT_CIVITAI'] = 'off'
    for name in ('FRONT_AI_BASE_URL', 'FRONT_AI_MODEL', 'FRONT_AI_API_KEY', 'FRONT_SD_WEBUI_URL', 'FRONT_COMFYUI_URL'):
        os.environ.pop(name, None)
    from fastapi.testclient import TestClient
    from PIL import Image, ImageDraw
    from sqlalchemy import insert, text
    from front_api.main import create_app
    from front_api.db import get_engine
    from front_api import models as m
    from datetime import date
    scales = (100, 500, 1000) if smoke else (10000, 50000, 100000)
    worlds, people, models, prompts, image_count, audio_count, chapters = (4, 20, 10, 10, 2, 4, 5) if smoke else (20, 2000, 300, 500, 1000, 200, 1000)
    report = {'scope': 'Synthetic SQL metadata plus real generated PNG/WAV/TXT uploads; in-process ASGI+client; not AI or clean Windows',
        'environment': {'python': platform.python_version(), 'sqlite': sqlite3.sqlite_version, 'platform': platform.platform(),
        'head': subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip(),
        'script_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}, 'scales': [], 'checks': {}}
    started = time.perf_counter()
    memory_samples = []
    stop_sampling = threading.Event()
    def sample_memory():
        while not stop_sampling.is_set():
            memory_samples.append(memory_snapshot())
            stop_sampling.wait(.25)
    sampler = threading.Thread(target=sample_memory, daemon=True); sampler.start()
    factory_start = time.perf_counter()
    app = create_app()
    report['factory_empty_ms_excludes_imports'] = round((time.perf_counter() - factory_start) * 1000, 3)
    with TestClient(app) as client:
        engine = get_engine()
        with engine.begin() as conn:
            conn.execute(insert(m.World), [{'id': i, 'name': f'Generated world {i}'} for i in range(1, worlds + 1)])
            conn.execute(insert(m.Tag), [{'id': 1, 'name': 'Generated parent', 'category': 'generated'}, {'id': 2, 'name': 'Generated second', 'category': 'generated'}])
            conn.execute(insert(m.Tag), [{'id': 3, 'name': 'Generated child', 'category': 'generated', 'parent_id': 1}])
            conn.execute(insert(m.Character), [{'id': i, 'name': f'Generated person {(i - 1) // worlds}', 'world_id': (i - 1) % worlds + 1} for i in range(1, people + 1)])
            conn.execute(insert(m.Relation), [{'source_id': i, 'target_id': i + worlds, 'kind': kind} for i in range(1, people - worlds + 1) for kind in ('generated ally', 'generated colleague')])
            conn.execute(insert(m.SDModel), [{'name': f'Generated model {i}', 'kind': 'lora' if i % 2 else 'checkpoint', 'base_model': 'unknown', 'notes': 'Metadata only; no weight file or compatibility claim'} for i in range(models)])
            conn.execute(insert(m.Prompt), [{'title': f'Generated prompt {i}', 'positive': 'generated study sample', 'negative': 'sample', 'params': {'seed': i}} for i in range(prompts)])
            conn.execute(insert(m.Collection), [{'id': 1, 'name': 'Generated mixed collection'}])
        last = 0
        for size in scales:
            start = time.perf_counter()
            with engine.begin() as conn:
                for lower in range(last + 1, size + 1, 1000):
                    rows = [{'id': i, 'title': f'Generated asset {i:06d}', 'kind': 'reference', 'world_id': (i - 1) % worlds + 1, 'work_date': date(2026, 1, (i - 1) % 28 + 1)} for i in range(lower, min(lower + 1000, size + 1))]
                    conn.execute(insert(m.Asset), rows)
                    conn.execute(insert(m.collection_assets), [{'collection_id': 1, 'asset_id': r['id'], 'position': r['id'] - 1} for r in rows])
                    links = [{'asset_id': r['id'], 'tag_id': 3} for r in rows if r['id'] % 2 == 0]
                    links += [{'asset_id': r['id'], 'tag_id': 2} for r in rows if r['id'] % 3 == 0]
                    if links: conn.execute(insert(m.asset_tags), links)
                    conn.execute(text('INSERT INTO search_index(entity,entity_id,title,body) VALUES(:e,:i,:t,:b)'), [{'e': 'asset', 'i': r['id'], 't': r['title'], 'b': 'generated test'} for r in rows])
            metrics = {'members': size, 'sql_seed_s': round(time.perf_counter() - start, 3)}
            for key, url, expected in [('assets', '/api/assets?limit=60', size), ('world', '/api/assets?limit=60&world_id=1', size // worlds),
                    ('positive_hierarchical_tags', '/api/assets?limit=60&tag=1&tag=2', size // 6), ('wide_search', '/api/assets?limit=60&q=Generated', size),
                    ('collection', '/api/collections/1/members?limit=60', size)]:
                metrics[key], _ = query(client, url, expected)
            report['scales'].append(metrics); last = size
            print(json.dumps({'stage': 'metadata', 'records': size, 'queries': metrics}), flush=True)
        report['checks']['characters'], chars = query(client, '/api/characters?limit=60', people)
        report['checks']['graph_world'], graph = query(client, '/api/graph?world_id=1')
        assert len(graph['nodes']) == people // worlds
        report['checks']['models'], _ = query(client, '/api/sd-models?limit=60', models)
        report['checks']['prompts'], _ = query(client, '/api/prompts?limit=60', prompts)
        body = '\n\n'.join(f'第{i + 1}章 Generated chapter\n' + ('云海与山川，人物在此讨论一个生成的设定。' * (4 if smoke else 60)) for i in range(chapters))
        novel = client.post('/api/assets/upload', files={'file': ('generated-long-novel.txt', body.encode('utf-8'), 'text/plain')})
        novel.raise_for_status(); novel_id = novel.json()['id']
        report['checks']['chapter_plan'], plan = query(client, f'/api/assets/{novel_id}/chapter-plan')
        assert len(plan['detected']) == chapters
        print(json.dumps({'stage': 'chapters', 'count': chapters, 'p50_ms': report['checks']['chapter_plan']['p50_ms']}), flush=True)
        response = client.put(f'/api/assets/{novel_id}/chapter-plan', json={'text_hash': plan['text_hash'], 'base_revision': 0, 'chapters': plan['detected'], 'note': 'Generated confirmed chapter plan'})
        response.raise_for_status()
        report['novel'] = {'bytes': len(body.encode('utf-8')), 'chapters': chapters, 'asset_id': novel_id}
        image_times = []
        for i in range(image_count):
            image = Image.new('RGB', (1024, 768), (i * 37 % 255, i * 73 % 255, i * 17 % 255))
            ImageDraw.Draw(image).text((40, 40), f'Generated mixed image {i}', fill='white')
            output = io.BytesIO(); image.save(output, 'PNG')
            start = time.perf_counter(); r = client.post('/api/assets/upload', files={'file': (f'generated-image-{i}.png', output.getvalue(), 'image/png')}); r.raise_for_status()
            client.get(f"/api/assets/{r.json()['id']}/thumb").raise_for_status(); image_times.append((time.perf_counter() - start) * 1000)
            if (i + 1) % 100 == 0: print(json.dumps({'stage': 'generated_png_uploads', 'done': i + 1}), flush=True)
        audio_ids = []
        for i in range(audio_count):
            output = io.BytesIO()
            with wave.open(output, 'wb') as wav:
                wav.setnchannels(1); wav.setsampwidth(2); wav.setframerate(8000)
                import struct
                wav.writeframes(b''.join(struct.pack('<h', int(1500 * math.sin(2 * math.pi * (220 + i) * t / 8000))) for t in range(16000)))
            r = client.post('/api/assets/upload', files={'file': (f'generated-track-{i}.wav', output.getvalue(), 'audio/wav')}); r.raise_for_status(); audio_ids.append(r.json()['id'])
        albums = []
        for start in range(0, audio_count, 20):
            r = client.post('/api/audio/albums', json={'title': f'Generated album {start // 20}'}); r.raise_for_status(); album = r.json(); albums.append(album['id'])
            client.post(f"/api/audio/albums/{album['id']}/tracks", json={'asset_ids': audio_ids[start:start + 20]}).raise_for_status()
        for aid in audio_ids[:5]:
            r = client.get(f'/api/audio/tracks/{aid}/state').json()
            client.put(f'/api/audio/tracks/{aid}/state', json={'asset_identity': r['asset_identity'], 'sha256': r['sha256'], 'expected_revision': r['revision'], 'position': 1.25, 'rate': 1.5}).raise_for_status()
            assert client.get(f'/api/audio/tracks/{aid}/state').json()['position'] == 1.25
        report['checks']['audio'], _ = query(client, '/api/audio/tracks?limit=60', audio_count)
        for i in range(4 if smoke else 100):
            r = client.post('/api/oc', json={'title': f'Generated OC {i}', 'character_id': i + 1, 'fields': {'hair': 'generated silver', 'notes': 'generated design'}, 'designs': [{'name': 'Study outfit', 'fields': {'clothes': 'generated jacket'}}]})
            r.raise_for_status()
        report['checks']['oc'], _ = query(client, '/api/oc?limit=60', 4 if smoke else 100)
        report['queue'] = queue_probe(root, client)
        with engine.connect() as conn:
            assert conn.exec_driver_sql('PRAGMA integrity_check').scalar() == 'ok'
            assert not conn.exec_driver_sql('PRAGMA foreign_key_check').fetchall()
            conn.exec_driver_sql('PRAGMA wal_checkpoint(TRUNCATE)')
        report['generated'] = {'assets': scales[-1], 'worlds': worlds, 'characters': people, 'relations': 2 * (people - worlds),
            'models_metadata_only': models, 'prompts': prompts, 'png_uploads': image_count, 'wav_uploads': audio_count, 'albums': len(albums), 'novels': 1, 'chapter_count': chapters}
        report['image_upload_thumb_p50_ms'] = round(statistics.median(image_times), 3)
    engine.dispose()
    factory_start = time.perf_counter()
    with TestClient(create_app()) as restart_client:
        restart_client.get('/api/health').raise_for_status()
        assert restart_client.get('/api/audio/tracks?limit=60').json()['total'] == audio_count
        assert restart_client.get(f'/api/audio/tracks/{audio_ids[0]}/state').json()['position'] == 1.25
    report['factory_populated_and_first_asgi_health_ms'] = round((time.perf_counter() - factory_start) * 1000, 3)
    get_engine().dispose()
    report['elapsed_s'] = round(time.perf_counter() - started, 3)
    stop_sampling.set(); sampler.join(timeout=3)
    valid = [r for r in memory_samples if r.get('available')]
    report['memory'] = {'scope': 'whole Python probe process, includes ASGI client and generators; not isolated backend or browser',
        'samples': len(valid), 'peak_sampled_working_set': max((r['working_set'] for r in valid), default=None),
        'peak_sampled_private_commit': max((r['private_commit'] for r in valid), default=None), 'end': memory_snapshot()}
    report['disk'] = {folder: sum(p.stat().st_size for p in (root / 'data' / folder).rglob('*') if p.is_file()) for folder in ('media', 'thumbs')}
    report['disk']['database'] = (root / 'data' / 'front.db').stat().st_size
    report['unverified'] = ['cold OS boot', 'standard TTI', 'browser Heap and FPS', 'GPU/VRAM', 'clean Windows', 'real AI/image inference', 'power loss']
    (root / 'report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps({'complete': True, 'elapsed_s': report['elapsed_s'], 'generated': report['generated'], 'queue': report['queue'], 'memory': report['memory'], 'disk': report['disk']}), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('new_output', type=Path, nargs='?')
    parser.add_argument('--smoke', action='store_true')
    parser.add_argument('--crash-worker', type=Path)
    args = parser.parse_args()
    if args.crash_worker: crash_worker(args.crash_worker)
    elif args.new_output: run(args.new_output, args.smoke)
    else: parser.error('new_output required')
