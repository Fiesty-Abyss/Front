"""Generated 1k/10k metadata and content; no personal library access."""
import json
import time
import tracemalloc
from datetime import datetime

import pytest
from sqlalchemy import event, text

from front_api import models as m
from front_api.db import get_engine


@pytest.mark.parametrize('count',[1000,10000])
def test_summary_page_size_query_plan_and_keyset(client,app,tmp_path,count):
    card=client.post('/api/cards',json={'name':'Generated scale card'}).json()
    engine=get_engine();stamp=datetime(2026,1,1)
    with engine.begin() as db:
        for start in range(1,count+1,1000):
            ids=range(start,min(start+1000,count+1))
            db.execute(m.ChatSession.__table__.insert(),[dict(id=i,card_id=card['id'],title=f'Generated {i}',user_name='Generated',head_id=i,created_at=stamp,updated_at=stamp) for i in ids])
            db.execute(m.ChatMessage.__table__.insert(),[dict(id=i,session_id=i,role='assistant',content='X'*8192,created_at=stamp) for i in ids])
        plans={sql:list(db.execute(text('EXPLAIN QUERY PLAN '+sql))) for sql in (
            'SELECT id FROM chat_sessions ORDER BY updated_at DESC,id DESC LIMIT 51',
            'SELECT session_id,count(*) FROM chat_messages WHERE session_id IN (1,2,3) GROUP BY session_id')}
    assert all('USE TEMP B-TREE' not in str(rows) for rows in plans.values())
    assert 'ix_chat_sessions_updated_id' in str(plans) and 'ix_chat_messages_session' in str(plans)
    queries=[]
    def record(conn,cursor,statement,*args):
        if statement.lstrip().startswith('SELECT') and 'chat_' in statement:queries.append(statement)
    event.listen(engine,'after_cursor_execute',record)
    try:
        tracemalloc.start();started=time.perf_counter()
        first=client.get('/api/ai/sessions/page?limit=50')
        duration=(time.perf_counter()-started)*1000;peak=tracemalloc.get_traced_memory()[1];tracemalloc.stop()
    finally:event.remove(engine,'after_cursor_execute',record)
    assert first.status_code==200,first.text
    data=first.json();assert len(data['items'])==50 and data['has_more']
    assert len(first.content)<20000 and all(len(i['last'])==60 for i in data['items'])
    assert len(queries)==2 and not any('chat_messages.meta' in q for q in queries)
    # Reproduce the pre-fix endpoint on this generated fixture only: same ASGI
    # transport/corpus/tracemalloc, old full ORM loading and unbounded response.
    from fastapi import Depends
    from sqlalchemy.orm import Session
    from sqlalchemy import select
    from front_api.db import get_session
    from front_api.routers import ai
    @app.get('/api/_generated/baseline-chat-list')
    def old_list(session: Session=Depends(get_session)):
        result=[]
        for c in session.scalars(select(m.ChatSession).order_by(m.ChatSession.updated_at.desc())).all():
            path=ai.path_to(c,c.head_id)
            result.append(dict(id=c.id,card_id=c.card_id,title=c.title,messages=len(path),
                               total_messages=len(c.messages),last=path[-1].content[:60] if path else '',updated_at=c.updated_at.isoformat()))
        return result
    app.router.routes.insert(0, app.router.routes.pop())  # before the generated app SPA fallback
    tracemalloc.start();started=time.perf_counter()
    baseline=client.get('/api/_generated/baseline-chat-list')
    old_duration=(time.perf_counter()-started)*1000;old_peak=tracemalloc.get_traced_memory()[1];tracemalloc.stop()
    assert baseline.status_code==200 and len(baseline.json())==count
    next_page=client.get('/api/ai/sessions/page',params={'cursor':data['next_cursor']}).json()
    assert not ({i['id'] for i in data['items']} & {i['id'] for i in next_page['items']})
    assert client.get('/api/ai/sessions/page',params={'cursor':data['next_cursor'],'q':'different'}).status_code==422
    legacy=client.get('/api/ai/sessions?limit=1').json()
    assert len(legacy)==1 and legacy[0]['messages']==1 and legacy[0]['total_messages']==1
    report={'sessions':count,'messages':count,'stored_content_bytes':count*8192,
            'response_bytes':len(first.content),'request_ms':round(duration,2),'python_peak_bytes':peak,
            'query_plan':{q:[list(r) for r in rows] for q,rows in plans.items()},'gui':False,
            'baseline_response_bytes':len(baseline.content),'baseline_request_ms':round(old_duration,2),
            'baseline_python_peak_bytes':old_peak,'measurement':'same warm generated corpus, ASGI and tracemalloc; old all vs new first 50'}
    (tmp_path/'measurements.json').write_text(json.dumps(report,indent=2),encoding='utf-8')


def test_index_upgrade_snapshot_and_literal_search(client,data_dir):
    import sqlite3
    from front_api import dbbackup,migrate
    from front_api.config import get_settings
    engine=get_engine()
    card=client.post('/api/cards',json={'name':'Generated'}).json()
    client.post('/api/ai/sessions',json={'card_id':card['id'],'title':'100%_literal'})
    assert len(client.get('/api/ai/sessions/page?q=%25_').json()['items'])==1
    assert not client.get('/api/ai/sessions/page?q=not-present').json()['items']
    for params in ({'limit':0},{'limit':101},{'cursor':'bad'},{'q':'x'*96}):
        assert client.get('/api/ai/sessions/page',params=params).status_code==422
    with engine.begin() as db:
        for _,name,_ in migrate.CHAT_INDEXES:db.exec_driver_sql('DROP INDEX '+name)
    dbbackup.before_schema_change(get_settings())
    folder=next((data_dir/'backups').glob('pre-schema-*'))
    with sqlite3.connect(folder/'front.db') as backup:
        assert backup.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
        assert backup.execute('SELECT title FROM chat_sessions').fetchone()[0]=='100%_literal'
    assert set(migrate.upgrade(engine))=={'index:'+name for _,name,_ in migrate.CHAT_INDEXES}
    assert migrate.upgrade(engine)==[]
