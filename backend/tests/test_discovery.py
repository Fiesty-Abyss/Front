import hashlib
import os
import subprocess
import threading
import time
import zipfile

import pytest
from fastapi import HTTPException

from front_api import discovery as d,jobs,models as m
from front_api.db import new_session


def guard(row):return {k:row[k] for k in ('uid','version')}


def create(client,path,**config):
    value=client.post('/api/discovery-roots',json={'name':'生成资料来源','path':str(path),'config':config})
    assert value.status_code==201,value.text
    return value.json()


def scan(client,row):
    response=client.post(f"/api/discovery-roots/{row['id']}/scan",json=guard(row))
    assert response.status_code==202,response.text
    return response.json()


def finish(client,start):
    for _ in range(600):
        job=client.get('/api/jobs/'+start['job']['id']).json()
        if job['status'] not in ('queued','running'):
            row=client.get('/api/discovery-roots/'+str(start['source']['id'])).json()
            return row,job
        time.sleep(.01)
    raise AssertionError('generated scan timeout')


def report(client,row):
    response=client.get('/api/project-previews/'+row['report_id'])
    assert response.status_code==200,response.text
    return response.json()


def test_saved_roots_grouping_incremental_import_and_missing(client,tmp_path):
    root=tmp_path/'生成 资料 & novel';(root/'星海录').mkdir(parents=True)
    body=root/'星海录'/'正文.txt';body.write_text('生成文本，仅用于测试。',encoding='utf-8')
    (root/'星海录'/'副本.txt').write_bytes(body.read_bytes())
    original=hashlib.sha256(body.read_bytes()).hexdigest()
    row=create(client,root,kind='novel')
    second=tmp_path/'另一个根目录';second.mkdir();create(client,second)
    assert len(client.get('/api/discovery-roots').json()['items'])==2
    assert client.post('/api/discovery-roots',json={'name':'同目录','path':str(root)}).status_code==409
    row,job=finish(client,scan(client,row));assert job['status']=='done',job
    data=report(client,row)
    assert row['state']=='done' and row['stats']['new']==2 and row['stats']['duplicates']==1
    assert all(i['group']=='星海录' and i['suggestion_only'] for i in data['items'])
    assert all(i['candidate']=='novel' for i in data['items'])
    assert client.get('/api/assets').json()['total']==0
    imported=client.post('/api/library-imports',json={'report_id':row['report_id'],'indices':[0,1],'mode':'indexed'})
    assert imported.status_code==202,imported.text
    for _ in range(300):
        run=client.get('/api/library-imports/'+imported.json()['import_id']).json()
        if run['status'] not in ('running','queued'):break
        time.sleep(.01)
    assert run['status']=='done',run
    assert client.get('/api/assets').json()['total']==1
    row,_=finish(client,scan(client,row));assert row['stats']['reused_hashes']==2
    assert row['stats']['new']==row['stats']['changed']==row['stats']['missing']==0
    (root/'星海录'/'副本.txt').unlink();(root/'星海录'/'新稿.md').write_text('独立生成稿',encoding='utf-8')
    row,_=finish(client,scan(client,row))
    assert row['stats']['new']==1 and row['stats']['missing']==1
    assert hashlib.sha256(body.read_bytes()).hexdigest()==original


def test_depth_ignores_entry_size_and_hash_budgets(client,tmp_path):
    root=tmp_path/'bounded';(root/'nested'/'deep').mkdir(parents=True)
    (root/'root.txt').write_text('hello')
    (root/'skip.txt').write_text('skip')
    (root/'nested'/'deep'/'deep.txt').write_text('deep')
    row=create(client,root,max_depth=0,ignores=['skip*'],hash_file_bytes=1)
    row,_=finish(client,scan(client,row));data=report(client,row)
    assert data['total']==1 and data['items'][0]['hash_deferred']
    assert client.post('/api/library-imports',json={'report_id':row['report_id'],'indices':[0]}).status_code==422
    for config,reason in [({'max_files':1},'file_budget'),({'max_entries':1},'entry_budget'),({'max_bytes':1},'size_budget')]:
        response=client.patch(f"/api/discovery-roots/{row['id']}",json={**guard(row),'name':'有限扫描','config':config})
        row=response.json();row,_=finish(client,scan(client,row));data=report(client,row)
        assert row['state']=='limited' and data['discovery']['enumeration']['limit']==reason
        assert row['stats']['missing'] is None


