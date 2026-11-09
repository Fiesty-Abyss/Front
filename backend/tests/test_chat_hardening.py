"""Generated messages and in-process ASGI/HTTP protocols; no GUI or service launch."""
import asyncio
import copy
import json
import threading
from concurrent.futures import ThreadPoolExecutor

import httpx
import pytest
from sqlalchemy import select

from front_api import chatmodels, models as m, schemas as s
from front_api.ai.provider import OpenAICompatibleProvider
from front_api.db import new_session
from front_api.routers import ai


def msg(role, content):
    return {'role':role,'content':content}


def test_trim_never_orphans_an_answer_and_counts_both_units():
    values=[msg('system','S'),msg('user','old question'),msg('assistant','answer'),msg('user','now')]
    original=copy.deepcopy(values)
    result,budget=chatmodels.bound_context(values,14)
    assert result==[values[0],values[-1]]
    assert budget['dropped_turns']==1 and budget['dropped_messages']==2
    assert budget['omitted'][0]['positions']==[1,2] and values==original
    for value in ([],[msg('system','S')],[msg('assistant','greeting')]):
        assert chatmodels.bound_context(value,100)[0]==value


def test_latest_whole_turn_and_all_system_messages_are_mandatory():
    values=[msg('system','S'),msg('user','long question'),msg('system','lore'),msg('assistant','answer')]
    with pytest.raises(Exception) as exc:chatmodels.bound_context(values,10)
    assert exc.value.status_code==422
    history=[msg('assistant','greeting')]
    for i in range(30):history += [msg('user',f'Q{i}'),msg('assistant',f'A{i}')]
    values=[msg('system','S'),*history,msg('system','footer')]
    result,budget=chatmodels.bound_context(values,None)
    assert result[0]['content']=='S' and result[1]['role']=='user' and result[-1]['content']=='footer'
    assert budget['dropped_messages']==21 and budget['dropped_turns']==10
    assert budget['dropped_units']==11 and budget['dropped_introductions']==1


@pytest.fixture
def chat(client):
    card=client.post('/api/cards',json={'name':'Generated','first_mes':'hello','description':'setting'}).json()
    return client.post('/api/ai/sessions',json={'card_id':card['id']}).json()


def response(chat,provider):
    with new_session() as db:
        return ai.generate(chat['id'],s.ChatGenerate(content='Generated request'),db,provider)


class Provider:
    name=model='generated'
    calls=0
    closed=False
    def available(self):return True
    def stream(self,messages):
        self.calls+=1
        try:yield 'generated partial';yield ' completion'
        finally:self.closed=True


async def asgi_disconnect(res, event):
    async def receive():return {'type':'http.disconnect'}
    async def send(message):
        if (event=='headers' and message['type']=='http.response.start') or (
            message['type']=='http.response.body' and ('event: '+event).encode() in message.get('body',b'')):
            raise OSError('generated browser disconnect')
    try:
        await res({'type':'http','asgi':{'spec_version':'2.4'}},receive,send)
    except Exception:
        pass  # ASGI implementations expose ClientDisconnect or an exception group.


@pytest.mark.parametrize('event',['headers','start','delta'])
def test_response_owns_disconnect_before_first_event_and_partial(client,chat,event):
    provider=Provider();res=response(chat,provider)
    assert ai.has_active_generations()
    asyncio.run(asgi_disconnect(res,event))
    assert res.owner.closed and not ai.has_active_generations()
    saved=client.get(f"/api/ai/sessions/{chat['id']}").json()
    if event=='delta':
        assert saved['messages'][-1]['content']=='generated partial'
        assert saved['messages'][-1]['meta']['interrupted'] and provider.closed
    else:assert provider.calls==0 and saved['messages'][-1]['role']=='user'
    assert client.patch(f"/api/ai/sessions/{chat['id']}",json={'title':'editable again'}).status_code==200
    retry=response(chat,Provider());retry.owner.close()
    assert not ai.has_active_generations()


def test_blocked_upstream_keeps_slot_until_worker_returns(client,chat):
    entered=threading.Event();finish=threading.Event()
    class Blocked(Provider):
        def stream(self,messages):
            entered.set();finish.wait(5)
            try:yield 'not admitted after cancel'
            finally:self.closed=True
    provider=Blocked();res=response(chat,provider);next(res.owner)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future=pool.submit(next,res.owner)
        try:
            assert entered.wait(2)
            res.owner.close()
            assert ai.has_active_generations()  # no false claim that remote computation stopped
            assert client.patch(f"/api/ai/sessions/{chat['id']}",json={'title':'blocked'}).status_code==409
        finally:finish.set()
        future.result(timeout=5)
    assert provider.closed and not ai.has_active_generations()


@pytest.mark.parametrize('failure',[httpx.ReadTimeout('generated secret'),ValueError('generated malformed'),64001,{}])
def test_failures_limits_close_stream_keep_partial_and_unlock(client,chat,failure):
    class Broken(Provider):
        def stream(self,messages):
            try:
                yield 'safe partial'
                if isinstance(failure,Exception):raise failure
                yield 'x'*failure if isinstance(failure,int) else failure
            finally:self.closed=True
    provider=Broken();res=response(chat,provider)
    events=list(res.owner);res.owner.close()
    assert 'event: error' in events[-1] and 'generated secret' not in ''.join(events)
    assert provider.closed and not ai.has_active_generations()
    saved=client.get(f"/api/ai/sessions/{chat['id']}").json()
    assert saved['messages'][-1]['content']=='safe partial' and saved['messages'][-1]['meta']['error']


