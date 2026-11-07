"""Generated data only: cursors, legacy compatibility, rollback and true CAS races."""
import base64
import json
import pytest
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from fastapi import HTTPException
from sqlalchemy import event, insert, select, text

from front_api import collectionpages as pages, models as m
from front_api.db import get_engine, new_session


def seed(client, count=125):
    col = client.post('/api/collections', json={'name': 'Generated collection'}).json()['id']
    with get_engine().begin() as conn:
        conn.execute(insert(m.Asset), [{'id': i, 'title': f'Generated {i}', 'kind': 'novel' if i % 2 else 'drawing',
            'content': 'PRIVATE TEST BODY ' * 100, 'meta': {'file': {'preview': 'not for lists', 'thumb': True}},
            'stars': i % 6, 'preference': i % 101, 'work_date': __import__('datetime').date(2026, 1, 1)} for i in range(1, count + 1)])
        conn.execute(m.collection_assets.insert(), [{'collection_id': col, 'asset_id': i, 'position': i - 1} for i in range(1, count + 1)])
    return col


def detail(client, cid):
    return client.get(f'/api/collections/{cid}/summary').json()


def members(client, cid, **params):
    response = client.get(f'/api/collections/{cid}/members', params=params)
    assert response.status_code == 200, response.text
    return response.json()


def test_bounded_summaries_and_cursor_scope_no_bodies(client):
    cid = seed(client)
    summary = client.get('/api/collections/summaries').json()['items'][0]
    assert summary['member_count'] == 125 and summary['effective_cover_id'] == 1
    assert 'assets' not in summary
    first = members(client, cid)
    assert [a['id'] for a in first['items']] == list(range(1, 61))
    assert first['total'] == 125 and len(json.dumps(first)) < 30000
    assert all('content' not in a and a['meta'] == {'file': {'thumb': True}} for a in first['items'])
    second = members(client, cid, cursor=first['next_cursor'])
    assert [a['id'] for a in second['items']] == list(range(61, 121))
    third = members(client, cid, cursor=second['next_cursor'])
    assert len(third['items']) == 5 and third['next_cursor'] is None
    assert client.get(f'/api/collections/{cid}/members', params={'cursor': first['next_cursor'], 'kind': 'novel'}).status_code == 422
    assert client.get(f'/api/collections/{cid}/members', params={'cursor': 'notbase64!'}).status_code == 422
    assert client.get(f'/api/collections/{cid}/members', params={'limit': 201}).status_code == 422
    edited = client.patch(f'/api/collections/{cid}/summary', json={'description': 'metadata only'}).json()
    assert edited['member_count'] == 125 and 'assets' not in edited
    assert client.patch(f'/api/collections/{cid}/summary', json={'asset_ids': []}).status_code == 422
    assert len(client.get(f'/api/collections/{cid}').json()['assets']) == 125  # legacy contract


def test_page_sort_keeps_other_pages_and_rejects_stale_or_filtered_windows(client):
    cid = seed(client)
    first = members(client, cid)
    second = members(client, cid, cursor=first['next_cursor'])
    ids = [a['id'] for a in second['items']]
    body = {'expected_revision': second['members_revision'], 'first_asset_id': ids[0], 'asset_ids': ids[::-1]}
    result = client.put(f'/api/collections/{cid}/members/order', json=body)
    assert result.status_code == 200, result.text
    assert client.put(f'/api/collections/{cid}/members/order', json=body).status_code == 409
    assert client.get(f'/api/collections/{cid}/members', params={'cursor': first['next_cursor']}).status_code == 409
    with get_engine().connect() as conn:
        order = list(conn.scalars(select(m.collection_assets.c.asset_id).where(m.collection_assets.c.collection_id == cid).order_by(m.collection_assets.c.position)))
    assert order == [*range(1, 61), *ids[::-1], *range(121, 126)]
    current = detail(client, cid)
    bad = {'expected_revision': current['members_revision'], 'first_asset_id': 1, 'asset_ids': [1, 3, 5]}
    assert client.put(f'/api/collections/{cid}/members/order', json=bad).status_code == 409
    assert detail(client, cid)['members_revision'] == current['members_revision']  # rolled back


def test_legacy_and_direct_writers_invalidate_cursors_and_duplicate_positions_safe(client):
    cid = seed(client, 65)
    first = members(client, cid)
    # OC/audio/generation code writes the shared link table directly.
    with get_engine().begin() as conn:
        conn.execute(m.collection_assets.update().where(m.collection_assets.c.collection_id == cid, m.collection_assets.c.asset_id == 2).values(position=0))
    assert client.get(f'/api/collections/{cid}/members', params={'cursor': first['next_cursor']}).status_code == 409
    current = members(client, cid)
    assert [a['id'] for a in current['items'][:2]] == [1, 2]  # stable tie breaker
    body = {'expected_revision': current['members_revision'], 'first_asset_id': 1, 'asset_ids': [2, 1]}
    assert client.put(f'/api/collections/{cid}/members/order', json=body).status_code == 409
    legacy = client.put(f'/api/collections/{cid}/order', json={'asset_ids': list(range(1, 66))})
    assert legacy.status_code == 200
    assert detail(client, cid)['members_revision'] > current['members_revision']
    with get_engine().begin() as conn:
        conn.execute(m.Asset.__table__.delete().where(m.Asset.id == 65))
    assert detail(client, cid)['member_count'] == 64


