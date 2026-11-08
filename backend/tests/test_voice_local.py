"""Generated files, HTTPX fixtures and one real loopback protocol server.

No model inference, authorized human voice, GPU or user service is used.
"""
import io,json,time,threading,wave
from pathlib import Path
import httpx
import pytest
from front_api import jobs,voiceinference as local
from front_api.tts import GPTSoVITSAdapter,GPT_CONTRACT
from test_voice_projects import project,add,base,token
from test_voice_studio import create,upload_wav

FIELDS=('text','text_lang','ref_audio_path','prompt_lang','prompt_text','speed_factor','seed','media_type','streaming_mode')


def schema():
    return {'paths':{'/tts':{'post':{'requestBody':{'content':{'application/json':{'schema':{'properties':{k:{} for k in FIELDS}}}}}}}}}


def wav():
    stream=io.BytesIO()
    with wave.open(stream,'wb') as out:
        out.setnchannels(1);out.setsampwidth(2);out.setframerate(16000);out.writeframes(b'\0\0'*1600)
    return stream.getvalue()


def fixture(client,tmp_path,endpoint='http://127.0.0.1:9880'):
    path=tmp_path/'generated-not-a-weight.stub';path.write_bytes(b'generated metadata only; never loaded')
    provider=create(client,'providers',engine='gpt_sovits',endpoint=endpoint)
    model=create(client,'models',provider_id=provider['id'],file_path=str(path),model_version='generated protocol fixture',source='generated fixture',license='Owned generated stub; not real weights; protocol only')
    profile=create(client,'profiles',model_id=model['id'],language='zh')
    p=project(client);p,s=add(client,p,'生成协议测试台词，不执行真实AI',profile_id=profile['id'])
    asset,ref=upload_wav(client)
    body={**token(p),'fingerprint':s['fingerprint'],'idempotency_key':'local-one','reference':ref,
        'reference_text':'Generated fixture, not a human voice','reference_language':'en','rights_source':'generated test tone; no human likeness',
        'rights_authorized':True,'confirm_local_request':True,'confirm_loaded_model_unverified':True,'confirm_model_rights':True,'seed':42,'parameters':{'top_k':10}}
    return p,s,asset,body,provider


def url(p,s):return base(p)+f'/segments/{s["id"]}/local-requests'


def wait(client,p,s,rid):
    for _ in range(1000):
        r=client.get(url(p,s)+f'/{rid}');assert r.status_code==200,r.text
        row=r.json()['render']
        if row['status'] not in ('queued','running'):return r.json()
        time.sleep(.01)
    raise AssertionError('local protocol task timeout')


class OwnedFixtureAdapter(GPTSoVITSAdapter):
    def close(self):self.client.close()


def inject(monkeypatch,handler):
    calls=[]
    def factory(base):
        def call(req):calls.append(req);return handler(req)
        return OwnedFixtureAdapter(base,allowed_origins=[base],client=httpx.Client(transport=httpx.MockTransport(call)))
    monkeypatch.setattr(local,'adapter',factory)
    return calls


def response(req):
    if req.url.path=='/openapi.json':return httpx.Response(200,json=schema())
    assert req.url.path=='/tts' and req.method=='POST'
    return httpx.Response(200,content=wav(),headers={'content-type':'audio/wav'})


def test_disabled_and_explicit_rights_origin_and_parameters_gate_before_network(client,tmp_path,monkeypatch):
    monkeypatch.delenv('FRONT_ENABLE_LOCAL_TTS',raising=False)
    p,s,a,body,provider=fixture(client,tmp_path);calls=inject(monkeypatch,response)
    assert client.get('/api/voice/local-capabilities').json()['enabled'] is False
    assert client.post(url(p,s),json=body).status_code==404
    monkeypatch.setenv('FRONT_ENABLE_LOCAL_TTS','1')
    for changes in ({'rights_authorized':False},{'rights_authorized':1},{'rights_source':' '},
                    {'confirm_loaded_model_unverified':False},{'confirm_model_rights':False},{'parameters':{'lora':'unsupported'}},
                    {'parameters':{'top_p':True}},{'seed':True}):
        assert client.post(url(p,s),json=body|changes).status_code==422
    assert client.post(url(p,s),json=body,headers={'origin':'https://evil.invalid'}).status_code==403
    preview=client.post(url(p,s)+'/preview',json=body)
    assert preview.status_code==200,preview.text
    assert preview.json()['will_contact_engine'] is False and not preview.json()['loaded_model_verified']
    assert client.get(base(p)+f'/segments/{s["id"]}/renders').json()['total']==0
    assert calls==[]


