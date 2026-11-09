"""Generated chat protocol regressions; no real engine, user text or API billing."""
import json
import threading
from concurrent.futures import ThreadPoolExecutor

import httpx
import pytest

from front_api.ai import registry
from front_api import chatmodels
from front_api.routers import ai


@pytest.fixture
def setup_chat(client):
    requests=[]
    def handler(req):
        body=json.loads(req.content);requests.append(body)
        return httpx.Response(200,json={'choices':[{'message':{'content':'Generated reply: '+body['model']}}]})
    provider=client.post('/api/ai/providers',json={'name':'Generated protocol','base_url':'http://127.0.0.1:9/v1','chat_model':'configured-old','api_key':'generated-never-display'}).json()
    registry.transport_override[provider['id']]=httpx.MockTransport(handler)
    card=client.post('/api/cards',json={'name':'Generated role','first_mes':'Generated greeting','description':'Generated setup'}).json()
    chat=client.post('/api/ai/sessions',json={'card_id':card['id']}).json()
    yield chat,provider,requests
    registry.transport_override.clear()
    assert not ai.has_active_generations()


def choose(client,chat,provider,**changes):
    url=f"/api/ai/sessions/{chat['id']}"
    data={'provider_id':provider['id'],'model':'explicit-one','temperature':.3,'max_tokens':321,'context_characters':32000,'expected':client.get(url+'/model-state').json()['expected']}
    return client.post(url+'/model-selection',json=data|changes)


def test_model_snapshot_stable_and_switch_preserves_chat(client,setup_chat):
    chat,p,requests=setup_chat;url=f"/api/ai/sessions/{chat['id']}"
    before=client.get(url).json()
    first=choose(client,chat,p).json();assert first['selection']['snapshot']['model']=='explicit-one'
    assert client.get(url).json()==before
    # Changing global default and configured model must not change this session's snapshot.
    client.patch(f"/api/ai/providers/{p['id']}",json={'chat_model':'configured-new','temperature':1.5})
    response=client.post(url+'/generate',json={'content':'Generated question','stream':False})
    assert response.status_code==200,response.text
    reply=response.json()['messages'][-1]
    assert reply['meta']['model']=='explicit-one' and reply['meta']['parameters']=={'temperature':.3,'max_tokens':321}
    assert requests[-1]['model']=='explicit-one' and requests[-1]['max_tokens']==321
    assert 'generated-never-display' not in json.dumps(reply)
    snapshot=client.get(url).json()
    second=choose(client,chat,p,model='explicit-two').json()
    assert second['selection']['id']!=first['selection']['id']
    assert client.get(url).json()==snapshot
    assert client.post(url+'/model-selection',json={'provider_id':p['id'],'model':'stale','expected':first['expected']}).status_code==409
    history=client.get(url+'/model-history?limit=1').json();assert history['total']==2 and len(history['items'])==1
    # Restoring settings is another explicit append, never a mutation of old messages.
    assert choose(client,chat,p,model=first['selection']['snapshot']['model']).status_code==200
    assert client.get(url+'/model-history').json()['total']==3
    assert client.get(url).json()==snapshot


def test_deleted_or_replaced_endpoint_does_not_fall_back(client,setup_chat):
    chat,p,requests=setup_chat;url=f"/api/ai/sessions/{chat['id']}"
    choose(client,chat,p)
    original=client.get(url).json()
    client.patch(f"/api/ai/providers/{p['id']}",json={'base_url':'http://127.0.0.1:10/v1'})
    assert client.post(url+'/generate',json={'content':'generated','stream':False}).status_code==409
    assert client.get(url).json()==original and requests==[]
    client.delete(f"/api/ai/providers/{p['id']}")
    assert client.post(url+'/generate',json={'content':'generated','stream':False}).status_code==409
    assert client.get(url).json()==original
    assert client.get(url+'/model-history').json()['total']==1


@pytest.mark.parametrize('url',['http://[bad','http://localhost:bad/v1','http://user:secret@localhost/v1','https://example.invalid/v1?key=generated'])
def test_endpoint_credentials_and_malformed_config_rejected(client,setup_chat,url):
    chat,p,requests=setup_chat
    client.patch(f"/api/ai/providers/{p['id']}",json={'base_url':url})
    assert choose(client,chat,p).status_code==422
    assert requests==[]


