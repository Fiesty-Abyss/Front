import json
import struct
import time
from pathlib import Path

import pytest

from front_api import modelscan


def wait(client, task):
    for _ in range(150):
        row = client.get('/api/jobs/' + task['id']).json()
        if row['status'] not in ('queued', 'running'):
            assert row['status'] == 'done', row
            return row['result']
        time.sleep(.02)
    pytest.fail('job timeout')


def model(path, meta, tensor=True):
    path.parent.mkdir(parents=True, exist_ok=True)
    header = {'__metadata__': meta}
    if tensor:
        header['test.weight'] = {'dtype': 'F32', 'shape': [1], 'data_offsets': [0, 4]}
    raw = json.dumps(header).encode()
    path.write_bytes(struct.pack('<Q', len(raw)) + raw + (b'\x00'*4 if tensor else b''))


def test_model_scan_wrapper_and_bounded_diagnostics(tmp_path):
    root = tmp_path/'engine'
    source = root/'engine/models/Stable-diffusion/demo.safetensors'
    model(source, {'ss_network_module':'lycoris.kohya', 'ss_base_model_version':'sdxl_base_v1-0'})
    model(root/'engine/venv/ignored.safetensors', {})
    assert modelscan.iter_model_files(root) == [source]
    info = modelscan.describe(source, root)
    assert info['kind'] == 'lycoris' and info['base_model'] == 'SDXL'
    assert info['compatibility'] == 'unverified'
    assert '头部与偏移' in info['diagnostics'][0]
    source.with_suffix('.json').write_text('x'*(2*1024*1024+1))
    assert modelscan.read_sidecars(source) == {}
    source.write_bytes(struct.pack('<Q', 32*1024*1024))
    assert '无效' in modelscan.diagnostics(source)[0]
    def cancel():
        raise RuntimeError('cancelled')
    with pytest.raises(RuntimeError, match='cancelled'):
        modelscan.compute_hashes(source, cancel)


def test_model_report_profiles_rescan_and_compatibility(client, tmp_path):
    folder = tmp_path/'models'
    file = folder/'Lora/generated.safetensors'
    model(file, {'ss_network_module':'networks.lora','ss_base_model_version':'sdxl_base_v1-0'})
    before = file.read_bytes()
    task = client.post('/api/model-assets/scan',json={'path':str(folder)}).json()
    result = wait(client, task)
    report = client.get('/api/model-assets/reports/'+result['report_id'],params={'limit':1}).json()
    assert report['total']==1 and not report['runtime_verified'] and report['items'][0]['kind']=='lora'
    registered = wait(client,client.post('/api/sd-models/scan/run',json={'path':str(folder),'import_previews':False}).json())
    mid=registered['created'][0]
    personal={'favorite':True,'stars':5,'preference':94,'style':'test style','usage_notes':'keep me',
              'engine_mappings':{'comfyui':'folder/generated.safetensors'}}
    assert client.put(f'/api/model-assets/{mid}/profile',json=personal).status_code==200
    client.patch(f'/api/sd-models/{mid}',json={'name':'Personal name','notes':'private note'})
    wait(client,client.post('/api/sd-models/scan/run',json={'path':str(folder),'update_existing':True,'import_previews':False}).json())
    p=client.get(f'/api/model-assets/{mid}/profile').json()
    assert p['preference']==94 and p['usage_notes']=='keep me' and p['observation']['kind']=='lora'
    registered=client.get(f'/api/sd-models/{mid}').json()
    assert registered['name']=='Personal name' and registered['notes']=='private note'
    other=client.post('/api/sd-models',json={'name':'different','base_model':'SD1.5'}).json()['id']
    mismatch=client.post('/api/model-assets/compatibility',json={'engine':'comfyui','model_ids':[mid,other]}).json()
    assert mismatch['status']=='incompatible' and not mismatch['configuration_changed']
    assert all(not x['runtime_verified'] for x in mismatch['items'])
    assert file.read_bytes()==before
    assert client.put(f'/api/model-assets/{mid}/profile',json={'stars':6}).status_code==422
    assert client.get('/api/model-assets/reports/invalid').status_code==404
    hash_result=wait(client,client.post(f'/api/model-assets/{mid}/hash').json())
    assert hash_result['model_id']==mid
    from front_api import backups,jobs
    import sqlite3
    backup=jobs.Job('full-backup','generated model profile');backups.create(backup)
    package=backups.package_for(backup.result['backup_id'])
    manifest,issues=backups.verify(package)
    assert not issues and any(r['kind']=='sd_model' and not r['included'] for r in manifest['references'])
    restored=jobs.Job('full-restore','isolated model profile');backups.restore(restored,package)
    with sqlite3.connect(Path(restored.result['path'])/'front.db') as db:
        assert db.execute('SELECT preference FROM sd_model_profiles WHERE model_id=?',(mid,)).fetchone()[0]==94
        assert not db.execute('PRAGMA foreign_key_check').fetchall()


def test_model_invalid_tensor_and_pickle_never_loaded(tmp_path):
    path=tmp_path/'bad.safetensors'
    header={'x':{'dtype':'F32','shape':[4],'data_offsets':[0,999]}}
    raw=json.dumps(header).encode();path.write_bytes(struct.pack('<Q',len(raw))+raw)
    assert '偏移' in modelscan.diagnostics(path)[0]
    pickled=tmp_path/'never.pt';pickled.write_bytes(b'invalid pickle')
    assert '未反序列化' in modelscan.describe(pickled,tmp_path)['diagnostics'][0]


def test_model_mapping_existing_generator_and_explicit_catalog_mock(client, monkeypatch):
    from front_api import sdgen
    from front_api.config import get_settings
    from conftest import png_bytes
    monkeypatch.setenv('FRONT_COMFYUI_URL','http://mock');get_settings.cache_clear()
    mid=client.post('/api/sd-models',json={'name':'local','file_name':'old.safetensors','base_model':'SDXL'}).json()['id']
    client.put(f'/api/model-assets/{mid}/profile',json={'engine_mappings':{'comfyui':'shared/model.safetensors'}})
    seen=[]
    def output(url,spec,workflow):
        seen.append(spec.model_file)
        return [(png_bytes(),42)]
    monkeypatch.setattr(sdgen,'comfy_txt2img',output)
    monkeypatch.setattr(sdgen,'comfy_options',lambda url:{'models':['shared/model.safetensors'],'loras':[]})
    assert client.post('/api/model-assets/catalog-check',json={'engine':'comfyui','model_ids':[mid]}).status_code==422
    checked=client.post('/api/model-assets/catalog-check',json={'engine':'comfyui','model_ids':[mid],'confirm_connect':True}).json()
    assert checked['items'][0]['catalog_verified'] and not checked['generation_performed']
    task=client.post('/api/generate',json={'backend':'comfyui','mapping_engine':'comfyui','positive':'generated sample','model_ids':[mid]}).json()
    result=wait(client,task)
    assert seen==['shared/model.safetensors']
    gen=client.get('/api/generations/'+str(result['items'][0]['generation_id'])).json()
    assert gen['params']['mapped_model_file']=='shared/model.safetensors'
    get_settings.cache_clear()
