"""Generated records and mocked HTTP only; no private files or actual AI calls."""
import hashlib
import json
import threading
import time

import httpx
import pytest

from front_api import jobs, matching, metadata as md
from front_api.galgame import meta, sources


@pytest.fixture()
def remote(monkeypatch):
    requests = []
    def handler(request):
        requests.append(request)
        if request.url.path == '/search.json':
            return httpx.Response(200, json={'docs': [
                {'key': '/works/OL10W', 'title': 'Generated Harbor', 'author_name': ['Test Author'], 'cover_i': 5},
                {'key': '/works/OL11W', 'title': 'Generated Harbor', 'author_name': ['Test Author']},
                {'key': '/works/OL12W', 'title': 'Generated Harbor Fan Disc', 'author_name': ['Another Author']}]})
        if request.url.path.startswith('/works/OL'):
            return httpx.Response(200, json={'title': 'Generated Harbor', 'description': {'value': 'Generated public metadata'},
                                            'subjects': ['Fiction', 'Study'], 'covers': [5]})
        return httpx.Response(404)
    monkeypatch.setattr(md, 'client_factory', lambda: httpx.Client(transport=httpx.MockTransport(handler)))
    # Avoid wall-clock sleeps in independent protocol tests. Production gates are tested separately.
    md._last.clear()
    return requests


def done(client, job):
    for _ in range(200):
        data = client.get(f"/api/jobs/{job['id']}").json()
        if data['status'] not in ('queued', 'running'):
            return data
        time.sleep(.02)
    pytest.fail('metadata job did not complete')


def details(client):
    data = done(client, client.post('/api/metadata/detail', json={'online': True, 'kind': 'book', 'provider': 'openlibrary', 'sid': 'OL10W'}).json())
    assert data['status'] == 'done', data
    return data['result']['results']['openlibrary']


def work(client):
    return client.post('/api/works', json={'title': 'Local title', 'kind': 'novel'}).json()['id']


def state(client, wid, kind='work'):
    response = client.get(f'/api/metadata/targets/{kind}/{wid}')
    response.raise_for_status()
    return response.json()


def test_public_search_is_bounded_explicit_and_ambiguous(client, remote):
    assert client.post('/api/metadata/search', json={'kind': 'book', 'title': 'Generated Harbor', 'providers': ['openlibrary']}).status_code == 422
    r = client.post('/api/metadata/search', json={'online': True, 'kind': 'book', 'title': 'Generated Harbor', 'author': 'Test Author', 'providers': ['openlibrary']})
    assert r.status_code == 202
    data = done(client, r.json())
    rows = data['result']['results']['openlibrary']['items']
    assert data['status'] == 'done' and len(rows) == 3
    assert rows[0]['match']['ambiguous'] and rows[1]['match']['ambiguous']
    assert rows[2]['match']['tier'] == 'weak' and rows[2]['match']['requires_confirmation']
    assert len(remote) == 1
    assert dict(remote[0].url.params) == {'title': 'Generated Harbor', 'limit': '10', 'fields': 'key,title,author_name,first_publish_year,cover_i', 'author': 'Test Author'}
    assert 'Fiesty-Abyss/Front' in remote[0].headers['User-Agent']
    assert not any('covers.' in str(r.url) for r in remote)


def test_provenance_manual_fields_history_restore_and_idempotence(client, remote):
    wid = work(client)
    detail = details(client)
    initial = state(client, wid)
    payload = {'expected': initial['expected'], 'receipt': detail['receipt'], 'fields': ['description', 'tags'], 'allow_refresh': ['description']}
    result = client.post(f'/api/metadata/targets/work/{wid}/apply', json=payload)
    assert result.status_code == 200, result.text
    updated = result.json()
    assert updated['changed'] and updated['values']['title'] == 'Local title'
    field = updated['catalog']['fields']['description']
    assert field['provider'] == 'openlibrary' and field['source_id'] == 'OL10W' and field['raw_value'] == 'Generated public metadata' and field['allow_refresh']
    history = client.get(f'/api/versions/work/{wid}').json()
    assert history['total'] == 2
    payload['expected'] = updated['expected']
    assert client.post(f'/api/metadata/targets/work/{wid}/apply', json=payload).json()['changed'] is False
    assert client.get(f'/api/versions/work/{wid}').json()['total'] == 2
    old = history['items'][-1]['id']
    restored = client.post(f'/api/versions/work/{wid}/{old}/restore', json={'expected_latest': history['items'][0]['id']})
    assert restored.status_code == 200, restored.text
    assert client.get(f'/api/works/{wid}').json()['description'] is None
    assert client.get(f'/api/versions/work/{wid}').json()['total'] == 3
    assert len(remote) == 1  # Restore and apply are local, never re-fetch.


