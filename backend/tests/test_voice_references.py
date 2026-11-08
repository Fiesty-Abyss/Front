"""Reference declarations/QC use generated PCM, not human voices or TTS."""
import io,time,wave,json,threading
import pytest
from front_api import models as m,voicereferences as refs,voiceexports as ve
from front_api.db import new_session
from test_voice_studio import upload_wav,create


def endpoint(a):return f'/api/voice/references/{a["id"]}'


def initial(client):
    a,ref=upload_wav(client)
    row=client.get(endpoint(a)).json();assert row['data'] is None and row['version'] is None
    return a,ref,row


def token(row):return {'asset_ref':row['asset_ref'],'expected_asset_version':row['version']}


def wait(client,job):
    for _ in range(1000):
        row=client.get('/api/jobs/'+job['id']).json()
        if row['status'] not in ('queued','running'):return row
        time.sleep(.01)
    raise AssertionError('reference analysis timeout')


def test_reference_annotations_versioned_and_preserve_all_asset_fields(client):
    a,ref,row=initial(client)
    client.patch(f'/api/assets/{a["id"]}',json={'favorite':True,'stars':4,'preference':90,'meta':{'unrelated':{'keep':True}},'description':'原笔记保留'})
    body={**token(row),'data':{'kind':'zero_shot','source':'生成音频','reference_text':'人工校对文本','declaration':{}}}
    r=client.put(endpoint(a),json=body);assert r.status_code==200,r.text
    saved=r.json();assert saved['version'] and saved['rights_verified'] is False and not saved['inference_enabled_by_record']
    old=client.get(f'/api/assets/{a["id"]}').json()
    assert old['favorite'] and old['stars']==4 and old['preference']==90 and old['description']=='原笔记保留'
    assert old['meta']['unrelated']=={'keep':True}
    assert client.put(endpoint(a),json=body).status_code==409
    changed=client.put(endpoint(a),json={**token(saved),'data':saved['data']|{'reference_text':'另一个版本'}})
    assert changed.status_code==200
    history=client.get(f'/api/versions/asset/{a["id"]}').json()
    assert history['total']>=2
    assert client.get('/api/voice/references').json()['total']==1
    assert 'reference_text' not in json.dumps(client.get('/api/voice/references').json())


@pytest.mark.parametrize('change',[{'allow_training':True},{'allow_zero_shot':True},{'speaker_authorized':1}])
def test_no_invented_rights_or_truthy_integer_permissions(client,change):
    a,ref,row=initial(client)
    r=client.put(endpoint(a),json={**token(row),'data':{'declaration':change}})
    assert r.status_code==422
    assert client.get(endpoint(a)).json()['data'] is None


def test_explicit_reference_declaration_does_not_enable_any_inference(client):
    a,ref,row=initial(client)
    data={'kind':'training','source':'自有生成正弦波','license':'生成测试数据，非人声',
        'declaration':{'speaker_authorized':True,'allow_training':True,'allow_zero_shot':False,'statement':'只记录测试用途，不执行训练'}}
    r=client.put(endpoint(a),json={**token(row),'data':data});assert r.status_code==200,r.text
    assert not r.json()['training_enabled_by_record'] and not r.json()['rights_verified']
    assert client.get('/api/jobs').json()==[]


def test_profile_uid_and_cross_world_binding_checked(client):
    a,ref,row=initial(client)
    world=client.post('/api/worlds',json={'name':'生成隔离世界'}).json()
    other=client.post('/api/worlds',json={'name':'生成另一个世界'}).json()
    char=client.post('/api/characters',json={'name':'虚构测试人物','world_id':world['id']}).json()
    profile=create(client,'profiles',character_id=char['id'])
    client.patch(f'/api/assets/{a["id"]}',json={'world_id':other['id']})
    data={'profile_ref':{'id':profile['id'],'uid':profile['uid']}}
    assert client.put(endpoint(a),json={**token(row),'data':data}).status_code==422
    assert client.put(endpoint(a),json={**token(row),'data':{'profile_ref':{'id':profile['id'],'uid':'f'*32}}}).status_code==409


