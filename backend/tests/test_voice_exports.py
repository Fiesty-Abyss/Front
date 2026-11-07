"""Generated PCM and temporary DB/media only; not TTS or GUI acceptance."""
import io
import json
import sqlite3
import threading
import time
import wave
import zipfile
from pathlib import Path

import pytest
from fastapi import HTTPException
from sqlalchemy import select
from front_api import models as m,jobs,voiceexports as ve
from front_api.db import new_session
from test_voice_projects import project,add,base,token


def audio(client,frames=400,rate=8000,value=1,truncate=False):
    out=io.BytesIO()
    with wave.open(out,'wb') as wav:
        wav.setnchannels(1);wav.setsampwidth(2);wav.setframerate(rate)
        wav.writeframes(value.to_bytes(2,'little')*frames)
    payload=out.getvalue();payload=payload[:-7] if truncate else payload
    row=client.post('/api/assets/upload',files={'file':('generated.wav',payload,'audio/wav')})
    assert row.status_code==201,row.text
    item=row.json();ref={'id':item['id'],'identity':item['created_at'].replace('Z','').replace('+00:00',''),'sha256':item['sha256']}
    return item,ref,payload


def accepted(client,p,text,frames=400,rate=8000,value=1,truncate=False):
    p,seg=add(client,p,text)
    asset,ref,payload=audio(client,frames,rate,value,truncate)
    result=client.post(base(p)+f'/segments/{seg["id"]}/renders',json={**token(p),'fingerprint':seg['fingerprint'],'audio_ref':ref})
    assert result.status_code==201,result.text
    p=result.json()['project'];render=result.json()['render']
    result=client.post(base(p)+f'/segments/{seg["id"]}/renders/{render["id"]}/accept',json=token(p))
    assert result.status_code==200,result.text
    return result.json()['project'],seg,asset,payload


def request(client,p,ids,key='generated_export'):
    preview=client.post(base(p)+'/exports/preview',json={**token(p),'segment_ids':ids})
    assert preview.status_code==200,preview.text
    body={**token(p),'segment_ids':ids,'fingerprint':preview.json()['fingerprint'],'idempotency_key':key}
    result=client.post(base(p)+'/exports',json=body)
    return result,body


def wait(client,p,rid):
    for _ in range(1000):
        row=next(r for r in client.get(base(p)+'/exports').json()['items'] if r['id']==rid)
        if row['status'] not in ('queued','running'):return row
        time.sleep(.01)
    raise AssertionError('generated export timeout')


def test_pcm_subtitles_source_manifest_order_and_persistent_idempotency(client,data_dir):
    p=project(client);p,a,asset,original=accepted(client,p,'<b>第一句</b>\n\n还有一行',value=1)
    p,b,_,_=accepted(client,p,'第二句',frames=800,value=2)
    result,body=request(client,p,[b['id'],a['id']])
    assert result.status_code==201,result.text
    row=wait(client,p,result.json()['id']);assert row['status']=='done',row
    binary=client.get(f'/api/assets/{row["asset_id"]}/file').content
    with zipfile.ZipFile(io.BytesIO(binary)) as bundle:
        assert set(bundle.namelist())=={'audio.wav','subtitles.srt','subtitles.vtt','manifest.json'}
        with wave.open(io.BytesIO(bundle.read('audio.wav')),'rb') as wav:
            assert wav.getnframes()==1200 and wav.getframerate()==8000
            assert wav.readframes(400)==b'\x01\0'*400
            assert wav.readframes(800)==b'\x02\0'*800
        subtitles=bundle.read('subtitles.srt').decode()
        assert '00:00:00,000 --> 00:00:00,050' in subtitles
        assert '00:00:00,050 --> 00:00:00,150' in subtitles
        assert '&lt;b&gt;第一句&lt;/b&gt;' in subtitles and '\n\n还有一行' not in subtitles
        assert bundle.read('subtitles.vtt').startswith(b'WEBVTT\n')
        manifest=json.loads(bundle.read('manifest.json'))
        assert [r['segment_uid'] for r in manifest['items']]==[a['uid'],b['uid']]
        assert manifest['not_forced_alignment'] and manifest['not_inference']
        assert manifest['contains_mock'] is False
        assert str(data_dir) not in json.dumps(manifest)
    assert client.get(f'/api/assets/{asset["id"]}/file').content==original
    again=client.post(base(p)+'/exports',json=body)
    assert again.status_code==201 and again.json()['uid']==row['uid']
    assert client.get(base(p)+'/exports').json()['total']==1
    assert client.post(base(p)+'/exports',json={**body,'fingerprint':'f'*64}).status_code==409
    assert not list((data_dir/'.staging').iterdir())


