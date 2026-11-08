"""Generated novels, generated WAV, isolated DB; no real AI or personal files."""
import time
import threading
import pytest
from front_api import jobs
from test_voice_books import novel,project
from test_voice_projects import base,token
from test_voice_studio import create


def setup(client,text='第一章 起点\n旁白。\n甲：“你好。”\n第二章 来信\n乙：“收到。”\n第三章 归程\n结束。'):
    aid=novel(client,text);p,source=project(client,aid)
    return aid,p,source


def body(p,source,first=0,last=2):
    return {**token(p),'source_fingerprint':source['source']['fingerprint'],'first':first,'last':last}


def batch(client,p,source,first=0,last=2):
    for _ in range(500):
        current=client.get(base(p)).json()
        r=client.post(f'/api/voice/books/projects/{p["id"]}/imports/batch',json=body(current,source,first,last))
        if r.status_code==409 and '旧任务' in r.text:time.sleep(.01);continue
        assert r.status_code==202,r.text
        return r.json()
    raise AssertionError('previous attempt did not stop')


def wait(client,p,first=0,last=2):
    for _ in range(1000):
        r=client.get(f'/api/voice/books/projects/{p["id"]}/imports/range',params={'first':first,'last':last})
        assert r.status_code==200,r.text
        rows=r.json()['items']
        if all(row['import'] and row['import']['status'] not in ('queued','running') for row in rows):return rows
        time.sleep(.01)
    raise AssertionError('range timeout')


def review_base(p):return f'/api/voice/books/projects/{p["id"]}'
def choice(row,**changes):
    return {k:row[k] for k in ('id','uid','version','speaker','profile_id')}|{'confirm':row['confirmed']}|changes


def test_batch_preview_serial_order_and_idempotent_repeated_range(client):
    aid,p,source=setup(client)
    preview=client.post(review_base(p)+'/imports/preview',json=body(p,source))
    assert preview.status_code==200,preview.text
    assert preview.json()['will_synthesize'] is False and len(preview.json()['items'])==3
    assert client.get(base(p)+'/segments').json()['total']==0
    batch(client,p,source);assert [r['import']['status'] for r in wait(client,p)]==['done']*3
    rows=client.get(base(p)+'/segments').json()['items']
    chapters=[client.get(base(p)+f'/segments/{r["id"]}').json()['source']['book']['chapter_index'] for r in rows]
    assert chapters==sorted(chapters) and len(rows)==4
    old=[r['uid'] for r in rows];p=client.get(base(p)).json()
    batch(client,p,source)
    assert [r['uid'] for r in client.get(base(p)+'/segments').json()['items']]==old
    assert client.get(base(p)).json()['version']==p['version']
    assert client.get(f'/api/assets/{aid}').json()['content'].startswith('第一章')


def test_partial_pauses_later_chapters_resume_preserves_manual_edits(client):
    text='第一章 长章\n'+'甲'*120000+'\n第二章 后续\n后续正文。'
    aid,p,source=setup(client,text);batch(client,p,source,0,1)
    state=wait(client,p,0,1)
    assert [r['import']['status'] for r in state]==['partial','waiting']
    first=client.get(base(p)+'/segments').json()['items'][0];p=client.get(base(p)).json()
    updated=client.put(base(p)+f'/segments/{first["id"]}',json={**token(p),'expected_segment_version':first['version'],'text':'手动修改朗读稿，不能被续导覆盖'})
    assert updated.status_code==200,updated.text
    batch(client,p,source,0,1);assert [r['import']['status'] for r in wait(client,p,0,1)]==['done','done']
    rows=client.get(base(p)+'/segments',params={'limit':100}).json()['items']
    assert rows[0]['text']=='手动修改朗读稿，不能被续导覆盖' and rows[-1]['text']=='后续正文。'
    assert len({r['uid'] for r in rows})==len(rows)
    assert client.get(f'/api/assets/{aid}').json()['content']==text


def test_cancel_range_preserves_committed_fragment_and_can_resume(client,monkeypatch):
    entered=threading.Event();release=threading.Event();original=jobs.Job.step
    def block(self,message=None):
        original(self,message)
        if self.kind=='voice-chapter' and self.done==1:entered.set();release.wait(10)
    monkeypatch.setattr(jobs.Job,'step',block)
    aid,p,source=setup(client)
    try:
        result=batch(client,p,source);assert entered.wait(5)
        row=result['imports'][-1];p=client.get(base(p)).json()
        r=client.post(review_base(p)+f'/imports/{row["id"]}/cancel',json=token(p))
        assert r.status_code==200,r.text
        assert client.get(base(p)+'/segments').json()['total']==1
    finally:release.set()
    monkeypatch.setattr(jobs.Job,'step',original)
    batch(client,p,source);assert all(r['import']['status']=='done' for r in wait(client,p))
    assert client.get(base(p)+'/segments').json()['total']==4


