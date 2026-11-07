"""Generated novels and isolated database; no AI inference or private files."""
import time
from front_api import models as m,voicebooks
from front_api.db import new_session
from test_voice_projects import token,base


def novel(client,text):
    r=client.post('/api/assets',json={'title':'生成小说','kind':'novel','content':text});assert r.status_code==201,r.text
    aid=r.json()['id'];plan=client.get(f'/api/assets/{aid}/chapter-plan').json()
    confirmed=client.put(f'/api/assets/{aid}/chapter-plan',json={key:plan[key] for key in ('text_hash','base_revision','chapters')})
    assert confirmed.status_code==200,confirmed.text
    return aid


def project(client,aid):
    source=client.get(f'/api/voice/books/sources/{aid}').json()
    r=client.post(f'/api/voice/books/sources/{aid}/projects',json={'title':'生成有声小说工程','source_fingerprint':source['source']['fingerprint']})
    assert r.status_code==201,r.text
    return r.json(),source


def queue(client,p,source,index=0):
    p=client.get(base(p)).json()
    r=client.post(f'/api/voice/books/projects/{p["id"]}/imports',json={**token(p),'source_fingerprint':source['source']['fingerprint'],'chapter_index':index})
    assert r.status_code==202,r.text
    return r.json()['import']


def wait(client,p,index=0):
    for _ in range(1000):
        data=client.get(f'/api/voice/books/projects/{p["id"]}').json()
        item=data['chapters'][index]['import']
        if item and item['status'] not in ('queued','running'):return item
        time.sleep(.01)
    raise AssertionError('chapter job timeout')


def test_confirmed_source_evidence_manual_review_and_original_unchanged(client):
    text='第一章 起点\n旁白文字。\n甲：“你好。”\n第二章 来信\n乙收到信。'
    aid=novel(client,text);p,source=project(client,aid)
    queue(client,p,source);assert wait(client,p)['status']=='done'
    rows=client.get(base(p)+'/segments').json()['items'];assert len(rows)==2
    item=client.get(base(p)+f'/segments/{rows[1]["id"]}').json()
    evidence=item['source']['suggestion'];span=item['source']['book']
    assert text[span['start']:span['end']]==evidence['evidence']
    assert evidence['speaker_name_candidate']=='甲' and evidence['method']=='punctuation_rule'
    assert item['source']['speaker_confirmed'] is False
    assert client.get(f'/api/assets/{aid}').json()['content']==text
    assert client.get(f'/api/voice/books/projects/{p["id"]}',params={'limit':1,'offset':1}).json()['chapters'][0]['index']==1
    assert 'content' not in str(source.keys())
    before=len(rows);queue(client,p,source)
    assert client.get(base(p)+'/segments').json()['total']==before


def test_long_chapter_partial_resume_and_user_edit_preserved(client):
    text='第一章 长篇\n'+'甲乙'*120000
    aid=novel(client,text);p,source=project(client,aid)
    queue(client,p,source);first=wait(client,p);assert first['status']=='partial'
    a=client.get(base(p)+'/segments',params={'limit':1}).json()['items'][0]
    p=client.get(base(p)).json()
    updated=client.put(base(p)+f'/segments/{a["id"]}',json={**token(p),'expected_segment_version':a['version'],'text':'用户独立修改的朗读稿','confirm_speaker':True})
    assert updated.status_code==200,updated.text
    for _ in range(3):
        queue(client,p,source);state=wait(client,p)
        if state['status']=='done':break
    assert state['status']=='done'
    assert client.get(base(p)+f'/segments/{a["id"]}').json()['text']=='用户独立修改的朗读稿'
    count=client.get(base(p)+'/segments',params={'limit':100}).json()['total']
    queue(client,p,source)
    assert client.get(base(p)+'/segments').json()['total']==count
    assert client.get(f'/api/assets/{aid}').json()['content']==text


def test_unconfirmed_or_changed_source_rejected_without_overwrite(client):
    raw=client.post('/api/assets',json={'title':'待确认','kind':'novel','content':'第一章\n原文'}).json()['id']
    assert client.get(f'/api/voice/books/sources/{raw}').status_code==409
    aid=novel(client,'第一章 初稿\n原始内容。');p,source=project(client,aid)
    client.patch(f'/api/assets/{aid}',json={'content':'第一章 新稿\n修改后的内容。'})
    queue(client,p,source)
    assert wait(client,p)['status']=='error'
    assert client.get(base(p)+'/segments').json()['total']==0
    assert client.get(f'/api/assets/{aid}').json()['content'].endswith('修改后的内容。')