def test_preview_refuses_unaccepted_archived_and_stale_audio(client):
    p=project(client);p,a=add(client,p,'待选择版本')
    assert client.post(base(p)+'/exports/preview',json={**token(p),'segment_ids':[a['id']]}).status_code==409
    p,b,_,_=accepted(client,p,'会改变的台词')
    changed=client.put(base(p)+f'/segments/{b["id"]}',json={**token(p),'expected_segment_version':b['version'],'text':'已改变'})
    assert changed.status_code==200,changed.text
    p=changed.json()['project']
    assert client.post(base(p)+'/exports/preview',json={**token(p),'segment_ids':[b['id']]}).status_code==409
    split=client.post(base(p)+f'/segments/{a["id"]}/split',json={**token(p),'at':1})
    assert split.status_code==200; p=split.json()['project']
    assert client.post(base(p)+'/exports/preview',json={**token(p),'segment_ids':[a['id']]}).status_code==409
    other=project(client)
    assert client.post(base(other)+'/exports/preview',json={**token(other),'segment_ids':[b['id']]}).status_code==409


@pytest.mark.parametrize('ids',[[],[True],['1'],[1,1],[2**100],list(range(1,102))])
def test_selection_is_strict_and_bounded(client,ids):
    p=project(client)
    assert client.post(base(p)+'/exports/preview',json={**token(p),'segment_ids':ids}).status_code==422


@pytest.mark.parametrize('damage',['format','truncated','hash','missing'])
def test_bad_audio_leaves_originals_and_no_downloadable_output(client,data_dir,damage):
    p=project(client);p,a,first,original=accepted(client,p,'第一句',value=10)
    ids=[a['id']]
    if damage in ('format','truncated'):
        p,b,_,_=accepted(client,p,'不支持的下一句',rate=16000 if damage=='format' else 8000,value=11,truncate=damage=='truncated')
        ids.append(b['id'])
    if damage=='hash':(data_dir/first['file_path']).write_bytes(b'x'*len(original))
    if damage=='missing':(data_dir/first['file_path']).unlink()
    result,_=request(client,p,ids);assert result.status_code==201,result.text
    row=wait(client,p,result.json()['id'])
    assert row['status']=='error' and row['asset_id'] is None
    assert row['error_code']=='export_validation_failed_'+({'hash':'409','missing':'404'}.get(damage,'422'))
    if damage=='missing':assert not (data_dir/first['file_path']).exists()
    else:assert (data_dir/first['file_path']).read_bytes()==(b'x'*len(original) if damage=='hash' else original)
    assert not list((data_dir/'.staging').iterdir())


@pytest.mark.parametrize('limit',['MAX_INPUT','MAX_PCM'])
def test_export_size_limits_refuse_without_rewriting_sources(client,data_dir,monkeypatch,limit):
    p=project(client);p,a,asset,original=accepted(client,p,'有界导出',value=71)
    monkeypatch.setattr(ve,limit,1)
    result,_=request(client,p,[a['id']]);assert result.status_code==201,result.text
    row=wait(client,p,result.json()['id'])
    assert row['status']=='error' and row['asset_id'] is None
    assert row['error_code']=='export_validation_failed_413'
    assert client.get(f'/api/assets/{asset["id"]}/file').content==original
    assert not list((data_dir/'.staging').iterdir())


