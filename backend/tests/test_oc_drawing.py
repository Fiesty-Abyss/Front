import io
import hashlib
from pathlib import Path
from PIL import Image,ImageDraw
from conftest import png_bytes
from test_ai_drawing import wait_job


def fixture(client):
    oc=client.post('/api/oc',json={'title':'练习OC'}).json();url=f"/api/oc/{oc['id']}"
    img=Image.new('RGB',(120,100),'white');ImageDraw.Draw(img).ellipse((20,10,90,80),fill='blue');b=io.BytesIO();img.save(b,'PNG');original=b.getvalue()
    r=client.post(url+'/manual-image',files={'file':('practice.png',original,'image/png')},data={'expected_version':oc['version']}).json()
    return client.get(url).json(),url,r['reference_id'],original


def test_learning_collection_refs_history_and_originals(client,data_dir):
    oc,url,rid,original=fixture(client);asset_id=oc['references'][0]['entity_id']
    s=client.post(url+'/studies',json={'title':'排线学习','notes':'生成样本'}).json();sid=s['id'];v=s['version']
    s=client.post(f'/api/oc-studies/{sid}/entries',json={'reference_id':rid,'stage':'hatching','notes':'第一次','learned_on':'2026-10-24','expected_version':v}).json()
    assert s['entries'][0]['stage']=='hatching'
    col=client.get(f"/api/collections/{s['collection_id']}").json();assert [a['id'] for a in col['assets']]==[asset_id]
    assert client.get('/api/assets').json()['total']==1
    eid=s['entries'][0]['id'];old=s['version']
    updated=client.patch(f'/api/oc-studies/{sid}/entries/{eid}',json={'stage':'color','notes':'修改过程','expected_version':old});assert updated.status_code==200
    assert client.patch(f'/api/oc-studies/{sid}/entries/{eid}',json={'expected_version':old}).status_code==409
    v=updated.json()['version'];restored=client.post(f'/api/versions/study/{sid}/{old}/restore',json={'expected_latest':v});assert restored.status_code==200,restored.text
    s=client.get(f'/api/oc-studies/{sid}').json();assert s['entries'][0]['stage']=='hatching'
    assert client.get(f'/api/versions/study/{sid}').json()['total']>=4
    # Removing the OC reference does not break a study's independently versioned reference.
    client.delete(url+f"/references/{rid}?expected_version={oc['version']}")
    assert client.get(f'/api/oc-studies/{sid}/entries/{eid}/file').content==original
    client.delete(f'/api/oc-studies/{sid}/entries/{eid}?expected_version={s["version"]}')
    assert client.get('/api/assets').json()['total']==1
    assert len(client.get(f"/api/collections/{s['collection_id']}").json()['assets'])==1


def test_raster_lineart_exports_and_managed_backup(client,data_dir):
    oc,url,rid,original=fixture(client)
    for fmt in ['png','jpeg','webp']:
        job=wait_job(client,client.post(url+'/render',json={'reference_id':rid,'operation':'export','format':fmt,'background':'white','expected_version':oc['version']}).json());assert job['status']=='done',job
        response=client.get(job['result']['download']);assert response.status_code==200
        with Image.open(io.BytesIO(response.content)) as img:assert img.size==(120,100) and img.format=={'png':'PNG','jpeg':'JPEG','webp':'WEBP'}[fmt]
    s=client.post(url+'/studies',json={'title':'线稿练习'}).json()
    job=wait_job(client,client.post(url+'/render',json={'reference_id':rid,'study_id':s['id'],'operation':'lineart','background':'transparent','expected_version':oc['version']}).json());assert job['status']=='done',job
    current=client.get(url).json();assert len(current['references'])==2
    aid=job['result']['asset_id'];asset=client.get(f'/api/assets/{aid}').json();assert asset['meta']['derivation']['raster']
    with Image.open(data_dir/asset['file_path']) as img:assert img.mode=='RGBA' and img.getextrema()[3][0]==0 and img.getextrema()[3][1]>0
    assert client.get(url+f'/images/{rid}/file?download=true').content==original
    assert len(client.get(f"/api/oc-studies/{s['id']}").json()['entries'])==1
    from front_api import backups,jobs
    j=jobs.Job('full-backup','generated study test');backups.create(j);package=backups.package_for(j.result['backup_id']);manifest,issues=backups.verify(package);assert not issues
    r=jobs.Job('full-restore','isolated study restore');backups.restore(r,package);assert r.result['status']=='verified'
    import sqlite3
    from contextlib import closing
    with closing(sqlite3.connect(Path(r.result['path'])/'front.db')) as db:
        assert db.execute('SELECT count(*) FROM oc_studies').fetchone()[0]==1
        assert db.execute('SELECT count(*) FROM oc_profiles').fetchone()[0]==1
    assert hashlib.sha256(client.get(url+f'/images/{rid}/file').content).digest()==hashlib.sha256(original).digest()


def test_drawing_scope_and_source_hash_guards(client,data_dir):
    oc,url,rid,original=fixture(client)
    other=client.post('/api/oc',json={'title':'另一个OC'}).json();s=client.post(f"/api/oc/{other['id']}/studies",json={'title':'隔离'}).json()
    assert client.post(url+'/render',json={'reference_id':rid,'study_id':s['id'],'expected_version':oc['version']}).status_code==422
    asset=client.get(f"/api/assets/{oc['references'][0]['entity_id']}").json();(data_dir/asset['file_path']).write_bytes(png_bytes())
    job=wait_job(client,client.post(url+'/render',json={'reference_id':rid,'operation':'lineart','expected_version':oc['version']}).json());assert job['status']=='error'
    assert client.get('/api/assets').json()['total']==1


def test_raster_limits_cancellation_and_no_source_mutation(tmp_path,monkeypatch):
    from front_api import artwork,jobs
    source=tmp_path/'source.png';source.write_bytes(png_bytes());before=source.read_bytes()
    def cancel():raise jobs.Cancelled()
    import pytest
    with pytest.raises(jobs.Cancelled):artwork.process(source,tmp_path/'derived.png',operation='lineart',check=cancel)
    assert not (tmp_path/'derived.png').exists() and source.read_bytes()==before
    with pytest.raises(ValueError):artwork.process(source,tmp_path/'derived.png',operation='lineart',expected_sha='0'*64)

    monkeypatch.setattr(artwork,'MAX_PIXELS',1)
    with pytest.raises(ValueError,match='3200'):artwork.process(source,tmp_path/'derived.png',operation='lineart')
    assert source.read_bytes()==before


def test_export_cache_cleanup_keeps_unrelated_files(client,tmp_path):
    import os,time
    from front_api.routers.ocdrawing import prune_exports
    expired=tmp_path/('a'*12+'.png');expired.write_bytes(b'generated disposable export')
    user_file=tmp_path/'personal.png';user_file.write_bytes(b'not an owned cache name')
    partial=tmp_path/('b'*12+'.partial');partial.write_bytes(b'active partial')
    os.utime(expired,(time.time()-8*86400,)*2)
    prune_exports(tmp_path)
    assert not expired.exists() and user_file.read_bytes()==b'not an owned cache name' and partial.exists()