def test_context_budget_preserves_instructions_and_original_history(client,setup_chat):
    chat,p,_=setup_chat;url=f"/api/ai/sessions/{chat['id']}"
    choose(client,chat,p,context_characters=1024)
    for i in range(4):
        assert client.post(url+'/generate',json={'content':'generated '+str(i)+'x'*600,'stream':False}).status_code==200
    original=client.get(url).json()
    context=client.get(url+'/context').json()
    assert context['budget']['characters']<=1024 and context['budget']['dropped_turns']>0
    assert 'Generated setup' in context['messages'][0]['content']
    assert client.get(url).json()==original
    assert chatmodels.bound_context([{'role':'system','content':'instructions'},{'role':'user','content':'latest'}],100)[1]['unit']=='characters-not-tokens'
    with pytest.raises(Exception):chatmodels.bound_context([{'role':'system','content':'x'*1025}],1024)


def test_stream_reply_has_actual_config_and_safe_service_error(client,setup_chat):
    chat,p,_=setup_chat;url=f"/api/ai/sessions/{chat['id']}"
    choose(client,chat,p)
    registry.transport_override[p['id']]=httpx.MockTransport(lambda req:httpx.Response(500,text='generated-never-display + private-remote-body'))
    result=client.post(url+'/generate',json={'content':'Generated retained draft'})
    assert '500' in result.text and 'generated-never-display' not in result.text and 'private-remote-body' not in result.text
    stored=client.get(url).json();assert stored['messages'][-1]['content']=='Generated retained draft'
    assert not ai.has_active_generations()


def test_one_generation_per_chat_and_global_limit(app,client,setup_chat):
    chat,p,_=setup_chat
    entered=threading.Event();finish=threading.Event()
    class Protocol:
        name='generated';model='generated';label='Protocol only'
        def available(self):return True
        def stream(self,messages):
            entered.set();finish.wait(5);yield 'Generated result'
    app.dependency_overrides[ai.provider_dep]=lambda:Protocol()
    url=f"/api/ai/sessions/{chat['id']}"
    with ThreadPoolExecutor(max_workers=1) as pool:
        task=pool.submit(client.post,url+'/generate',json={'content':'generated'})
        try:
            assert entered.wait(3)
            before=client.get(url).json()['total_messages']
            assert client.post(url+'/generate',json={'content':'duplicate','stream':False}).status_code==409
            assert choose(client,chat,p).status_code==409
            assert client.patch(url,json={'title':'changed while active'}).status_code==409
            assert client.post(url+'/select',json={'message_id':chat['messages'][0]['id']}).status_code==409
            assert client.patch('/api/ai/messages/'+str(chat['messages'][0]['id']),json={'content':'changed'}).status_code==409
            assert client.delete('/api/ai/messages/'+str(chat['messages'][0]['id'])).status_code==409
            assert client.delete(url).status_code==409
            assert client.get(url).json()['total_messages']==before
            with ai._generation_lock:
                ai._running['generated-second-marker']=threading.Event()
            other=client.post('/api/ai/sessions',json={'card_id':chat['card_id']}).json()
            assert client.post(f"/api/ai/sessions/{other['id']}/generate",json={'content':'overload'}).status_code==429
        finally:
            with ai._generation_lock:ai._running.pop('generated-second-marker',None)
            finish.set()
        assert task.result().status_code==200
    app.dependency_overrides.clear()


def test_branch_changed_during_generation_is_not_silently_reset(app,client,setup_chat):
    chat,_,_=setup_chat;url=f"/api/ai/sessions/{chat['id']}"
    entered=threading.Event();finish=threading.Event()
    class Protocol:
        name='generated';model='generated'
        def available(self):return True
        def stream(self,messages):
            entered.set();finish.wait(5);yield 'Generated alternate branch'
    app.dependency_overrides[ai.provider_dep]=lambda:Protocol()
    with ThreadPoolExecutor(max_workers=1) as pool:
        task=pool.submit(client.post,url+'/generate',json={'content':'Generated question'})
        try:
            assert entered.wait(3)
            from front_api.db import new_session
            from front_api import models as m
            with new_session() as db:
                current=db.get(m.ChatSession,chat['id']);current.head_id=chat['messages'][0]['id'];db.commit()
        finally:finish.set()
        assert task.result().status_code==200
    saved=client.get(url).json();assert saved['head_id']==chat['messages'][0]['id'] and saved['total_messages']==3
    app.dependency_overrides.clear()