def test_queue_failure_retains_all_chapter_cursors_for_explicit_retry(client,monkeypatch):
    from fastapi import HTTPException
    aid,p,source=setup(client);original=jobs.start
    def full(*args,**kwargs):raise HTTPException(429,'generated queue full')
    monkeypatch.setattr(jobs,'start',full)
    r=client.post(review_base(p)+'/imports/batch',json=body(p,source))
    assert r.status_code==429
    assert all(r['import']['error_code']=='queue_unavailable' for r in wait(client,p))
    monkeypatch.setattr(jobs,'start',original)
    batch(client,p,source);assert all(r['import']['status']=='done' for r in wait(client,p))


def test_generic_queue_cancellation_before_runner_is_visible_and_resumable(client,monkeypatch):
    aid,p,source=setup(client);original=jobs.start
    def cancelled_before_runner(kind,title,total,fn):
        job=jobs.Job(kind,title,total);job.status='cancelled';manager=jobs.manager()
        with manager.lock:
            manager.jobs[job.id]=job;manager.save(job)
        return job
    monkeypatch.setattr(jobs,'start',cancelled_before_runner)
    batch(client,p,source)
    assert all(r['import']['status']=='cancelled' for r in wait(client,p))
    assert client.get(base(p)+'/segments').json()['total']==0
    monkeypatch.setattr(jobs,'start',original)
    batch(client,p,source);assert all(r['import']['status']=='done' for r in wait(client,p))


