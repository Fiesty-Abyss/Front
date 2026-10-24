from front_api.db import new_session
from front_api.routers.aitools import _known


def test_unscoped_known_does_not_include_world_names_or_aliases(client):
    world=client.post('/api/worlds',json={'name':'World'}).json()['id']
    scoped=client.post('/api/characters',json={'name':'Scoped','alias':'PrivateAlias','world_id':world}).json()['id']
    unscoped=client.post('/api/characters',json={'name':'Unscoped'}).json()['id']
    with new_session() as session:
        assert _known(session,None)=={'Unscoped':unscoped}
        assert _known(session,world)=={'Scoped':scoped,'PrivateAlias':scoped}


def test_apply_rejects_foreign_world_ids_atomically(client):
    one=client.post('/api/worlds',json={'name':'Same'}).json()['id']
    two=client.post('/api/worlds',json={'name':'Same'}).json()['id']
    original=client.post('/api/characters',json={'name':'Hero','world_id':two,'profile':'original'}).json()
    request={'world_id':one,'update_existing':True,'characters':[{'name':'New'},{'name':'Hero','existing_id':original['id'],'summary':'wrong world'}]}
    assert client.post('/api/ai/extract/apply',json=request).status_code==422
    assert client.get('/api/characters').json()['total']==1
    assert client.get('/api/characters/'+str(original['id'])).json()['profile']=='original'
    request['world_id']=None
    assert client.post('/api/ai/extract/apply',json=request).status_code==422
    request['world_id']=two
    assert client.post('/api/ai/extract/apply',json=request).status_code==200


def test_scoped_source_rejected_before_ai_call(client):
    world=client.post('/api/worlds',json={'name':'World'}).json()['id']
    asset=client.post('/api/assets',json={'title':'Novel','kind':'novel','content':'private fictional text','world_id':world}).json()['id']
    assert client.post('/api/ai/extract/characters',json={'asset_id':asset}).status_code==422
    assert client.get('/api/jobs?kind=extract').json()==[]
    # Correct scope reaches normal provider availability validation, without sending text.
    assert client.post('/api/ai/extract/characters',json={'asset_id':asset,'world_id':world}).status_code==503
