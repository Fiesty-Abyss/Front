"""Generated WAV and isolated SQLite only; no TTS or real user assets."""
import io
import wave
import sqlite3
import pytest
from sqlalchemy import select, func
from front_api import models as m
from front_api.db import new_session


def create(client, resource, **body):
    r = client.post('/api/voice/'+resource, json={'title':'生成测试档案', **body})
    assert r.status_code == 201, r.text
    return r.json()


def put(client, resource, row, **changes):
    from front_api.voicestudio import ProviderDraft, ModelDraft, ProfileDraft
    schema = {'providers':ProviderDraft,'models':ModelDraft,'profiles':ProfileDraft}[resource]
    data = {key:row[key] for key in schema.model_fields if key in row}
    return client.put(f'/api/voice/{resource}/{row["id"]}', json={**data,
        'expected_uid':row['uid'], 'expected_version':row['version'], **changes})


def upload_wav(client):
    buf = io.BytesIO()
    with wave.open(buf, 'wb') as audio:
        audio.setnchannels(1); audio.setsampwidth(2); audio.setframerate(8000)
        audio.writeframes(b'\0\0' * 800)
    r = client.post('/api/assets/upload', files={'file':('generated.wav',buf.getvalue(),'audio/wav')})
    assert r.status_code == 201, r.text
    a = r.json()
    return a, {'id':a['id'],'identity':a['created_at'].removesuffix('Z').removesuffix('+00:00'),'sha256':a['sha256']}


def test_no_engine_profile_model_provider_and_secret_reference(client, tmp_path):
    from front_api.voicestudio import identity
    with new_session() as s:
        secret = m.AIProviderConfig(name='生成配置', kind='openai', api_key='DO-NOT-RETURN', base_url='https://example.invalid')
        s.add(secret); s.commit(); credential = secret.id
    provider = create(client,'providers',engine='gpt_sovits',endpoint='http://127.0.0.1:9880',credential_id=credential)
    assert provider['capabilities']['synthesize'] is False
    assert provider['status'] == 'not_connected'
    path=tmp_path/'not-a-real-model.bin';path.write_bytes(b'generated stub, never executed')
    model=create(client,'models',provider_id=provider['id'],file_path=str(path),license='Generated sample')
    before=path.read_bytes()
    diagnostic=client.post(f'/api/voice/models/{model["id"]}/diagnose').json()
    assert diagnostic['status']=='file_present' and diagnostic['runtime_verified'] is False
    assert path.read_bytes()==before
    standalone=create(client,'profiles',model_id=model['id'],license='personal test',favorite=True,stars=4,preference=88)
    assert standalone['character_id'] is None and standalone['binding']=={}
    assert standalone['uid'] and standalone['version']
    url=f'/api/versions/voice_provider/{provider["id"]}/{provider["version"]}'
    assert 'DO-NOT-RETURN' not in client.get(url).text
    for resource in ('providers','models','profiles'):
        assert 'DO-NOT-RETURN' not in client.get('/api/voice/'+resource).text
    with new_session() as s:
        assert s.get(m.VoiceProvider, provider['id']).credential_id==credential
        assert identity(s.get(m.VoiceProfile, standalone['id']))


def test_profile_version_restore_and_conflicting_edit(client):
    profile=create(client,'profiles',notes='旧版本')
    changed=put(client,'profiles',profile,notes='新版本')
    assert changed.status_code==200,changed.text
    row=changed.json();assert row['version'] != profile['version']
    assert put(client,'profiles',profile,notes='并发覆盖').status_code==409
    url=f'/api/versions/voice_profile/{profile["id"]}'
    restored=client.post(url+f'/{profile["version"]}/restore',json={'expected_latest':row['version']})
    assert restored.status_code==200,restored.text
    now=client.get(f'/api/voice/profiles/{profile["id"]}').json()
    assert now['notes']=='旧版本' and now['version'] not in (profile['version'],row['version'])
    assert client.get(url).json()['total']==3
    with new_session() as s:
        assert s.scalar(select(func.count()).select_from(m.VoiceProfile))==1


