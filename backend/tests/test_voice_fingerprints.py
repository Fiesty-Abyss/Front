"""Generated WAV only; v1 snapshots recreated from the previous public format."""
import json
import pytest
from front_api import models as m, voiceprojects as vp
from front_api.db import new_session
from test_voice_studio import create,put,upload_wav
from test_voice_projects import project,add,base,token


def fixture(client,legacy=False):
    provider=create(client,'providers',engine='gpt_sovits',endpoint='http://127.0.0.1:9880')
    model=create(client,'models',provider_id=provider['id'],file_path='/generated/model.stub',model_version='one')
    profile=create(client,'profiles',model_id=model['id'],voice_key='voice-one',language='zh')
    p=project(client);p,s=add(client,p,'生成台词',profile_id=profile['id'])
    asset,ref=upload_wav(client);url=base(p)+f'/segments/{s["id"]}'
    attached=client.post(url+'/renders',json={**token(p),'audio_ref':ref,'fingerprint':s['fingerprint']})
    assert attached.status_code==201,attached.text
    p=attached.json()['project'];r=attached.json()['render']
    if legacy:
        from front_api.voicefingerprints import digest
        with new_session() as session:
            row=session.get(m.VoiceRender,r['id']);old={k:value for k,value in row.snapshot.items() if k!='synthesis'}
            row.snapshot=old;row.fingerprint=digest({k:old[k] for k in ('segment_uid','text','speaker','recipe','profile','model','provider')})
            session.commit()
    return p,s,r,url,provider,model,profile


@pytest.mark.parametrize('legacy',[False,True])
def test_preferences_notes_labels_keep_candidate_current_and_exportable(client,legacy):
    p,s,r,url,provider,model,profile=fixture(client,legacy)
    before=client.get(url+'/renders').json()['items'][0]['snapshot']
    assert put(client,'profiles',profile,favorite=True,stars=5,preference=97,notes='使用心得',title='新显示名称').status_code==200
    assert put(client,'models',model,title='模型别名',notes='个人备注',license='授权说明').status_code==200
    assert put(client,'providers',provider,title='引擎显示名称',notes='服务备注').status_code==200
    assert client.get(url+'/renders').json()['items'][0]['stale'] is False
    current=client.get(url).json()
    edited=client.put(url,json={**token(p),'expected_segment_version':current['version'],'text':current['text'],
        'speaker':'更新显示说话人','profile_id':profile['id'],'language':'zh'})
    assert edited.status_code==200,edited.text
    p=edited.json()['project']
    assert edited.json()['segment']['fingerprint']==s['fingerprint'] # effective fallback vs explicit language
    accepted=client.post(url+f'/renders/{r["id"]}/accept',json=token(p))
    assert accepted.status_code==200,accepted.text
    p=accepted.json()['project']
    preview=client.post(base(p)+'/exports/preview',json={**token(p),'segment_ids':[s['id']]})
    assert preview.status_code==200,preview.text
    assert client.get(url+'/renders').json()['items'][0]['snapshot']==before


@pytest.mark.parametrize('legacy',[False,True])
@pytest.mark.parametrize('resource,changes',[
    ('profiles',{'voice_key':'another-voice'}),('profiles',{'language':'en'}),
    ('models',{'file_path':'/generated/another.stub'}),('models',{'model_version':'two'}),
    ('providers',{'endpoint':'http://127.0.0.1:9881'}),('providers',{'engine':'custom'})])
def test_actual_synthesis_configuration_stales_only_related_candidates(client,legacy,resource,changes):
    p,s,r,url,provider,model,profile=fixture(client,legacy)
    p,independent=add(client,p,'独立旁白')
    old_other=independent['fingerprint']
    row={'profiles':profile,'models':model,'providers':provider}[resource]
    changed=put(client,resource,row,**changes);assert changed.status_code==200,changed.text
    assert client.get(url+'/renders').json()['items'][0]['stale'] is True
    assert client.post(url+f'/renders/{r["id"]}/accept',json=token(p)).status_code==409
    assert client.get(base(p)+f'/segments/{independent["id"]}').json()['fingerprint']==old_other


def test_explicit_language_overrides_profile_default_and_no_paths_in_frame(client):
    p,s,r,url,provider,model,profile=fixture(client)
    edited=client.put(url,json={**token(p),'expected_segment_version':s['version'],'text':s['text'],
        'profile_id':profile['id'],'language':'zh'})
    assert edited.status_code==200,edited.text
    assert put(client,'profiles',profile,language='en').status_code==200
    assert client.get(url).json()['fingerprint']==s['fingerprint']
    snapshot=client.get(url+'/renders').json()['items'][0]['snapshot']
    frame=json.dumps(snapshot['synthesis'])
    assert '/generated/model.stub' not in frame and '127.0.0.1' not in frame
    assert snapshot['profile']['version']==profile['version'] # full provenance is retained


@pytest.mark.parametrize('damage',['missing_history','wrong_generation','snapshot_tamper'])
def test_unverifiable_legacy_history_is_conservatively_stale(client,damage):
    p,s,r,url,provider,model,profile=fixture(client,True)
    with new_session() as session:
        row=session.get(m.VoiceRender,r['id'])
        if damage=='snapshot_tamper':row.snapshot={**row.snapshot,'text':'不是原台词'}
        else:
            version=session.get(m.EntityVersion,profile['version'])
            if damage=='missing_history':session.delete(version)
            else:version.generation='0'*32
        session.commit()
    assert client.get(url+'/renders').json()['items'][0]['stale'] is True
    assert client.post(url+f'/renders/{r["id"]}/accept',json=token(p)).status_code==409


def test_legacy_without_profile_needs_no_historical_lookup(client):
    from front_api.voicefingerprints import digest
    p=project(client);p,s=add(client,p,'无声线的手动音频')
    asset,ref=upload_wav(client);url=base(p)+f'/segments/{s["id"]}'
    attached=client.post(url+'/renders',json={**token(p),'audio_ref':ref,'fingerprint':s['fingerprint']})
    assert attached.status_code==201
    with new_session() as session:
        row=session.get(m.VoiceRender,attached.json()['render']['id'])
        row.snapshot={k:value for k,value in row.snapshot.items() if k!='synthesis'}
        row.fingerprint=digest({k:row.snapshot[k] for k in ('segment_uid','text','speaker','recipe')})
        session.commit()
    assert client.get(url+'/renders').json()['items'][0]['stale'] is False


def test_audition_reference_is_not_a_cloning_input_or_candidate_dependency(client):
    import io,wave
    p,s,r,url,provider,model,profile=fixture(client)
    audio=io.BytesIO()
    with wave.open(audio,'wb') as wav:
        wav.setnchannels(1);wav.setsampwidth(2);wav.setframerate(8000);wav.writeframes(b'\1\0'*800)
    asset=client.post('/api/assets/upload',files={'file':('different-generated-audition.wav',audio.getvalue(),'audio/wav')}).json()
    ref={'id':asset['id'],'identity':asset['created_at'].removesuffix('Z').removesuffix('+00:00'),'sha256':asset['sha256']}
    changed=put(client,'profiles',profile,sample_ref=ref);assert changed.status_code==200,changed.text
    assert client.get(url+'/renders').json()['items'][0]['stale'] is False
    client.delete(f'/api/assets/{asset["id"]}')
    assert client.get(f'/api/voice/profiles/{profile["id"]}').json()['issues']
    result=client.get(url+'/renders').json()['items'][0]
    assert not result['stale'] and result['audio_status']=='ok'
    assert client.get(url).json()['fingerprint']==s['fingerprint']
