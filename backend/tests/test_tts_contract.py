"""Generated marker WAV and HTTP MockTransport only. No TTS inference."""
from dataclasses import replace
import io
import json
import struct
import wave
import httpx
import pytest
from front_api.tts import (AdapterError,Unsupported,Cancelled,Cancellation,Capabilities,
    VoiceSpec,SynthesisRequest,MockAdapter,GPTSoVITSAdapter,GPT_CONTRACT)


def request():
    voice=VoiceSpec('generated-profile',1,'generated-model',1,
        reference_path='/fixtures/generated-marker.wav',reference_text='Generated fixture',
        reference_language='en',rights_authorized=True,rights_source='generated test tone, not a human voice')
    return SynthesisRequest('生成测试台词','zh',voice)


def wav_bytes(frames=100):
    output=io.BytesIO()
    with wave.open(output,'wb') as wav:
        wav.setnchannels(1);wav.setsampwidth(2);wav.setframerate(16000);wav.writeframes(b'\0\0'*frames)
    return output.getvalue()


def adapter(handler,**kwargs):
    client=httpx.Client(transport=httpx.MockTransport(handler))
    return GPTSoVITSAdapter('http://127.0.0.1:9880',allowed_origins=['http://127.0.0.1:9880'],client=client,**kwargs)


def test_mock_is_marker_not_speech_and_has_stable_recipe_identity():
    a=MockAdapter();body=request();out=io.BytesIO()
    result=a.synthesize(body,out,Cancellation())
    assert result.origin=='mock' and result.duration==1 and result.sample_rate==16000
    assert a.capabilities().speech is False and a.capabilities().runtime_verified is False
    assert out.read(4)==b'RIFF'
    assert body.fingerprint('mock-v1')==body.fingerprint('mock-v1')
    assert body.fingerprint('mock-v1')!=replace(body,text='改一句').fingerprint('mock-v1')
    assert body.fingerprint('mock-v1')!=replace(body,voice=replace(body.voice,profile_version=2)).fingerprint('mock-v1')
    assert body.fingerprint('mock-v1')!=body.fingerprint('mock-v2')
    token=Cancellation();a.cancel(token)
    with pytest.raises(Cancelled):a.synthesize(body,io.BytesIO(),token)
    with pytest.raises(Unsupported):a.synthesize(replace(body,speed=2),io.BytesIO(),Cancellation())


def test_official_v2_payload_binary_output_and_no_control_routes():
    seen=[];raw=wav_bytes()
    def handle(req):
        seen.append(req.url.path)
        assert req.method=='POST' and req.url.path=='/tts'
        body=json.loads(req.content)
        assert body['text_lang']=='zh' and body['prompt_lang']=='en'
        assert body['ref_audio_path']=='/fixtures/generated-marker.wav'
        assert body['prompt_text']=='Generated fixture'
        assert body['speed_factor']==1.2 and body['seed']==42
        assert body['media_type']=='wav' and body['streaming_mode'] is False
        assert 'rights_source' not in body and 'profile_uid' not in body
        return httpx.Response(200,content=raw,headers={'content-type':'audio/wav'})
    a=adapter(handle);output=io.BytesIO()
    result=a.synthesize(replace(request(),speed=1.2,seed=42,parameters={'top_k':10,'top_p':.8}),output,Cancellation())
    assert output.read()==raw and result.size==len(raw) and result.origin=='gpt_sovits'
    assert a.capabilities().contract==GPT_CONTRACT
    assert a.capabilities().cancellation=='client_only' and a.capabilities().training is False
    with pytest.raises(Unsupported):a.list_voices()
    with pytest.raises(Unsupported):a.train()
    assert seen==['/tts']


def test_health_reads_only_openapi_and_does_not_claim_inference_ready():
    def handle(req):
        assert req.method=='GET' and req.url.path=='/openapi.json'
        return httpx.Response(200,json={'paths':{'/tts':{'post':{'requestBody':{'content':{'application/json':{'schema':{'$ref':'#/components/schemas/TTS_Request'}}}}}}},
            'components':{'schemas':{'TTS_Request':{'properties':{key:{} for key in ('text','text_lang','ref_audio_path','prompt_lang','prompt_text','speed_factor','seed','media_type','streaming_mode')}}}}})
    data=adapter(handle).health()
    assert data['reachable'] and data['contract_matches']
    assert data['runtime_verified'] is False and data['server_revision_verified'] is False


@pytest.mark.parametrize('url',['http://user:secret@127.0.0.1:9880','http://127.0.0.1:9880?token=secret','file:///private/file','https://other.invalid'])
def test_endpoint_allowlist_and_secret_free_urls(url):
    with pytest.raises(AdapterError):GPTSoVITSAdapter(url,allowed_origins=['http://127.0.0.1:9880'])


def test_reference_authorization_and_parameters_rejected_before_network():
    seen=[]
    a=adapter(lambda req:seen.append(req))
    for voice in (replace(request().voice,rights_authorized=False),replace(request().voice,rights_source=''),replace(request().voice,reference_path=''),replace(request().voice,reference_path='https://other.invalid/ref.wav')):
        with pytest.raises(AdapterError):a.synthesize(replace(request(),voice=voice),io.BytesIO(),Cancellation())
    for params in ({'lora':'not-supported'},{'top_k':True},{'temperature':float('nan')},{'top_p':2},{'text_split_method':'arbitrary'}):
        with pytest.raises(AdapterError):a.synthesize(replace(request(),parameters=params),io.BytesIO(),Cancellation())
    assert seen==[]


