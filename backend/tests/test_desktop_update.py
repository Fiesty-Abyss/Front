import io
import time
import threading
import asyncio
from concurrent.futures import ThreadPoolExecutor

from fastapi.testclient import TestClient
from PIL import Image

from front_api import jobs, maintenance
from front_api.desktop import protect


def terminal(client, identifier):
    deadline=time.monotonic()+10
    while time.monotonic()<deadline:
        result=client.get('/api/jobs/'+identifier).json()
        if result['status'] in ('done','error','cancelled','interrupted'):return result
        time.sleep(.02)
    raise AssertionError('generated update preparation timed out')


def test_update_requires_shell_and_keeps_writes_paused_through_verified_backup(app):
    protect(app,token='generated-shell-secret',port=23456,stop=lambda:None)
    with TestClient(app,base_url='http://127.0.0.1:23456') as client:
        bearer={'Authorization':'Bearer generated-shell-secret','x-front-update-request':'1'}
        assert client.post('/_desktop/session',headers=bearer).status_code==200
        assert client.post('/_desktop/update/prepare').status_code==403
        image=io.BytesIO();Image.new('RGB',(20,20),'purple').save(image,'PNG')
        assert client.post('/api/assets/upload',files={'file':('generated.png',image.getvalue(),'image/png')}).status_code==201
        prepared=client.post('/_desktop/update/prepare',headers=bearer)
        assert prepared.status_code==202
        data=prepared.json()
        try:
            result=terminal(client,data['id'])
            assert result['status']=='done' and result['result']['status']=='complete'
            assert result['result']['verified'] and result['result']['restore_verified']
            assert client.post('/api/worlds',json={'name':'blocked generated world'}).status_code==423
            same=client.post('/_desktop/update/prepare',headers=bearer).json()
            assert same['id']==data['id'] 
            assert not client.post('/_desktop/update/release',headers={**bearer,'x-front-update-request':'2'}).json()['released']
            assert client.post('/api/worlds',json={'name':'still blocked'}).status_code==423
        finally:
            assert client.post('/_desktop/update/release',headers={**bearer,'x-front-update-request':'1'}).json()['released']
        assert client.post('/api/worlds',json={'name':'generated after deferral'}).status_code==201


def test_update_rejects_active_jobs_without_stranding_worker_queue(app):
    protect(app,token='generated-shell-secret',port=23456,stop=lambda:None)
    entered=threading.Event();release=threading.Event()
    def work(job):entered.set();release.wait(5)
    running=jobs.start('generated-wait','generated',0,work)
    assert entered.wait(2)
    try:
        with TestClient(app,base_url='http://127.0.0.1:23456') as client:
            headers={'Authorization':'Bearer generated-shell-secret','x-front-update-request':'1'}
            client.headers.update(headers)
            assert client.post('/_desktop/update/prepare',headers=headers).status_code==409
            assert client.post('/api/worlds',json={'name':'generated unpaused'},headers=headers).status_code==201
            release.set()
            assert terminal(client,running.id)['status']=='done'
    finally:release.set()


def test_failed_update_backup_releases_writer_reservation(app,monkeypatch):
    from front_api import backups
    def fault(job):raise OSError('generated disk fault')
    monkeypatch.setattr(backups,'create',fault)
    protect(app,token='generated-shell-secret',port=23456,stop=lambda:None)
    with TestClient(app,base_url='http://127.0.0.1:23456') as client:
        headers={'Authorization':'Bearer generated-shell-secret','x-front-update-request':'1'}
        client.headers.update(headers)
        data=client.post('/_desktop/update/prepare',headers=headers).json()
        assert terminal(client,data['id'])['status']=='error'
        assert client.post('/api/worlds',json={'name':'generated after backup fault'},headers=headers).status_code==201


def test_reservation_cannot_freeze_inflight_mutation():
    assert maintenance.begin()
    try:
        try:maintenance.reserve_writes()
        except RuntimeError:pass
        else:raise AssertionError('must retry after inflight writer finishes')
    finally:maintenance.end()