def test_cancellation_and_stale_completion_cannot_adopt_output(client,data_dir,monkeypatch):
    for mode in ('cancel','edit'):
        p=project(client);p,a,asset,original=accepted(client,p,'不能覆盖的原文',value=21 if mode=='cancel' else 22)
        entered=threading.Event();release=threading.Event();real=ve.package
        def blocked(*args,**kwargs):
            result=real(*args,**kwargs);entered.set();release.wait(10);return result
        with monkeypatch.context() as patch:
            patch.setattr(ve,'package',blocked)
            try:
                result,_=request(client,p,[a['id']],mode);assert result.status_code==201,result.text
                assert entered.wait(5)
                if mode=='cancel':
                    response=client.post(base(p)+f'/exports/{result.json()["id"]}/cancel',json=token(p))
                    assert response.status_code==200,response.text
                else:
                    response=client.put(base(p)+f'/segments/{a["id"]}',json={**token(p),'expected_segment_version':a['version'],'text':'新台词'})
                    assert response.status_code==200,response.text
            finally:release.set()
            row=wait(client,p,result.json()['id'])
            assert row['status']==('cancelled' if mode=='cancel' else 'error') and row['asset_id'] is None
            job=jobs.get(result.json()['job_id'])
            for _ in range(500):
                if not job or job.status not in ('queued','running'):break
                time.sleep(.01)
        assert client.get(f'/api/assets/{asset["id"]}/file').content==original
        assert not list((data_dir/'.staging').iterdir())


def test_queue_full_and_recovery_do_not_replay(client,monkeypatch):
    p=project(client);p,a,_,_=accepted(client,p,'队列回归',value=31)
    def full(*args,**kwargs):raise HTTPException(429,'generated saturation')
    with monkeypatch.context() as patch:
        patch.setattr(jobs,'start',full)
        result,body=request(client,p,[a['id']]);assert result.status_code==429
    again=client.post(base(p)+'/exports',json=body)
    assert again.status_code==201 and again.json()['error_code']=='queue_unavailable'
    with new_session() as session:
        interrupted=m.VoiceExport(project_id=p['id'],fingerprint=body['fingerprint'],snapshot={},status='running')
        session.add(interrupted);session.commit();uid=interrupted.uid;engine=session.bind
    count=len(jobs.listing());ve.recover(engine)
    with new_session() as session:
        row=session.scalar(select(m.VoiceExport).where(m.VoiceExport.uid==uid))
        assert row.status=='interrupted'
    assert len(jobs.listing())==count


def test_preview_invalidated_by_reorder_and_error_record_is_project_scoped(client):
    p=project(client);p,a,_,_=accepted(client,p,'排序甲',value=61)
    p,b,_,_=accepted(client,p,'排序乙',value=62)
    ids=[a['id'],b['id']]
    preview=client.post(base(p)+'/exports/preview',json={**token(p),'segment_ids':ids}).json()
    moved=client.post(base(p)+f'/segments/{b["id"]}/move',json={**token(p),'direction':-1})
    assert moved.status_code==200,moved.text
    p=moved.json()['project']
    stale=client.post(base(p)+'/exports',json={**token(p),'segment_ids':ids,'fingerprint':preview['fingerprint'],'idempotency_key':'stale-order'})
    assert stale.status_code==409
    result,_=request(client,p,ids,'ordered');assert result.status_code==201,result.text
    other=project(client)
    assert client.get(base(other)+'/exports').json()['total']==0
    assert client.post(base(other)+f'/exports/{result.json()["id"]}/cancel',json=token(other)).status_code==404
    row=wait(client,p,result.json()['id']);assert row['status']=='done',row
    binary=client.get(f'/api/assets/{row["asset_id"]}/file').content
    with zipfile.ZipFile(io.BytesIO(binary)) as bundle:
        manifest=json.loads(bundle.read('manifest.json'))
        assert [e['segment_uid'] for e in manifest['items']]==[b['uid'],a['uid']]


