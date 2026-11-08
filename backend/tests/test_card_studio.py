"""Generated content, real database/files, protocol-only AI. No actual inference."""
import base64
import hashlib
import io
import json
import time
import threading
import uuid

import httpx
import pytest
from PIL import Image

from conftest import png_bytes
from front_api import cardassist, cardstudio, jobs, models as m
from front_api.ai import registry
from front_api.db import new_session, get_engine


def saved(client, fields, card_id=None, expected=None, draft_id=None):
    r = client.post('/api/cards/save-reviewed', json={'card': fields, 'card_id': card_id, 'expected': expected, 'draft_id': draft_id})
    r.raise_for_status()
    return r.json()


def wait(client, draft_id):
    for _ in range(300):
        row = client.get('/api/cards/assist/drafts/' + draft_id).json()
        if row['status'] not in ('queued', 'running'):
            return row
        time.sleep(.01)
    pytest.fail('draft timeout')


@pytest.fixture()
def ai(client):
    pid = client.post('/api/ai/providers', json={'name': 'Generated protocol provider', 'base_url': 'http://127.0.0.1:12345/v1', 'chat_model': 'generated-text', 'api_key': 'generated-private-key'}).json()['id']
    seen = []
    def handler(request):
        seen.append(json.loads(request.content))
        return httpx.Response(200, json={'choices': [{'message': {'content': json.dumps({'name': 'Generated Librarian', 'description': 'Generated suggestion', 'first_mes': 'Hello, {{user}}', 'card_tags': ['generated']})}}]})
    registry.transport_override[pid] = httpx.MockTransport(handler)
    yield pid, seen
    registry.transport_override.pop(pid, None)


def generate(client, pid, **changes):
    body = {'provider_id': pid, 'brief': 'Generated fictional librarian, no source novel', 'style': 'concise'}
    prepared = client.post('/api/cards/assist/prepare', json=body)
    prepared.raise_for_status()
    payload = {**body, 'request_hash': prepared.json()['request_hash'], 'request_id': uuid.uuid4().hex, 'confirm_send': True, **changes}
    r = client.post('/api/cards/assist/generate', json=payload)
    return prepared.json(), payload, r


def test_import_rejects_wrong_types_before_any_records(client):
    for payload in ({'name': {'bad': 'type'}}, {'name': 'x' * 201}, {'name': '  '},
                    {'name': 'Valid', 'description': []}, {'name': 'Valid', 'tags': [7]},
                    {'name': 'Valid', 'creator': ['wrong']}, {'name': 'Valid', 'alternate_greetings': [None]}):
        r = client.post('/api/cards/import', files={'file': ('generated.json', json.dumps(payload).encode(), 'application/json')})
        assert r.status_code == 422, r.text
    assert client.get('/api/cards').json()['total'] == 0
    assert client.get('/api/assets').json()['total'] == 0
    assert client.get('/api/lorebooks').json()['total'] == 0
    assert client.post('/api/cards', json={'name': 'Card', 'character_id': 999}).status_code == 422
    card = saved(client, {'name': 'Stable'})['card']
    assert client.patch(f"/api/cards/{card['id']}", json={'name': None}).status_code == 422
    assert client.get(f"/api/cards/{card['id']}").json()['name'] == 'Stable'


def test_import_budgets_and_invalid_book_roll_back(client, monkeypatch):
    monkeypatch.setattr(cardstudio, 'MAX_IMPORT', 128)
    assert client.post('/api/cards/import', files={'file': ('generated.json', b'x' * 129, 'application/json')}).status_code == 413
    monkeypatch.setattr(cardstudio, 'MAX_IMPORT', 16 * 1024 * 1024)
    data = {'spec': 'chara_card_v2', 'data': {'name': 'Generated', 'character_book': {'entries': [{'content': 'x', 'priority': 'wrong'}]}}}
    assert client.post('/api/cards/import', files={'file': ('generated.json', json.dumps(data).encode(), 'application/json')}).status_code == 422
    assert client.get('/api/cards').json()['total'] == client.get('/api/lorebooks').json()['total'] == 0


def test_png_import_keeps_shared_cover_and_exports_pixels(client):
    payload = {'name': 'Generated color', 'description': 'Generated text', 'extensions': {'custom': {'kept': True}}}
    raw = png_bytes(color=(20, 140, 80), text={'chara': base64.b64encode(json.dumps(payload).encode()).decode()})
    ids = []
    for _ in range(2):
        r = client.post('/api/cards/import', files={'file': ('generated.png', raw, 'image/png')})
        assert r.status_code == 201, r.text
        ids.append(r.json()['avatar_asset_id'])
    assert ids[0] == ids[1] and client.get('/api/assets').json()['total'] == 1
    card = client.get('/api/cards').json()['items'][0]
    assert card['extensions']['custom'] == {'kept': True} and card['character_id'] is None
    exported = client.get(f"/api/cards/{card['id']}/export.png")
    assert exported.status_code == 200
    assert Image.open(io.BytesIO(exported.content)).getpixel((0, 0)) == (20, 140, 80)
    assert client.get(f"/api/versions/card/{card['id']}").json()['total'] == 1