def test_configuration_changes_do_not_report_false_missing_and_optimistic_guard(client,tmp_path):
    root=tmp_path/'scope';(root/'nested').mkdir(parents=True);(root/'nested'/'a.txt').write_text('A')
    row=create(client,root);row,_=finish(client,scan(client,row));old=dict(row)
    row=client.patch(f"/api/discovery-roots/{row['id']}",json={**guard(row),'name':'新配置','config':{'max_depth':0}}).json()
    assert client.post(f"/api/discovery-roots/{row['id']}/scan",json=guard(old)).status_code==409
    row,_=finish(client,scan(client,row))
    assert row['stats']['missing'] is None and not row['stats']['comparison_available']
    assert client.get('/api/discovery-roots/999999999999999999999').status_code==422
    assert client.post('/api/discovery-roots',json={'name':'bad','path':str(root),'config':{'max_depth':True}}).status_code==422
    assert client.post('/api/discovery-roots',json={'name':'bad','path':str(root),'config':{'ignores':['x'*201]}}).status_code==422


def test_nested_books_keep_resources_below_the_detected_work_boundary(client,tmp_path):
    root=tmp_path/'nested-books';work=root/'小说'/'长篇'/'生成作品';(work/'插图').mkdir(parents=True)
    (work/'正文.txt').write_text('generated novel');(work/'附录.md').write_text('generated appendix')
    (work/'插图'/'scene.svg').write_text('<svg xmlns="http://www.w3.org/2000/svg"/>')
    row=create(client,root);row,_=finish(client,scan(client,row));data=report(client,row)
    assert data['total']==3
    assert {i['group'] for i in data['items']}=={'小说/长篇/生成作品'}
    assert {i['suggested_title'] for i in data['items']}=={'生成作品'}
    assert client.get('/api/works').json()['total']==0


def test_archives_are_bounded_read_only_and_model_or_exe_not_imported(client,tmp_path):
    root=tmp_path/'archives';root.mkdir()
    with zipfile.ZipFile(root/'valid.zip','w') as archive:archive.writestr('正文.txt','generated content')
    with zipfile.ZipFile(root/'escape.zip','w') as archive:archive.writestr('../outside.txt','do not extract')
    with zipfile.ZipFile(root/'ratio.zip','w',zipfile.ZIP_DEFLATED) as archive:archive.writestr('huge.txt',b'0'*200000)
    (root/'broken.zip').write_bytes(b'not a zip')
    (root/'model.safetensors').write_bytes(b'not weights')
    (root/'game.exe').write_bytes(b'not a program')
    (root/'script.py').write_text("raise RuntimeError('never execute scanned scripts')")
    (root/'附录.md').write_text('generated appendix')
    row=create(client,root);row,_=finish(client,scan(client,row));items={i['name']:i for i in report(client,row)['items']}
    assert items['valid.zip']['archive']['extracted_bytes']==0
    assert items['valid.zip']['archive']['crc_verified'] is False
    assert items['escape.zip']['error']=='archive_unsafe_path'
    assert items['ratio.zip']['error']=='archive_expansion_budget'
    assert items['broken.zip']['error']=='archive_invalid_directory'
    assert row['stats']['errors']==3 and report(client,row)['errors']==3
    assert items['model.safetensors']['hash_deferred'] and items['game.exe']['hash_deferred']
    assert items['附录.md']['role']=='appendix' and items['附录.md']['candidate']=='novel'
    assert not (tmp_path/'outside.txt').exists()
    assert client.get('/api/assets').json()['total']==0


