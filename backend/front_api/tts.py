"""Lightweight TTS contracts. No model imports, service starts or implicit requests."""
from dataclasses import asdict, dataclass, field
import hashlib
import json
import math
from time import monotonic
import struct
import threading
from typing import BinaryIO, Protocol
from urllib.parse import urlsplit
import wave

import httpx

GPT_CONTRACT = 'GPT-SoVITS/api_v2.py@04a44eb977586645f33594b72af13a035a2056c6'


class AdapterError(Exception):
    """Safe stable code only; never echo upstream bodies, paths or credentials."""


class Unsupported(AdapterError):
    pass


class Cancelled(AdapterError):
    pass


class Cancellation:
    def __init__(self):
        self.event = threading.Event()

    def cancel(self):
        self.event.set()

    def check(self):
        if self.event.is_set():
            raise Cancelled('cancelled')


@dataclass(frozen=True)
class Capabilities:
    adapter: str
    contract: str
    formats: tuple[str, ...] = ('wav',)
    parameters: tuple[str, ...] = ()
    voice_listing: bool = False
    training: bool = False
    cancellation: str = 'client_only'
    runtime_verified: bool = False
    speech: bool = True


@dataclass(frozen=True)
class VoiceSpec:
    profile_uid: str
    profile_version: int
    model_uid: str
    model_version: int
    reference_path: str = ''
    reference_text: str = ''
    reference_language: str = ''
    rights_authorized: bool = False
    rights_source: str = ''


@dataclass(frozen=True)
class SynthesisRequest:
    text: str
    language: str
    voice: VoiceSpec
    speed: float = 1
    seed: int = -1
    parameters: dict = field(default_factory=dict)

    def fingerprint(self, contract):
        value={'contract':contract,**asdict(self)}
        return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode()).hexdigest()


@dataclass(frozen=True)
class AudioResult:
    sha256: str
    size: int
    sample_rate: int
    channels: int
    duration: float
    origin: str


class TTSAdapter(Protocol):
    def health(self) -> dict: ...
    def capabilities(self) -> Capabilities: ...
    def list_voices(self) -> list[VoiceSpec]: ...
    def validate_voice(self, voice: VoiceSpec) -> None: ...
    def synthesize(self, request: SynthesisRequest, output: BinaryIO, cancel: Cancellation) -> AudioResult: ...
    def cancel(self, token: Cancellation) -> None: ...
    def train(self, *args, **kwargs): ...


def empty_output(output):
    if output.tell()!=0:
        raise AdapterError('output_must_be_empty')
    output.seek(0,2)
    size=output.tell();output.seek(0)
    if size:
        raise AdapterError('output_must_be_empty')


def common(request):
    if not isinstance(request.text,str) or not request.text.strip() or len(request.text)>20000:
        raise AdapterError('invalid_text')
    if not request.language or len(request.language)>40:
        raise AdapterError('invalid_language')
    if type(request.speed) not in (int,float) or not math.isfinite(request.speed) or not .25<=request.speed<=4:
        raise AdapterError('invalid_speed')
    if type(request.seed) is not int or not -1<=request.seed<=4294967295:
        raise AdapterError('invalid_seed')
    voice=request.voice
    if not voice.profile_uid or not voice.model_uid or voice.profile_version<1 or voice.model_version<1:
        raise AdapterError('voice_identity_required')


def validated_wav(output,origin,limit=64*1024*1024):
    output.seek(0,2);size=output.tell();output.seek(0)
    if not 44<=size<=limit:
        raise AdapterError('invalid_audio_size')
    try:
        with wave.open(output,'rb') as wav:
            rate,channels,width,frames=wav.getframerate(),wav.getnchannels(),wav.getsampwidth(),wav.getnframes()
            if channels not in (1,2) or width not in (1,2,3,4) or not 8000<=rate<=192000 or frames<1:
                raise AdapterError('invalid_wav_metadata')
            expected=frames*channels*width
            if expected>limit:
                raise AdapterError('audio_limit_exceeded')
            actual=0
            while block:=wav.readframes(8192):
                actual+=len(block)
                if actual>limit:
                    raise AdapterError('audio_limit_exceeded')
            if actual!=expected:
                raise AdapterError('truncated_audio')
    except (wave.Error,EOFError,ValueError):
        raise AdapterError('invalid_wav') from None
    output.seek(0);digest=hashlib.sha256()
    while block:=output.read(65536):digest.update(block)
    output.seek(0)
    return AudioResult(digest.hexdigest(),size,rate,channels,frames/rate,origin)