def test_manual_replacement_stale_target_and_atomic_failure(client, remote):
    wid = work(client)
    detail = details(client)
    initial = state(client, wid)
    payload = {'expected': initial['expected'], 'receipt': detail['receipt'], 'fields': ['title', 'description']}
    assert client.post(f'/api/metadata/targets/work/{wid}/apply', json=payload).status_code == 409
    assert client.get(f'/api/works/{wid}').json()['description'] is None
    assert client.get(f'/api/versions/work/{wid}').json()['total'] == 0
    payload['replace'] = ['title']
    assert client.post(f'/api/metadata/targets/work/{wid}/apply', json=payload).status_code == 200
    assert client.post(f'/api/metadata/targets/work/{wid}/apply', json=payload).status_code == 409
    current = state(client, wid)
    client.patch(f'/api/works/{wid}', json={'description': ''}).raise_for_status()
    payload.update(expected=current['expected'], fields=['description'], replace=[])
    assert client.post(f'/api/metadata/targets/work/{wid}/apply', json=payload).status_code == 409
    payload['expected'] = state(client, wid)['expected']
    assert client.post(f'/api/metadata/targets/work/{wid}/apply', json=payload).status_code == 409  # Manual clearing is protected too.


def test_refresh_permission_only_unchanged_source_fields(client, remote, monkeypatch):
    wid = work(client)
    detail = details(client)
    first = client.post(f'/api/metadata/targets/work/{wid}/apply', json={'expected': state(client, wid)['expected'], 'receipt': detail['receipt'], 'fields': ['description'], 'allow_refresh': ['description']}).json()
    new = json.loads(json.dumps(detail))
    new['receipt'] = 'a' * 32
    new['item']['description'] = 'Updated public metadata'
    md._save(new['receipt'], new)
    payload = {'expected': first['expected'], 'receipt': new['receipt'], 'fields': ['description'], 'allow_refresh': ['description']}
    assert client.post(f'/api/metadata/targets/work/{wid}/apply', json=payload).status_code == 200
    client.patch(f'/api/works/{wid}', json={'description': 'Personal rewrite'}).raise_for_status()
    assert state(client, wid)['catalog']['fields']['description']['manual'] is True
    payload['expected'] = state(client, wid)['expected']
    assert client.post(f'/api/metadata/targets/work/{wid}/apply', json=payload).status_code == 409


def test_expired_fabricated_receipts_type_isolation_and_offline(client, remote, monkeypatch):
    wid = work(client)
    detail = details(client)
    payload = {'expected': state(client, wid)['expected'], 'receipt': 'f' * 32, 'fields': ['description']}
    assert client.post(f'/api/metadata/targets/work/{wid}/apply', json=payload).status_code == 410
    payload['receipt'] = detail['receipt']
    client.patch(f'/api/works/{wid}', json={'kind': 'anime'}).raise_for_status()
    payload['expected'] = state(client, wid)['expected']
    assert client.post(f'/api/metadata/targets/work/{wid}/apply', json=payload).status_code == 409
    for endpoint, body in [('search', {'title': 'x', 'providers': ['vndb']}), ('detail', {'provider': 'openlibrary', 'sid': '../bad'})]:
        assert client.post('/api/metadata/' + endpoint, json={'online': True, 'kind': 'book', **body}).status_code == 422
    assert client.get(f'/api/metadata/targets/work/{2**63}').status_code == 422
    monkeypatch.setenv('FRONT_METADATA', 'off')
    assert client.post('/api/metadata/search', json={'online': True, 'kind': 'book', 'title': 'x', 'providers': ['openlibrary']}).status_code == 403
    assert client.get(f'/api/works/{wid}').status_code == 200
    assert len(remote) == 1