def test_export_media_and_record_survive_isolated_backup_restore(client):
    from front_api import backups
    p=project(client);p,a,_,_=accepted(client,p,'备份导出',value=41)
    result,_=request(client,p,[a['id']]);assert result.status_code==201,result.text
    row=wait(client,p,result.json()['id']);assert row['status']=='done',row
    asset=client.get(f'/api/assets/{row["asset_id"]}').json()
    backup=jobs.Job('full-backup','generated export backup');backups.create(backup)
    restore=jobs.Job('full-restore','isolated export restore');backups.restore(restore,backups.package_for(backup.result['backup_id']))
    folder=Path(restore.result['path'])
    with zipfile.ZipFile(folder/asset['file_path']) as bundle:assert bundle.testzip() is None
    with sqlite3.connect(folder/'front.db') as db:
        assert db.execute('SELECT uid FROM voice_exports').fetchone()[0]==row['uid']
        assert db.execute('PRAGMA foreign_key_check').fetchall()==[]


def test_novel_speaker_review_and_mock_warning_are_preserved(client):
    p=project(client);p,a,_,_=accepted(client,p,'测试标记音',value=51)
    with new_session() as session:
        segment=session.get(m.VoiceSegment,a['id'])
        segment.source={**segment.source,'suggestion':{'method':'punctuation_rule'},'speaker_confirmed':False}
        render=session.scalar(select(m.VoiceRender).where(m.VoiceRender.segment_id==a['id']))
        render.snapshot={**render.snapshot,'origin':'mock','speech':False};session.commit()
    p=client.get(base(p)).json()
    assert client.post(base(p)+'/exports/preview',json={**token(p),'segment_ids':[a['id']]}).status_code==409
    with new_session() as session:
        segment=session.get(m.VoiceSegment,a['id']);segment.source={**segment.source,'speaker_confirmed':True};session.commit()
    p=client.get(base(p)).json()
    result,_=request(client,p,[a['id']]);assert result.status_code==201,result.text
    row=wait(client,p,result.json()['id']);assert row['status']=='done',row
    binary=client.get(f'/api/assets/{row["asset_id"]}/file').content
    with zipfile.ZipFile(io.BytesIO(binary)) as bundle:
        assert json.loads(bundle.read('manifest.json'))['contains_mock'] is True


def test_additive_export_schema_takes_backup_and_preserves_existing_data(client,data_dir,tmp_path):
    from sqlalchemy import create_engine
    from front_api.config import Settings
    from front_api.db import Base
    from front_api.dbbackup import before_schema_change
    p=project(client);p,a=add(client,p,'升级前的生成台词')
    folder=tmp_path/'prior-export-schema';folder.mkdir()
    settings=Settings(folder,None,None,None,200)
    with sqlite3.connect(data_dir/'front.db') as src,sqlite3.connect(settings.db_path) as old:
        src.backup(old);old.execute('DROP TABLE voice_exports')
    before_schema_change(settings)
    assert len(list((folder/'backups').glob('pre-schema-*/front.db')))==1
    engine=create_engine(f'sqlite:///{settings.db_path}');Base.metadata.create_all(engine);engine.dispose()
    with sqlite3.connect(settings.db_path) as db:
        assert db.execute('SELECT text FROM voice_segments').fetchone()[0]=='升级前的生成台词'
        assert db.execute('SELECT count(*) FROM voice_exports').fetchone()[0]==0


def test_export_history_listing_does_not_fetch_text_snapshots(client):
    from sqlalchemy import event
    p=project(client)
    with new_session() as session:
        session.add(m.VoiceExport(project_id=p['id'],fingerprint='a'*64,snapshot={'text':'生成长快照'*100000},status='interrupted'))
        session.commit();engine=session.bind
    queries=[]
    def capture(conn,cursor,statement,parameters,context,executemany):
        if 'FROM voice_exports' in statement:queries.append(statement)
    event.listen(engine,'before_cursor_execute',capture)
    try:
        response=client.get(base(p)+'/exports',params={'limit':1})
        assert response.status_code==200 and response.json()['total']==1
        assert 'snapshot' not in response.json()['items'][0]
    finally:event.remove(engine,'before_cursor_execute',capture)
    assert queries and all('voice_exports.snapshot' not in statement for statement in queries)