class BaseAdapter:
    def list_voices(self):
        raise Unsupported('voice_listing_unsupported')

    def cancel(self,token):
        # Cooperative client cancellation only. Never call a server-wide control.
        token.cancel()

    def train(self,*args,**kwargs):
        raise Unsupported('training_unsupported')


class MockAdapter(BaseAdapter):
    """One-second marker tone, not speech, inference or a cloned voice."""
    def health(self):
        return {'reachable':True,'mock':True,'runtime_verified':False}

    def capabilities(self):
        return Capabilities('mock','generated-marker-v1',speech=False)

    def validate_voice(self,voice):
        if not voice.profile_uid or not voice.model_uid:
            raise AdapterError('voice_identity_required')

    def synthesize(self,request,output,cancel):
        common(request);self.validate_voice(request.voice)
        if request.parameters or request.speed!=1 or request.seed!=-1:
            raise Unsupported('mock_parameters_unsupported')
        cancel.check();empty_output(output)
        try:
            with wave.open(output,'wb') as wav:
                wav.setnchannels(1);wav.setsampwidth(2);wav.setframerate(16000)
                for start in range(0,16000,1000):
                    cancel.check()
                    wav.writeframes(b''.join(struct.pack('<h',round(1800*math.sin(2*math.pi*220*i/16000))) for i in range(start,start+1000)))
            cancel.check()
            return validated_wav(output,'mock')
        except BaseException:
            output.seek(0);output.truncate();raise


def endpoint(value):
    if not isinstance(value,str) or any(ord(char)<32 for char in value):
        raise AdapterError('invalid_endpoint')
    try:
        url=urlsplit(value)
        if url.scheme not in ('http','https') or not url.hostname or url.username or url.password or url.query or url.fragment:
            raise ValueError()
        host=url.hostname.lower();port=url.port or (443 if url.scheme=='https' else 80)
        origin=(url.scheme,host,port)
    except ValueError:
        raise AdapterError('invalid_endpoint') from None
    return value.rstrip('/'),origin