def test_terminal_event_already_released_both_slots(client,chat):
    res=response(chat,Provider())
    while True:
        event=next(res.owner)
        if 'event: done' in event:break
    assert not ai.has_active_generations()
    retry=response(chat,Provider());res.owner.close();assert ai.has_active_generations();retry.owner.close()
    assert not ai._session_running and not ai._running


@pytest.mark.parametrize('body',[b'data: not-json\n\n',b'data: []\n\n',b'data: {"choices":{}}\n\n',
    b'data: {"choices":[{"delta":{"content":7}}]}\n\n',
    b'data: {"choices":[{"delta":{"content":"partial"}}]}\n\n'])
def test_malformed_or_truncated_upstream_is_not_success(body):
    provider=OpenAICompatibleProvider('http://generated.invalid/v1','generated',transport=httpx.MockTransport(
        lambda req:httpx.Response(200,headers={'content-type':'text/event-stream'},content=body)))
    with pytest.raises(Exception):list(provider.stream([msg('user','generated')]))


def test_preview_omissions_and_rejected_budget_leave_database_unchanged(client,chat):
    from front_api.db import new_session
    with new_session() as db:
        c=db.get(m.ChatSession,chat['id']);parent=c.head_id
        for i in range(25):
            for role in ('user','assistant'):
                row=m.ChatMessage(session_id=c.id,parent_id=parent,role=role,content=f'{role}{i}')
                db.add(row);db.flush();parent=row.id
        c.head_id=parent;db.commit()
    url=f"/api/ai/sessions/{chat['id']}"
    original=client.get(url).json()
    context=client.get(url+'/context').json()
    assert context['budget']['dropped_messages']==11 and len(context['omitted_messages'])==11
    assert context['messages'][1]['role']=='user' and client.get(url).json()==original
    # A different selected branch must not send the old branch's text.
    client.post(url+'/select',json={'message_id':chat['messages'][0]['id']})
    # Update a long system setting and a small explicit model budget.
    p=client.post('/api/ai/providers',json={'name':'generated','base_url':'http://generated.invalid/v1','chat_model':'generated'}).json()
    expected=client.get(url+'/model-state').json()['expected']
    client.post(url+'/model-selection',json={'provider_id':p['id'],'model':'generated','context_characters':1024,'expected':expected})
    client.patch('/api/cards/'+str(chat['card_id']),json={'description':'x'*2000})
    before=client.get(url).json()
    assert client.post(url+'/generate',json={'content':'must not be committed'}).status_code==422
    assert client.get(url).json()==before and not ai.has_active_generations()


def test_long_context_omission_preview_is_bounded_and_paged(client,chat,tmp_path):
    with new_session() as db:
        c=db.get(m.ChatSession,chat['id']);parent=c.head_id
        for i in range(120):
            for role in ('user','assistant'):
                row=m.ChatMessage(session_id=c.id,parent_id=parent,role=role,content=f'{role}-{i} '+('X'*4096))
                db.add(row);db.flush();parent=row.id
        row=m.ChatMessage(session_id=c.id,parent_id=parent,role='user',content='current request')
        db.add(row);db.flush();c.head_id=row.id;db.commit()
    url=f"/api/ai/sessions/{chat['id']}"
    p=client.post('/api/ai/providers',json={'name':'generated','base_url':'http://generated.invalid/v1','chat_model':'generated'}).json()
    expected=client.get(url+'/model-state').json()['expected']
    assert client.post(url+'/model-selection',json={'provider_id':p['id'],'model':'generated','context_characters':1024,'expected':expected}).status_code==200
    response=client.get(url+'/context')
    assert response.status_code==200 and len(response.content)<16000
    page=response.json()
    assert page['budget']['dropped_messages']==241 and page['budget']['dropped_turns']==120
    assert page['omitted_total']==241 and len(page['omitted_messages'])==20
    assert any(m['truncated'] for m in page['omitted_messages'])
    assert len(page['budget']['omitted'])<=20
    later=client.get(url+'/context?omitted_offset=20&omitted_limit=20').json()
    assert later['head_id']==page['head_id']
    assert not ({m['position'] for m in page['omitted_messages']} & {m['position'] for m in later['omitted_messages']})
    assert client.get(url+'/context?omitted_limit=101').status_code==422
    (tmp_path/'omission-preview.json').write_text(json.dumps({'response_bytes':len(response.content),
        'omitted_messages':241,'page_size':20,'excerpt_characters':240,'gui':False}),encoding='utf-8')


def test_asgi_disconnect_task_cancels_before_first_body(client,chat):
    res=response(chat,Provider())
    async def run():
        async def send(message):await asyncio.Event().wait()
        async def receive():return {'type':'http.disconnect'}
        await res({'type':'http','asgi':{'spec_version':'2.0'}},receive,send)
    asyncio.run(run())
    assert res.owner.closed and not ai.has_active_generations()


def test_actual_request_has_complete_turns_and_no_other_branch(app,client,chat):
    captured=[]
    class Capture(Provider):
        def stream(self,messages):captured.append(copy.deepcopy(messages));yield 'generated answer'
    app.dependency_overrides[ai.provider_dep]=lambda:Capture()
    try:
        url=f"/api/ai/sessions/{chat['id']}"
        first=client.post(url+'/generate',json={'content':'old branch question'}).text
        state=client.get(url).json();old_user=next(x for x in state['messages'] if x['role']=='user')
        client.post(url+'/generate',json={'edit_id':old_user['id'],'content':'new branch question'})
        client.post(url+'/generate',json={'content':'latest request'})
        request=captured[-1]
        assert 'old branch question' not in json.dumps(request)
        assert [x['role'] for x in request]==['system','assistant','user','assistant','user']
        assert request[-1]['content']=='latest request' and request[-3]['content']=='new branch question'
    finally:app.dependency_overrides.clear()