def test_qc_is_local_bounded_versioned_and_does_not_change_source(client,data_dir):
    a,ref,row=initial(client);original=(data_dir/a['file_path']).read_bytes()
    assert client.post(endpoint(a)+'/inspect',json=token(row)|{'confirm_local_analysis':1}).status_code==422
    r=client.post(endpoint(a)+'/inspect',json=token(row)|{'confirm_local_analysis':True});assert r.status_code==200,r.text
    job=wait(client,r.json());assert job['status']=='done',job
    result=client.get(endpoint(a)).json();report=result['qc']
    assert result['version'] and report['audio_ref']==ref and report['pcm']['level_measured']
    assert report['pcm']['silent'] and report['pcm']['near_zero_samples_ratio']==1
    assert report['pcm']['near_full_scale_samples_ratio']==0
    assert not report['will_synthesize'] and not report['will_train'] and not report['speech_quality_verified']
    assert str(data_dir) not in json.dumps(report)
    assert (data_dir/a['file_path']).read_bytes()==original
    assert not list((data_dir/'.staging').iterdir())


def test_generated_near_full_scale_and_unsupported_levels(client):
    for width,value in ((2,b'\xff\x7f'),(1,b'\x80')):
        stream=io.BytesIO()
        with wave.open(stream,'wb') as out:
            out.setnchannels(1);out.setsampwidth(width);out.setframerate(8000);out.writeframes(value*800)
        a=client.post('/api/assets/upload',files={'file':('generated-pcm.wav',stream.getvalue(),'audio/wav')}).json()
        row=client.get(endpoint(a)).json()
        r=client.post(endpoint(a)+'/inspect',json=token(row)|{'confirm_local_analysis':True})
        job=wait(client,r.json());assert job['status']=='done',job
        pcm=client.get(endpoint(a)).json()['qc']['pcm']
        assert pcm['near_full_scale_samples_ratio']==(1 if width==2 else None)
        assert pcm['level_measured']==(width==2)


def test_qc_does_not_overwrite_concurrent_asset_edits(client,monkeypatch):
    a,ref,row=initial(client);entered=threading.Event();release=threading.Event();scan=ve.inspect_pcm
    def block(*args):entered.set();release.wait(10);return scan(*args)
    monkeypatch.setattr(ve,'inspect_pcm',block)
    try:
        r=client.post(endpoint(a)+'/inspect',json=token(row)|{'confirm_local_analysis':True});assert entered.wait(5)
        client.patch(f'/api/assets/{a["id"]}',json={'description':'扫描期间人工备注'})
    finally:release.set()
    job=wait(client,r.json());assert job['status']=='error' and job['result']['error_code']=='reference_validation_failed_409'
    assert client.get(endpoint(a)).json()['qc'] is None
    assert client.get(f'/api/assets/{a["id"]}').json()['description']=='扫描期间人工备注'


def test_missing_file_and_wrong_ref_never_create_report(client,data_dir):
    a,ref,row=initial(client)
    assert client.put(endpoint(a),json={**token(row),'asset_ref':ref|{'sha256':'f'*64},'data':{}}).status_code==409
    (data_dir/a['file_path']).unlink()
    r=client.post(endpoint(a)+'/inspect',json=token(row)|{'confirm_local_analysis':True})
    job=wait(client,r.json());assert job['status']=='error' and job['result']['error_code']=='reference_validation_failed_404'
    assert client.get(endpoint(a)).json()['qc'] is None