def test_generation_limits_and_legacy_compatibility(client,setup_chat):
    chat,p,requests=setup_chat;url=f"/api/ai/sessions/{chat['id']}"
    assert client.get(url+'/model-state').json()['selection'] is None
    client.patch('/api/settings',json={'chat_provider_id':p['id']})
    assert client.post(url+'/messages',json={'content':'Generated legacy'}).status_code==200
    assert requests[-1]['model']=='configured-old'
    assert client.post(url+'/generate',json={'content':'x'*64001}).status_code==422
    assert choose(client,chat,p,temperature=3).status_code==422
    assert choose(client,chat,p,max_tokens=0).status_code==422
    assert client.get(url+'/model-history?limit=101').status_code==422
    assert client.get(url+'/model-history?offset='+str(2**100)).status_code==422
    assert client.get('/api/ai/sessions/'+str(2**100)+'/model-state').status_code==422

def test_additive_selection_table_snapshot_and_isolated_backup(client,data_dir,setup_chat):
    import sqlite3
    from pathlib import Path
    from front_api import backups, dbbackup, models as m
    from front_api.config import get_settings
    from front_api.db import get_engine
    from test_backups import wait
    chat,p,_=setup_chat
    engine=get_engine()
    with engine.begin() as conn:conn.exec_driver_sql('DROP TABLE chat_model_selections')
    dbbackup.before_schema_change(get_settings())
    files=list((data_dir/'backups').glob('pre-schema-*/front.db'));assert files
    with sqlite3.connect(files[-1]) as db:
        assert db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
        assert db.execute('SELECT card_id FROM chat_sessions WHERE id=?',(chat['id'],)).fetchone()[0]==chat['card_id']
        assert not db.execute("SELECT name FROM sqlite_master WHERE name='chat_model_selections'").fetchone()
    m.ChatModelSelection.__table__.create(engine)
    chosen=choose(client,chat,p).json()
    assert client.post(f"/api/ai/sessions/{chat['id']}/generate",json={'content':'Generated backup','stream':False}).status_code==200
    backup=wait(client,client.post('/api/backups',json={}).json());assert backup['status']=='done'
    package=backups.package_for(backup['result']['backup_id'])
    restored=wait(client,client.post('/api/backups/restore',json={'path':str(package),'confirmed':True}).json());assert restored['status']=='done',restored
    with sqlite3.connect(Path(restored['result']['path'])/'front.db') as db:
        assert db.execute('PRAGMA integrity_check').fetchone()[0]=='ok' and not db.execute('PRAGMA foreign_key_check').fetchall()
        saved=json.loads(db.execute('SELECT snapshot FROM chat_model_selections WHERE id=?',(chosen['selection']['id'],)).fetchone()[0])
        assert saved['model']=='explicit-one'
        meta=json.loads(db.execute("SELECT meta FROM chat_messages WHERE role='assistant' ORDER BY id DESC LIMIT 1").fetchone()[0])
        assert meta['model_selection']['id']==chosen['selection']['id']


def test_legacy_endpoint_label_and_partial_error_do_not_persist_credentials(app,client,setup_chat):
    chat,_,_=setup_chat
    from front_api.ai import AIUnavailable
    class Protocol:
        name='generated-protocol-only'
        model='generated'
        base_url=label='https://generated-user:generated-private-password@example.invalid/v1?key=generated-private-key'
        def available(self):return True
        def stream(self,messages):
            yield 'Generated retained fragment'
            raise AIUnavailable('generated-private-error-body '+self.base_url)
    app.dependency_overrides[ai.provider_dep]=lambda:Protocol()
    try:
        response=client.post(f"/api/ai/sessions/{chat['id']}/generate",json={'content':'Generated question'})
        assert 'generated-private-' not in response.text
        saved=client.get(f"/api/ai/sessions/{chat['id']}").json()['messages'][-1]
        assert saved['content']=='Generated retained fragment' and saved['meta']['provider']=='generated-protocol-only'
        assert 'generated-private-' not in json.dumps(saved)
    finally:app.dependency_overrides.clear()
