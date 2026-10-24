import hashlib
import json
import sqlite3
import time

from front_api import projectarchive as archive
from front_api.db import new_session,get_engine
from front_api import models as m


def wait(client,job_id):
    for _ in range(500):
        job=client.get('/api/jobs/'+job_id).json()
        if job['status'] not in ('queued','running'):return job
        time.sleep(.01)
    raise AssertionError('timeout')


def preview(client,root):
    job=client.post('/api/project-previews',json={'path':str(root)}).json()
    result=wait(client,job['id']);assert result['status']=='done',result
    return result['result']['report_id']


def begin(client,root,mode='index',world=None):
    pid=preview(client,root)
    entries=client.get('/api/project-previews/'+pid).json()['items']
    request={'report_id':pid,'mode':mode,'files':[{'index':f['index']} for f in entries]}
    request.update({'world_id':world} if world else {'new_world_name':'Generated world'})
    response=client.post('/api/project-imports',json=request)
    assert response.status_code==202,response.text
    result=response.json();job=wait(client,result['job']['id']);assert job['status']=='done',job
    return result


def test_index_managed_dedup_and_local_preferences(client,tmp_path,data_dir):
    root=tmp_path/'original';root.mkdir();source=root/'novel.txt';source.write_text('第一章 开始\n原始设定',encoding='utf-8')
    original=source.read_bytes()
    first=begin(client,root)
    page=client.get(f'/api/worlds/{first["world_id"]}/archive').json();assert page['total']==1
    resource=page['items'][0];asset_id=resource['entity_id']
    assert not list(data_dir.glob('media/**/*txt'))
    assert client.get(f'/api/assets/{asset_id}/file').content==original
    client.patch(f'/api/assets/{asset_id}',json={'meta':{'external_path':str(tmp_path/'secret')}})
    assert client.get(f'/api/assets/{asset_id}/file').content==original
    again=begin(client,root,world=first['world_id'])
    assert client.get(f'/api/project-imports/{again["import_id"]}').json()['counts']=={'duplicate':1}
    second=begin(client,root,mode='managed')
    assert client.get('/api/assets').json()['total']==1
    assert client.get(f'/api/worlds/{second["world_id"]}/archive').json()['total']==1
    label=client.post(f'/api/worlds/{first["world_id"]}/labels',json={'name':'正式','aliases':['final']}).json()['id']
    assert client.patch(f'/api/worlds/{first["world_id"]}/archive',json={'ids':[resource['id']],'favorite':True,'stars':4,'preference':90,'label_ids':[label],'notes':'world-local'}).status_code==200
    assert client.get(f'/api/worlds/{first["world_id"]}/archive?label_id={label}&q=原始设定').json()['total']==1
    foreign=client.get(f'/api/worlds/{second["world_id"]}/archive').json()['items'][0]
    assert not foreign['favorite'] and not foreign['notes']
    assert client.patch(f'/api/worlds/{second["world_id"]}/archive',json={'ids':[foreign['id']],'label_ids':[label]}).status_code==422
    assert client.delete(f'/api/worlds/{first["world_id"]}/archive/{resource["id"]}').status_code==204
    assert source.read_bytes()==original
    global_one=client.post('/api/tags',json={'name':'global-one'}).json()['id']
    global_two=client.post('/api/tags',json={'name':'global-two'}).json()['id']
    client.patch(f'/api/worlds/{second["world_id"]}/archive',json={'ids':[foreign['id']],'global_tag_ids':[global_one]})
    assert client.get('/api/tags/usage').json()[str(global_one)]['direct']==1
    assert client.post(f'/api/tags/{global_one}/merge',json={'into_id':global_two}).status_code==200
    assert client.get(f'/api/worlds/{second["world_id"]}/archive?tag_id={global_two}').json()['total']==1
    client.delete(f'/api/tags/{global_two}')
    assert client.get(f'/api/worlds/{second["world_id"]}/archive').json()['items'][0]['global_tag_ids']==[]