def test_restore_adds_history_and_full_backup_preserves_reference_and_qc(client):
    import sqlite3
    from pathlib import Path
    from front_api import backups,jobs
    a,ref,row=initial(client)
    saved=client.put(endpoint(a),json={**token(row),'data':{'reference_text':'旧的人工参考文本'}}).json()
    edited=client.put(endpoint(a),json={**token(saved),'data':saved['data']|{'reference_text':'新版人工文本'}}).json()
    r=client.post(f'/api/versions/asset/{a["id"]}/{saved["version"]}/restore',json={'expected_latest':edited['version']})
    assert r.status_code==200,r.text
    restored=client.get(endpoint(a)).json();assert restored['data']['reference_text']=='旧的人工参考文本'
    assert restored['version'] not in (saved['version'],edited['version'])
    r=client.post(endpoint(a)+'/inspect',json=token(restored)|{'confirm_local_analysis':True});assert wait(client,r.json())['status']=='done'
    backup=jobs.Job('full-backup','generated reference');backups.create(backup)
    package=backups.package_for(backup.result['backup_id']);assert not backups.verify(package)[1]
    recovery=jobs.Job('full-restore','generated isolated reference');backups.restore(recovery,package)
    with sqlite3.connect(Path(recovery.result['path'])/'front.db') as db:
        meta=json.loads(db.execute('SELECT meta FROM assets WHERE id=?',(a['id'],)).fetchone()[0])
        assert meta['voice_reference']['data']['reference_text']=='旧的人工参考文本'
        assert meta['voice_reference_qc']['audio_ref']==ref
        assert db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
    assert client.get(endpoint(a)).json()['qc']


def test_saved_training_only_declaration_blocks_zero_shot_before_network(client,tmp_path,monkeypatch):
    from test_voice_local import fixture,url,inject,response,wait as render_wait
    monkeypatch.setenv('FRONT_ENABLE_LOCAL_TTS','1')
    p,s,a,body,provider=fixture(client,tmp_path);row=client.get(endpoint(a)).json()
    data={'kind':'training','source':'自行生成','license':'测试样本，不涉及人声','declaration':{
        'speaker_authorized':True,'allow_training':True,'allow_zero_shot':False,'statement':'没有推理授权'}}
    saved=client.put(endpoint(a),json={**token(row),'data':data});assert saved.status_code==200,saved.text
    calls=inject(monkeypatch,response)
    assert client.post(url(p,s),json=body).status_code==409 and calls==[]
    data['kind']='zero_shot';data['declaration']['allow_zero_shot']=True
    assert client.put(endpoint(a),json={**token(saved.json()),'data':data}).status_code==200
    r=client.post(url(p,s),json=body);assert r.status_code==201,r.text
    assert render_wait(client,p,s,r.json()['render']['id'])['render']['status']=='candidate'
    assert len(calls)==2  # Protocol/fixture only, never a real model.


def test_revoked_annotation_during_protocol_request_prevents_output_ingest(client,tmp_path,monkeypatch):
    import httpx
    from test_voice_local import fixture,url,inject,response,wait as render_wait,wav
    monkeypatch.setenv('FRONT_ENABLE_LOCAL_TTS','1')
    p,s,a,body,provider=fixture(client,tmp_path);row=client.get(endpoint(a)).json()
    data={'kind':'zero_shot','source':'生成音频','license':'非人声协议样本','declaration':{
        'speaker_authorized':True,'allow_zero_shot':True,'statement':'仅协议验证'}}
    saved=client.put(endpoint(a),json={**token(row),'data':data}).json()
    entered=threading.Event();release=threading.Event()
    def block(req):
        if req.url.path=='/openapi.json':return response(req)
        entered.set();release.wait(10);return httpx.Response(200,content=wav(),headers={'content-type':'audio/wav'})
    inject(monkeypatch,block)
    try:
        r=client.post(url(p,s),json=body);assert entered.wait(5)
        data['declaration']['allow_zero_shot']=False
        assert client.put(endpoint(a),json={**token(saved),'data':data}).status_code==200
    finally:release.set()
    result=render_wait(client,p,s,r.json()['render']['id'])['render']
    assert result['status']=='error' and result['audio_ref'] is None
    assert result['snapshot']['error_code']=='reference_scope_changed'