def test_partial_sources_failure_redacts_secrets_and_cancel(client, remote, monkeypatch):
    def fail(*args):
        raise httpx.ConnectError('https://secret:password@example.invalid/private?api_key=hidden')
    monkeypatch.setattr(sources, 'search', lambda name, *args: fail() if name == 'vndb' else [{'sid': '10', 'title': 'Generated Game'}])
    data = done(client, client.post('/api/metadata/search', json={'online': True, 'kind': 'game', 'title': 'Generated Game', 'providers': ['bangumi', 'vndb']}).json())
    assert data['status'] == 'done' and 'bangumi' in data['result']['results'] and 'vndb' in data['result']['errors']
    assert 'password' not in json.dumps(data) and 'hidden' not in json.dumps(data)
    job = jobs.Job('metadata-search', 'generated')
    job.cancel_requested = True
    with pytest.raises(jobs.Cancelled):
        md.run(job, 'search', {'providers': ['openlibrary'], 'title': 'Generated', 'kind': 'book'}, {})
    assert not remote


def test_response_size_json_schema_and_redirect_refusal(client, monkeypatch):
    for response in (httpx.Response(200, content=b'x' * (md.MAX_RESPONSE + 1)), httpx.Response(200, json=[]), httpx.Response(302, headers={'Location': 'http://127.0.0.1/private'})):
        calls = []
        def handler(request):
            calls.append(request)
            return response
        monkeypatch.setattr(md, 'client_factory', lambda: httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=False))
        with pytest.raises((ValueError, httpx.HTTPStatusError)):
            md._json('/search.json')
        assert len(calls) == 1


def test_legacy_prefixes_and_ambiguous_ids_are_not_auto_matches(monkeypatch):
    query = {'title': 'Generated Story', 'date': '2020-01-01'}
    for rows in ([{'sid': '1', 'title': 'Generated Story Fan Disc', 'date': '2020'}],
                 [{'sid': '1', 'title': 'Generated Story'}, {'sid': '2', 'title': 'Generated Story'}],
                 [{'sid': '1', 'title': 'Generated Story', 'date': '2030'}]):
        monkeypatch.setattr(sources, 'search', lambda *args: rows)
        assert not meta.auto_match(query, ['vndb'], meta.DEFAULTS)['vndb'].get('sid')
    assert matching.confidence('Story', {'title': 'Story II'})['tier'] == 'weak'
    assert matching.confidence('A+B', {'title': 'AB'})['tier'] == 'weak'
    assert matching.confidence('Story', {'title': 'Story', 'authors': ['Another']}, 'Writer')['tier'] == 'weak'


def test_galgame_apply_preserves_legacy_overrides_and_manual_cover(client, remote):
    from front_api import models as m
    from front_api.db import new_session
    from front_api.routers.galgames import _apply_meta, _download_cover
    gid = client.post('/api/galgames', json={'title': 'Local Game', 'notes': 'Private note'}).json()['id']
    item = {'provider': 'bangumi', 'sid': '123', 'kind': 'game', 'title': 'Generated Game', 'description': 'Generated description', 'url': 'https://bgm.tv/subject/123'}
    md._save('b' * 32, {'receipt': 'b' * 32, 'item': item, 'fetched_at': '2026-11-08T00:00:00Z'})
    r = client.post(f'/api/metadata/targets/galgame/{gid}/apply', json={'expected': state(client, gid, 'galgame')['expected'], 'receipt': 'b' * 32, 'fields': ['description']})
    assert r.status_code == 200, r.text
    assert client.get(f'/api/versions/galgame/{gid}').json()['total'] == 2
    from conftest import png_bytes
    client.put(f'/api/galgames/{gid}/cover', files={'file': ('generated.png', png_bytes(), 'image/png')}).raise_for_status()
    with new_session() as session:
        game = session.get(m.Galgame, gid)
        _apply_meta(game, {'description': 'Remote overwrite', 'cover_url': 'https://lain.bgm.tv/generated.png'})
        assert game.description == 'Generated description' and game.notes == 'Private note'
        assert _download_cover(game).startswith('保留手动')


def test_cached_detail_is_read_only_and_preserves_missing_edition_facts(client, remote):
    a, b = details(client), details(client)
    assert a == b and len(remote) == 1
    assert a['item']['publisher'] is None and a['item']['year'] is None
    assert client.get('/api/works').json()['total'] == 0
    assert client.get('/api/galgames').json()['total'] == 0
    assert not a['item']['authors']  # Work author keys are not invented names.


