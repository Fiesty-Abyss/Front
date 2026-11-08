"""Generated PCM, explicit bounded preflight; no inference or user media."""
import io,json,time,wave,zipfile,threading
import pytest
from front_api import models as m,jobs,voiceexports as ve
from front_api.db import new_session
from test_voice_projects import project,add,base,token
from test_voice_exports import accepted,wait


def request(client,p,ids,pause=0,**changes):
    body={**token(p),'segment_ids':ids,'pause_ms':pause,**changes}
    preview=client.post(base(p)+'/exports/preview',json=body)
    assert preview.status_code==200,preview.text
    result=client.post(base(p)+'/exports',json={**body,'fingerprint':preview.json()['fingerprint'],'idempotency_key':'generated-selection'})
    assert result.status_code==201,result.text
    return wait(client,p,result.json()['id']),preview.json()


def job_wait(client,jid):
    for _ in range(1000):
        row=client.get('/api/jobs/'+jid).json()
        if row['status'] not in ('queued','running'):return row
        time.sleep(.01)
    raise AssertionError('preflight timeout')


def test_cross_page_chapter_list_and_strict_selection_identity(client):
    p=project(client);p,first,_,_=accepted(client,p,'首句')
    for n in range(23):p,_=add(client,p,f'生成中间句{n}')
    p,last,_,_=accepted(client,p,'末句',value=2)
    with new_session() as s:
        for obj in s.query(m.VoiceSegment).filter_by(project_id=p['id']):
            obj.source={**obj.source,'book':{'chapter_index':0 if obj.id!=last['id'] else 1}}
        s.commit()
    a=client.get(base(p)+'/exports/segments',params={'limit':20}).json()
    b=client.get(base(p)+'/exports/segments',params={'limit':20,'offset':20}).json()
    assert a['total']==b['total']==25 and len(a['items'])==20 and len(b['items'])==5
    assert set(r['uid'] for r in a['items']).isdisjoint(r['uid'] for r in b['items'])
    assert client.get(base(p)+'/exports/segments',params={'chapter':1}).json()['total']==1
    refs=[{k:r[k] for k in ('id','uid','version')} for r in (a['items'][0],b['items'][-1])]
    body={**token(p),'segment_ids':[last['id'],first['id']],'segment_refs':refs}
    preview=client.post(base(p)+'/exports/preview',json=body);assert preview.status_code==200,preview.text
    assert [e['segment_id'] for e in preview.json()['snapshot']['items']]==[first['id'],last['id']]
    assert client.post(base(p)+'/exports/preview',json=body|{'segment_refs':[refs[0]|{'uid':'f'*32},refs[1]]}).status_code==409
    assert client.post(base(p)+'/exports/preview',json=body|{'segment_refs':[refs[0],refs[0]]}).status_code==422
    other=project(client)
    assert client.post(base(other)+'/exports/preview',json=body|token(other)).status_code==409
    assert client.get(base(p)+'/exports/segments',params={'limit':101}).status_code==422
    assert '首句' not in json.dumps(a['items'][1:])


def test_pause_writes_new_silence_and_subtitle_gap_without_touching_sources(client):
    p=project(client);p,a,asset,original=accepted(client,p,'甲句',value=2)
    p,b,_,_=accepted(client,p,'乙句',value=3)
    row,preview=request(client,p,[b['id'],a['id']],125)
    assert row['status']=='done',row
    raw=client.get(f'/api/assets/{row["asset_id"]}/file').content
    with zipfile.ZipFile(io.BytesIO(raw)) as bundle:
        with wave.open(io.BytesIO(bundle.read('audio.wav')),'rb') as audio:
            assert audio.getnframes()==1800
            assert audio.readframes(400)==b'\x02\0'*400
            assert audio.readframes(1000)==b'\0\0'*1000
            assert audio.readframes(400)==b'\x03\0'*400
        manifest=json.loads(bundle.read('manifest.json'))
        assert manifest['pause_ms']==125
        assert manifest['items'][1]['start_frame']==1400
        assert '00:00:00,175 --> 00:00:00,225' in bundle.read('subtitles.srt').decode()
    assert client.get(f'/api/assets/{asset["id"]}/file').content==original
    old=client.post(base(p)+'/exports/preview',json={**token(p),'segment_ids':[a['id']]}).json()
    zero=client.post(base(p)+'/exports/preview',json={**token(p),'segment_ids':[a['id']],'pause_ms':0}).json()
    assert old['fingerprint']==zero['fingerprint'] and 'pause_ms' not in old['snapshot']
    bad=client.post(base(p)+'/exports',json={**token(p),'segment_ids':[a['id'],b['id']],
        'fingerprint':preview['fingerprint'],'pause_ms':126,'idempotency_key':'generated-selection'})
    assert bad.status_code==409


@pytest.mark.parametrize('value',[True,-1,10001,1.5,'125'])
def test_pause_is_explicit_strict_bounded(client,value):
    p=project(client)
    assert client.post(base(p)+'/exports/preview',json={**token(p),'segment_ids':[1],'pause_ms':value}).status_code==422


