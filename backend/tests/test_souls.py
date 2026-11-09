"""Generated fictional data only. No AI, personal library or external services."""
import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy import select

from front_api import backups, jobs, models as m, souls, versions
from front_api.db import new_session
from front_api.main import create_app


def post(c, url, data):
    r = c.post(url, json=data)
    assert r.status_code in (200, 201), r.text
    return r.json()


def soul(c, name='虚构灯塔守望者', world_id=None):
    return post(c, '/api/souls', {'name': name, 'world_id': world_id})


def memory(c, sid, **data):
    return post(c, f'/api/souls/{sid}/memories', {'kind': 'suggestion', 'content': '虚构角色约定在灯塔见面', **data})


def patch(c, sid, row, **data):
    r = c.patch(f'/api/souls/{sid}/memories/{row["id"]}', json={'expected_revision': row['revision'], **data})
    assert r.status_code == 200, r.text
    return r.json()


def recall(c, sid, **data):
    return post(c, f'/api/souls/{sid}/recall', data)


def linked_chat(c, sid, world_id=None):
    char = post(c, '/api/characters', {'name': '相同名字', 'world_id': world_id})
    card = post(c, '/api/cards', {'name': '灯塔角色卡', 'character_id': char['id']})
    post(c, f'/api/souls/{sid}/links', {'kind': 'character', 'target_id': char['id']})
    post(c, f'/api/souls/{sid}/links', {'kind': 'card', 'target_id': card['id']})
    chat = post(c, '/api/ai/sessions', {'card_id': card['id'], 'title': '虚构航行'})
    post(c, f'/api/souls/{sid}/links', {'kind': 'chat', 'target_id': chat['id']})
    with new_session() as db:
        a = m.ChatMessage(session_id=chat['id'], role='user', content='我们在灯塔见面。')
        db.add(a); db.flush()
        b = m.ChatMessage(session_id=chat['id'], parent_id=a.id, role='assistant', content='虚构剧情：我记下了约定。')
        other = m.ChatMessage(session_id=chat['id'], parent_id=a.id, role='assistant', content='平行剧情：我们没有见面。')
        db.add_all([b, other]); db.flush()
        db.get(m.ChatSession, chat['id']).head_id = b.id
        db.commit()
        return char, card, chat, a.id, b.id, other.id


def test_manual_review_edit_conflict_pin_literal_search_and_bounded_preview(client):
    s = soul(client); sid = s['id']
    a = memory(client, sid)
    assert a['review'] == 'pending' and not a['allow_injection']
    assert not recall(client, sid)['items']
    a = patch(client, sid, a, review='approved', allow_injection=True, pinned=True)
    preview = recall(client, sid, query='不存在的关键词')
    assert preview['items'][0]['uid'] == a['uid']
    assert preview['sent_to_ai'] is False and len(preview['context']) == preview['chars']
    assert preview['items'][0]['source']['origin'] == 'user'
    assert recall(client, sid, max_chars=64)['chars'] <= 64
    long_row = memory(client, sid, content='长段落测试' * 100)
    long_row = patch(client, sid, long_row, review='approved', allow_injection=True)
    assert all(x['id'] != long_row['id'] for x in recall(client, sid, query='长段落', max_chars=64)['items'])
    patch(client, sid, long_row, active=False)
    a = patch(client, sid, a, content='新的虚构约定 100%_literal')
    assert a['review'] == 'pending' and not a['allow_injection']
    a = patch(client, sid, a, review='approved', allow_injection=True, pinned=False)
    for term in ('虚构约定', '%_', '" OR *'):
        rows = client.get(f'/api/souls/{sid}/memories', params={'q': term}).json()['items']
        assert bool(rows) == (term != '" OR *')
    a = patch(client, sid, a, conflict=True, conflict_note='平行版本尚待确认')
    assert not a['allow_injection'] and not recall(client, sid)['items']
    a = patch(client, sid, a, conflict=False, allow_injection=True)
    assert recall(client, sid)['items']
    a = patch(client, sid, a, active=False)
    assert not recall(client, sid)['items']
    assert not client.get(f'/api/souls/{sid}/memories').json()['items']
    assert client.get(f'/api/souls/{sid}/memories', params={'include_inactive': True}).json()['items']
    history = client.get(f'/api/versions/soul_memory/{a["id"]}').json()
    assert history['enabled'] and history['total'] >= 7


