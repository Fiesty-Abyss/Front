import io,wave,json,hashlib
from pathlib import Path
from test_ai_drawing import wait_job


def wav_bytes(seconds=2):
    out=io.BytesIO()
    with wave.open(out,'wb') as w:w.setnchannels(1);w.setsampwidth(2);w.setframerate(8000);w.writeframes(b'\x10\x01'*int(8000*seconds))
    return out.getvalue()


def audio(client):
    return client.post('/api/assets/upload',files={'file':('generated.wav',wav_bytes(),'audio/wav')}).json()


def state_payload(s,**kw):
    return {'asset_identity':s['asset_identity'],'sha256':s['sha256'],'expected_revision':s['revision'],**kw}


def test_audio_album_references_resume_bookmarks_and_subtitles(client):
    asset=audio(client);aid=asset['id'];assert asset['meta']['file']['samplerate']==8000
    album=client.post('/api/audio/albums',json={'title':'Generated album','category':'ASMR','favorite':True,'stars':5,'preference':90}).json()
    assert client.post(f"/api/audio/albums/{album['id']}/tracks",json={'asset_ids':[aid,aid]}).status_code==200
    assert client.get('/api/audio/tracks',params={'album_id':album['id']}).json()['total']==1
    assert client.get('/api/assets').json()['total']==1
    state=client.get(f'/api/audio/tracks/{aid}/state').json()
    subtitle=client.post('/api/assets/upload',files={'file':('generated.lrc',b'[00:00.20]generated lyric\n[00:01.00]second cue','text/plain')}).json()
    url=f'/api/audio/tracks/{aid}/state'
    response=client.put(url,json=state_payload(state,position=1.25,rate=1.5,loop=True,notes='Learning note',bookmarks=[{'id':'one','position':.75,'label':'entry'}],subtitle_asset_ids=[subtitle['id']]));assert response.status_code==200,response.text
    saved=response.json();assert saved['position']==1.25 and saved['bookmarks'][0]['sha256']==asset['sha256']
    assert client.put(url,json=state_payload(state,position=0)).status_code==409
    vtt=client.get(f"/api/audio/tracks/{aid}/subtitles/{subtitle['id']}");assert vtt.status_code==200 and '00:00:00.200 --> 00:00:01.000' in vtt.text
    response=client.get(f'/api/assets/{aid}/file?inline=true',headers={'Range':'bytes=0-99'});assert response.status_code==206 and len(response.content)==100
    job=wait_job(client,client.post(f'/api/audio/tracks/{aid}/waveform').json());assert job['status']=='done',job
    wave=client.get(f'/api/audio/tracks/{aid}/waveform').json();assert wave['available'] and 1<=len(wave['peaks'])<=512
    client.delete(f"/api/audio/albums/{album['id']}/tracks/{aid}")
    assert client.get(f'/api/assets/{aid}/file').content==wav_bytes()


def test_audio_state_identity_world_and_version_guards(client):
    a=audio(client);aid=a['id'];s=client.get(f'/api/audio/tracks/{aid}/state').json();url=f'/api/audio/tracks/{aid}/state'
    assert client.put(url,json=state_payload(s,rate=4)).status_code==422
    assert client.put(url,json=state_payload(s,asset_identity='different',position=1)).status_code==409
    client.put(url,json=state_payload(s,position=1))
    # A reused asset ID cannot inherit a prior recording's progress.
    client.delete(f'/api/assets/{aid}');b=audio(client);assert b['id']==aid
    assert client.get(url).json()['position']==0
    assert client.put(url,json=state_payload(s,position=1)).status_code==409
    w=client.post('/api/worlds',json={'name':'other'}).json()['id']
    client.patch(f'/api/assets/{aid}',json={'world_id':w})
    album=client.post('/api/audio/albums',json={'title':'Independent'}).json()
    assert client.post(f"/api/audio/albums/{album['id']}/tracks",json={'asset_ids':[aid]}).status_code==422
    assert client.post(f"/api/audio/albums/{album['id']}/tracks",json={'asset_ids':[aid],'allow_cross_scope':True}).status_code==200


