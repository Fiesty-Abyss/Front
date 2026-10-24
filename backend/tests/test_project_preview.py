import hashlib
import time

from conftest import png_bytes


def wait(client,job):
    for _ in range(300):
        data=client.get('/api/jobs/'+job['id']).json()
        if data['status'] not in ('queued','running'):
            assert data['status']=='done',data
            return data['result']['report_id']
        time.sleep(.01)
    raise AssertionError('preview timeout')


def test_preview_is_read_only_incremental_and_paginated(client,tmp_path):
    root=tmp_path/'original'
    (root/'人物').mkdir(parents=True)
    text=root/'人物'/'设定.txt';text.write_text('原创设定片段',encoding='utf-8')
    (root/'duplicate.txt').write_bytes(text.read_bytes())
    (root/'portrait.png').write_bytes(png_bytes())
    script=root/'reference.py';script.write_text("raise RuntimeError('never execute this')")
    before={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in root.rglob('*') if p.is_file()}
    pid=wait(client,client.post('/api/project-previews',json={'path':str(root)}).json())
    report=client.get('/api/project-previews/'+pid+'?limit=2').json()
    assert report['total']==4 and len(report['items'])==2 and report['duplicate_files']==1
    rest=client.get('/api/project-previews/'+pid+'?limit=2&offset=2').json()
    files=report['items']+rest['items']
    person=next(f for f in files if f['relative'].startswith('人物'))
    assert person['candidate']=='character'
    assert '原创设定片段' in client.get(f'/api/project-previews/{pid}/files/{person["index"]}').json()['text']
    image=next(f for f in files if f['kind']=='drawing')
    response=client.get(f'/api/project-previews/{pid}/files/{image["index"]}/image')
    assert response.status_code==200 and response.headers['x-content-type-options']=='nosniff'
    code=next(f for f in files if f['kind']=='code')
    assert 'never execute' in client.get(f'/api/project-previews/{pid}/files/{code["index"]}').json()['text']
    assert client.get(f'/api/project-previews/{pid}/files/{code["index"]}/image').status_code==415
    again=wait(client,client.post('/api/project-previews',json={'path':str(root)}).json())
    assert client.get('/api/project-previews/'+again).json()['reused_hashes']==4
    assert client.get('/api/assets').json()['total']==0
    assert client.get('/api/worlds').json()['total']==0
    assert before=={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in root.rglob('*') if p.is_file()}
    text.write_text('改过的设定',encoding='utf-8')
    assert client.get(f'/api/project-previews/{pid}/files/{person["index"]}').status_code==409


def test_preview_cross_world_duplicates_do_not_merge(client,tmp_path):
    first=client.post('/api/worlds',json={'name':'Same name'}).json()['id']
    second=client.post('/api/worlds',json={'name':'Same name'}).json()['id']
    assert first!=second
    root=tmp_path/'files';root.mkdir();(root/'ref.txt').write_bytes(b'original-reference')
    asset=client.post('/api/assets/upload',files={'file':('ref.txt',b'original-reference')},data={'world_id':second}).json()
    pid=wait(client,client.post('/api/project-previews',json={'path':str(root),'world_id':first}).json())
    report=client.get('/api/project-previews/'+pid).json()
    assert report['items'][0]['existing']==[{'asset_id':asset['id'],'same_world':False}]
    assert client.get('/api/assets').json()['total']==1
    assert client.get('/api/assets/'+str(asset['id'])).json()['world_id']==second
    assert client.post('/api/project-previews',json={'path':str(root),'world_id':99999}).status_code==404
    assert client.get('/api/project-previews/invalid').status_code==404
    assert client.get(f'/api/project-previews/{pid}/files/9999').status_code==409
