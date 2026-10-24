import hashlib
import json
import sqlite3
import time
from pathlib import Path
import pytest
from front_api import backups,jobs
from conftest import png_bytes


def wait(c,job):
    for _ in range(500):
        j=c.get('/api/jobs/'+job['id']).json()
        if j['status'] not in ('queued','running'):return j
        time.sleep(.01)
    pytest.fail('timeout')


def test_backup_restores_owned_history_and_optional_external(client,data_dir,tmp_path):
    from front_api.db import new_session
    from front_api.ingest import index_file
    raw=png_bytes();a=client.post('/api/assets/upload',files={'file':('sample.png',raw,'image/png')}).json()
    client.post(f'/api/versions/asset/{a["id"]}',json={})
    p=tmp_path/'external.txt';p.write_text('原件只读',encoding='utf-8')
    with new_session() as s:
        indexed,_=index_file(s,p,tmp_path,hashlib.sha256(p.read_bytes()).hexdigest());s.commit();external_id=indexed.id
    j=wait(client,client.post('/api/backups',json={}).json());assert j['status']=='done',j
    package=backups.package_for(j['result']['backup_id']);manifest,issues=backups.verify(package)
    assert not issues and manifest['status']=='complete'
    assert all(not r['included'] for r in manifest['references'])
    assert not any(f['path'].startswith('external/') for f in manifest['files'])
    assert client.post('/api/backups/restore',json={'path':str(package)}).status_code==422
    preview=wait(client,client.post('/api/backups/preview',json={'path':str(package)}).json());assert preview['result']['can_restore']
    before=client.get('/api/assets').json()['total']
    restored=wait(client,client.post('/api/backups/restore',json={'path':str(package),'confirmed':True}).json())
    assert restored['status']=='done',restored
    target=Path(restored['result']['path']);assert (target/a['file_path']).read_bytes()==raw
    assert client.get('/api/backups/restores').json()[0]['status']=='verified'
    with sqlite3.connect(target/'front.db') as db:
        assert db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
        assert db.execute('SELECT count(*) FROM entity_versions').fetchone()[0]==1
    assert client.get('/api/assets').json()['total']==before
    selected=wait(client,client.post('/api/backups',json={'external_asset_ids':[external_id]}).json())
    package2=backups.package_for(selected['result']['backup_id'])
    copy=wait(client,client.post('/api/backups/restore',json={'path':str(package2),'confirmed':True}).json());assert copy['status']=='done',copy
    with sqlite3.connect(Path(copy['result']['path'])/'front.db') as db:
        location=db.execute('SELECT path FROM external_asset_files WHERE asset_id=?',(external_id,)).fetchone()[0]
        assert Path(location).read_bytes()==p.read_bytes() and Path(location)!=p
        from front_api.projectpreview import stamp
        assert json.loads(db.execute('SELECT stamp FROM external_asset_files WHERE asset_id=?',(external_id,)).fetchone()[0])==stamp(Path(location))
    assert p.read_text(encoding='utf-8')=='原件只读'


def test_corruption_missing_media_and_unsafe_manifest(client,data_dir):
    a=client.post('/api/assets/upload',files={'file':('sample.png',png_bytes(),'image/png')}).json()
    (data_dir/a['file_path']).unlink()
    j=wait(client,client.post('/api/backups',json={}).json());assert j['status']=='done',j
    package=backups.package_for(j['result']['backup_id']);manifest,issues=backups.verify(package)
    assert manifest['status']=='partial' and not issues and manifest['issues'][0]['status']=='missing'
    bad=wait(client,client.post('/api/backups/restore',json={'path':str(package),'confirmed':True}).json());assert bad['status']=='error'
    good=wait(client,client.post('/api/backups/restore',json={'path':str(package),'confirmed':True,'allow_partial':True}).json());assert good['status']=='done',good
    (package/'front.db').write_bytes(b'broken')
    assert backups.verify(package)[1]
    for name in ('../front.db','media/../../escape','C:/file','media/CON','media/a\\b','/absolute','jobs.sqlite3/nested'):
        with pytest.raises(ValueError):backups.safe_relative(name)


def test_backup_write_barrier_cancel_and_reject_future_schema(client,data_dir,monkeypatch):
    client.post('/api/assets/upload',files={'file':('sample.png',png_bytes(),'image/png')})
    original=backups.put_file;seen=[]
    def copy(*args,**kwargs):
        assert client.post('/api/worlds',json={'name':'blocked'}).status_code==423
        with sqlite3.connect(data_dir/'front.db',timeout=0) as db:
            with pytest.raises(sqlite3.OperationalError):db.execute("INSERT INTO worlds(name,created_at,updated_at) VALUES ('blocked','now','now')")
        seen.append(True);return original(*args,**kwargs)
    monkeypatch.setattr(backups,'put_file',copy)
    j=wait(client,client.post('/api/backups',json={}).json());assert j['status']=='done',j;assert seen
    package=backups.package_for(j['result']['backup_id'])
    with sqlite3.connect(package/'front.db') as db:db.execute('CREATE TABLE future_table (id INTEGER)')
    manifest=json.loads((package/'manifest.json').read_text(encoding='utf-8'))
    manifest['database']={'sha256':backups.digest(package/'front.db')[0],'size':(package/'front.db').stat().st_size}
    backups.atomic_json(package/'manifest.json',manifest)
    assert any('future_table' in e for e in backups.verify(package)[1])
    job=jobs.Job('test','cancel');job.cancel_requested=True
    with pytest.raises(jobs.Cancelled):backups.create(job)