def test_world_identity_same_name_isolation_and_reference_reuse(client):
    w1 = post(client, '/api/worlds', {'name': '同名世界'})['id']
    w2 = post(client, '/api/worlds', {'name': '同名世界'})['id']
    s1 = soul(client, '同名人物', w1); s2 = soul(client, '同名人物', w2)
    c1 = post(client, '/api/characters', {'name': '同名人物', 'world_id': w1})
    c2 = post(client, '/api/characters', {'name': '同名人物', 'world_id': w2})
    url = f'/api/souls/{s1["id"]}/links'
    post(client, url, {'kind': 'character', 'target_id': c1['id']})
    assert client.post(url, json={'kind': 'character', 'target_id': c2['id']}).status_code == 409
    a = patch(client, s1['id'], memory(client, s1['id']), review='approved', allow_injection=True)
    assert not recall(client, s2['id'])['items']
    client.delete(f'/api/characters/{c1["id"]}')
    c3 = post(client, '/api/characters', {'name': '另一个人', 'world_id': w1})
    # The specific max-row ID reuse scenario is tested separately below.
    links = client.get(f'/api/souls/{s1["id"]}').json()['links']
    assert links[0]['diagnostic']
    client.delete(f'/api/worlds/{w1}')
    assert client.get(f'/api/souls/{s1["id"]}').json()['diagnostic']
    assert client.post(f'/api/souls/{s1["id"]}/recall', json={}).status_code == 409


def test_deleted_reused_numeric_id_never_attaches_old_memory(client):
    s = soul(client); sid = s['id']
    char = post(client, '/api/characters', {'name': '旧角色', 'profile': '旧正式设定'})
    post(client, f'/api/souls/{sid}/links', {'kind': 'character', 'target_id': char['id']})
    row = memory(client, sid, kind='core', source={'kind': 'character', 'id': char['id']})
    row = patch(client, sid, row, review='approved', allow_injection=True)
    assert recall(client, sid)['items']
    client.delete(f'/api/characters/{char["id"]}')
    new = post(client, '/api/characters', {'name': '新角色', 'profile': '另一人'})
    assert new['id'] == char['id']
    assert not recall(client, sid)['items']
    rows = client.get(f'/api/souls/{sid}/memories').json()['items']
    assert rows[0]['diagnostic']
    hist = client.get(f'/api/versions/soul_memory/{row["id"]}').json()['items']
    assert client.post(f'/api/versions/soul_memory/{row["id"]}/{hist[-1]["id"]}/restore',
                       json={'expected_latest': hist[0]['id']}).status_code == 409


def test_multiple_chats_branch_ancestry_scope_and_source_tampering(client):
    sid = soul(client)['id']
    char, card, chat, a, b, other = linked_chat(client, sid)
    row = memory(client, sid, kind='episode', scope='branch', session_id=chat['id'],
                 branch_head_id=b, source={'kind': 'message', 'id': a})
    row = patch(client, sid, row, review='approved', allow_injection=True)
    assert not recall(client, sid)['items']
    assert len(recall(client, sid, session_id=chat['id'], branch_head_id=b)['items']) == 1
    assert not recall(client, sid, session_id=chat['id'], branch_head_id=other)['items']
    second = post(client, '/api/ai/sessions', {'card_id': card['id']})
    post(client, f'/api/souls/{sid}/links', {'kind': 'chat', 'target_id': second['id']})
    assert not recall(client, sid, session_id=second['id'])['items']
    shared = memory(client, sid, kind='relationship', content='用户确认的虚构角色关系', source={'kind': 'message', 'id': a})
    shared = patch(client, sid, shared, review='approved', allow_injection=True)
    assert recall(client, sid, session_id=second['id'])['items'][0]['id'] == shared['id']
    # A child of a branch may recall it; a sibling must never inherit it.
    with new_session() as db:
        child = m.ChatMessage(session_id=chat['id'], parent_id=b, role='user', content='继续这个版本')
        db.add(child); db.commit(); child_id = child.id
    assert len(recall(client, sid, session_id=chat['id'], branch_head_id=child_id)['items']) == 2
    with new_session() as db:
        db.get(m.ChatMessage, a).content = '原证据被更改'
        db.commit()
    assert not recall(client, sid, session_id=chat['id'], branch_head_id=child_id)['items']
    assert client.get(f'/api/characters/{char["id"]}').json()['profile'] is None


