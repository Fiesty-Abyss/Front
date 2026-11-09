"""Isolated generated metadata benchmark. Refuses to use an existing directory."""
import argparse
import json
import os
from pathlib import Path
import platform
import sqlite3
import statistics
import time
import tracemalloc
import uuid


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    root = Path(args.output).resolve()
    root.mkdir(parents=True, exist_ok=False)
    os.environ['FRONT_DATA_DIR'] = str(root/'data')
    for name in ('FRONT_AI_BASE_URL', 'FRONT_AI_API_KEY', 'FRONT_AI_MODEL'):
        os.environ.pop(name, None)
    from fastapi.testclient import TestClient
    from sqlalchemy import insert, text
    from front_api.config import get_settings
    from front_api.db import get_engine
    from front_api.main import create_app
    from front_api import models as m
    get_settings.cache_clear()
    results = []
    with TestClient(create_app()) as client:
        sid = client.post('/api/souls', json={'name': 'Generated benchmark role'}).json()['id']
        count = 0
        for total in (1000, 10000):
            engine = get_engine()
            rows = [{'uid': uuid.uuid4().hex, 'soul_id': sid, 'kind': 'relationship',
                     'content': f'Generated fictional lighthouse memory {i}. ' + '海港约定 ' * 12,
                     'scope': 'character', 'scope_ref': {'world': {}}, 'source': {'kind': 'manual', 'origin': 'user'},
                     'review': 'approved', 'allow_injection': True} for i in range(count, total)]
            start = time.perf_counter()
            with engine.begin() as conn:
                conn.execute(insert(m.SoulMemory), rows)
                conn.execute(text('DELETE FROM soul_memory_index'))
                conn.execute(text('INSERT INTO soul_memory_index(rowid,content) SELECT id,content FROM soul_memories'))
            seed_ms = (time.perf_counter()-start)*1000
            del rows
            scenarios = {}
            for name, method, url, options in (
                ('page30', 'get', f'/api/souls/{sid}/memories', {'params': {'limit': 30, 'q': '海港约定'}}),
                ('recall8', 'post', f'/api/souls/{sid}/recall', {'json': {'query': '海港约定', 'max_chars': 4000}}),
            ):
                times = []; peaks = []; sizes = []
                for _ in range(7):
                    tracemalloc.start(); start = time.perf_counter()
                    response = getattr(client, method)(url, **options)
                    times.append((time.perf_counter()-start)*1000)
                    peaks.append(tracemalloc.get_traced_memory()[1]); tracemalloc.stop()
                    assert response.status_code == 200, response.text
                    sizes.append(len(response.content))
                scenarios[name] = {'median_ms': round(statistics.median(times), 2), 'max_ms': round(max(times), 2),
                    'response_bytes': max(sizes), 'python_traced_peak_bytes': max(peaks)}
            with engine.connect() as conn:
                plan = [list(x) for x in conn.exec_driver_sql('EXPLAIN QUERY PLAN SELECT id FROM soul_memories WHERE soul_id=1 ORDER BY id DESC LIMIT 30')]
                logical_bytes = conn.exec_driver_sql('PRAGMA page_count').scalar() * conn.exec_driver_sql('PRAGMA page_size').scalar()
            results.append({'rows': total, 'seed_ms': round(seed_ms, 2), 'scenarios': scenarios,
                            'database_logical_bytes': logical_bytes, 'query_plan': plan})
            count = total
    report = {'python': platform.python_version(), 'sqlite': sqlite3.sqlite_version,
              'scope': 'Generated ASGI metadata/FTS, 7 sequential samples. Not browser/GPU/RSS or historical snapshot cost.', 'results': results}
    (root/'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=True))


if __name__ == '__main__':
    main()