@pytest.mark.parametrize('status,mime,data,code',[
    (400,'application/json',b'{"message":"PRIVATE_KEY_AND_PATH"}','upstream_http_400'),
    (302,'audio/wav',b'','upstream_http_302'),
    (200,'application/json',b'{}','unexpected_content_type'),
    (200,'audio/wav',b'not a wav','invalid_audio_size'),
    (200,'audio/wav',wav_bytes()[:-30],'truncated_audio'),
])
def test_failure_is_sanitized_and_output_truncated(status,mime,data,code):
    out=io.BytesIO()
    a=adapter(lambda req:httpx.Response(status,content=data,headers={'content-type':mime,'location':'https://other.invalid'}))
    with pytest.raises(AdapterError,match=code) as error:a.synthesize(request(),out,Cancellation())
    assert 'PRIVATE' not in str(error.value) and out.getvalue()==b''


def test_timeout_interruption_output_limit_and_existing_file_protection():
    def timeout(req):raise httpx.ReadTimeout('PRIVATE_KEY secret url')
    with pytest.raises(AdapterError,match='timeout') as err:adapter(timeout).synthesize(request(),io.BytesIO(),Cancellation())
    assert str(err.value)=='timeout'
    out=io.BytesIO()
    with pytest.raises(AdapterError,match='audio_limit_exceeded'):
        adapter(lambda req:httpx.Response(200,content=wav_bytes(),headers={'content-type':'audio/wav'}),max_audio_bytes=100).synthesize(request(),out,Cancellation())
    assert out.getvalue()==b''
    original=io.BytesIO(b'original content')
    with pytest.raises(AdapterError,match='output_must_be_empty'):MockAdapter().synthesize(request(),original,Cancellation())
    assert original.getvalue()==b'original content'


def test_cooperative_cancel_leaves_no_partial_audio():
    token=Cancellation();raw=wav_bytes(40000)
    class Stream(httpx.SyncByteStream):
        def __iter__(self):
            yield raw[:65536]
            token.cancel()
            yield raw[65536:]
    a=adapter(lambda req:httpx.Response(200,stream=Stream(),headers={'content-type':'audio/wav'}))
    out=io.BytesIO()
    with pytest.raises(Cancelled):a.synthesize(request(),out,token)
    assert out.getvalue()==b''


def test_encoded_audio_is_rejected_before_body_decoding():
    read=[]
    class Encoded(httpx.SyncByteStream):
        def __iter__(self):
            read.append(True)
            yield b'not actually gzip; must never be decoded'
    def handle(req):
        assert req.headers['accept-encoding']=='identity'
        return httpx.Response(200,stream=Encoded(),headers={'content-type':'audio/wav','content-encoding':'gzip'})
    with pytest.raises(AdapterError,match='encoded_response_unsupported'):
        adapter(handle).synthesize(request(),io.BytesIO(),Cancellation())
    assert not read


def test_transport_interruption_leaves_no_partial_audio():
    raw=wav_bytes(40000);out=io.BytesIO()
    class Broken(httpx.SyncByteStream):
        def __iter__(self):
            yield raw[:65536]
            raise httpx.ReadError('PRIVATE path and key')
    a=adapter(lambda req:httpx.Response(200,stream=Broken(),headers={'content-type':'audio/wav'}))
    with pytest.raises(AdapterError,match='transport_failed'):a.synthesize(request(),out,Cancellation())
    assert out.getvalue()==b''


def test_small_transport_chunks_are_observed_before_64k_for_cancellation():
    output=io.BytesIO();token=Cancellation();raw=wav_bytes()
    class Stream(httpx.SyncByteStream):
        def __iter__(self):
            yield raw[:44]
            assert output.tell()==44  # Waiting for 64KiB would hide cancellation.
            token.cancel();yield raw[44:]
    a=adapter(lambda req:httpx.Response(200,stream=Stream(),headers={'content-type':'audio/wav'}))
    with pytest.raises(Cancelled):a.synthesize(request(),output,token)
    assert output.getvalue()==b''


def test_total_receive_deadline_clears_output(monkeypatch):
    from front_api import tts
    samples=iter([0,121])
    monkeypatch.setattr(tts,'monotonic',lambda:next(samples))
    a=adapter(lambda req:httpx.Response(200,content=wav_bytes(),headers={'content-type':'audio/wav'}))
    output=io.BytesIO()
    with pytest.raises(AdapterError,match='deadline_exceeded'):a.synthesize(request(),output,Cancellation())
    assert output.getvalue()==b''


def test_health_rejects_schema_missing_fields_that_are_sent():
    spec={'paths':{'/tts':{'post':{'requestBody':{'content':{'application/json':{'schema':{'properties':{k:{} for k in ('text','text_lang','ref_audio_path','prompt_lang')}}}}}}}}}
    result=adapter(lambda req:httpx.Response(200,json=spec)).health()
    assert result['reachable'] and not result['contract_matches'] and not result['runtime_verified']
