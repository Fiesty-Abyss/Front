import base64
import json
import httpx
from fastapi.testclient import TestClient
from conftest import png_bytes
from test_ai_drawing import wait_job
from front_api import sdgen,imageapi
from front_api.mock_sd import create_mock_app
from front_api.config import get_settings


def test_oc_manual_compare_versions_and_independent_use(client):
    oc=client.post('/api/oc',json={'title':'生成OC'}).json();url=f"/api/oc/{oc['id']}"
    refs=[]
    for i,color in enumerate([(10,20,30),(40,50,60)]):
        r=client.post(url+'/manual-image',files={'file':(f'{i}.png',png_bytes(color),'image/png')},data={'expected_version':oc['version'],'parameters':json.dumps({'model':f'model{i}','seed':i})})
        assert r.status_code==200,r.text
        refs.append(r.json()['reference_id']);oc=client.get(url).json()
    d=client.get(url+'/compare',params={'left':refs[0],'right':refs[1]}).json()
    assert [x['field'] for x in d['differences']]==['model','seed']
    assert client.get(url+f'/images/{refs[0]}/file').content==png_bytes((10,20,30))
    assert len(oc['references'])==2
    caps=client.get('/api/oc-image-services').json();assert caps['items']==[]
    provider=client.post('/api/ai/providers',json={'name':'Chat only','base_url':'http://mock/v1','chat_model':'chat'}).json()
    assert client.get('/api/oc-image-services').json()['items']==[]
    assert client.post('/api/oc-image-services',json={'provider_id':provider['id'],'name':'not confirmed','model':'chat'}).status_code==422


def test_existing_sd_engine_oc_binding_and_mock_comfy(client,monkeypatch):
    mock=create_mock_app();monkeypatch.setattr(sdgen,'client_factory',lambda url,timeout:TestClient(mock,base_url=url));monkeypatch.setattr(sdgen,'POLL_INTERVAL',.01)
    monkeypatch.setenv('FRONT_SD_WEBUI_URL','http://mock');monkeypatch.setenv('FRONT_COMFYUI_URL','http://mock');get_settings.cache_clear()
    oc=client.post('/api/oc',json={'title':'Mock OC','designs':[{'name':'日常'}]}).json();url=f"/api/oc/{oc['id']}"
    for backend in ['webui','comfyui']:
        j=client.post('/api/generate',json={'backend':backend,'positive':'generated geometric portrait','oc_profile_id':oc['id'],'oc_design_id':oc['designs'][0]['id'],'oc_expected_version':oc['version']})
        assert j.status_code==200,j.text
        job=wait_job(client,j.json());assert job['status']=='done',job
        oc=client.get(url).json();assert oc['references'][-1]['parameters']['backend']==backend
        if backend=='comfyui':
            assert oc['references'][-1]['parameters']['workflow_sha256']
            generation=client.get(f"/api/generations/{oc['references'][-1]['generation_id']}").json();assert generation['params']['workflow']
    b=client.get(url+'/batches').json();assert b['total']==2 and all(x['job']['status']=='done' for x in b['items'])
    assert client.post('/api/generate',json={'positive':'x','oc_profile_id':oc['id'],'oc_expected_version':1}).status_code==409
    get_settings.cache_clear()


def test_images_api_explicit_contract_mock_and_unsupported_parameters(client,monkeypatch):
    oc=client.post('/api/oc',json={'title':'API OC'}).json();url=f"/api/oc/{oc['id']}"
    p=client.post('/api/ai/providers',json={'name':'Explicit Images','base_url':'http://images/v1','api_key':'test-secret','chat_model':'chat'}).json()
    service=client.post('/api/oc-image-services',json={'provider_id':p['id'],'name':'image test','model':'image-model','confirmed_images_api':True}).json()['id']
    seen=[]
    def handler(request):
        assert request.url.path=='/v1/images/generations';seen.append(json.loads(request.content))
        return httpx.Response(200,json={'data':[{'b64_json':base64.b64encode(png_bytes()).decode()}]})
    monkeypatch.setattr(imageapi,'client_factory',lambda **kw:httpx.Client(transport=httpx.MockTransport(handler),**kw))
    payload={'service_id':service,'positive':'abstract portrait','expected_version':oc['version']}
    assert client.post(url+'/generate-api',json=payload|{'loras':[1]}).status_code==422
    job=wait_job(client,client.post(url+'/generate-api',json=payload).json());assert job['status']=='done',job
    assert seen==[{'model':'image-model','prompt':'abstract portrait','size':'1024x1024','n':1}]
    assert client.get('/api/oc-image-services').json()['items'][0]['last_success']
    oc=client.get(url).json();assert oc['references'][0]['parameters']['model']=='image-model'
    assert 'test-secret' not in json.dumps(client.get(url+'/batches').json())
    import io
    from PIL import Image
    encoded=io.BytesIO();Image.new('RGB',(20,24),'blue').save(encoded,'JPEG')
    monkeypatch.setattr(imageapi,'client_factory',lambda **kw:httpx.Client(transport=httpx.MockTransport(lambda r:httpx.Response(200,json={'data':[{'b64_json':base64.b64encode(encoded.getvalue()).decode()}]})),**kw))
    jpeg_job=wait_job(client,client.post(url+'/generate-api',json=payload|{'expected_version':oc['version']}).json());assert jpeg_job['status']=='done',jpeg_job
    aid=jpeg_job['result']['items'][0]['asset_id'];asset=client.get(f'/api/assets/{aid}').json()
    assert asset['original_name'].endswith('.jpg') and asset['mime']=='image/jpeg'
    oc=client.get(url).json()
    monkeypatch.setattr(imageapi,'client_factory',lambda **kw:httpx.Client(transport=httpx.MockTransport(lambda r:httpx.Response(401,json={'error':'test-secret'})),**kw))
    job=wait_job(client,client.post(url+'/generate-api',json=payload|{'expected_version':oc['version']}).json());assert job['status']=='error'
    assert 'test-secret' not in json.dumps(job)


def test_generation_scope_change_keeps_output_without_cross_world_link(client,monkeypatch):
    from front_api import models as m
    from front_api.db import new_session
    a=client.post('/api/worlds',json={'name':'A'}).json()['id'];b=client.post('/api/worlds',json={'name':'B'}).json()['id']
    oc=client.post('/api/oc',json={'title':'范围测试','world_id':a}).json()
    def fake_output(url,spec):
        with new_session() as ses:
            c=ses.get(m.Character,oc['character_id']);c.world_id=b;ses.commit()
        return [(png_bytes(),42)]
    monkeypatch.setenv('FRONT_SD_WEBUI_URL','http://mock');get_settings.cache_clear();monkeypatch.setattr(sdgen,'webui_txt2img',fake_output)
    j=client.post('/api/generate',json={'positive':'generated','oc_profile_id':oc['id'],'oc_expected_version':oc['version']}).json()
    result=wait_job(client,j);assert result['status']=='done' and result['errors']
    assert client.get(f"/api/oc/{oc['id']}").json()['references']==[]
    assert client.get('/api/assets').json()['total']==1
    get_settings.cache_clear()