def test_source_identity_and_world_moves_are_not_merged(client):
    aid=novel(client,'第一章\n测试。');p,source=project(client,aid)
    w=client.post('/api/worlds',json={'name':'新世界'}).json()['id']
    client.patch(f'/api/assets/{aid}',json={'world_id':w})
    assert client.get(f'/api/voice/books/projects/{p["id"]}').status_code==409
    client.delete(f'/api/assets/{aid}')
    other=novel(client,'第一章\n另一份原文。');assert other==aid
    assert client.get(f'/api/voice/books/projects/{p["id"]}').status_code==409
    assert client.get(base(p)).json()['source_asset_id'] is None


def test_import_recovery_never_automatically_replays(client):
    aid=novel(client,'第一章\n测试。');p,source=project(client,aid)
    with new_session() as session:
        row=m.VoiceChapterImport(project_id=p['id'],chapter_index=0,cursor=4,end=7,status='running')
        session.add(row);session.commit();key=row.id;engine=session.bind
    voicebooks.recover(engine)
    with new_session() as session:assert session.get(m.VoiceChapterImport,key).status=='interrupted'
    assert client.get(base(p)+'/segments').json()['total']==0


def test_full_backup_restores_source_and_narration_drafts(client):
    import sqlite3
    from pathlib import Path
    from front_api import backups,jobs
    aid=novel(client,'第一章 测试\n独立生成的原文。');p,source=project(client,aid)
    queue(client,p,source);assert wait(client,p)['status']=='done'
    job=jobs.Job('full-backup','generated voice book backup');backups.create(job)
    restored=jobs.Job('full-restore','isolated restore');backups.restore(restored,backups.package_for(job.result['backup_id']))
    with sqlite3.connect(Path(restored.result['path'])/'front.db') as db:
        assert db.execute('SELECT count(*) FROM voice_book_sources').fetchone()[0]==1
        assert db.execute('SELECT count(*) FROM voice_chapter_imports').fetchone()[0]==1
        assert db.execute('SELECT text FROM voice_segments').fetchone()[0]=='独立生成的原文。'
        assert db.execute('PRAGMA foreign_key_check').fetchall()==[]


def test_additive_tables_take_pre_schema_snapshot_and_keep_existing_notes(client,data_dir,tmp_path):
    import sqlite3
    from sqlalchemy import create_engine
    from front_api.config import Settings
    from front_api.db import Base
    from front_api.dbbackup import before_schema_change
    client.post('/api/notes',json={'title':'旧库生成笔记'})
    folder=tmp_path/'old-book-schema';folder.mkdir()
    settings=Settings(folder,None,None,None,200)
    with sqlite3.connect(data_dir/'front.db') as src,sqlite3.connect(settings.db_path) as old:
        src.backup(old)
        old.execute('DROP TABLE voice_chapter_imports');old.execute('DROP TABLE voice_book_sources')
    before_schema_change(settings)
    assert len(list((folder/'backups').glob('pre-schema-*/front.db')))==1
    engine=create_engine(f'sqlite:///{settings.db_path}');Base.metadata.create_all(engine);engine.dispose()
    with sqlite3.connect(settings.db_path) as db:
        assert db.execute('SELECT title FROM notes').fetchone()[0]=='旧库生成笔记'
        assert db.execute('SELECT count(*) FROM voice_book_sources').fetchone()[0]==0


def test_metadata_polling_does_not_load_novel_content(client):
    from sqlalchemy import event
    aid=novel(client,'第一章\n生成原文。');p,source=project(client,aid)
    with new_session() as s:engine=s.bind
    queries=[]
    def capture(conn,cursor,statement,parameters,context,executemany):
        if 'FROM assets' in statement:queries.append(statement)
    event.listen(engine,'before_cursor_execute',capture)
    try:assert client.get(f'/api/voice/books/projects/{p["id"]}').status_code==200
    finally:event.remove(engine,'before_cursor_execute',capture)
    assert queries and all('assets.content' not in sql for sql in queries)


def test_source_speaker_review_required_before_mock_request(client,monkeypatch):
    monkeypatch.setenv('FRONT_ENABLE_VOICE_MOCK','1')
    aid=novel(client,'第一章\n甲：“生成台词。”');p,source=project(client,aid)
    queue(client,p,source);assert wait(client,p)['status']=='done'
    row=client.get(base(p)+'/segments').json()['items'][0];p=client.get(base(p)).json()
    url=base(p)+f'/segments/{row["id"]}/mock-requests'
    body={**token(p),'idempotency_key':'review-required','fingerprint':row['fingerprint'],'confirm_mock':True}
    assert client.post(url,json=body).status_code==409
    edited=client.put(base(p)+f'/segments/{row["id"]}',json={**token(p),'expected_segment_version':row['version'],'text':row['text'],'speaker':'甲','confirm_speaker':True})
    assert edited.status_code==200,edited.text
    result=edited.json();body.update(**token(result['project']),fingerprint=result['segment']['fingerprint'])
    assert client.post(url,json=body).status_code==201