def test_sources_ownership_world_changes_and_hard_scope_validation(client):
    sid = soul(client)['id']; other_soul = soul(client)['id']
    _, card, chat, a, b, parallel = linked_chat(client, sid)
    assert client.post(f'/api/souls/{other_soul}/links', json={'kind': 'card', 'target_id': card['id']}).status_code == 409
    assert client.post(f'/api/souls/{other_soul}/links', json={'kind': 'chat', 'target_id': chat['id']}).status_code == 409
    assert client.post(f'/api/souls/{other_soul}/memories', json={'kind': 'suggestion', 'content': 'x', 'source': {'kind': 'message', 'id': a}}).status_code == 409
    for payload in (
        {'kind': 'core', 'content': '编造核心来源'},
        {'kind': 'world', 'content': '编造世界书'},
        {'kind': 'episode', 'content': '越过分支', 'source': {'kind': 'message', 'id': a}},
        {'kind': 'episode', 'content': '错误分支', 'scope': 'branch', 'session_id': chat['id'], 'branch_head_id': b, 'source': {'kind': 'message', 'id': parallel}},
    ):
        assert client.post(f'/api/souls/{sid}/memories', json=payload).status_code in (409, 422)
    world = post(client, '/api/worlds', {'name': '后来转入的世界'})['id']
    client.patch(f'/api/characters/{card["character_id"]}', json={'world_id': world})
    assert client.get(f'/api/souls/{sid}').json()['links'][0]['diagnostic']
    assert client.post(f'/api/souls/{sid}/recall', json={'session_id': chat['id']}).status_code == 409


def test_restore_appends_versions_reapproval_concurrency_and_export(client):
    sid = soul(client)['id']; row = memory(client, sid)
    url = f'/api/versions/soul_memory/{row["id"]}'
    original = client.get(url).json()['items'][0]['id']
    row = patch(client, sid, row, content='人工修改的版本')
    row = patch(client, sid, row, review='approved', allow_injection=True)
    head = client.get(url).json()['items'][0]['id']
    result = client.post(f'{url}/{original}/restore', json={'expected_latest': head})
    assert result.status_code == 200, result.text
    restored = client.get(f'/api/souls/{sid}/memories').json()['items'][0]
    assert restored['revision'] == row['revision'] + 1
    assert restored['review'] == 'pending' and not restored['allow_injection']
    assert len(client.get(url).json()['items']) == 4
    def update_once(note):
        return client.patch(f'/api/souls/{sid}/memories/{row["id"]}', json={'expected_revision': restored['revision'], 'conflict_note': note}).status_code
    with ThreadPoolExecutor(2) as pool:
        assert sorted(pool.map(update_once, ['A', 'B'])) == [200, 409]
    for i in range(3):
        memory(client, sid, content=f'虚构记录 {i}')
    exported = client.get(f'/api/souls/{sid}/export', params={'limit': 2}).json()
    assert len(exported['memories']) == 2 and exported['next_after_id']
    nxt = client.get(f'/api/souls/{sid}/export', params={'after_id': exported['next_after_id'], 'limit': 2}).json()
    assert not nxt['next_after_id'] and len(nxt['memories']) == 2
    assert {x['uid'] for x in exported['memories']}.isdisjoint(x['uid'] for x in nxt['memories'])