@pytest.mark.parametrize('endpoint',['https://remote.invalid','http://localhost:9880','http://127.0.0.1:9880/proxy','http://127.0.0.2:9880'])
def test_only_registered_literal_loopback_root_is_accepted(client,tmp_path,monkeypatch,endpoint):
    monkeypatch.setenv('FRONT_ENABLE_LOCAL_TTS','1')
    p,s,a,body,provider=fixture(client,tmp_path,endpoint);calls=inject(monkeypatch,response)
    assert client.post(url(p,s),json=body).status_code==422
    assert calls==[]


def test_protocol_candidate_persisted_idempotent_adoption_and_reference_unmodified(client,tmp_path,monkeypatch,data_dir):
    monkeypatch.setenv('FRONT_ENABLE_LOCAL_TTS','1')
    p,s,a,body,provider=fixture(client,tmp_path);original=(data_dir/a['file_path']).read_bytes()
    calls=inject(monkeypatch,response)
    created=client.post(url(p,s),json=body);assert created.status_code==201,created.text
    completed=wait(client,p,s,created.json()['render']['id']);r=completed['render'];p=completed['project']
    assert r['status']=='candidate' and r['origin']=='gpt_sovits' and r['snapshot']['speech'] is None
    assert r['snapshot']['contract']==GPT_CONTRACT and r['snapshot']['reference_version']
    assert r['snapshot']['loaded_model_verified'] is False and r['snapshot']['quality_verified'] is False
    assert r['snapshot']['local_request']['seed']==42 and r['snapshot']['job_id']
    assert [req.url.path for req in calls]==['/openapi.json','/tts']
    payload=json.loads(calls[-1].content)
    staged=Path(payload['ref_audio_path'])
    assert staged.is_relative_to(data_dir/'.staging') and not staged.exists()
    assert payload['seed']==42 and payload['top_k']==10 and payload['streaming_mode'] is False
    assert 'rights_source' not in payload and 'profile_uid' not in payload
    assert (data_dir/a['file_path']).read_bytes()==original
    assert client.get(f'/api/assets/{r["audio_ref"]["id"]}/file').content==wav()
    repeated=client.post(url(p,s),json=body);assert repeated.status_code==201,repeated.text
    assert repeated.json()['render']['uid']==r['uid'] and len(calls)==2
    assert client.post(url(p,s),json=body|{'seed':43}).status_code==409
    accepted=client.post(base(p)+f'/segments/{s["id"]}/renders/{r["id"]}/accept',json=token(p))
    assert accepted.status_code==200,accepted.text
    assert client.post(url(p,s)+f'/{r["id"]}/cancel',json=token(accepted.json()['project'])).status_code==409
    # The exported production manifest retains actual per-request parameters,
    # while keeping local endpoint/model paths out of the portable bundle.
    from test_voice_exports import request as export_request,wait as export_wait
    import zipfile
    p=accepted.json()['project']
    exported,_=export_request(client,p,[s['id']],key='local-protocol-export')
    assert exported.status_code==201,exported.text
    bundle=export_wait(client,p,exported.json()['id']);assert bundle['status']=='done',bundle
    raw=client.get(f'/api/assets/{bundle["asset_id"]}/file').content
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        manifest=json.loads(archive.read('manifest.json'))
        generation=manifest['items'][0]['generation']
        assert generation['contract']==GPT_CONTRACT and generation['reference_version']
        assert generation['local_request']['seed']==42
        assert generation['local_request']['parameters']['top_k']==10
        assert generation['loaded_model_verified'] is False and generation['quality_verified'] is False
        assert str(tmp_path) not in json.dumps(manifest) and provider['endpoint'] not in json.dumps(manifest)
    assert len(calls)==2  # Export never reruns the external inference request.


