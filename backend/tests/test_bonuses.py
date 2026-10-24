from conftest import png_bytes
from test_ai_drawing import wait_job


def test_bonus_shared_files_suggestions_personal_versions_and_groups(client,data_dir):
    work=client.post('/api/works',json={'title':'Generated work','kind':'game'}).json()
    a=client.post('/api/assets/upload',files={'file':('Steam-wallpaper.png',png_bytes(),'image/png')},data={'work_id':work['id']}).json()
    package=client.post('/api/bonuses',json={'title':'Generated Deluxe extras','work_id':work['id']}).json();pid=package['id']
    group=client.post(f'/api/bonuses/{pid}/groups',json={'name':'壁纸'}).json()['id']
    r=client.post(f'/api/bonuses/{pid}/items',json={'asset_ids':[a['id']],'group_id':group});assert r.status_code==200,r.text
    client.post(f'/api/bonuses/{pid}/items',json={'asset_ids':[a['id']]})
    items=client.get(f'/api/bonuses/{pid}/items').json();assert items['total']==1
    item=items['items'][0];assert item['category']=='未确认' and item['source']=='' and not item['suggestion']['confirmed']
    assert client.get('/api/assets').json()['total']==1
    old=item['version'];updated=client.put(f"/api/bonuses/{pid}/items/{item['id']}",json={'category':'CG与壁纸','group_id':group,'source':'人工确认：自制生成样本','version_label':'v2','notes':'修改记录','stars':5,'preference':91,'expected_version':old})
    assert updated.status_code==200,updated.text
    new=updated.json();assert new['version']!=old
    assert client.post(f"/api/versions/bonus_item/{item['id']}/{old}/restore",json={'expected_latest':new['version']}).status_code==200
    assert client.get(f'/api/bonuses/{pid}/items').json()['items'][0]['category']=='未确认'
    assert (data_dir/a['file_path']).read_bytes()==png_bytes()


def test_bonus_scope_identity_and_sync_reuse(client):
    x=client.post('/api/works',json={'title':'A'}).json()['id'];y=client.post('/api/works',json={'title':'B'}).json()['id']
    a=client.post('/api/assets/upload',files={'file':('generated.png',png_bytes(),'image/png')},data={'work_id':y}).json()
    package=client.post('/api/bonuses',json={'title':'A extras','work_id':x}).json();pid=package['id']
    assert client.post(f'/api/bonuses/{pid}/items',json={'asset_ids':[a['id']]}).status_code==422
    assert client.post(f'/api/bonuses/{pid}/items',json={'asset_ids':[a['id']],'allow_cross_scope':True}).status_code==200
    item=client.get(f'/api/bonuses/{pid}/items').json()['items'][0];assert item['status']=='ok'
    client.delete(f"/api/assets/{a['id']}");new=client.post('/api/assets/upload',files={'file':('new.png',png_bytes((45,50,60)),'image/png')}).json();assert new['id']==a['id']
    assert client.get(f'/api/bonuses/{pid}/items').json()['items'][0]['status']!='ok'
    client.post(f"/api/collections/{package['collection_id']}/items",json={'asset_ids':[new['id']]})
    job=wait_job(client,client.post(f'/api/bonuses/{pid}/sync').json());assert job['status']=='done',job
    assert client.get(f'/api/bonuses/{pid}/items').json()['total']==2
    assert client.get('/api/assets').json()['total']==1


def test_bonus_directory_groups_scope_and_backup(client,tmp_path):
    from pathlib import Path
    from front_api import backups,jobs
    from contextlib import closing
    import sqlite3
    a=client.post('/api/assets/upload',files={'file':('generated.png',png_bytes(),'image/png')}).json()
    package=client.post('/api/bonuses',json={'title':'Folders'}).json();pid=package['id']
    root=tmp_path/'Generated extras';folder=root/'Artbook'/'Wallpapers';folder.mkdir(parents=True);(folder/'generated.png').write_bytes(png_bytes())
    scan=wait_job(client,client.post('/api/project-previews',json={'path':str(root)}).json())
    imported=client.post('/api/library-imports',json={'report_id':scan['result']['report_id'],'indices':[0],'collection_id':package['collection_id']}).json();wait_job(client,imported['job'])
    wait_job(client,client.post(f'/api/bonuses/{pid}/sync').json())
    assert client.get('/api/assets').json()['total']==1
    groups=client.get(f'/api/bonuses/{pid}/groups').json()['items'];assert len(groups)==2 and any(g['parent_id'] for g in groups)
    other=client.post('/api/bonuses',json={'title':'Other'}).json()['id']
    assert client.post(f'/api/bonuses/{other}/groups',json={'name':'wrong','parent_id':groups[0]['id']}).status_code==422
    item=client.get(f'/api/bonuses/{pid}/items').json()['items'][0]
    world=client.post('/api/worlds',json={'name':'New scope'}).json()['id']
    client.put(f'/api/bonuses/{pid}',json={'title':'Folders','world_id':world,'expected_version':package['version']})
    assert client.post(f"/api/versions/bonus_item/{item['id']}/{item['version']}/restore",json={'expected_latest':item['version']}).status_code==409
    job=jobs.Job('full-backup','generated extras');backups.create(job);restored=jobs.Job('full-restore','isolated extras');backups.restore(restored,backups.package_for(job.result['backup_id']))
    with closing(sqlite3.connect(Path(restored.result['path'])/'front.db')) as db:
        assert db.execute('SELECT count(*) FROM bonus_archives').fetchone()[0]==2
        assert db.execute('SELECT count(*) FROM bonus_items').fetchone()[0]==1
        assert db.execute('PRAGMA foreign_key_check').fetchall()==[]