def test_fts_isolated_from_global_search_backup_restore_restart_and_old_migration(client, data_dir):
    sid = soul(client)['id']; row = memory(client, sid)
    row = patch(client, sid, row, review='approved', allow_injection=True)
    assert not client.get('/api/search', params={'q': '虚构角色约定'}).json()
    j = jobs.Job('full-backup', 'generated soul backup'); backups.create(j)
    package = backups.package_for(j.result['backup_id'])
    assert not backups.verify(package)[1]
    r = jobs.Job('full-restore', 'generated soul isolated restore'); backups.restore(r, package)
    assert r.result['active_data_unchanged']
    restored_path = data_dir / 'restores' / r.result['restore_id'] / 'front.db'
    with sqlite3.connect(restored_path) as db:
        assert db.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
        assert not db.execute('PRAGMA foreign_key_check').fetchall()
        assert db.execute('SELECT uid FROM soul_memories').fetchone()[0] == row['uid']
        assert db.execute('SELECT COUNT(*) FROM entity_versions').fetchone()[0] >= 3
    # Restart the real application factory against the same isolated data.
    app = create_app()
    from fastapi.testclient import TestClient
    with TestClient(app) as c:
        assert recall(c, sid)['items'][0]['uid'] == row['uid']
    # Emulate an old schema only in another SQLite copy, never in active data.
    old_path = data_dir / 'old-generated.db'
    with sqlite3.connect(data_dir/'front.db') as src, sqlite3.connect(old_path) as dst:
        src.backup(dst)
        dst.execute('DROP TABLE soul_memory_index')
        for table in ('soul_memories', 'soul_links', 'soul_identities'):
            dst.execute(f'DROP TABLE {table}')
        dst.commit()
    from sqlalchemy import create_engine
    from front_api.db import Base
    from front_api.migrate import upgrade
    engine = create_engine('sqlite:///'+str(old_path))
    Base.metadata.create_all(engine); upgrade(engine); souls.ensure_fts(engine); engine.dispose()
    assert not backups.schema_issues(old_path, complete=True)


@pytest.mark.parametrize('payload', [
    {'name': ' '}, {'name': 'x', 'world_id': 9999}, {'name': 'x', 'extra': 'not allowed'},
])
def test_invalid_soul_input(client, payload):
    assert client.post('/api/souls', json=payload).status_code in (409, 422)


def test_upgrade_takes_pre_schema_snapshot_and_preserves_old_records(data_dir):
    from fastapi.testclient import TestClient
    from front_api.db import get_engine
    with TestClient(create_app()) as c:
        wid = post(c, '/api/worlds', {'name': '旧结构生成资料'})['id']
    get_engine().dispose()
    with sqlite3.connect(data_dir/'front.db') as db:
        db.execute('DROP TABLE soul_memory_index')
        for table in ('soul_memories', 'soul_links', 'soul_identities'):
            db.execute(f'DROP TABLE {table}')
    with TestClient(create_app()) as c:
        assert c.get(f'/api/worlds/{wid}').json()['name'] == '旧结构生成资料'
        assert c.get('/api/souls').json()['total'] == 0
    snapshots = list((data_dir/'backups').glob('pre-schema-*/manifest.json'))
    assert len(snapshots) == 1
    manifest = json.loads(snapshots[0].read_text(encoding='utf-8'))
    assert set(manifest['reason']) >= {'soul_identities', 'soul_links', 'soul_memories'}
    with sqlite3.connect(snapshots[0].parent/'front.db') as db:
        assert db.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
        assert db.execute('SELECT name FROM worlds WHERE id=?', (wid,)).fetchone()[0] == '旧结构生成资料'
        assert not db.execute("SELECT name FROM sqlite_master WHERE name='soul_identities'").fetchone()


