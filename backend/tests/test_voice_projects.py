"""Generated dialogue/WAV only. No Mock inference or real TTS is claimed."""
import pytest
from test_voice_studio import upload_wav,create


def project(c,**changes):
    r=c.post('/api/voice/projects',json={'title':'生成配音项目',**changes})
    assert r.status_code==201,r.text
    return r.json()


def token(p):return {'project_uid':p['uid'],'expected_project_version':p['version']}
def base(p):return f'/api/voice/projects/{p["id"]}'


def add(c,p,text,**changes):
    r=c.post(base(p)+'/segments',json={**token(p),'text':text,**changes})
    assert r.status_code==201,r.text
    return r.json()['project'],r.json()['segment']


def test_manual_candidate_adoption_and_only_changed_segment_becomes_stale(client):
    p=project(client);voice=create(client,'profiles')
    p,a=add(client,p,'第一句',profile_id=voice['id'],speaker='甲')
    p,b=add(client,p,'第二句',speaker='旁白')
    original_b=b['fingerprint'];asset,ref=upload_wav(client)
    url=base(p)+f'/segments/{a["id"]}'
    attached=client.post(url+'/renders',json={**token(p),'audio_ref':ref,'fingerprint':a['fingerprint'],'note':'用户手动上传的测试候选'})
    assert attached.status_code==201,attached.text
    p=attached.json()['project'];r=attached.json()['render']
    assert r['origin']=='manual' and r['snapshot']['text']=='第一句'
    accepted=client.post(url+f'/renders/{r["id"]}/accept',json=token(p))
    assert accepted.status_code==200,accepted.text
    p=accepted.json()['project']
    edited=client.put(url,json={**token(p),'text':'修改第一句','speaker':'甲','profile_id':voice['id']})
    assert edited.status_code==200,edited.text
    p=edited.json()['project']
    assert client.get(url+'/renders').json()['items'][0]['stale'] is True
    assert client.get(base(p)+f'/segments/{b["id"]}').json()['fingerprint']==original_b
    assert client.post(url+f'/renders/{r["id"]}/accept',json=token(p)).status_code==409
    assert client.get(f'/api/assets/{asset["id"]}/file').content.startswith(b'RIFF')


def test_split_merge_preserves_original_and_unicode_boundaries(client):
    p=project(client);p,a=add(client,p,'甲😀乙\n你好')
    url=base(p)+f'/segments/{a["id"]}'
    r=client.post(url+'/split',json={**token(p),'at':2});assert r.status_code==200,r.text
    p=r.json()['project'];rows=client.get(base(p)+'/segments').json()['items']
    assert [r['text'] for r in rows]==['甲😀','乙\n你好']
    assert client.get(url).json()['archived'] is True
    assert client.put(url,json={**token(p),'text':'覆盖原片段'}).status_code==409
    assert client.get(base(p)+'/segments',params={'archived':True}).json()['total']==1
    merged=client.post(base(p)+f'/segments/{rows[0]["id"]}/merge-next',json=token(p))
    assert merged.status_code==200,merged.text
    p=merged.json()['project'];assert merged.json()['segment']['text']=='甲😀\n乙\n你好'
    assert client.get(base(p)+'/segments').json()['total']==1
    assert client.get(base(p)+'/segments',params={'archived':True}).json()['total']==3
    original=client.get(url).json()
    versions=client.get(f'/api/versions/voice_segment/{a["id"]}').json()['items']
    target=versions[-1]['id']
    restore=client.post(f'/api/versions/voice_segment/{a["id"]}/{target}/restore',json={'expected_latest':original['version']})
    assert restore.status_code==409 # Restoring text must not reverse structural edits.


def test_paging_move_and_stale_project_guard(client):
    p=project(client);items=[]
    for i in range(35):p,a=add(client,p,f'生成台词 {i}');items.append(a)
    stale=dict(p)
    r=client.post(base(p)+f'/segments/{items[30]["id"]}/move',json={**token(p),'direction':-1})
    assert r.status_code==200,r.text
    p=r.json()['project']
    first=client.get(base(p)+'/segments',params={'limit':30}).json()
    second=client.get(base(p)+'/segments',params={'limit':30,'offset':30}).json()
    assert first['total']==35 and len(second['items'])==5
    assert first['items'][-1]['uid']==items[30]['uid'] and second['items'][0]['uid']==items[29]['uid']
    assert client.put(base(p)+f'/segments/{items[0]["id"]}',json={**token(stale),'text':'过期覆盖'}).status_code==409
    assert client.get(base(p)+f'/segments/{items[0]["id"]}').json()['text']=='生成台词 0'
    assert client.get(base(p)+'/segments',params={'limit':101}).status_code==422


