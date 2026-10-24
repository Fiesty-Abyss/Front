"""Generated metadata: exact counts and world filtering beyond the old 10k cap."""
from sqlalchemy import create_engine, insert, text

from front_api import models as m
from front_api.db import get_engine
from front_api.migrate import upgrade


def test_search_counts_deep_pages_and_world_filters_are_not_truncated(client):
    first=client.post('/api/worlds',json={'name':'Generated world one'}).json()['id']
    second=client.post('/api/worlds',json={'name':'Generated world two'}).json()['id']
    with get_engine().begin() as conn:
        for start in range(1,10021,1000):
            rows=[{'id':i,'title':'generated asset','kind':'drawing','world_id':first if i<=10000 else second}
                  for i in range(start,min(10021,start+1000))]
            conn.execute(insert(m.Asset),rows)
            conn.execute(text('INSERT INTO search_index(entity,entity_id,title,body) VALUES(:entity,:id,:title,:body)'),
                         [{'entity':'asset','id':r['id'],'title':r['title'],'body':'generated evidence'} for r in rows])
    for query in ['as','generated']:
        value=client.get('/api/assets',params={'q':query,'limit':60}).json()
        assert value['total']==10020 and len(value['items'])==60
        deep=client.get('/api/assets',params={'q':query,'limit':60,'offset':10000}).json()
        assert deep['total']==10020 and len(deep['items'])==20
        scoped=client.get('/api/assets',params={'q':query,'world_id':second}).json()
        assert scoped['total']==20 and {r['world_id'] for r in scoped['items']}=={second}
    # Quick-search suggestions keep their intentionally bounded contract.
    assert len(client.get('/api/search',params={'q':'generated'}).json())<=50
    assert client.get('/api/assets',params={'q':'   '}).json()['total']==0


def test_short_search_keeps_literal_wildcards_and_entity_isolation(client):
    client.post('/api/assets',json={'title':'literal %_','kind':'drawing'})
    client.post('/api/assets',json={'title':'ordinary title','kind':'drawing'})
    client.post('/api/worlds',json={'name':'world-only unique evidence'})
    assert client.get('/api/assets',params={'q':'%_'}).json()['total']==1
    assert client.get('/api/assets',params={'q':'world-only unique evidence'}).json()['total']==0
    assert client.get('/api/assets',params={'q':'"; DROP TABLE assets; --'}).json()['total']==0
    assert client.get('/api/assets').json()['total']==2


def test_world_index_upgrade_preserves_rows_and_is_idempotent(tmp_path):
    engine=create_engine('sqlite:///'+str(tmp_path/'generated-legacy.db'))
    with engine.begin() as conn:
        conn.exec_driver_sql('CREATE TABLE assets(id INTEGER PRIMARY KEY,world_id INTEGER,work_date DATE,title TEXT)')
        conn.exec_driver_sql("INSERT INTO assets VALUES(7,2,'2026-01-01','preserve exact text')")
    assert 'index:ix_assets_world_date_id' in upgrade(engine)
    assert upgrade(engine)==[]
    with engine.connect() as conn:
        assert conn.exec_driver_sql('SELECT * FROM assets').fetchall()==[(7,2,'2026-01-01','preserve exact text')]
        plan=conn.exec_driver_sql('EXPLAIN QUERY PLAN SELECT id FROM assets WHERE world_id=2 ORDER BY work_date DESC NULLS LAST,id DESC LIMIT 60').fetchall()
        assert any('SEARCH assets USING COVERING INDEX ix_assets_world_date_id' in r[-1] for r in plan)
        assert conn.exec_driver_sql('PRAGMA integrity_check').scalar()=='ok'
    engine.dispose()