def test_model_hash_provider_reuses_existing_lookup_without_weights(client, monkeypatch):
    from front_api import civitai
    sha = 'c' * 64
    calls = []
    def lookup(value):
        calls.append(value)
        return {'id': 5, 'modelId': 4, 'name': 'Generated v1', 'baseModel': 'SDXL 1.0', 'trainedWords': ['generated'],
                'model': {'name': 'Generated LoRA', 'type': 'LORA'}, 'files': [{'hashes': {'SHA256': sha}}]}
    monkeypatch.setattr(civitai, 'lookup', lookup)
    data = done(client, client.post('/api/metadata/search', json={'online': True, 'kind': 'model', 'title': sha, 'providers': ['civitai']}).json())
    item = data['result']['results']['civitai']['items'][0]
    assert item['match']['tier'] == 'exact' and item['model_type'] == 'LORA' and item['version_id'] == '5'
    assert calls == [sha] and client.get('/api/sd-models').json()['total'] == 0
    assert client.post('/api/metadata/search', json={'online': True, 'kind': 'model', 'title': 'not-a-hash', 'providers': ['civitai']}).status_code == 422
    with pytest.raises(ValueError, match='hash mismatch'):
        md.CivitaiProvider().detail('d' * 64, 'model')


def test_detail_cache_retries_if_receipt_evicted(client, remote):
    first = details(client)
    (md.cache_dir() / (first['receipt'] + '.json')).unlink()
    second = details(client)
    assert first['receipt'] != second['receipt'] and len(remote) == 2


def test_queue_saturation_does_not_write_targets(client, remote, monkeypatch):
    from fastapi import HTTPException
    def full(*args):
        raise HTTPException(429, 'generated queue full')
    monkeypatch.setattr(jobs, 'start', full)
    assert client.post('/api/metadata/search', json={'online': True, 'kind': 'book', 'title': 'Generated', 'providers': ['openlibrary']}).status_code == 429
    assert not remote and client.get('/api/works').json()['total'] == 0


def test_additive_catalog_upgrade_and_isolated_full_restore(client, data_dir, remote):
    import sqlite3
    from pathlib import Path
    from front_api import backups, dbbackup
    from front_api.config import get_settings
    from front_api.db import get_engine
    from front_api.migrate import upgrade
    from test_backups import wait
    wid = work(client)
    engine = get_engine()
    with engine.begin() as conn:
        conn.exec_driver_sql('ALTER TABLE works DROP COLUMN metadata_catalog')
        conn.exec_driver_sql('ALTER TABLE galgames DROP COLUMN metadata_catalog')
    dbbackup.before_schema_change(get_settings())
    assert set(upgrade(engine)) == {'works.metadata_catalog', 'galgames.metadata_catalog'}
    snapshots = list((data_dir / 'backups').glob('pre-schema-*/front.db'))
    assert snapshots
    with sqlite3.connect(snapshots[-1]) as db:
        assert db.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
        assert db.execute('SELECT title FROM works WHERE id=?', (wid,)).fetchone()[0] == 'Local title'
        assert 'metadata_catalog' not in {r[1] for r in db.execute('PRAGMA table_info(works)')}
    preview = details(client)
    applied = client.post(f'/api/metadata/targets/work/{wid}/apply', json={'expected': state(client, wid)['expected'], 'receipt': preview['receipt'], 'fields': ['description']})
    assert applied.status_code == 200
    backup = wait(client, client.post('/api/backups', json={}).json())
    assert backup['status'] == 'done'
    package = backups.package_for(backup['result']['backup_id'])
    restored = wait(client, client.post('/api/backups/restore', json={'path': str(package), 'confirmed': True}).json())
    assert restored['status'] == 'done', restored
    with sqlite3.connect(Path(restored['result']['path']) / 'front.db') as db:
        assert db.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
        assert not db.execute('PRAGMA foreign_key_check').fetchall()
        catalog = json.loads(db.execute('SELECT metadata_catalog FROM works WHERE id=?', (wid,)).fetchone()[0])
        assert catalog['fields']['description']['source_id'] == 'OL10W'
        assert db.execute('SELECT count(*) FROM entity_versions').fetchone()[0] == 2


def test_legacy_quick_add_keeps_prefix_candidate_unmatched(client, monkeypatch):
    def search(*args):
        return {'order': ['bangumi'], 'results': {'bangumi': {'items': [{'source': 'bangumi', 'sid': '1', 'title': 'Generated Story Fan Disc'}]}}}
    monkeypatch.setattr(meta, 'search', search)
    r = client.post('/api/galgames/quick-add', json={'title': 'Generated Story'})
    assert r.status_code == 201 and r.json()['status'] == 'unmatched'
    assert client.get(f"/api/galgames/{r.json()['id']}").json()['sources'] == {}
