"""Opt-in Mock queue integration, generated sources, isolated DB/media only."""
import time
import threading
from sqlalchemy import select
from front_api import models as m,jobs,voicerenders
from front_api.db import new_session
from test_voice_projects import project,add,base,token


def wait(client,p,segment,rid):
    for _ in range(500):
        row=next(r for r in client.get(base(p)+f'/segments/{segment["id"]}/renders').json()['items'] if r['id']==rid)
        if row['status'] not in ('queued','running'):return row
        time.sleep(.01)
    raise AssertionError('Mock task timed out')


def test_default_disabled_and_idempotent_completed_audio(client,monkeypatch):
    p=project(client);p,a=add(client,p,'生成测试台词')
    url=base(p)+f'/segments/{a["id"]}/mock-requests'
    body={**token(p),'idempotency_key':'one-key','fingerprint':a['fingerprint'],'confirm_mock':True}
    assert client.post(url,json=body).status_code==404
    monkeypatch.setenv('FRONT_ENABLE_VOICE_MOCK','1')
    missing=dict(body);missing.pop('confirm_mock')
    assert client.post(url,json=missing).status_code==422
    first=client.post(url,json=body);assert first.status_code==201,first.text
    rid=first.json()['render']['id'];row=wait(client,p,a,rid)
    assert row['status']=='candidate' and row['origin']=='mock' and row['snapshot']['speech'] is False
    assert row['snapshot']['job_id'] and row['snapshot']['audio_version']
    assert client.get(f'/api/assets/{row["audio_ref"]["id"]}/file').content.startswith(b'RIFF')
    second=client.post(url,json=body);assert second.status_code==201,second.text
    assert second.json()['render']['uid']==row['uid']
    assert client.get(base(p)+f'/segments/{a["id"]}/renders').json()['total']==1
    p=client.get(base(p)).json()
    edit=client.put(base(p)+f'/segments/{a["id"]}',json={**token(p),'expected_segment_version':a['version'],'text':'修改后的台词'})
    assert edit.status_code==200,edit.text
    assert client.post(url,json=body).json()['render']['stale'] is True
    changed={**body,'fingerprint':'0'*64}
    assert client.post(url,json=changed).status_code==409


def test_queue_saturation_keeps_failure_and_explicit_new_key_retries(client,monkeypatch):
    monkeypatch.setenv('FRONT_ENABLE_VOICE_MOCK','1')
    p=project(client);p,a=add(client,p,'队列测试')
    url=base(p)+f'/segments/{a["id"]}/mock-requests'
    body={**token(p),'idempotency_key':'full-key','fingerprint':a['fingerprint'],'confirm_mock':True}
    original=jobs.start
    def full(*args,**kwargs):
        from fastapi import HTTPException
        raise HTTPException(429,'generated full queue')
    monkeypatch.setattr(jobs,'start',full)
    assert client.post(url,json=body).status_code==429
    repeated=client.post(url,json=body)
    assert repeated.status_code==201 and repeated.json()['render']['status']=='error'
    monkeypatch.setattr(jobs,'start',original)
    p=client.get(base(p)).json()
    retry=client.post(url,json={**body,**token(p),'idempotency_key':'explicit-retry'})
    assert retry.status_code==201,retry.text
    assert wait(client,p,a,retry.json()['render']['id'])['status']=='candidate'


def test_cancel_running_job_keeps_source_and_no_audio_adoption(client,monkeypatch):
    from front_api.tts import MockAdapter
    monkeypatch.setenv('FRONT_ENABLE_VOICE_MOCK','1')
    entered=threading.Event();release=threading.Event();original=MockAdapter.synthesize
    def blocked(self,request,output,cancel):
        entered.set();release.wait(10);cancel.check()
        return original(self,request,output,cancel)
    monkeypatch.setattr(MockAdapter,'synthesize',blocked)
    p=project(client);p,a=add(client,p,'不修改这条原始台词')
    url=base(p)+f'/segments/{a["id"]}/mock-requests'
    try:
        posted=client.post(url,json={**token(p),'idempotency_key':'cancel-key','fingerprint':a['fingerprint'],'confirm_mock':True})
        assert posted.status_code==201,posted.text
        assert entered.wait(5)
        p=client.get(base(p)).json();rid=posted.json()['render']['id']
        cancelled=client.post(url+f'/{rid}/cancel',json=token(p))
        assert cancelled.status_code==200,cancelled.text
    finally:release.set()
    row=wait(client,p,a,rid)
    assert row['status']=='cancelled' and row['audio_ref'] is None
    assert client.get(base(p)+f'/segments/{a["id"]}').json()['text']=='不修改这条原始台词'


def test_restart_marks_interrupted_and_does_not_replay(client,monkeypatch):
    p=project(client);p,a=add(client,p,'恢复测试')
    with new_session() as session:
        row=m.VoiceRender(segment_id=a['id'],fingerprint=a['fingerprint'],snapshot={'origin':'mock'},status='running')
        session.add(row);session.commit();uid=row.uid
        engine=session.bind
    original_count=len(jobs.listing())
    voicerenders.recover(engine)
    with new_session() as session:
        assert session.scalar(select(m.VoiceRender).where(m.VoiceRender.uid==uid)).status=='interrupted'
    assert len(jobs.listing())==original_count


def test_corrupt_managed_duplicate_is_not_adopted_or_overwritten(client,data_dir,monkeypatch):
    monkeypatch.setenv('FRONT_ENABLE_VOICE_MOCK','1')
    p=project(client);p,a=add(client,p,'生成测试')
    url=base(p)+f'/segments/{a["id"]}/mock-requests'
    body={**token(p),'idempotency_key':'first-healthy','fingerprint':a['fingerprint'],'confirm_mock':True}
    first=client.post(url,json=body);assert first.status_code==201,first.text
    completed=wait(client,p,a,first.json()['render']['id'])
    asset=client.get(f'/api/assets/{completed["audio_ref"]["id"]}').json()
    path=data_dir/asset['file_path'];path.write_bytes(b'generated deliberate corruption')
    p=client.get(base(p)).json()
    second=client.post(url,json={**body,**token(p),'idempotency_key':'retry-after-corruption'})
    assert second.status_code==201,second.text
    failed=wait(client,p,a,second.json()['render']['id'])
    assert failed['status']=='error'
    assert failed['snapshot']['error_code']=='stored_audio_hash_mismatch'
    assert path.read_bytes()==b'generated deliberate corruption'