def test_partial_import_resume_and_missing_source(client,tmp_path,monkeypatch):
    root=tmp_path/'original';root.mkdir()
    for name in ('a.txt','b.txt'):(root/name).write_text(name,encoding='utf-8')
    original=archive.index_file;fail=[True]
    def injected(session,path,*args,**kwargs):
        if path.name=='b.txt' and fail[0]:fail[0]=False;raise OSError('injected failure')
        return original(session,path,*args,**kwargs)
    monkeypatch.setattr(archive,'index_file',injected)
    run=begin(client,root)
    assert client.get(f'/api/project-imports/{run["import_id"]}').json()['status']=='partial'
    resumed=client.post(f'/api/project-imports/{run["import_id"]}/resume').json()
    assert wait(client,resumed['job']['id'])['status']=='done'
    assert client.get(f'/api/project-imports/{run["import_id"]}').json()['status']=='done'
    assert client.get('/api/assets').json()['total']==2
    page=client.get(f'/api/worlds/{run["world_id"]}/archive').json()
    chosen=next(r for r in page['items'] if r['title']=='a')
    (root/'a.txt').rename(root/'moved.txt')
    assert client.get(f'/api/assets/{chosen["entity_id"]}/file').status_code==409
    begin(client,root,world=run['world_id'])
    assert client.get(f'/api/assets/{chosen["entity_id"]}/file').content==b'a.txt'
    assert client.delete(f'/api/assets/{chosen["entity_id"]}').status_code==204
    assert (root/'moved.txt').is_file()
    assert client.get(f'/api/worlds/{run["world_id"]}/archive/{chosen["id"]}').json()['missing_record']
    with new_session() as session:
        pending=m.ProjectImport(id='interrupted-test',world_id=run['world_id'],mode='index',report_id='000000000000',status='running')
        session.add(pending);session.commit()
    archive.recover(get_engine())
    assert client.get('/api/project-imports/interrupted-test').json()['status']=='interrupted'


def test_world_label_hierarchy_and_reference_confirmation(client):
    one=client.post('/api/worlds',json={'name':'Same'}).json()['id']
    two=client.post('/api/worlds',json={'name':'Same'}).json()['id']
    parent=client.post(f'/api/worlds/{one}/labels',json={'name':'人物'}).json()['id']
    child=client.post(f'/api/worlds/{one}/labels',json={'name':'主角','parent_id':parent}).json()['id']
    assert client.put(f'/api/worlds/{one}/labels/{parent}',json={'name':'人物','parent_id':child}).status_code==422
    assert client.post(f'/api/worlds/{two}/labels',json={'name':'人物'}).status_code==200
    assert client.post(f'/api/worlds/{two}/labels',json={'name':'主角','parent_id':parent}).status_code==422
    char=client.post('/api/characters',json={'name':'同名人物','world_id':one}).json()['id']
    assert client.post(f'/api/worlds/{two}/archive/references',json={'entity_kind':'character','entity_id':char}).status_code==422
    assert client.post(f'/api/worlds/{two}/archive/references',json={'entity_kind':'character','entity_id':char,'allow_cross_world':True}).status_code==200
    client.post(f'/api/worlds/{one}/archive/sync')
    assert client.get(f'/api/worlds/{one}/archive?q=同名人物').json()['total']==1


def test_schema_backup_restores_legacy_rows(data_dir):
    from front_api.main import create_app
    data_dir.mkdir()
    with sqlite3.connect(data_dir/'front.db') as conn:
        conn.execute('CREATE TABLE worlds (id INTEGER PRIMARY KEY,name TEXT,summary TEXT,content TEXT,created_at DATETIME,updated_at DATETIME)')
        conn.execute("INSERT INTO worlds VALUES (1,'legacy','keep','original setting','2026-01-01','2026-01-01')")
    create_app()
    backups=list((data_dir/'backups').glob('pre-schema-*/front.db'))
    assert len(backups)==1
    with sqlite3.connect(backups[0]) as old,sqlite3.connect(data_dir/'restored-test.db') as restored:
        old.backup(restored)
        assert restored.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
        assert restored.execute('SELECT content FROM worlds').fetchone()[0]=='original setting'
    with sqlite3.connect(data_dir/'front.db') as current:
        assert current.execute('SELECT content FROM worlds').fetchone()[0]=='original setting'
        assert current.execute("SELECT name FROM sqlite_master WHERE name='world_resources'").fetchone()
