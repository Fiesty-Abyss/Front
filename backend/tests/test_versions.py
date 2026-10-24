from sqlalchemy import select, func
from front_api.db import new_session
from front_api import models as m
from conftest import png_bytes


def history(c,kind,id):return c.get(f'/api/versions/{kind}/{id}').json()['items']


def test_immutable_text_structured_restore_reuse_and_rollback(client):
    w=client.post('/api/worlds',json={'name':'测试世界'}).json()['id']
    c=client.post('/api/characters',json={'name':'甲','world_id':w,'profile':'第一段\n\n旧设定','gender':'unknown'}).json()['id']
    url=f'/api/versions/character/{c}'
    assert client.get(url).json()['enabled'] is False
    a=client.post(url,json={'note':'初稿'}).json()['id']
    client.patch(f'/api/characters/{c}',json={'profile':'第一段\n\n新设定','gender':'female'})
    rows=history(client,'character',c);b=rows[0]['id']
    diff=client.get(url+'/compare',params={'left':a,'right':b}).json()
    assert {f['field'] for f in diff['fields']}=={'profile','gender'}
    assert any(f.get('paragraphs') for f in diff['fields'])
    assert client.post(url+f'/{a}/restore',json={'expected_latest':a}).status_code==409
    restore=client.post(url+f'/{a}/restore',json={'expected_latest':b,'note':'采用旧稿'})
    assert restore.status_code==200,restore.text
    assert len(history(client,'character',c))==3
    assert client.get(f'/api/characters/{c}').json()['profile'].endswith('旧设定')
    assert client.get(url+f'/{a}').json()['payload']['gender']=='unknown'
    with new_session() as s:
        obj=s.get(m.Character,c);obj.name='不提交';s.flush();s.rollback()
    assert len(history(client,'character',c))==3
    client.delete(f'/api/characters/{c}')
    replacement=client.post('/api/characters',json={'name':'新人物','world_id':w}).json()['id']
    assert replacement==c # SQLite reuses max integer ID: never expose old history.
    assert client.get(url).json()['enabled'] is False
    assert client.get(url+f'/{a}').status_code==404
    with new_session() as s:assert s.scalar(select(func.count()).select_from(m.EntityVersion))==3


def test_media_retained_shared_restore_and_no_duplicate_blob(client,data_dir):
    def upload(color,name):
        r=client.post('/api/assets/upload',files={'file':(name,png_bytes(color),'image/png')});assert r.status_code==201,r.text
        return r.json()
    a=upload((10,20,30),'old.png');b=upload((80,90,100),'new.png')
    url=f'/api/versions/asset/{a["id"]}'
    v1=client.post(url,json={'note':'原图'}).json()['id']
    assert client.post(url,json={'note':'相同内容'}).json()['id']==v1
    v2=client.post(url+'/adopt',json={'asset_id':b['id'],'expected_latest':v1}).json()['id']
    assert len(history(client,'asset',a['id']))==2
    assert client.get(url+f'/{v1}/media').content==png_bytes((10,20,30))
    client.delete(f'/api/assets/{b["id"]}')
    assert (data_dir/b['file_path']).exists()
    r=client.post(url+f'/{v1}/restore',json={'expected_latest':v2})
    assert r.status_code==200,r.text
    assert client.get(f'/api/assets/{a["id"]}/file').content==png_bytes((10,20,30))
    with new_session() as s:
        assert s.scalar(select(func.count()).select_from(m.VersionBlob))==2
    client.delete(f'/api/assets/{a["id"]}')
    assert (data_dir/a['file_path']).exists() # Retained snapshots never delete owned historical bytes.


def test_index_snapshots_do_not_claim_media_or_copy_without_pin(client,tmp_path,data_dir):
    from front_api.ingest import index_file
    from front_api.projectpreview import stamp
    import hashlib
    p=tmp_path/'original.png';raw=png_bytes();p.write_bytes(raw)
    with new_session() as s:
        a,_=index_file(s,p,tmp_path,hashlib.sha256(raw).hexdigest());s.commit();aid=a.id
    url=f'/api/versions/asset/{aid}'
    old=client.post(url,json={}).json()['id']
    assert not list((data_dir/'media').iterdir())
    assert client.get(url+f'/{old}').json()['media_saved'] is False
    assert client.get(url+f'/{old}/media').status_code==409
    pinned=client.post(url+'/pin',json={'expected_latest':old,'note':'明确保存原件副本'})
    assert pinned.status_code==200,pinned.text
    rid=pinned.json()['id'];assert p.read_bytes()==raw
    assert client.get(url+f'/{rid}/media').content==raw
    assert len(list((data_dir/'media').rglob('*.png')))==1


def test_chapter_versions_and_reused_foreign_key_rejected(client):
    a=client.post('/api/assets',json={'title':'章节样本','kind':'novel','content':'第一章 起点\n甲出发。\n第二章 来信\n乙来信。'}).json()['id']
    url=f'/api/versions/asset/{a}';client.post(url,json={})
    plan=client.get(f'/api/assets/{a}/chapter-plan').json()
    original=[dict(c) for c in plan['chapters']]
    body={k:plan[k] for k in ('text_hash','base_revision','chapters')}
    body['chapters'][0]['title']='人工标题'
    assert client.put(f'/api/assets/{a}/chapter-plan',json=body).status_code==200
    before=history(client,'asset',a)[0]['id']
    body['base_revision']=client.get(f'/api/assets/{a}/chapter-plan').json()['base_revision']
    body['chapters'][0]['title']='再次修改'
    client.put(f'/api/assets/{a}/chapter-plan',json=body)
    now=history(client,'asset',a)[0]['id'];assert now!=before
    assert client.post(url+f'/{before}/restore',json={'expected_latest':now}).status_code==200
    assert client.get(f'/api/assets/{a}/chapter-plan').json()['chapters'][0]['title']=='人工标题'
    world=client.post('/api/worlds',json={'name':'旧世界'}).json()['id']
    char=client.post('/api/characters',json={'name':'角色','world_id':world}).json()['id']
    u=f'/api/versions/character/{char}';old=client.post(u,json={}).json()['id']
    client.delete(f'/api/worlds/{world}')
    reused=client.post('/api/worlds',json={'name':'新世界'}).json()['id'];assert reused==world
    client.patch(f'/api/characters/{char}',json={'world_id':reused})
    current=history(client,'character',char)[0]['id']
    assert client.post(u+f'/{old}/restore',json={'expected_latest':current}).status_code==409