def test_world_isolation_and_cross_project_ids(client):
    w1=client.post('/api/worlds',json={'name':'甲世界'}).json()['id'];w2=client.post('/api/worlds',json={'name':'乙世界'}).json()['id']
    char=client.post('/api/characters',json={'name':'同名角色','world_id':w1}).json()['id']
    voice=create(client,'profiles',character_id=char)
    p=project(client,world_id=w2)
    assert client.post(base(p)+'/segments',json={**token(p),'text':'不可跨世界','profile_id':voice['id']}).status_code==422
    p,a=add(client,p,'正常旁白')
    other=project(client)
    assert client.get(base(other)+f'/segments/{a["id"]}').status_code==404
    assert client.put(base(p),json={'title':'新名','world_id':w1,'expected_uid':p['uid'],'expected_version':p['version']}).status_code==409


def test_candidate_audio_identity_and_scope_rechecked_on_adoption(client):
    p=project(client);p,a=add(client,p,'测试句')
    asset,ref=upload_wav(client);url=base(p)+f'/segments/{a["id"]}'
    r=client.post(url+'/renders',json={**token(p),'audio_ref':ref,'fingerprint':a['fingerprint']})
    assert r.status_code==201,r.text
    p=r.json()['project'];rid=r.json()['render']['id']
    world=client.post('/api/worlds',json={'name':'其他世界'}).json()['id']
    client.patch(f'/api/assets/{asset["id"]}',json={'world_id':world})
    assert client.post(url+f'/renders/{rid}/accept',json=token(p)).status_code==409
    client.delete(f'/api/assets/{asset["id"]}')
    upload_wav(client)
    assert client.get(url+'/renders').json()['items'][0]['audio_status']=='missing_or_changed'
    assert client.post(url+f'/renders/{rid}/accept',json=token(p)).status_code==409


def test_segment_history_restore_changes_project_cursor_and_keeps_new_versions(client):
    p=project(client);p,a=add(client,p,'旧台词');url=base(p)+f'/segments/{a["id"]}'
    r=client.put(url,json={**token(p),'text':'新台词'});assert r.status_code==200,r.text
    p=r.json()['project'];current=r.json()['segment']
    path=f'/api/versions/voice_segment/{a["id"]}'
    restore=client.post(path+f'/{a["version"]}/restore',json={'expected_latest':current['version']})
    assert restore.status_code==200,restore.text
    assert client.get(url).json()['text']=='旧台词'
    assert client.get(path).json()['total']==3
    assert client.get(base(p)).json()['version']!=p['version']


def test_backup_keeps_dialogue_candidates_and_audio_versions(client):
    import sqlite3
    from pathlib import Path
    from front_api import backups,jobs
    p=project(client);p,a=add(client,p,'备份测试台词')
    asset,ref=upload_wav(client)
    r=client.post(base(p)+f'/segments/{a["id"]}/renders',json={**token(p),'audio_ref':ref,'fingerprint':a['fingerprint']})
    assert r.status_code==201,r.text
    assert r.json()['render']['snapshot']['audio_version']
    backup=jobs.Job('full-backup','generated dialogue backup');backups.create(backup)
    restore=jobs.Job('full-restore','isolated dialogue restore');backups.restore(restore,backups.package_for(backup.result['backup_id']))
    folder=Path(restore.result['path'])
    assert (folder/asset['file_path']).read_bytes().startswith(b'RIFF')
    with sqlite3.connect(folder/'front.db') as db:
        assert db.execute('SELECT uid FROM voice_projects').fetchone()[0]==p['uid']
        assert db.execute('SELECT text FROM voice_segments').fetchone()[0]=='备份测试台词'
        assert db.execute('SELECT fingerprint FROM voice_renders').fetchone()[0]==a['fingerprint']
        assert db.execute('PRAGMA foreign_key_check').fetchall()==[]


def test_text_restore_after_reorder_preserves_current_order(client):
    p=project(client);p,a=add(client,p,'旧台词');p,b=add(client,p,'第二条')
    url=base(p)+f'/segments/{a["id"]}'
    edit=client.put(url,json={**token(p),'text':'新台词'});assert edit.status_code==200,edit.text
    p=edit.json()['project']
    moved=client.post(url+'/move',json={**token(p),'direction':1});assert moved.status_code==200,moved.text
    p=moved.json()['project'];current=client.get(url).json()
    restored=client.post(f'/api/versions/voice_segment/{a["id"]}/{a["version"]}/restore',json={'expected_latest':current['version']})
    assert restored.status_code==200,restored.text
    rows=client.get(base(p)+'/segments').json()['items']
    assert [r['uid'] for r in rows]==[b['uid'],a['uid']]
    assert rows[1]['text']=='旧台词'


@pytest.mark.parametrize('changes',[{'speed':0},{'speed':5},{'text':'a'*20001},{'unexpected':'not-a-TTS-param'}])
def test_segment_parameter_limits(client,changes):
    p=project(client)
    assert client.post(base(p)+'/segments',json={**token(p),'text':'测试',**changes}).status_code==422