def test_cancel_resume_reuses_completed_fingerprints_without_import(client,tmp_path,monkeypatch):
    root=tmp_path/'resume';root.mkdir()
    for n in range(8):(root/f'{n}.txt').write_text(f'unique {n}')
    row=create(client,root);entered=threading.Event();release=threading.Event();decorate=d.decorate
    def blocked(*args):
        entered.set();assert release.wait(5);return decorate(*args)
    monkeypatch.setattr(d,'decorate',blocked)
    start=scan(client,row)
    try:
        assert entered.wait(3)
        current=client.get('/api/discovery-roots/'+str(row['id'])).json()
        assert client.patch(f"/api/discovery-roots/{row['id']}",json={**guard(current),'name':'busy','config':{}}).status_code==409
        paused=client.post(f"/api/discovery-roots/{row['id']}/control/pause",json=guard(current));assert paused.status_code==200,paused.text
    finally:release.set()
    row,job=finish(client,start)
    assert row['state']=='paused' and job['status']=='cancelled'
    partial=report(client,row);assert partial['total']>=1
    assert client.post('/api/library-imports',json={'report_id':row['report_id'],'indices':[0]}).status_code==422
    monkeypatch.setattr(d,'decorate',decorate)
    old_report=row['report_id'];row,job=finish(client,scan(client,row))
    assert row['state']=='done' and row['stats']['files']==8 and row['stats']['reused_hashes']>=1
    assert row['report_id']!=old_report and client.get('/api/project-previews/'+old_report).json()['discovery']['state']=='paused'
    assert client.get('/api/assets').json()['total']==0


@pytest.mark.parametrize('failure',[429,503])
def test_queue_failure_persists_recoverable_state(client,tmp_path,monkeypatch,failure):
    root=tmp_path/'queue';root.mkdir();(root/'a.txt').write_text('generated')
    row=create(client,root)
    with monkeypatch.context() as patch:
        def fail(*args):
            if failure==429:raise HTTPException(429,'test queue full')
            raise RuntimeError('generated executor failure')
        patch.setattr(d.jobs,'start',fail)
        assert client.post(f"/api/discovery-roots/{row['id']}/scan",json=guard(row)).status_code==failure
    row=client.get('/api/discovery-roots/'+str(row['id'])).json()
    assert row['state']=='interrupted' and row['job_id'] is None
    row,_=finish(client,scan(client,row));assert row['state']=='done'


def test_symlink_ancestor_rejected_for_new_scan_and_existing_preview(client,tmp_path):
    root=tmp_path/'plain';root.mkdir();outside=tmp_path/'outside';outside.mkdir()
    (root/'a.txt').write_text('original');(outside/'b.txt').write_text('outside')
    link=root/'link'
    try:os.symlink(outside,link,target_is_directory=True)
    except OSError:pytest.skip('symlink creation not permitted')
    try:
        assert client.post('/api/discovery-roots',json={'name':'link','path':str(link)}).status_code==422
        row=create(client,root);row,_=finish(client,scan(client,row));assert report(client,row)['total']==1
        original=root/'a.txt';original.unlink();os.symlink(outside/'b.txt',original)
        assert client.get(f"/api/project-previews/{row['report_id']}/files/0").status_code==409
    finally:link.unlink()


@pytest.mark.skipif(os.name!='nt',reason='real Windows Junction test')
def test_windows_junction_is_never_followed(client,tmp_path):
    root=tmp_path/'junction-source';root.mkdir();target=tmp_path/'junction-target';target.mkdir();(target/'private.txt').write_text('generated private')
    link=root/'junction'
    result=subprocess.run(['cmd','/c','mklink','/J',str(link),str(target)],capture_output=True,timeout=5)
    assert result.returncode==0,result.stderr
    try:
        assert client.post('/api/discovery-roots',json={'name':'Junction','path':str(link)}).status_code==422
        row=create(client,root);row,_=finish(client,scan(client,row));assert report(client,row)['total']==0
        assert (target/'private.txt').read_text()=='generated private'
    finally:os.rmdir(link)


def test_removed_directory_reports_error_without_repairing_or_deleting_configuration(client,tmp_path):
    root=tmp_path/'disappeared';root.mkdir();row=create(client,root);root.rmdir()
    row,job=finish(client,scan(client,row));data=report(client,row)
    assert row['state']=='error' and data['discovery']['enumeration']['error_code']=='source_unavailable'
    assert job['status']=='error' and job['result']['state']=='error'
    assert row['stats']['error_code']=='source_unavailable' and row['stats']['errors']==1
    assert not root.exists()
    assert client.get('/api/discovery-roots').json()['items'][0]['uid']==row['uid']


def test_restart_does_not_replay_and_configuration_is_preserved(client,tmp_path):
    from front_api.db import get_engine
    root=tmp_path/'restart';root.mkdir();row=create(client,root)
    with new_session() as session:
        obj=session.get(m.DiscoveryRoot,row['id']);obj.state='queued';obj.job_id=None;session.commit()
    d.recover(get_engine())
    row=client.get('/api/discovery-roots/'+str(row['id'])).json()
    assert row['state']=='interrupted' and row['config']['max_depth']==4
    assert client.post(f"/api/discovery-roots/{row['id']}/remove",json=guard(row)).status_code==204
    assert root.is_dir() and client.get('/api/discovery-roots').json()['items']==[]