def test_indexed_cover_export_reads_original_without_copy_and_detects_changes(client, tmp_path):
    from front_api.ingest import index_file
    raw = png_bytes(color=(10, 30, 60))
    path = tmp_path / 'generated.png'
    path.write_bytes(raw)
    sha = hashlib.sha256(raw).hexdigest()
    with new_session() as session:
        asset, _ = index_file(session, path, tmp_path, sha)
        session.commit()
        aid = asset.id
    card = saved(client, {'name': 'Indexed cover', 'avatar_asset_id': aid})['card']
    r = client.get(f"/api/cards/{card['id']}/export.png")
    assert r.status_code == 200 and Image.open(io.BytesIO(r.content)).getpixel((0, 0)) == (10, 30, 60)
    assert hashlib.sha256(path.read_bytes()).hexdigest() == sha
    assert client.get(f'/api/assets/{aid}').json()['file_path'] is None
    path.write_bytes(png_bytes(color=(60, 30, 10)))
    assert client.get(f"/api/cards/{card['id']}/export.png").status_code == 409
    assert client.get(f"/api/cards/{card['id']}/export.json").status_code == 200


def test_reviewed_save_conflict_versions_and_summary_omit_body(client):
    a = saved(client, {'name': 'Generated card', 'description': 'a' * 20000, 'extensions': {'private': 'NOT_IN_SUMMARY'}})
    card_id = a['card']['id']
    b = saved(client, {'name': 'Generated card', 'description': 'new'}, card_id, a['expected'])
    assert client.post('/api/cards/save-reviewed', json={'card_id': card_id, 'expected': a['expected'], 'card': {'name': 'Stale'}}).status_code == 409
    history = client.get(f'/api/versions/card/{card_id}').json()
    assert history['total'] == 2
    old = history['items'][-1]['id']
    r = client.post(f'/api/versions/card/{card_id}/{old}/restore', json={'expected_latest': history['items'][0]['id']})
    assert r.status_code == 200
    assert client.get(f'/api/versions/card/{card_id}').json()['total'] == 3
    assert client.get(f'/api/cards/{card_id}').json()['description'] == 'a' * 20000
    page = client.get('/api/cards/summaries', params={'limit': 1})
    assert page.json()['total'] == 1 and len(page.content) < 1000
    assert 'description' not in page.json()['items'][0] and 'NOT_IN_SUMMARY' not in page.text


def test_world_source_and_restore_guards(client):
    w1, w2 = [client.post('/api/worlds', json={'name': 'Generated world ' + str(i)}).json()['id'] for i in range(2)]
    c1, c2 = [client.post('/api/characters', json={'name': 'Same Name', 'alias': 'Generated Alias、Other Alias', 'world_id': w}).json()['id'] for w in (w1, w2)]
    row = client.post(f'/api/cards/from-character/{c1}').json()
    assert row['extensions']['front_source_v1']['world_id'] == w1 and row['character_id'] == c1
    assert row['extensions']['front_design_v1']['aliases'] == ['Generated Alias', 'Other Alias']
    book = client.post('/api/lorebooks', json={'name': 'Other world', 'world_id': w2}).json()['id']
    assert client.patch(f"/api/cards/{row['id']}", json={'lorebook_id': book}).status_code == 422
    client.patch(f'/api/characters/{c1}', json={'world_id': w2}).raise_for_status()
    hist = client.get(f"/api/versions/card/{row['id']}").json()
    r = client.post(f"/api/versions/card/{row['id']}/{hist['items'][0]['id']}/restore", json={'expected_latest': hist['items'][0]['id']})
    assert r.status_code == 409
    assert client.get(f'/api/characters/{c2}').json()['world_id'] == w2


