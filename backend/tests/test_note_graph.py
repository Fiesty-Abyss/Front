"""Generated note trees; no personal notes or external services."""
import pytest
from front_api.db import new_session
from front_api import models as m


def note(client, title, parent=None):
    r=client.post('/api/notes',json={'title':title,'parent_id':parent})
    assert r.status_code==201,r.text
    return r.json()['id']


def test_patch_cannot_bypass_move_cycle_guard(client):
    a=note(client,'root');b=note(client,'child',a);c=note(client,'grandchild',b)
    for parent in (a,b,c):
        r=client.patch(f'/api/notes/{a}',json={'parent_id':parent})
        assert r.status_code==422,r.text
        assert client.get(f'/api/notes/{a}').json()['parent_id'] is None
    assert client.patch(f'/api/notes/{a}',json={'parent_id':99999}).status_code==422
    assert client.post('/api/notes',json={'title':'invalid','parent_id':99999}).status_code==422
    assert client.patch(f'/api/notes/{b}',json={'parent_id':None}).status_code==200
    assert client.patch(f'/api/notes/{a}',json={'parent_id':c}).status_code==200
    assert client.get(f'/api/notes/{c}').json()['parent_id']==b


def test_history_restore_cannot_create_new_cycle(client):
    b=note(client,'旧父');a=note(client,'旧子',b)
    url=f'/api/versions/note/{a}'
    first=client.post(url,json={}).json()['id']
    assert client.patch(f'/api/notes/{a}',json={'parent_id':None}).status_code==200
    assert client.patch(f'/api/notes/{b}',json={'parent_id':a}).status_code==200
    latest=client.get(url).json()['items'][0]['id']
    r=client.post(url+f'/{first}/restore',json={'expected_latest':latest})
    assert r.status_code==422,r.text
    assert client.get(f'/api/notes/{a}').json()['parent_id'] is None
    assert client.get(url).json()['total']==2


@pytest.mark.parametrize('body',[{'parent_id':'invalid'}, {'parent_id':-1},
    {'parent_id':1.5}, {'position':'invalid'}, {'position':None}, {'unexpected':'field'}])
def test_move_bad_input_returns_422_without_mutation(client,body):
    a=note(client,'root')
    assert client.post(f'/api/notes/{a}/move',json=body).status_code==422
    row=client.get(f'/api/notes/{a}').json()
    assert row['parent_id'] is None and row['position']==0


def test_existing_cycle_diagnosed_and_can_be_detached(client):
    a=note(client,'one');b=note(client,'two',a);c=note(client,'other')
    # Deliberately simulate a legacy corrupt graph in an isolated fixture.
    with new_session() as s:
        s.get(m.Note,a).parent_id=b;s.commit()
    assert client.post(f'/api/notes/{c}/move',json={'parent_id':a}).status_code==409
    assert client.patch(f'/api/notes/{c}',json={'parent_id':a}).status_code==409
    assert client.patch(f'/api/notes/{a}',json={'parent_id':None}).status_code==200
    assert client.post(f'/api/notes/{c}/move',json={'parent_id':b,'position':7}).json()['position']==7
    assert client.post(f'/api/notes/{c}/move',json={'parent_id':None}).json()['position']==7


@pytest.mark.parametrize('key',['title','content','pinned','position'])
def test_non_nullable_patch_is_rejected_before_database_write(client,key):
    a=note(client,'root')
    assert client.patch(f'/api/notes/{a}',json={key:None}).status_code==422
    assert client.get(f'/api/notes/{a}').json()['title']=='root'


def test_filters_remain_422_via_existing_crud_guard(client):
    for key in ('work_id','parent_id'):
        assert client.get('/api/notes',params={key:'invalid'}).status_code==422
