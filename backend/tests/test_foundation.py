import io
import json
import sqlite3
import threading
import time

import pytest
from fastapi import HTTPException
from sqlalchemy import event

from front_api.db import get_engine, new_session
from front_api.ingest import ingest_stream
from front_api.jobs import Manager


def wait_job(client, job_id):
    for _ in range(300):
        result = client.get(f"/api/jobs/{job_id}").json()
        if result["status"] not in ("queued", "running"):
            return result
        time.sleep(.01)
    pytest.fail("job did not finish")


def test_pagination_omits_body_but_detail_and_search_preserve_it(client):
    body = "unique-body-needle " * 3000
    ids = [client.post('/api/assets', json={"kind": "novel", "title": f"page {i}", "content": body}).json()['id'] for i in range(63)]
    queries = []
    def record(conn, cursor, statement, parameters, context, executemany):
        queries.append(statement)
    event.listen(get_engine(), 'before_cursor_execute', record)
    try:
        first = client.get('/api/assets?limit=60').json()
    finally:
        event.remove(get_engine(), 'before_cursor_execute', record)
    last = client.get('/api/assets?limit=60&offset=60').json()
    assert first['total'] == 63
    assert {x['id'] for x in first['items'] + last['items']} == set(ids)
    assert all(x['content'] is None for x in first['items'])
    data_query = next(q for q in queries if 'LIMIT' in q and 'assets' in q)
    assert 'assets.content' not in data_query
    assert client.get(f'/api/assets/{ids[0]}').json()['content'] == body
    assert client.get('/api/assets?q=unique-body-needle').json()['total'] == 63
    assert client.get('/api/assets?year=invalid').status_code == 422


def test_stream_bounded_duplicate_and_size_limit(client, data_dir, monkeypatch):
    class Bounded(io.BytesIO):
        def read(self, size=-1):
            assert 0 < size <= 1024 * 1024
            return super().read(size)
    content = b'bounded-blob' * 300000
    with new_session() as session:
        a, created = ingest_stream(session, Bounded(content), 'large.dat')
        session.commit()
        assert created and (data_dir / a.file_path).read_bytes() == content
        duplicate, created = ingest_stream(session, Bounded(content), 'same.dat')
        assert not created and duplicate.id == a.id
    from front_api.config import get_settings
    monkeypatch.setenv('FRONT_MAX_UPLOAD_MB', '1')
    get_settings.cache_clear()
    with new_session() as session, pytest.raises(HTTPException) as exc:
        ingest_stream(session, Bounded(content), 'too-big.dat')
    assert exc.value.status_code == 413
    assert not list((data_dir / '.staging').iterdir())
    get_settings.cache_clear()


def test_job_capacity_cancel_history_and_restart(tmp_path):
    mgr = Manager(tmp_path / 'jobs.sqlite3', workers=1, queue_size=1)
    gate, entered = threading.Event(), threading.Event()
    def work(job):
        entered.set()
        assert gate.wait(5)
        job.step()
    first = mgr.start('test', 'first', 1, work)
    assert entered.wait(5)
    second = mgr.start('test', 'queued', 1, lambda job: pytest.fail('cancelled callback ran'))
    try:
        with pytest.raises(HTTPException) as exc:
            mgr.start('test', 'overflow', 0, work)
        assert exc.value.status_code == 429
        second.cancel_requested = True
    finally:
        gate.set()
        mgr.shutdown()
    assert second.status == 'cancelled'
    recovered = Manager(mgr.path)
    assert recovered.jobs[second.id].status == 'cancelled'
    assert recovered.executor is None
    record = first.to_dict() | {'status': 'running', 'result': {'committed': 3}}
    with sqlite3.connect(mgr.path) as db:
        db.execute('UPDATE jobs SET snapshot=? WHERE id=?', (json.dumps(record), first.id))
    restarted = Manager(mgr.path)
    assert restarted.jobs[first.id].status == 'interrupted'
    assert restarted.jobs[first.id].result == {'committed': 3}
    assert restarted.executor is None


def test_background_import_originals_duplicates_history(client, tmp_path):
    source = tmp_path / 'originals'
    source.mkdir()
    for i in range(3):
        (source / f'{i}.txt').write_text(f'original {i}', encoding='utf-8')
    payload = {'path': str(source)}
    response = client.post('/api/import/jobs', json=payload)
    assert response.status_code == 200
    result = wait_job(client, response.json()['id'])
    assert result['status'] == 'done'
    assert result['result']['created'] == 3
    again = wait_job(client, client.post('/api/import/jobs', json=payload).json()['id'])
    assert again['result']['created'] == 0
    assert len(again['result']['duplicates']) == 3
    for i in range(3):
        assert (source / f'{i}.txt').read_text(encoding='utf-8') == f'original {i}'
    assert len(client.get('/api/jobs?kind=import').json()) == 2