def test_ai_preview_exact_range_draft_review_and_idempotent_adoption(client, ai):
    pid, seen = ai
    client.post('/api/worlds', json={'name': 'Generated private world', 'content': 'NOT_SELECTED_WORLD_CONTENT'}).raise_for_status()
    prepared, payload, response = generate(client, pid)
    assert response.status_code == 202, response.text
    draft_id = response.json()['id']
    draft = wait(client, draft_id)
    assert draft['status'] == 'ready' and len(seen) == 1
    assert seen[0]['messages'] == prepared['messages'] and seen[0]['max_tokens'] == 2048
    assert 'NOT_SELECTED_WORLD_CONTENT' not in json.dumps(seen)
    assert 'generated-private-key' not in json.dumps(draft)
    assert client.get('/api/cards').json()['total'] == 0
    assert client.post('/api/cards/assist/generate', json=payload).json()['id'] == draft_id
    assert len(seen) == 1
    fields = {**draft['fields'], 'description': 'User reviewed rewrite'}
    a = saved(client, fields, draft_id=draft_id)
    b = saved(client, fields, draft_id=draft_id)
    assert b['repeated'] and a['card']['id'] == b['card']['id']
    assert a['card']['extensions']['front_assist_v1']['edited_fields'] == ['description']
    assert client.get('/api/cards').json()['total'] == 1 and client.get(f"/api/versions/card/{a['card']['id']}").json()['total'] == 1


def test_ai_prepare_changed_service_remote_opt_in_and_no_implicit_provider(client, ai):
    pid, seen = ai
    assert client.post('/api/cards/assist/prepare', json={'provider_id': 999, 'brief': 'Generated'}).status_code == 422
    body = {'provider_id': pid, 'brief': 'Generated only'}
    p = client.post('/api/cards/assist/prepare', json=body).json()
    client.patch(f'/api/ai/providers/{pid}', json={'chat_model': 'changed'}).raise_for_status()
    request = {**body, 'request_id': uuid.uuid4().hex, 'request_hash': p['request_hash'], 'confirm_send': True}
    assert client.post('/api/cards/assist/generate', json=request).status_code == 409
    client.patch(f'/api/ai/providers/{pid}', json={'base_url': 'https://generated.example.invalid/v1'}).raise_for_status()
    p = client.post('/api/cards/assist/prepare', json=body).json()
    assert p['remote'] is True
    request.update(request_hash=p['request_hash'])
    assert client.post('/api/cards/assist/generate', json=request).status_code == 422
    assert not seen and client.get('/api/cards/assist/drafts').json()['total'] == 0
    client.patch(f'/api/ai/providers/{pid}', json={'base_url': 'http://[invalid'}).raise_for_status()
    assert client.post('/api/cards/assist/prepare', json=body).status_code == 422
    assert client.get('/api/cards/choices', params={'kind': 'lorebook', 'world_id': 2**63}).status_code == 422


def test_ai_invalid_output_and_saturated_queue_preserve_cards(client, ai, monkeypatch):
    pid, seen = ai
    registry.transport_override[pid] = httpx.MockTransport(lambda req: httpx.Response(200, json={'choices': [{'message': {'content': '{"name":"Unsafe", "character_id":999}'}}]}))
    _, _, r = generate(client, pid)
    assert wait(client, r.json()['id'])['status'] == 'error'
    assert client.get('/api/cards').json()['total'] == 0
    from fastapi import HTTPException
    def full(*args):
        raise HTTPException(429, 'generated queue full')
    monkeypatch.setattr(jobs, 'start', full)
    _, _, r = generate(client, pid)
    assert r.status_code == 429 and client.get('/api/cards/assist/drafts').json()['total'] == 1


def test_cancel_discards_inflight_candidate_without_harming_old_card(client, ai):
    pid, _ = ai
    started, release = threading.Event(), threading.Event()
    def delayed(request):
        started.set()
        assert release.wait(5)
        return httpx.Response(200, json={'choices': [{'message': {'content': '{"name":"Generated delayed"}'}}]})
    registry.transport_override[pid] = httpx.MockTransport(delayed)
    old = saved(client, {'name': 'Stable original'})['card']
    _, _, response = generate(client, pid)
    try:
        assert started.wait(3)
        client.post(f"/api/cards/assist/drafts/{response.json()['id']}/cancel").raise_for_status()
    finally:
        release.set()
    assert wait(client, response.json()['id'])['status'] == 'cancelled'
    assert client.get(f"/api/cards/{old['id']}").json()['name'] == 'Stable original'
    assert client.get('/api/cards').json()['total'] == 1