def test_cross_page_batch_filters_tags_versions_and_atomic_failure(client):
    cid = seed(client)
    tag = client.post('/api/tags', json={'name': 'Generated parent'}).json()['id']
    child = client.post('/api/tags', json={'name': 'Generated child', 'parent_id': tag}).json()['id']
    assert client.post('/api/versions/asset/2', json={'note': 'Before generated batch'}).status_code == 200
    body = {'expected_revision': detail(client, cid)['members_revision'], 'asset_ids': [2, 122], 'stars': 5, 'preference': 99, 'favorite': True, 'add_tag_ids': [child]}
    assert client.patch(f'/api/collections/{cid}/members/batch', json=body).status_code == 200
    filtered = members(client, cid, tag=tag, min_stars=5, min_preference=99, kind='drawing', date_from='2026-01-01', date_to='2026-01-02')
    assert [a['id'] for a in filtered['items']] == [2, 122]
    history = client.get('/api/versions/asset/2').json()
    assert history['total'] == 2
    diff = client.get('/api/versions/asset/2/compare', params={'left': history['items'][1]['id'], 'right': history['items'][0]['id']}).json()
    assert any(item['field'] == 'stars' for item in diff['fields'])
    body['expected_revision'] = detail(client, cid)['members_revision']
    body['asset_ids'] = [2, 9000]; body['stars'] = 0
    assert client.patch(f'/api/collections/{cid}/members/batch', json=body).status_code == 409
    assert client.get('/api/assets/2').json()['stars'] == 5
    body['asset_ids'] = [2]; body['add_tag_ids'] = [9000]
    assert client.patch(f'/api/collections/{cid}/members/batch', json=body).status_code == 422
    assert client.get('/api/assets/2').json()['stars'] == 5
    body = {'expected_revision': detail(client, cid)['members_revision'], 'asset_ids': [2, 122], 'remove': True}
    assert client.patch(f'/api/collections/{cid}/members/batch', json=body).status_code == 200
    assert detail(client, cid)['member_count'] == 123
    assert client.get('/api/assets/2').status_code == 200
    assert client.patch('/api/assets/2', json={'stars': None}).status_code == 422


def test_competing_transactions_only_one_window_order_commits(client):
    cid = seed(client, 6)
    revision = detail(client, cid)['members_revision']
    barrier = Barrier(2)
    def writer(ids):
        with new_session() as session:
            barrier.wait(timeout=10)
            try:
                pages.lock(session, cid, revision)
                pages.reorder_window(session, cid, 1, ids)
                session.commit()
                return 200
            except HTTPException as exc:
                session.rollback()
                return exc.status_code
    with ThreadPoolExecutor(2) as pool:
        outcomes = list(pool.map(writer, ([3, 2, 1], [2, 1, 3])))
    assert sorted(outcomes) == [200, 409]
    with get_engine().connect() as conn:
        order = list(conn.scalars(select(m.collection_assets.c.asset_id).order_by(m.collection_assets.c.position)))
        assert order in ([3, 2, 1, 4, 5, 6], [2, 1, 3, 4, 5, 6])
        assert conn.execute(text('PRAGMA integrity_check')).scalar() == 'ok'


def test_write_failure_after_first_flush_rolls_back_entire_batch(client):
    cid = seed(client, 35)
    revision = detail(client, cid)['members_revision']
    def fail_later(_mapper, _connection, target):
        if target.id == 30:
            raise RuntimeError('generated second-chunk database write failure')
    event.listen(m.Asset, 'before_update', fail_later)
    try:
        with pytest.raises(RuntimeError, match='generated second-chunk'):
            client.patch(f'/api/collections/{cid}/members/batch', json={
                'expected_revision': revision, 'asset_ids': list(range(1, 36)), 'stars': 5})
    finally:
        event.remove(m.Asset, 'before_update', fail_later)
    assert detail(client, cid)['members_revision'] == revision
    with get_engine().connect() as conn:
        assert conn.execute(select(m.Asset.id, m.Asset.stars).order_by(m.Asset.id)).all() == [(i, i % 6) for i in range(1, 36)]
        assert conn.execute(text('PRAGMA integrity_check')).scalar() == 'ok'