def test_cancel_while_queued_reconciles_without_reading_any_source(client,tmp_path,monkeypatch):
    root=tmp_path/'queued';root.mkdir();row=create(client,root)
    release=threading.Event();started=[threading.Event(),threading.Event()]
    blockers=[]
    for event in started:
        def block(job,event=event):event.set();assert release.wait(5)
        blockers.append(jobs.start('generated-blocker','generated queue test',0,block))
    try:
        assert all(e.wait(2) for e in started)
        start=scan(client,row);current=client.get('/api/discovery-roots/'+str(row['id'])).json()
        assert jobs.get(start['job']['id']).status=='queued'
        assert client.post(f"/api/discovery-roots/{row['id']}/control/pause",json=guard(current)).status_code==200
    finally:release.set()
    row,job=finish(client,start)
    assert row['state']=='paused' and job['status']=='cancelled' and not row['report_available']
    assert not row['stats']


def test_growing_hash_input_is_bounded_by_declared_size_plus_one(client,tmp_path,monkeypatch):
    import io
    from pathlib import Path
    root=tmp_path/'grow';root.mkdir();target=root/'a.txt';target.write_bytes(b'a')
    original=Path.open;reads=[]
    class Changed(io.BytesIO):
        def read(self,size=-1):reads.append(size);return super().read(size)
    def opening(path,*args,**kwargs):
        if path==target and args and args[0]=='rb':return Changed(b'x'*10000)
        return original(path,*args,**kwargs)
    monkeypatch.setattr(Path,'open',opening)
    row=create(client,root);row,_=finish(client,scan(client,row));data=report(client,row)
    assert data['items'][0]['error']=='扫描时文件增大，请重新预览'
    assert reads==[2] and row['stats']['hash_bytes_read']==2


def test_scan_configuration_and_reports_survive_full_backup_isolated_restore(client,tmp_path):
    import sqlite3
    from pathlib import Path
    from front_api import backups
    from test_backups import wait
    root=tmp_path/'backup-source';root.mkdir();(root/'sample.txt').write_text('generated backup fixture')
    row=create(client,root);row,_=finish(client,scan(client,row))
    backed=wait(client,client.post('/api/backups',json={}).json());assert backed['status']=='done',backed
    package=backups.package_for(backed['result']['backup_id']);manifest,issues=backups.verify(package)
    assert not issues and any(f['path'].startswith('project-previews/') for f in manifest['files'])
    restored=wait(client,client.post('/api/backups/restore',json={'path':str(package),'confirmed':True}).json())
    assert restored['status']=='done',restored
    target=Path(restored['result']['path'])
    with sqlite3.connect(target/'front.db') as db:
        assert db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
        assert db.execute('PRAGMA foreign_key_check').fetchall()==[]
        assert db.execute('SELECT uid,path,report_id FROM discovery_roots').fetchone()==(row['uid'],str(root),row['report_id'])
    assert (target/'project-previews'/f"{row['report_id']}.json").is_file()
    assert client.get('/api/discovery-roots').json()['items'][0]['uid']==row['uid']


def test_additive_root_table_has_pre_schema_snapshot_and_preserves_old_rows(client,data_dir):
    import sqlite3
    from front_api import dbbackup
    from front_api.config import get_settings
    from front_api.db import get_engine,Base
    world=client.post('/api/worlds',json={'name':'generated legacy world'}).json()
    engine=get_engine();m.DiscoveryRoot.__table__.drop(engine)
    dbbackup.before_schema_change(get_settings());Base.metadata.create_all(engine)
    snapshots=list((data_dir/'backups').glob('pre-schema-*/front.db'));assert snapshots
    with sqlite3.connect(snapshots[-1]) as db:
        assert db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
        assert db.execute('SELECT name FROM worlds WHERE id=?',(world['id'],)).fetchone()[0]=='generated legacy world'
        assert not db.execute("SELECT name FROM sqlite_master WHERE name='discovery_roots'").fetchall()
    assert client.get('/api/worlds/'+str(world['id'])).json()['name']=='generated legacy world'
    assert client.get('/api/discovery-roots').json()['items']==[]
