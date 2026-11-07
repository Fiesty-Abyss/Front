"""Generated collection scale matrix. Never accepts an existing output directory.

ASGI latency/allocations include the test client; not startup, browser or backend RSS.
Existing unbounded API is measured as the compatibility baseline on the same DB.
"""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import platform
import sqlite3
import statistics
import subprocess
import time
import tracemalloc

parser = argparse.ArgumentParser()
parser.add_argument('new_output', type=Path)
args = parser.parse_args()
root = args.new_output.resolve()
root.mkdir(parents=True, exist_ok=False)
os.environ['FRONT_DATA_DIR'] = str(root / 'data')
os.environ['FRONT_CIVITAI'] = 'off'
for name in ('FRONT_AI_API_KEY', 'FRONT_AI_BASE_URL', 'FRONT_AI_MODEL', 'FRONT_SD_WEBUI_URL', 'FRONT_COMFYUI_URL'):
    os.environ.pop(name, None)

from fastapi.testclient import TestClient
from PIL import Image, ImageDraw
from sqlalchemy import insert, text
from front_api.main import create_app
from front_api.db import get_engine
from front_api import models as m

report = {'environment': {'python': platform.python_version(), 'sqlite': sqlite3.sqlite_version,
    'platform': platform.platform(), 'head': subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip(),
    'tracked_dirty': subprocess.run(['git', 'diff', '--quiet', 'HEAD']).returncode != 0,
    'script_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()},
    'scope': 'Generated SQL metadata plus 120 real generated PNG uploads. Warm ASGI+client measurements; not cold startup or real art.', 'scales': []}


def measure(client, url, repeats=5, allocations=False):
    samples = []
    for _ in range(repeats):
        started = time.perf_counter()
        result = client.get(url)
        result.raise_for_status()
        samples.append((time.perf_counter() - started) * 1000)
    value = {'p50_ms': round(statistics.median(samples), 3), 'max_ms': round(max(samples), 3), 'bytes': len(result.content)}
    if allocations:
        tracemalloc.start()
        result = client.get(url)
        result.raise_for_status()
        value['python_peak_asgi_client_bytes'] = tracemalloc.get_traced_memory()[1]
        tracemalloc.stop()
    return value, result.json()


with TestClient(create_app()) as client:
    cid = client.post('/api/collections', json={'name': 'Generated scale collection', 'description': 'Synthetic reliability test; no user materials.'}).json()['id']
    for index in range(120):
        image = Image.new('RGB', (256, 256), (index * 29 % 255, index * 47 % 255, index * 71 % 255))
        ImageDraw.Draw(image).text((20, 30), f'Generated image {index + 1}', fill='white')
        data = io.BytesIO(); image.save(data, format='PNG')
        response = client.post('/api/assets/upload', files={'file': (f'generated-{index + 1}.png', data.getvalue(), 'image/png')})
        response.raise_for_status()
        client.get(f"/api/assets/{response.json()['id']}/thumb").raise_for_status()
    engine = get_engine()
    last = 120
    with engine.begin() as conn:
        conn.execute(insert(m.collection_assets), [{'collection_id': cid, 'asset_id': i, 'position': i - 1} for i in range(1, 121)])
    for size in (10000, 50000, 100000):
        started = time.perf_counter()
        with engine.begin() as conn:
            for start in range(last + 1, size + 1, 1000):
                rows = [{'id': i, 'title': f'Generated asset {i:06}', 'kind': 'novel' if i % 5 == 0 else 'reference',
                    'content': 'generated text ' * 80 if i % 5 == 0 else None} for i in range(start, min(size + 1, start + 1000))]
                conn.execute(insert(m.Asset), rows)
                conn.execute(insert(m.collection_assets), [{'collection_id': cid, 'asset_id': r['id'], 'position': r['id'] - 1} for r in rows])
        entry = {'members': size, 'sql_seed_s': round(time.perf_counter() - started, 3)}
        entry['legacy_full'], _ = measure(client, f'/api/collections/{cid}', repeats=3, allocations=True)
        entry['summary'], summary = measure(client, f'/api/collections/{cid}/summary', allocations=True)
        entry['page60'], first = measure(client, f'/api/collections/{cid}/members?limit=60', allocations=True)
        entry['page2'], second = measure(client, f"/api/collections/{cid}/members?limit=60&cursor={first['next_cursor']}")
        assert len(first['items']) == len(second['items']) == 60 and first['total'] == size and summary['member_count'] == size
        # Boundaries are checked through the entire cursor chain, not only offset 0.
        started = time.perf_counter(); seen = []; cursor = None
        while True:
            response = client.get(f'/api/collections/{cid}/members', params={'limit': 200, **({'cursor': cursor} if cursor else {})})
            response.raise_for_status(); page = response.json(); seen.extend(r['id'] for r in page['items'])
            cursor = page['next_cursor']
            if not cursor: break
        assert seen == list(range(1, size + 1))
        entry['full_cursor_walk_s'] = round(time.perf_counter() - started, 3)
        with engine.connect() as conn:
            entry['plan'] = [list(r) for r in conn.exec_driver_sql(f'EXPLAIN QUERY PLAN SELECT asset_id FROM collection_assets WHERE collection_id={cid} ORDER BY position,asset_id LIMIT 60')]
            assert conn.exec_driver_sql('PRAGMA integrity_check').scalar() == 'ok'
        # Evidence for the new index, isolated DB only, restore in finally.
        with engine.begin() as conn:
            conn.exec_driver_sql('DROP INDEX ix_collection_members_position')
            try:
                entry['without_index_plan'] = [list(r) for r in conn.exec_driver_sql(f'EXPLAIN QUERY PLAN SELECT asset_id FROM collection_assets WHERE collection_id={cid} ORDER BY position,asset_id LIMIT 60')]
                samples = []
                for _ in range(5):
                    started = time.perf_counter()
                    conn.exec_driver_sql(f'SELECT asset_id FROM collection_assets WHERE collection_id={cid} ORDER BY position,asset_id LIMIT 60').all()
                    samples.append((time.perf_counter() - started) * 1000)
                entry['without_index_sql_p50_ms'] = round(statistics.median(samples), 3)
            finally:
                conn.exec_driver_sql('CREATE INDEX ix_collection_members_position ON collection_assets(collection_id,position,asset_id)')
        report['scales'].append(entry)
        (root / 'report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
        print(json.dumps(entry), flush=True)
        last = size
print(json.dumps({'output': str(root), 'complete': True}), flush=True)