def test_scope_change_and_old_character_identity_rejected(client):
    w1=client.post('/api/worlds',json={'name':'世界甲'}).json()['id']
    w2=client.post('/api/worlds',json={'name':'世界乙'}).json()['id']
    c1=client.post('/api/characters',json={'name':'同名','world_id':w1}).json()['id']
    c2=client.post('/api/characters',json={'name':'同名','world_id':w2}).json()['id']
    p1=create(client,'profiles',character_id=c1)
    p2=create(client,'profiles',character_id=c2)
    assert p1['binding'] != p2['binding']
    client.patch(f'/api/characters/{c1}',json={'world_id':w2})
    detail=client.get(f'/api/voice/profiles/{p1["id"]}').json()
    assert detail['issues']
    assert put(client,'profiles',detail,notes='不能悄悄采纳新范围').status_code==409
    url=f'/api/versions/voice_profile/{p1["id"]}'
    assert client.post(url+f'/{p1["version"]}/restore',json={'expected_latest':p1['version']}).status_code==409
    detached=put(client,'profiles',detail,character_id=None)
    assert detached.status_code==200,detached.text
    assert detached.json()['binding']=={}


def test_sample_asset_reused_missing_or_modified_not_silently_accepted(client):
    a,ref=upload_wav(client)
    p=create(client,'profiles',sample_ref=ref)
    url=f'/api/versions/voice_profile/{p["id"]}'
    assert client.get(f'/api/assets/{a["id"]}/file').content.startswith(b'RIFF')
    client.delete(f'/api/assets/{a["id"]}')
    assert client.get(f'/api/voice/profiles/{p["id"]}').json()['issues']
    replacement,_=upload_wav(client)
    assert replacement['id']==a['id']
    assert put(client,'profiles',p,notes='旧试听引用').status_code==409
    assert client.post(url+f'/{p["version"]}/restore',json={'expected_latest':p['version']}).status_code==409


def test_bind_oc_without_creating_another_character(client):
    oc=client.post('/api/oc',json={'title':'生成 OC'}).json()
    assert 'id' in oc,oc
    p=create(client,'profiles',oc_id=oc['id'])
    assert p['binding']['oc'][0]==oc['id']
    assert client.post('/api/voice/profiles',json={'title':'冲突关联','oc_id':oc['id'],'character_id':oc['character_id']}).status_code==422


@pytest.mark.parametrize('resource,body',[
    ('providers',{'endpoint':'https://user:secret@example.invalid'}),
    ('providers',{'endpoint':'https://example.invalid/?key=secret'}),
    ('providers',{'engine':'chat-is-not-tts'}),
    ('profiles',{'stars':6}), ('profiles',{'preference':101}),
    ('profiles',{'sample_ref':{'id':1}}), ('models',{'api_key':'never-accepted'}),
    ('profiles',{'title':'  '}),
])
def test_validation(client,resource,body):
    r=client.post('/api/voice/'+resource,json={'title':'测试',**body})
    assert r.status_code==422,r.text


def test_paging_search_tag_filter_and_no_large_list_notes(client):
    tag=client.post('/api/tags',json={'name':'声线测试'}).json()['id']
    for index in range(5):
        create(client,'profiles',title=f'voice {index}',notes='n'*20000,license='l'*20000,tag_ids=[tag],favorite=index%2==0)
    page=client.get('/api/voice/profiles',params={'limit':2,'offset':1,'q':'voice','favorite':True,'tag':tag})
    assert page.status_code==200,page.text
    rows=page.json();assert rows['total']==3 and len(rows['items'])==2
    assert 'notes' not in rows['items'][0] and 'license' not in rows['items'][0]
    assert len(page.content)<6000
    assert client.get('/api/voice/profiles',params={'limit':101}).status_code==422
    assert client.get('/api/voice/profiles',params={'q':'%'}).json()['total']==0


def test_local_path_diagnostics_do_not_probe_network(client,tmp_path):
    for path in ('',str(tmp_path/'missing.bin'),'relative.bin',r'\\server\share\model.bin','https://example.invalid/model'):
        row=create(client,'models',file_path=path)
        r=client.post(f'/api/voice/models/{row["id"]}/diagnose')
        assert r.status_code==200,r.text
        assert r.json()['runtime_verified'] is False
        assert r.json()['status'] in ('unregistered','missing','unsupported_path')