def test_scope_move_requires_explicit_detach(client):
    a,ref,row=initial(client)
    first=client.post('/api/worlds',json={'name':'生成A'}).json()['id'];second=client.post('/api/worlds',json={'name':'生成B'}).json()['id']
    char=client.post('/api/characters',json={'name':'生成角色','world_id':first}).json()
    profile=create(client,'profiles',character_id=char['id'])
    data={'profile_ref':{'id':profile['id'],'uid':profile['uid']}}
    saved=client.put(endpoint(a),json={**token(row),'data':data}).json()
    client.patch(f'/api/characters/{char["id"]}',json={'world_id':second})
    assert client.get(endpoint(a)).json()['issues']
    assert client.put(endpoint(a),json={**token(saved),'data':data}).status_code==409
    detached=client.put(endpoint(a),json={**token(saved),'data':{'profile_ref':None}})
    assert detached.status_code==200,detached.text
    assert detached.json()['issues']==[]


def test_cancel_reference_analysis_leaves_no_report_or_source_changes(client,data_dir,monkeypatch):
    a,ref,row=initial(client);original=(data_dir/a['file_path']).read_bytes()
    entered=threading.Event();release=threading.Event();scan=ve.inspect_pcm
    def block(*args):entered.set();release.wait(10);return scan(*args)
    monkeypatch.setattr(ve,'inspect_pcm',block)
    try:
        r=client.post(endpoint(a)+'/inspect',json=token(row)|{'confirm_local_analysis':True});assert entered.wait(5)
        assert client.post('/api/jobs/'+r.json()['id']+'/cancel').status_code==200
    finally:release.set()
    assert wait(client,r.json())['status']=='cancelled'
    assert client.get(endpoint(a)).json()['qc'] is None
    assert (data_dir/a['file_path']).read_bytes()==original


def test_future_reference_and_qc_schema_not_overwritten(client):
    a,ref,row=initial(client)
    future={'voice_reference':{'schema':2,'data':{'private_future_field':'preserve'}},'voice_reference_qc':{'schema':2,'future_report':'preserve'}}
    client.patch(f'/api/assets/{a["id"]}',json={'meta':future})
    current=client.get(endpoint(a)).json();assert current['issues'] and current['qc'] is None
    assert client.put(endpoint(a),json={**token(current),'data':{}}).status_code==409
    assert client.post(endpoint(a)+'/inspect',json=token(current)|{'confirm_local_analysis':True}).status_code==409
    assert client.get(f'/api/assets/{a["id"]}').json()['meta']==future
    assert client.get('/api/voice/references/'+str(2**100)).status_code==422


def test_long_reference_text_does_not_bloat_shared_asset_lists(client):
    from test_voice_exports import audio
    ids=[]
    for number in range(3):
        a,_,_=audio(client,value=number+41);ids.append(a['id'])
        row=client.get(endpoint(a)).json()
        data={'reference_text':'T'*20000,'license':'L'*20000,'notes':'N'*5000,'source':'S'*2000}
        r=client.put(endpoint(a),json={**token(row),'data':data});assert r.status_code==200
    current=client.get('/api/voice/references/'+str(ids[0])).json()
    check=client.post('/api/voice/references/'+str(ids[0])+'/inspect',json=token(current)|{'confirm_local_analysis':True})
    assert check.status_code==200 and wait(client,check.json())['status']=='done'
    page=client.get('/api/assets',params={'kind':'audio','limit':3})
    assert page.status_code==200
    assert len(page.content)<10000,f'Asset list contains {len(page.content)} bytes for three reference audio records'
    assert all('voice_reference' not in a['meta'] and 'voice_reference_qc' not in a['meta'] for a in page.json()['items'])
    print('generated_three_reference_asset_list_bytes='+str(len(page.content)))
    assert len(client.get('/api/voice/references').content)<2000
    assert len(client.get('/api/audio/tracks').content)<5000
    for aid in ids:
        asset=client.get(f'/api/assets/{aid}').json()
        assert asset['meta']['voice_reference']['data']['reference_text']=='T'*20000
        assert client.get(f'/api/voice/references/{aid}').json()['data']['license']=='L'*20000
    assert client.get('/api/assets/'+str(ids[0])).json()['meta']['voice_reference_qc']['pcm']['frames']==400