def test_shared_index_import_incremental_recovery_and_original_hash(client,tmp_path,data_dir):
    root=tmp_path/'generated-audio';root.mkdir();source=root/'episode.wav';source.write_bytes(wav_bytes());(root/'episode.lrc').write_text('[00:00.20]hello',encoding='utf-8')
    before=hashlib.sha256(source.read_bytes()).hexdigest()
    scan=wait_job(client,client.post('/api/project-previews',json={'path':str(root)}).json());assert scan['status']=='done'
    rid=scan['result']['report_id'];report=client.get(f'/api/project-previews/{rid}').json();audio_item=next(i for i in report['items'] if i['kind']=='audio');assert audio_item['audio']['duration']==2
    album=client.post('/api/audio/albums',json={'title':'Imported'}).json();body={'report_id':rid,'indices':[i['index'] for i in report['items']],'mode':'indexed','collection_id':album['collection_id']}
    run=client.post('/api/library-imports',json=body).json();j=wait_job(client,run['job']);assert j['status']=='done',j
    result=client.get(f"/api/library-imports/{run['import_id']}").json();assert result['counts']=={'done':2}
    again=client.post('/api/library-imports',json=body).json();wait_job(client,again['job'])
    assert client.get('/api/assets').json()['total']==2
    assert not list((data_dir/'media').rglob('*.wav'))
    assert hashlib.sha256(source.read_bytes()).hexdigest()==before
    # New content is a new Asset; old original-path records are never overwritten.
    source.write_bytes(wav_bytes(3));scan=wait_job(client,client.post('/api/project-previews',json={'path':str(root)}).json());body['report_id']=scan['result']['report_id']
    wait_job(client,client.post('/api/library-imports',json=body).json()['job']);assert client.get('/api/assets').json()['total']==3


def test_subtitle_formats_and_limits():
    import pytest
    from front_api.subtitles import convert
    assert '00:00:01.000 --> 00:00:02.000' in convert('1\n00:00:01,000 --> 00:00:02,000\nText\n','.srt')
    assert 'Text' in convert('WEBVTT\n\n00:01.000 --> 00:02.000\nText\n','.vtt')
    assert '<script>' not in convert('[00:01.00]<script>bad</script>','.lrc')
    with pytest.raises(ValueError):convert(''.join(f'[{i}:00.00]text\n' for i in range(10001)),'.lrc')


def test_shared_import_cancel_resume_only_pending(client,tmp_path,monkeypatch):
    from front_api import referenceimports
    root=tmp_path/'resume';root.mkdir();(root/'a.wav').write_bytes(wav_bytes());(root/'b.wav').write_bytes(wav_bytes(3))
    scan=wait_job(client,client.post('/api/project-previews',json={'path':str(root)}).json());rid=scan['result']['report_id']
    original=referenceimports.index_file;once=[False]
    def cancel_after_one(session,path,root,sha,check):
        result=original(session,path,root,sha,check)
        if not once[0]:once[0]=True;check.__self__.cancel_requested=True
        return result
    monkeypatch.setattr(referenceimports,'index_file',cancel_after_one)
    run=client.post('/api/library-imports',json={'report_id':rid,'indices':[0,1]}).json();job=wait_job(client,run['job']);assert job['status']=='cancelled'
    current=client.get(f"/api/library-imports/{run['import_id']}").json();assert current['counts']=={'done':1,'pending':1}
    monkeypatch.setattr(referenceimports,'index_file',original)
    resumed=client.post(f"/api/library-imports/{run['import_id']}/resume");assert resumed.status_code==202,resumed.text
    job=wait_job(client,resumed.json()['job']);assert job['status']=='done' and job['total']==1
    assert client.get('/api/assets').json()['total']==2


def test_audio_backup_preserves_progress_and_associations(client,data_dir):
    from front_api import backups,jobs
    import sqlite3
    from contextlib import closing
    asset=audio(client);aid=asset['id'];state=client.get(f'/api/audio/tracks/{aid}/state').json()
    client.put(f'/api/audio/tracks/{aid}/state',json=state_payload(state,position=1.2,notes='generated backup note'))
    album=client.post('/api/audio/albums',json={'title':'Backup audio'}).json();client.post(f"/api/audio/albums/{album['id']}/tracks",json={'asset_ids':[aid]})
    job=jobs.Job('full-backup','generated audio');backups.create(job)
    restored=jobs.Job('full-restore','generated isolated audio');backups.restore(restored,backups.package_for(job.result['backup_id']))
    with closing(sqlite3.connect(Path(restored.result['path'])/'front.db')) as db:
        assert db.execute('SELECT position,notes FROM audio_states').fetchone()==(1.2,'generated backup note')
        assert db.execute('SELECT count(*) FROM collection_assets').fetchone()[0]==1
        assert db.execute('PRAGMA foreign_key_check').fetchall()==[]
    assert client.get(f'/api/assets/{aid}/file').content==wav_bytes()