class GPTSoVITSAdapter(BaseAdapter):
    """Pinned v2 wire contract; not exposed as a public Front inference endpoint.

    Explicit endpoint allowlist and authorized reference are required even for
    a caller-owned already-running service. Tests inject MockTransport only.
    """
    def __init__(self,base_url,*,allowed_origins,client=None,max_audio_bytes=64*1024*1024):
        self.base,self.origin=endpoint(base_url)
        allowed={endpoint(value)[1] for value in allowed_origins}
        if self.origin not in allowed:
            raise AdapterError('endpoint_not_allowlisted')
        if not 44<=max_audio_bytes<=64*1024*1024:
            raise AdapterError('invalid_audio_limit')
        self.limit=max_audio_bytes
        self.timeout=httpx.Timeout(20,connect=5,write=5,pool=5)
        self.owned=client is None
        self.client=client or httpx.Client(trust_env=False,follow_redirects=False,timeout=self.timeout)

    def close(self):
        if self.owned:self.client.close()

    def capabilities(self):
        return Capabilities('gpt_sovits',GPT_CONTRACT,parameters=('speed','seed','top_k','top_p','temperature','text_split_method'))

    def health(self,cancel=None):
        deadline=monotonic()+120
        try:
            with self.client.stream('GET',self.base+'/openapi.json',headers={'Accept-Encoding':'identity'},timeout=self.timeout,follow_redirects=False) as response:
                if response.status_code!=200:return {'reachable':False,'contract_matches':False,'runtime_verified':False}
                if response.headers.get('content-encoding','identity').lower()!='identity':raise AdapterError('encoded_response_unsupported')
                data=bytearray()
                for block in response.iter_bytes():
                    if cancel:cancel.check()
                    if monotonic()>deadline:raise AdapterError('deadline_exceeded')
                    if len(data)+len(block)>1024*1024:raise AdapterError('schema_limit_exceeded')
                    data.extend(block)
                spec=json.loads(data)
                schema=spec['paths']['/tts']['post']['requestBody']['content']['application/json']['schema']
                if '$ref' in schema:schema=spec['components']['schemas'][schema['$ref'].rsplit('/',1)[-1]]
                required={'text','text_lang','ref_audio_path','prompt_lang','prompt_text','speed_factor','seed','media_type','streaming_mode'}
                matches=required<=schema.get('properties',{}).keys()
                return {'reachable':True,'contract_matches':matches,'runtime_verified':False,'server_revision_verified':False}
        except httpx.HTTPError:
            raise AdapterError('health_transport_failed') from None
        except (ValueError,KeyError,TypeError,AttributeError):
            raise AdapterError('invalid_openapi') from None

    def validate_voice(self,voice):
        if voice.rights_authorized is not True or not voice.rights_source.strip() or len(voice.rights_source)>2000:
            raise AdapterError('reference_authorization_required')
        if not voice.reference_path or len(voice.reference_path)>2000 or not voice.reference_language or len(voice.reference_language)>40 or len(voice.reference_text)>20000:
            raise AdapterError('invalid_reference')
        if '://' in voice.reference_path or voice.reference_path.startswith(('\\\\','//')) or any(ord(char)<32 for char in voice.reference_path):
            raise AdapterError('reference_must_be_engine_local')

    def payload(self,request):
        common(request);self.validate_voice(request.voice)
        params=dict(request.parameters)
        if set(params)-{'top_k','top_p','temperature','text_split_method'}:
            raise Unsupported('parameter_unsupported')
        for key,low,high in [('top_k',1,100),('top_p',.01,1),('temperature',.01,2)]:
            if key not in params:continue
            value=params[key]
            if type(value) not in (int,float) or not math.isfinite(value) or not low<=value<=high or (key=='top_k' and type(value) is not int):
                raise AdapterError('invalid_parameter')
        if params.get('text_split_method','cut5') not in ('cut0','cut5'):
            raise Unsupported('split_method_unsupported')
        return {'text':request.text,'text_lang':request.language,'ref_audio_path':request.voice.reference_path,
            'prompt_text':request.voice.reference_text,'prompt_lang':request.voice.reference_language,
            'speed_factor':request.speed,'seed':request.seed,'media_type':'wav','streaming_mode':False,**params}

    def synthesize(self,request,output,cancel):
        payload=self.payload(request);cancel.check();empty_output(output)
        deadline=monotonic()+120
        try:
            with self.client.stream('POST',self.base+'/tts',json=payload,headers={'Accept-Encoding':'identity'},timeout=self.timeout,follow_redirects=False) as response:
                if response.status_code!=200:raise AdapterError('upstream_http_'+str(response.status_code))
                if response.headers.get('content-encoding','identity').lower()!='identity':raise AdapterError('encoded_response_unsupported')
                if response.headers.get('content-type','').split(';')[0].lower() not in ('audio/wav','audio/x-wav'):
                    raise AdapterError('unexpected_content_type')
                size=0
                for block in response.iter_bytes():
                    cancel.check()
                    if monotonic()>deadline:raise AdapterError('deadline_exceeded')
                    size+=len(block)
                    if size>self.limit:raise AdapterError('audio_limit_exceeded')
                    for start in range(0,len(block),65536):
                        cancel.check();output.write(block[start:start+65536])
                cancel.check()
                return validated_wav(output,'gpt_sovits',self.limit)
        except httpx.TimeoutException:
            output.seek(0);output.truncate();raise AdapterError('timeout') from None
        except httpx.HTTPError:
            output.seek(0);output.truncate();raise AdapterError('transport_failed') from None
        except BaseException:
            output.seek(0);output.truncate();raise