def test_retry_detaches_old_job_before_new_queue_attachment(client,monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from front_api import models as m
    from front_api.db import new_session
    aid,p,source=setup(client)
    old=jobs.Job('voice-chapter','generated cancelled attempt');old.status='cancelled'
    manager=jobs.manager()
    with manager.lock:manager.jobs[old.id]=old;manager.save(old)
    chapter=source['chapters'][0]
    with new_session() as session:
        session.add(m.VoiceChapterImport(project_id=p['id'],chapter_index=0,
            cursor=chapter.get('body_start',chapter['start']),end=chapter['end'],status='interrupted',job_id=old.id))
        session.commit()
    entered=threading.Event();release=threading.Event();original=jobs.start
    def delayed(*args,**kwargs):entered.set();release.wait(10);return original(*args,**kwargs)
    monkeypatch.setattr(jobs,'start',delayed)
    with ThreadPoolExecutor(max_workers=1) as pool:
        first=pool.submit(client.post,review_base(p)+'/imports/batch',json=body(p,source))
        try:
            assert entered.wait(5)
            state=client.get(review_base(p)+'/imports/range',params={'first':0,'last':2}).json()['items']
            assert all(r['import']['status']=='queued' and r['import']['job_id'] is None for r in state)
            second=client.post(review_base(p)+'/imports/batch',json=body(client.get(base(p)).json(),source))
            assert second.status_code==202,second.text
        finally:release.set()
        assert first.result(timeout=10).status_code==202
    assert all(r['import']['status']=='done' for r in wait(client,p))
    assert client.get(base(p)+'/segments').json()['total']==4


@pytest.mark.parametrize('changes',[{'last':20},{'first':2,'last':1},{'last':3}])
def test_range_limits_and_source_token_are_checked_before_queue(client,changes):
    aid,p,source=setup(client)
    assert client.post(review_base(p)+'/imports/batch',json=body(p,source)|changes).status_code==422
    assert client.post(review_base(p)+'/imports/batch',json=body(p,source)|{'source_fingerprint':'0'*64}).status_code==409
    assert client.get(base(p)+'/segments').json()['total']==0


def populated(client):
    aid,p,source=setup(client);batch(client,p,source);wait(client,p)
    p=client.get(base(p)).json()
    rows=client.get(review_base(p)+'/review',params={'review':'all'}).json()['items']
    return aid,p,rows


def test_paged_review_atomic_updates_preserve_text_evidence_and_source(client):
    aid,p,rows=populated(client);profile=create(client,'profiles')
    before=client.get(base(p)+f'/segments/{rows[0]["id"]}').json()
    edited=client.put(base(p)+f'/segments/{rows[0]["id"]}',json={**token(p),'expected_segment_version':before['version'],'text':'人工修订朗读稿'})
    assert edited.status_code==200,edited.text
    p=edited.json()['project'];rows=client.get(review_base(p)+'/review').json()['items']
    page=client.get(review_base(p)+'/review',params={'limit':1,'offset':1}).json()
    assert page['total']==4 and len(page['items'])==1 and 'content' not in page
    entries=[choice(row,speaker='已审核角色',profile_id=profile['id'],confirm=True) for row in rows[:2]]
    saved=client.post(review_base(p)+'/review',json={**token(p),'entries':entries})
    assert saved.status_code==200,saved.text
    after=client.get(base(p)+f'/segments/{rows[0]["id"]}').json()
    assert after['text']=='人工修订朗读稿' and after['source']['suggestion']==before['source']['suggestion']
    assert after['source']['book']==before['source']['book'] and after['profile_id']==profile['id']
    page=client.get(review_base(p)+'/review').json()
    assert page['stats']=={'total':4,'pending':2,'voice_missing':2,'accepted_records':0}
    assert client.get(review_base(p)+'/review',params={'review':'confirmed','speaker':'已审核角色'}).json()['total']==2
    assert client.get(f'/api/assets/{aid}').json()['content'].startswith('第一章 起点\n旁白。')


@pytest.mark.parametrize('damage',['version','uid','profile','unknown'])
def test_review_batch_rejects_invalid_second_entry_without_partial_write(client,damage):
    aid,p,rows=populated(client)
    first=choice(rows[0],speaker='不能被部分写入',confirm=True)
    bad=choice(rows[1],speaker='确认角色',confirm=True)
    if damage=='version':bad['version']+=1000
    if damage=='uid':bad['uid']='0'*32
    if damage=='profile':bad['profile_id']=999999
    if damage=='unknown':bad['speaker']='待确认'
    r=client.post(review_base(p)+'/review',json={**token(p),'entries':[first,bad]})
    assert r.status_code in (404,409,422),r.text
    after=client.get(base(p)+f'/segments/{rows[0]["id"]}').json()
    assert after['speaker']==rows[0]['speaker'] and after['version']==rows[0]['version']
    assert client.get(base(p)).json()['version']==p['version']


def test_review_scope_and_duplicate_limits(client):
    aid,p,rows=populated(client)
    world=client.post('/api/worlds',json={'name':'另一世界'}).json()['id']
    char=client.post('/api/characters',json={'name':'同名人物','world_id':world}).json()['id']
    profile=create(client,'profiles',character_id=char)
    entry=choice(rows[0],profile_id=profile['id'],confirm=True)
    assert client.post(review_base(p)+'/review',json={**token(p),'entries':[entry]}).status_code==422
    assert client.post(review_base(p)+'/review',json={**token(p),'entries':[entry,entry]}).status_code==422
    assert client.post(review_base(p)+'/review',json={**token(p),'entries':[entry]*101}).status_code==422
    aid2,p2,rows2=populated(client)
    assert client.post(review_base(p2)+'/review',json={**token(p2),'entries':[choice(rows[0])]}).status_code==404


def test_preparation_reports_missing_configuration_without_jobs_or_inference(client):
    aid,p,rows=populated(client)
    before=len(jobs.listing())
    result=client.post(review_base(p)+'/prepare',json={**token(p),'entries':[choice(rows[0])]})
    assert result.status_code==200,result.text
    item=result.json()['items'][0]
    assert {'speaker_review_required','voice_missing','model_missing','engine_unconfigured','language_missing'}<=set(item['issues'])
    assert item['configuration_ready'] is False and item['will_synthesize'] is False and not item['runtime_verified']
    assert len(jobs.listing())==before


def test_review_metadata_never_selects_novel_content(client):
    from front_api.db import new_session
    from sqlalchemy import event
    aid,p,rows=populated(client)
    with new_session() as session:engine=session.bind
    statements=[]
    def capture(conn,cursor,statement,parameters,context,executemany):
        if 'FROM assets' in statement:statements.append(statement)
    event.listen(engine,'before_cursor_execute',capture)
    try:assert client.get(review_base(p)+'/review').status_code==200
    finally:event.remove(engine,'before_cursor_execute',capture)
    assert statements and all('assets.content' not in s for s in statements)