def test_pause_obeys_total_pcm_limit(client,monkeypatch):
    p=project(client);p,a,_,_=accepted(client,p,'甲');p,b,_,_=accepted(client,p,'乙',value=2)
    monkeypatch.setattr(ve,'MAX_PCM',1600)
    row,_=request(client,p,[a['id'],b['id']],1)
    assert row['status']=='error' and row['asset_id'] is None and row['error_code']=='export_validation_failed_413'


def test_unsigned_pcm8_pause_uses_midpoint_not_negative_full_scale(client):
    from test_voice_studio import upload_wav
    p=project(client);ids=[]
    for value in (129,130):
        p,seg=add(client,p,'生成8bit停顿样本'+str(value))
        stream=io.BytesIO()
        with wave.open(stream,'wb') as out:
            out.setnchannels(1);out.setsampwidth(1);out.setframerate(8000);out.writeframes(bytes([value])*400)
        asset=client.post('/api/assets/upload',files={'file':('pcm8.wav',stream.getvalue(),'audio/wav')}).json()
        ref={'id':asset['id'],'identity':asset['created_at'].replace('Z','').replace('+00:00',''),'sha256':asset['sha256']}
        result=client.post(base(p)+f'/segments/{seg["id"]}/renders',json={**token(p),'fingerprint':seg['fingerprint'],'audio_ref':ref}).json()
        p=result['project'];render=result['render']
        p=client.post(base(p)+f'/segments/{seg["id"]}/renders/{render["id"]}/accept',json=token(p)).json()['project'];ids.append(seg['id'])
    row,_=request(client,p,ids,125);assert row['status']=='done',row
    with zipfile.ZipFile(io.BytesIO(client.get(f'/api/assets/{row["asset_id"]}/file').content)) as bundle:
        with wave.open(io.BytesIO(bundle.read('audio.wav')),'rb') as audio:
            assert audio.readframes(400)==bytes([129])*400
            assert audio.readframes(1000)==b'\x80'*1000
            assert audio.readframes(400)==bytes([130])*400


def test_preflight_reports_format_and_pcm16_level_difference_without_output(client,data_dir):
    p=project(client);p,a,asset,original=accepted(client,p,'小音量',value=1)
    p,b,_,_=accepted(client,p,'大音量异采样',rate=16000,value=1000)
    result=client.post(base(p)+'/exports/preflight',json={**token(p),'segment_ids':[a['id'],b['id']],'pause_ms':125})
    assert result.status_code==200,result.text
    job=job_wait(client,result.json()['id']);assert job['status']=='done',job
    report=job['result'];assert not report['compatible'] and not report['formats_match'] and report['level_difference_warning']
    assert report['not_loudness_normalization'] and not report['will_modify_sources']
    assert report['items'][0]['levels_method']=='all_samples_pcm16'
    assert str(data_dir) not in json.dumps(report)
    assert client.get(base(p)+'/exports').json()['total']==0
    assert client.get(f'/api/assets/{asset["id"]}/file').content==original
    assert not list((data_dir/'.staging').iterdir())


def test_preflight_missing_file_gives_stable_report_and_no_fake_duration(client,data_dir):
    p=project(client);p,a,asset,_=accepted(client,p,'只用生成缺失样本')
    (data_dir/asset['file_path']).unlink()
    # Metadata is not proof that the actual file remains present.
    result=client.post(base(p)+'/exports/preflight',json={**token(p),'segment_ids':[a['id']]})
    assert result.status_code==200,result.text
    report=job_wait(client,result.json()['id'])['result']
    assert not report['compatible'] and report['duration_seconds_with_pauses'] is None
    assert report['items'][0]['issue']=='audio_validation_404'
    assert client.get(base(p)+'/exports').json()['total']==0


def test_preflight_rechecks_stale_project_after_scan(client,monkeypatch):
    p=project(client);p,a,_,_=accepted(client,p,'校验期间变更')
    entered=threading.Event();release=threading.Event();inspect=ve.inspect_pcm
    def block(*args):entered.set();release.wait(10);return inspect(*args)
    monkeypatch.setattr(ve,'inspect_pcm',block)
    try:
        result=client.post(base(p)+'/exports/preflight',json={**token(p),'segment_ids':[a['id']]})
        assert entered.wait(5)
        current=client.get(base(p)+f'/segments/{a["id"]}').json()
        changed=client.put(base(p)+f'/segments/{a["id"]}',json={**token(p),'text':'人工新稿','expected_segment_version':current['version']})
        assert changed.status_code==200,changed.text
    finally:release.set()
    assert job_wait(client,result.json()['id'])['status']=='error'


def test_export_generic_cancel_before_runner_is_not_displayed_as_running(client,monkeypatch):
    p=project(client);p,a,_,_=accepted(client,p,'生成取消样本')
    def canceled(kind,title,total,fn):
        job=jobs.Job(kind,title,total);job.status='cancelled';manager=jobs.manager()
        with manager.lock:manager.jobs[job.id]=job;manager.save(job)
        return job
    monkeypatch.setattr(jobs,'start',canceled)
    row,_=request(client,p,[a['id']])
    assert row['status']=='cancelled' and row['recorded_status']=='queued' and row['asset_id'] is None