@pytest.mark.parametrize('mode',['wrong_hash','bad_wav','wrong_scope'])
def test_invalid_reference_never_contacts_engine(client,tmp_path,monkeypatch,data_dir,mode):
    monkeypatch.setenv('FRONT_ENABLE_LOCAL_TTS','1')
    p,s,a,body,provider=fixture(client,tmp_path);calls=inject(monkeypatch,response)
    if mode=='wrong_scope':
        world=client.post('/api/worlds',json={'name':'另一个生成世界'}).json()['id']
        client.patch(f'/api/assets/{a["id"]}',json={'world_id':world})
        assert client.post(url(p,s),json=body).status_code==422
    else:
        path=data_dir/a['file_path'];path.write_bytes(b'bad generated reference')
        if mode=='bad_wav':
            import hashlib
            from front_api.db import new_session
            from front_api import models as m
            digest=hashlib.sha256(path.read_bytes()).hexdigest()
            with new_session() as session:session.get(m.Asset,a['id']).sha256=digest;session.commit()
            body['reference']['sha256']=digest
        result=client.post(url(p,s),json=body);assert result.status_code==201,result.text
        row=wait(client,p,s,result.json()['render']['id'])['render']
        assert row['status']=='error' and not row['audio_ref']
    assert calls==[]


@pytest.mark.parametrize('mode',['contract','http_error','invalid_output','timeout'])
def test_failure_is_sanitized_no_partial_audio_and_explicit_retry(client,tmp_path,monkeypatch,mode):
    monkeypatch.setenv('FRONT_ENABLE_LOCAL_TTS','1')
    p,s,a,body,provider=fixture(client,tmp_path)
    def fail(req):
        if mode=='contract':return httpx.Response(200,json={'paths':{}})
        if req.url.path=='/openapi.json':return response(req)
        if mode=='http_error':return httpx.Response(400,content=b'PRIVATE_ENGINE_SECRET_AND_PATH')
        if mode=='timeout':raise httpx.ReadTimeout('PRIVATE_ENGINE_SECRET_AND_PATH')
        return httpx.Response(200,content=b'invalid',headers={'content-type':'audio/wav'})
    calls=inject(monkeypatch,fail)
    result=client.post(url(p,s),json=body);assert result.status_code==201,result.text
    done=wait(client,p,s,result.json()['render']['id'])
    assert done['render']['status']=='error' and done['render']['audio_ref'] is None
    assert 'PRIVATE_ENGINE' not in json.dumps(done) and 'PRIVATE_ENGINE' not in json.dumps(jobs.listing())
    before=len(calls);repeat=client.post(url(p,s),json=body)
    assert repeat.json()['render']['uid']==done['render']['uid'] and len(calls)==before
    inject(monkeypatch,response)
    retry=client.post(url(p,s),json=body|token(done['project'])|{'idempotency_key':'explicit-retry'})
    assert retry.status_code==201,retry.text
    assert wait(client,p,s,retry.json()['render']['id'])['render']['status']=='candidate'


def test_real_loopback_http_protocol_service_generated_wav_only(client,tmp_path,monkeypatch,data_dir):
    from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
    observed=[]
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def send(self,raw,mime):
            self.send_response(200);self.send_header('Content-Type',mime);self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
        def do_GET(self):
            observed.append(self.path);self.send(json.dumps(schema()).encode(),'application/json')
        def do_POST(self):
            observed.append(self.path);payload=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            ref=Path(payload['ref_audio_path']);assert ref.is_relative_to(data_dir/'.staging') and ref.read_bytes().startswith(b'RIFF')
            self.send(wav(),'audio/wav')
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    try:
        monkeypatch.setenv('FRONT_ENABLE_LOCAL_TTS','1')
        p,s,a,body,provider=fixture(client,tmp_path,f'http://127.0.0.1:{server.server_port}')
        result=client.post(url(p,s),json=body);assert result.status_code==201,result.text
        row=wait(client,p,s,result.json()['render']['id'])['render']
        assert row['status']=='candidate' and row['snapshot']['quality_verified'] is False
        assert observed==['/openapi.json','/tts']
    finally:server.shutdown();server.server_close();thread.join(timeout=5)


