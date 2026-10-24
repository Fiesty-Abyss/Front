from conftest import png_bytes


def draft(row,**changes):
    keys=('title','fields','designs','source','favorite','stars','preference','notes')
    return {k:row[k] for k in keys}|{'tag_ids':[t['id'] for t in row['tags']],'expected_version':row['version']}|changes


def test_independent_oc_versions_publish_and_existing_character(client):
    r=client.post('/api/oc',json={'title':'生成独立OC','fields':{'发型':'短发','自定义能力':''},'designs':[{'name':'日常服','fields':{'服装':'风衣'}}]})
    assert r.status_code==201,r.text
    oc=r.json();assert oc['world_id'] is None and oc['character_id']
    assert client.get('/api/oc?world_id=none').json()['total']==1
    old=oc['version'];oc=client.put(f'/api/oc/{oc["id"]}',json=draft(oc,fields={'发型':'长发'},stars=5,preference=92)).json()
    assert oc['version']!=old
    assert client.put(f'/api/oc/{oc["id"]}',json=draft(oc,expected_version=old)).status_code==409
    history=client.get(f'/api/versions/oc/{oc["id"]}').json();assert history['total']==2
    restored=client.post(f'/api/versions/oc/{oc["id"]}/{old}/restore',json={'expected_latest':oc['version']})
    assert restored.status_code==200,restored.text
    current=client.get(f'/api/oc/{oc["id"]}').json();assert current['fields']['发型']=='短发'
    assert client.get(f'/api/versions/oc/{oc["id"]}').json()['total']==3
    pub=f'/api/oc/{oc["id"]}/publish'
    assert client.post(pub,json={'expected_version':current['version']}).status_code==422
    assert client.post(pub,json={'expected_version':current['version'],'confirmed':True}).status_code==200
    c=client.get(f'/api/characters/{oc["character_id"]}').json()
    assert '短发' in c['profile']
    client.post(pub,json={'expected_version':current['version'],'confirmed':True})
    assert client.get(f'/api/characters/{oc["character_id"]}').json()['profile']==c['profile']
    source=client.post('/api/characters',json={'name':'已有角色','profile':'正式设定保持不变'}).json()
    from_existing=client.post('/api/oc',json={'title':'创作档案','character_id':source['id']});assert from_existing.status_code==201
    assert client.get(f'/api/characters/{source["id"]}').json()['profile']==source['profile']
    assert client.post('/api/oc',json={'title':'重复','character_id':source['id']}).status_code==409


def test_oc_reference_scope_identity_and_non_destructive_remove(client,data_dir):
    a=client.post('/api/worlds',json={'name':'同名世界'}).json()['id'];b=client.post('/api/worlds',json={'name':'同名世界'}).json()['id']
    oc=client.post('/api/oc',json={'title':'角色','world_id':a}).json();url=f'/api/oc/{oc["id"]}'
    asset=client.post('/api/assets/upload',files={'file':('generated.png',png_bytes(),'image/png')},data={'world_id':b}).json()
    ref={'kind':'asset','entity_id':asset['id'],'expected_version':oc['version'],'as_cover':True}
    assert client.post(url+'/references',json=ref).status_code==422
    r=client.post(url+'/references',json=ref|{'allow_cross_world':True});assert r.status_code==200,r.text
    oc=r.json();assert oc['references'][0]['status']=='ok' and oc['cover_asset_id']==asset['id']
    old=oc['version']
    client.patch(f'/api/characters/{oc["character_id"]}',json={'world_id':b})
    assert client.post(f'/api/versions/oc/{oc["id"]}/{old}/restore',json={'expected_latest':old}).status_code==409
    rid=oc['references'][0]['id']
    removed=client.delete(url+f'/references/{rid}?expected_version={old}');assert removed.status_code==200
    assert (data_dir/asset['file_path']).exists()
    oc=removed.json();client.post(url+'/references',json={'kind':'asset','entity_id':asset['id'],'expected_version':oc['version']})
    client.delete(f'/api/assets/{asset["id"]}')
    new=client.post('/api/assets/upload',files={'file':('new.png',png_bytes((20,30,40)),'image/png')}).json()
    assert new['id']==asset['id']
    assert client.get(url).json()['references'][0]['status']!='ok'
    assert client.get('/api/oc',params={'world_id':a}).json()['total']==0
    assert client.get('/api/oc',params={'world_id':b}).json()['total']==1


def test_oc_validation_and_delete_keeps_canonical_assets(client):
    assert client.post('/api/oc',json={'title':'bad','fields':{'x':'a'*10001}}).status_code==422
    oc=client.post('/api/oc',json={'title':'设计','designs':[{'id':'same','name':'A'},{'id':'same','name':'B'}]});assert oc.status_code==422
    assert client.get('/api/characters').json()['total']==0
    oc=client.post('/api/oc',json={'title':'保留百科'}).json()
    assert client.delete(f'/api/oc/{oc["id"]}?expected_version={oc["version"]}').status_code==204
    assert client.get(f'/api/characters/{oc["character_id"]}').status_code==200