def test_additive_schema_prebackup_preserves_old_notes(client,data_dir,tmp_path):
    from front_api.dbbackup import before_schema_change
    from front_api.config import Settings
    folder=tmp_path/'old-data';folder.mkdir()
    settings=Settings(data_dir=folder,ai_base_url=None,ai_api_key=None,ai_model=None,max_upload_mb=200)
    with sqlite3.connect(settings.db_path) as db:
        db.execute('CREATE TABLE notes (id INTEGER PRIMARY KEY, title TEXT)')
        db.execute("INSERT INTO notes VALUES (1, 'generated old note')")
    before_schema_change(settings)
    backups=list((folder/'backups').glob('pre-schema-*/front.db'))
    assert len(backups)==1
    for path in (settings.db_path,backups[0]):
        with sqlite3.connect(path) as db:
            assert db.execute('SELECT title FROM notes').fetchone()[0]=='generated old note'
            assert db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'


def test_voice_history_and_sample_survive_existing_isolated_backup_restore(client):
    from pathlib import Path
    from front_api import backups, jobs
    asset,ref=upload_wav(client)
    profile=create(client,'profiles',sample_ref=ref,notes='需要保留的声线版本')
    original=create(client,'models',file_path='/external/registration-only.bin')
    backup=jobs.Job('full-backup','generated voice test');backups.create(backup)
    package=backups.package_for(backup.result['backup_id'])
    assert not backups.verify(package)[1]
    restore=jobs.Job('full-restore','generated isolated restore');backups.restore(restore,package)
    folder=Path(restore.result['path'])
    assert (folder/asset['file_path']).read_bytes().startswith(b'RIFF')
    with sqlite3.connect(folder/'front.db') as db:
        assert db.execute('SELECT uid FROM voice_profiles').fetchone()[0]==profile['uid']
        assert db.execute('SELECT file_path FROM voice_models').fetchone()[0]==original['file_path']
        assert db.execute('SELECT count(*) FROM entity_versions').fetchone()[0]>=2
        assert db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
    assert client.get(f'/api/voice/profiles/{profile["id"]}').json()['uid']==profile['uid']


def test_sample_world_move_is_diagnosed_and_history_cannot_rebind(client):
    a,ref=upload_wav(client)
    world=client.post('/api/worlds',json={'name':'声线世界'}).json()['id']
    other=client.post('/api/worlds',json={'name':'另一世界'}).json()['id']
    char=client.post('/api/characters',json={'name':'测试角色','world_id':world}).json()['id']
    profile=create(client,'profiles',character_id=char,sample_ref=ref)
    client.patch(f'/api/assets/{a["id"]}',json={'world_id':other})
    assert client.get(f'/api/voice/profiles/{profile["id"]}').json()['issues']
    assert put(client,'profiles',profile,notes='不能静默接受移动后的音频').status_code==409
    url=f'/api/versions/voice_profile/{profile["id"]}/{profile["version"]}/restore'
    assert client.post(url,json={'expected_latest':profile['version']}).status_code==409



def test_deleted_character_or_oc_binding_can_be_explicitly_cleared(client):
    for owner in ('character','oc'):
        if owner=='character':
            char=client.post('/api/characters',json={'name':'可删除的生成角色'}).json()['id']
            profile=create(client,'profiles',character_id=char)
            assert client.delete(f'/api/characters/{char}').status_code==204
        else:
            oc=client.post('/api/oc',json={'title':'可删除的生成OC'}).json()
            profile=create(client,'profiles',oc_id=oc['id'])
            assert client.delete(f'/api/oc/{oc["id"]}',params={'expected_version':oc['version']}).status_code==204
        current=client.get(f'/api/voice/profiles/{profile["id"]}').json()
        assert current['issues'] and current['character_id'] is None and current['oc_id'] is None
        cleared=put(client,'profiles',current,character_id=None,oc_id=None,notes='明确保留为独立声线')
        assert cleared.status_code==200,cleared.text
        assert cleared.json()['binding']=={} and cleared.json()['issues']==[]
        assert cleared.json()['uid']==profile['uid'] and cleared.json()['version']!=profile['version']
        history=f'/api/versions/voice_profile/{profile["id"]}'
        # Clearing a missing association must not silently resurrect its old ID.
        assert client.post(history+f'/{profile["version"]}/restore',json={'expected_latest':cleared.json()['version']}).status_code in (404,409)