def test_oc_source_choices_ratings_and_png_budget(client):
    oc = client.post('/api/oc', json={'title': 'Generated OC', 'fields': {'appearance': 'Generated blue hair'}, 'designs': []}).json()
    r = client.post(f"/api/cards/from-oc/{oc['id']}")
    assert r.status_code == 201, r.text
    assert r.json()['extensions']['front_source_v1']['oc_id'] == oc['id']
    assert client.get('/api/cards/choices', params={'kind': 'oc', 'limit': 1}).json()['items'][0]['name'] == 'Generated OC'
    assert 'profile' not in client.get('/api/cards/choices', params={'kind': 'character'}).text
    for design in ({'schema': 1, 'stars': 6}, {'schema': 1, 'preference': True}, {'schema': 1, 'aliases': 'not-list'}):
        assert client.post('/api/cards', json={'name': 'Invalid design', 'extensions': {'front_design_v1': design}}).status_code == 422
    good = saved(client, {'name': 'Portable design', 'extensions': {'front_design_v1': {'schema': 1, 'aliases': ['GeneratedAliasToken'], 'stars': 4, 'preference': 85, 'favorite': True, 'appearance': '', 'custom': {'optional': None}}}})['card']
    assert client.get('/api/cards/summaries', params={'q': 'GeneratedAliasToken'}).json()['items'][0]['id'] == good['id']
    assert any(r['entity'] == 'card' and r['id'] == good['id'] for r in client.get('/api/search', params={'q': 'GeneratedAliasToken'}).json())
    assert client.get(f"/api/cards/{good['id']}/export.json").json()['data']['extensions']['front_design_v1']['preference'] == 85
    with cardstudio.image_operation():
        assert client.get(f"/api/cards/{good['id']}/export.png").status_code == 429
        assert client.post('/api/cards/import', files={'file': ('generated.json', b'{"name":"Generated"}', 'application/json')}).status_code == 429
    assert client.get(f"/api/cards/{good['id']}/export.png").status_code == 200


def test_draft_backup_isolated_restore_and_restart_does_not_replay(client, data_dir, ai):
    import sqlite3
    from pathlib import Path
    from front_api import backups, dbbackup
    from front_api.config import get_settings
    from front_api.db import Base
    from test_backups import wait as wait_job
    card = saved(client, {'name': 'Generated pre-upgrade card'})['card']
    engine = get_engine()
    m.CharacterCardDraft.__table__.drop(engine)
    dbbackup.before_schema_change(get_settings())
    Base.metadata.create_all(engine)
    snapshots = list((data_dir / 'backups').glob('pre-schema-*/front.db'))
    with sqlite3.connect(snapshots[-1]) as db:
        assert db.execute('SELECT name FROM character_cards WHERE id=?', (card['id'],)).fetchone()[0] == 'Generated pre-upgrade card'
        assert db.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
    pid, seen = ai
    _, _, response = generate(client, pid)
    ready = wait(client, response.json()['id'])
    assert ready['status'] == 'ready'
    with new_session() as session:
        session.add(m.CharacterCardDraft(id='d' * 32, request_hash='e' * 64, status='queued'))
        session.commit()
    cardassist.recover(engine)
    assert client.get('/api/cards/assist/drafts/' + 'd' * 32).json()['status'] == 'interrupted'
    assert len(seen) == 1
    backed = wait_job(client, client.post('/api/backups', json={}).json())
    assert backed['status'] == 'done'
    package = backups.package_for(backed['result']['backup_id'])
    restored = wait_job(client, client.post('/api/backups/restore', json={'path': str(package), 'confirmed': True}).json())
    assert restored['status'] == 'done', restored
    with sqlite3.connect(Path(restored['result']['path']) / 'front.db') as db:
        assert db.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
        assert not db.execute('PRAGMA foreign_key_check').fetchall()
        assert json.loads(db.execute('SELECT fields FROM character_card_drafts WHERE id=?', (ready['id'],)).fetchone()[0])['name'] == 'Generated Librarian'


def test_stale_poll_does_not_overwrite_completed_draft(client, monkeypatch):
    draft_id = 'f' * 32
    with new_session() as session:
        session.add(m.CharacterCardDraft(id=draft_id, request_hash='e' * 64, status='running', job_id='generated-job'))
        session.commit()
    terminal = jobs.Job('card-assist', 'Generated terminal')
    terminal.status = 'done'
    monkeypatch.setattr(jobs, 'get', lambda identity: terminal)
    with new_session() as stale:
        row = stale.get(m.CharacterCardDraft, draft_id)
        assert row.status == 'running'
        with new_session() as worker:
            actual = worker.get(m.CharacterCardDraft, draft_id)
            actual.fields, actual.status = {'name': 'Generated completed'}, 'ready'
            worker.commit()
        assert cardassist.reconcile(row) is False
        stale.commit()
        assert row.status == 'ready' and row.fields['name'] == 'Generated completed'
    assert client.get('/api/cards/assist/drafts/' + draft_id).json()['status'] == 'ready'