def test_desktop_shutdown_releases_update_reservation(app):
    protect(app,token='generated-shell-secret',port=23456,stop=lambda:None)
    with TestClient(app,base_url='http://127.0.0.1:23456') as client:
        client.headers.update({'Authorization':'Bearer generated-shell-secret','x-front-update-request':'1'})
        data=client.post('/_desktop/update/prepare').json()
        assert terminal(client,data['id'])['status']=='done'
        assert not maintenance.begin()
    assert maintenance.begin()
    maintenance.end()


def test_cancel_before_prepare_and_lost_response_recovery(app):
    protect(app,token='generated-shell-secret',port=23456,stop=lambda:None)
    with TestClient(app,base_url='http://127.0.0.1:23456') as client:
        client.headers.update({'Authorization':'Bearer generated-shell-secret','x-front-update-request':'1'})
        assert not client.post('/_desktop/update/release').json()['released']
        assert client.post('/_desktop/update/prepare').status_code==409
        assert client.post('/api/worlds',json={'name':'generated after early cancellation'}).status_code==201
        client.headers['x-front-update-request']='2'
        # Server completed preparation; simulate losing the response rather than knowing a server lease.
        assert client.post('/_desktop/update/prepare').status_code==202
        old=jobs.listing('full-backup')[0]['id'];assert terminal(client,old)['status']=='done'
        client.headers['x-front-update-request']='3'
        new=client.post('/_desktop/update/prepare').json();assert new['id']!=old
        assert terminal(client,new['id'])['status']=='done'
        assert not client.post('/_desktop/update/release',headers={'x-front-update-request':'2'}).json()['released']
        assert client.post('/api/worlds',json={'name':'still protected generated world'}).status_code==423
        assert client.post('/_desktop/update/release').json()['released']
        assert client.post('/api/worlds',json={'name':'generated after recovery'}).status_code==201


def test_asgi_gate_retains_streaming_writer_until_body_finishes():
    async def scenario():
        sent=asyncio.Event();finish=asyncio.Event();late_write=[]
        async def stream(scope,receive,send):
            await send({'type':'http.response.start','status':200,'headers':[]})
            sent.set();await finish.wait()
            late_write.append('generated final commit')
            await send({'type':'http.response.body','body':b'done','more_body':False})
        async def send(message):pass
        task=asyncio.create_task(maintenance.MutationGate(stream)({'type':'http','path':'/api/generated','method':'POST'},None,send))
        await sent.wait()
        try:
            try:maintenance.reserve_writes()
            except RuntimeError:pass
            else:raise AssertionError('headers must not release streaming writer')
        finally:finish.set();await task
        assert late_write==['generated final commit']
        reservation=maintenance.reserve_writes();maintenance.release_writes(reservation)
    asyncio.run(scenario())


def test_mock_ai_stream_blocks_update_until_real_reply_commit(app):
    from front_api.routers import ai
    entered=threading.Event();finish=threading.Event()
    class GeneratedProvider:
        name='generated mock';model='generated';label='generated'
        def available(self):return True
        def stream(self,messages):
            yield 'Generated first'
            entered.set();finish.wait(5)
            yield ' completed'
    app.dependency_overrides[ai.provider_dep]=lambda:GeneratedProvider()
    protect(app,token='generated-shell-secret',port=23456,stop=lambda:None)
    with TestClient(app,base_url='http://127.0.0.1:23456') as client:
        client.headers.update({'Authorization':'Bearer generated-shell-secret','x-front-update-request':'1'})
        card=client.post('/api/cards',json={'name':'Generated card','first_mes':'Generated greeting'}).json()
        chat=client.post('/api/ai/sessions',json={'card_id':card['id']}).json()
        with ThreadPoolExecutor(max_workers=1) as pool:
            future=pool.submit(client.post,f"/api/ai/sessions/{chat['id']}/generate",json={'content':'generated question'})
            try:
                assert entered.wait(3)
                assert client.post('/_desktop/update/prepare').status_code==409
            finally:finish.set()
            response=future.result(timeout=10);assert response.status_code==200
        assert not ai.has_active_generations()
        saved=client.get(f"/api/ai/sessions/{chat['id']}").json()
        assert saved['messages'][-1]['content']=='Generated first completed'
        client.headers['x-front-update-request']='2'
        data=client.post('/_desktop/update/prepare').json()
        try:assert terminal(client,data['id'])['status']=='done'
        finally:client.post('/_desktop/update/release')