def test_disabled_link_restore_and_lore_source_remain_explicit(client):
    sid = soul(client)['id']
    _, card, chat, a, b, parallel = linked_chat(client, sid)
    link = next(x for x in client.get(f'/api/souls/{sid}').json()['links'] if x['kind'] == 'chat')
    url = f'/api/souls/{sid}/links/{link["id"]}'
    r = client.patch(url, json={'expected_revision': link['revision'], 'active': False})
    assert r.status_code == 200, r.text
    assert client.post(f'/api/souls/{sid}/recall', json={'session_id': chat['id']}).status_code == 409
    r = client.patch(url, json={'expected_revision': r.json()['revision'], 'active': True})
    assert r.status_code == 200, r.text
    assert recall(client, sid, session_id=chat['id'])['items'] == []
    book = post(client, '/api/lorebooks', {'name': '生成世界书'})
    entry = post(client, f'/api/lorebooks/{book["id"]}/entries', {'title': '灯塔规则', 'content': '虚构世界规则'})
    post(client, f'/api/souls/{sid}/links', {'kind': 'lore', 'target_id': entry['id']})
    row = memory(client, sid, kind='world', source={'kind': 'lore', 'id': entry['id']})
    patch(client, sid, row, review='approved', allow_injection=True)
    assert recall(client, sid)['items']
    client.patch(f'/api/lore-entries/{entry["id"]}', json={'enabled': False})
    assert not recall(client, sid)['items']
    client.patch(f'/api/lore-entries/{entry["id"]}', json={'enabled': True})
    assert recall(client, sid)['items']
    client.patch(f'/api/lore-entries/{entry["id"]}', json={'content': '新规则'})
    assert not recall(client, sid)['items']


def test_same_world_work_move_invalidates_existing_role_scope(client):
    sid = soul(client)['id']
    char, card, chat, *_ = linked_chat(client, sid)
    work = post(client, '/api/works', {'title': '生成的另一作品'})
    client.patch(f'/api/characters/{char["id"]}', json={'work_id': work['id']})
    links = client.get(f'/api/souls/{sid}').json()['links']
    assert all(x['diagnostic'] for x in links)
    assert client.post(f'/api/souls/{sid}/recall', json={'session_id': chat['id']}).status_code == 409


@pytest.mark.parametrize('kind', ['asset', 'voice_profile'])
def test_source_media_hash_or_voice_configuration_change_requires_review(client, kind):
    sid = soul(client)['id']
    with new_session() as db:
        model = m.VoiceModel(title='Generated registered model', model_version='v1')
        if kind == 'voice_profile':
            db.add(model); db.flush()
        obj = (m.Asset(title='Generated reference', kind='image', sha256='a'*64)
               if kind == 'asset' else m.VoiceProfile(title='Generated voice', voice_key='generated-v1', model_id=model.id))
        db.add(obj); db.commit(); target_id = obj.id
    post(client, f'/api/souls/{sid}/links', {'kind': kind, 'target_id': target_id})
    row = memory(client, sid, source={'kind': kind, 'id': target_id})
    patch(client, sid, row, review='approved', allow_injection=True)
    assert recall(client, sid)['items']
    with new_session() as db:
        obj = db.get(souls.TARGETS[kind], target_id)
        if kind == 'asset':
            obj.stars = 4
        else:
            obj.notes = 'Personal rating/notes are not source content'
        db.commit()
    assert recall(client, sid)['items']
    with new_session() as db:
        obj = db.get(souls.TARGETS[kind], target_id)
        if kind == 'asset':
            obj.sha256 = 'b'*64
        else:
            obj.voice_key = 'generated-v2'
        db.commit()
    assert not recall(client, sid)['items']
    if kind == 'voice_profile':
        with new_session() as db:
            obj = db.get(m.VoiceProfile, target_id); obj.voice_key = 'generated-v1'; db.commit()
        assert recall(client, sid)['items']
        with new_session() as db:
            obj = db.get(m.VoiceProfile, target_id)
            db.get(m.VoiceModel, obj.model_id).model_version = 'v2'; db.commit()
        assert not recall(client, sid)['items']