def test_queue_full_persists_failure_without_network_and_new_key_retries(client,tmp_path,monkeypatch):
    from fastapi import HTTPException
    monkeypatch.setenv('FRONT_ENABLE_LOCAL_TTS','1')
    p,s,a,body,provider=fixture(client,tmp_path);calls=inject(monkeypatch,response);original=jobs.start
    def full(*args,**kwargs):raise HTTPException(429,'generated queue full')
    monkeypatch.setattr(jobs,'start',full)
    assert client.post(url(p,s),json=body).status_code==429
    again=client.post(url(p,s),json=body);assert again.status_code==201,again.text
    assert again.json()['render']['status']=='error' and again.json()['render']['snapshot']['error_code']=='queue_unavailable'
    assert calls==[]
    monkeypatch.setattr(jobs,'start',original)
    retry=client.post(url(p,s),json=body|token(again.json()['project'])|{'idempotency_key':'new-queue-attempt'})
    assert retry.status_code==201,retry.text
    assert wait(client,p,s,retry.json()['render']['id'])['render']['status']=='candidate'


def test_client_cancel_preserves_reference_and_prior_manual_candidate(client,tmp_path,monkeypatch,data_dir):
    monkeypatch.setenv('FRONT_ENABLE_LOCAL_TTS','1')
    p,s,a,body,provider=fixture(client,tmp_path)
    manual=client.post(base(p)+f'/segments/{s["id"]}/renders',json={**token(p),'audio_ref':body['reference'],'fingerprint':s['fingerprint']})
    assert manual.status_code==201,manual.text
    p=manual.json()['project'];body.update(token(p))
    before=(data_dir/a['file_path']).read_bytes();entered=threading.Event();release=threading.Event()
    class Stream(httpx.SyncByteStream):
        def __iter__(self):
            yield wav()[:44]
            entered.set();release.wait(10)
            yield wav()[44:]
    def blocking(req):
        if req.url.path=='/openapi.json':return response(req)
        return httpx.Response(200,stream=Stream(),headers={'content-type':'audio/wav'})
    inject(monkeypatch,blocking)
    try:
        result=client.post(url(p,s),json=body);assert result.status_code==201,result.text
        assert entered.wait(5)
        rid=result.json()['render']['id'];p=client.get(base(p)).json()
        cancel=client.post(url(p,s)+f'/{rid}/cancel',json=token(p));assert cancel.status_code==200,cancel.text
    finally:release.set()
    row=wait(client,p,s,rid)['render'];assert row['status']=='cancelled' and row['audio_ref'] is None
    for _ in range(500):
        job=jobs.get(row['snapshot']['job_id'])
        if job.status not in ('queued','running'):break
        time.sleep(.01)
    assert job.status=='cancelled'
    all_rows=client.get(base(p)+f'/segments/{s["id"]}/renders').json()['items']
    assert len(all_rows)==2 and any(r['uid']==manual.json()['render']['uid'] and r['audio_status']=='ok' for r in all_rows)
    assert (data_dir/a['file_path']).read_bytes()==before


def test_generic_cancel_before_runner_has_visible_terminal_status_and_no_network(client,tmp_path,monkeypatch):
    monkeypatch.setenv('FRONT_ENABLE_LOCAL_TTS','1')
    p,s,a,body,provider=fixture(client,tmp_path);calls=inject(monkeypatch,response)
    def never_run(kind,title,total,fn):
        job=jobs.Job(kind,title,total);job.status='cancelled';manager=jobs.manager()
        with manager.lock:manager.jobs[job.id]=job;manager.save(job)
        return job
    monkeypatch.setattr(jobs,'start',never_run)
    result=client.post(url(p,s),json=body);assert result.status_code==201,result.text
    row=result.json()['render'];assert row['status']=='cancelled' and row['recorded_status']=='queued'
    assert client.get(url(p,s)+f'/{row["id"]}').json()['render']['status']=='cancelled'
    assert calls==[]


def test_health_is_explicit_bounded_job_and_never_synthesizes(client,tmp_path,monkeypatch):
    monkeypatch.setenv('FRONT_ENABLE_LOCAL_TTS','1')
    p,s,a,body,provider=fixture(client,tmp_path);calls=inject(monkeypatch,response)
    result=client.post(f'/api/voice/providers/{provider["id"]}/check-local',json={'expected_uid':provider['uid'],
        'expected_version':provider['version'],'confirm_local_request':True})
    assert result.status_code==200,result.text
    job=jobs.get(result.json()['id'])
    for _ in range(500):
        if job.status not in ('queued','running'):break
        time.sleep(.01)
    assert job.status=='done' and job.result['contract_matches'] and not job.result['runtime_verified']
    assert [r.url.path for r in calls]==['/openapi.json']
