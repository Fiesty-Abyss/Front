"""Generated text + in-process fake provider; NOT a real DeepSeek capability test."""
import json
import time
import pytest
from front_api.routers.ai import provider_dep
from front_api.ai import AIUnavailable

TEXT='第一章 起点\n林汐是女记录员。林汐称陈舟为老师。\n第二章 来信\n陈舟向林汐寄信。小汐打开信件。'


class Provider:
    name='unit-test';model='simulated-fixture'
    def __init__(self):self.calls=0;self.fail=False
    def available(self):return True
    def chat(self,messages,**kwargs):
        self.calls+=1;content=messages[-1]['content']
        if self.fail and self.calls==2:raise AIUnavailable('secret-do-not-store')
        first='称陈舟' in content
        quote='林汐称陈舟为老师。' if first else '陈舟向林汐寄信。'
        chars=[{'name':n,'aliases':['小汐'] if n=='林汐' else [],'summary':'生成候选','gender':'女','evidence':[{'quote':quote,'category':'dialogue' if first else 'narrator','confidence':0.8}],
                'relations':[{'target':'陈舟','kind':'师徒','evidence':quote}] if n=='林汐' and first else []} for n in ('林汐','陈舟')]
        if not first:chars.append({'name':'小汐','aliases':['林汐'],'evidence':[{'quote':'小汐打开信件。','category':'inference'}]})
        chars.append({'name':'虚构幻觉','evidence':[{'quote':'不存在的原文'}]})
        return json.dumps({'characters':chars},ensure_ascii=False)


def setup(client):
    w=client.post('/api/worlds',json={'name':'生成世界'}).json()['id']
    work=client.post('/api/works',json={'title':'生成小说','kind':'novel'}).json()['id']
    a=client.post('/api/assets',json={'title':'生成证据样本','kind':'novel','content':TEXT,'world_id':w,'work_id':work}).json()['id']
    plan=client.get(f'/api/assets/{a}/chapter-plan').json()
    r=client.put(f'/api/assets/{a}/chapter-plan',json={k:plan[k] for k in ('text_hash','base_revision','chapters')})
    assert r.status_code==200,r.text
    return {'asset_id':a,'world_id':w,'work_id':work,'chapter_revision':r.json()['revision'],'chapter_indices':[0,1],'confirm_send':True,'chunk_size':500}


def wait(client,job):
    for _ in range(300):
        row=client.get('/api/jobs/'+job['id']).json()
        if row['status'] not in ('queued','running'):return row
        time.sleep(.01)
    pytest.fail('job timeout')


def decisions(detail):
    return [{'candidate_name':c['name'],'name':c['name'],'aliases':c['aliases'],'gender':c['gender'],'summary':c['summary']} for c in detail['characters']]


def test_confirmed_scope_grounding_review_idempotency_and_relations(client,app):
    p=Provider();app.dependency_overrides[provider_dep]=lambda:p
    body=setup(client)
    for change,code in [({'confirm_send':False},422),({'chapter_revision':0},409),({'max_chunks':1},413),({'chapter_indices':[-1]},422)]:
        assert client.post('/api/ai/extract/characters',json=body|change).status_code==code
    assert p.calls==0
    j=client.post('/api/ai/extract/characters',json=body).json();assert wait(client,j)['status']=='done'
    url='/api/ai/extract/reviews/'+j['batch_id'];detail=client.get(url).json()
    assert {c['name'] for c in detail['characters']}=={'林汐','陈舟','小汐'}
    for c in detail['characters']:
        assert c['gender']=='unknown' # name/prose alone is not evidence of gender
        for e in c['evidence']:assert TEXT[e['start']:e['end']]==e['quote']
    chars=decisions(detail);edges=[r['key'] for c in detail['characters'] for r in c['relations']]
    invalid=client.post(url+'/apply',json={'characters':chars,'relation_keys':['invalid']})
    assert invalid.status_code==422
    assert client.get('/api/characters').json()['total']==0 # atomic rejection
    result=client.post(url+'/apply',json={'characters':chars,'relation_keys':edges})
    assert result.status_code==200,result.text
    assert len(result.json()['created'])==3 # aliases never auto-merge 小汐 with 林汐
    assert result.json()['relations']==1
    again=client.post(url+'/apply',json={'characters':chars,'relation_keys':edges}).json()
    assert again['created']==[] and again['relations']==0
    cid=result.json()['mapping']['林汐']
    proofs=client.get(f'/api/ai/extract/reviews/evidence/character/{cid}').json();assert proofs and proofs[0]['batch_id']==j['batch_id']
    rel=client.get('/api/relations').json()['items'][0];assert rel['confirmed'] is False
    assert client.get(f'/api/ai/extract/reviews/evidence/relation/{rel["id"]}').json()
    j2=client.post('/api/ai/extract/characters',json=body).json();wait(client,j2)
    d2=client.get('/api/ai/extract/reviews/'+j2['batch_id']).json()
    result2=client.post('/api/ai/extract/reviews/'+j2['batch_id']+'/apply',json={'characters':decisions(d2)}).json()
    assert result2['created']==[]
    diff=client.get('/api/ai/extract/reviews/'+j2['batch_id']+'/compare/'+j['batch_id']).json()
    assert diff['added']==[] and diff['same_scope'] is True


def test_partial_retry_scope_and_updated_novel_protection(client,app):
    p=Provider();p.fail=True;app.dependency_overrides[provider_dep]=lambda:p
    body=setup(client);j=client.post('/api/ai/extract/characters',json=body).json();wait(client,j)
    url='/api/ai/extract/reviews/'+j['batch_id'];d=client.get(url).json()
    assert d['status']=='partial' and 'secret-do-not-store' not in json.dumps(d)
    assert client.post(url+'/resume',json={}).status_code==422
    retried=client.post(url+'/resume',json={'confirm_send':True});assert retried.status_code==200,retried.text
    wait(client,retried.json());assert p.calls==3
    d=client.get(url).json();assert d['status']=='done'
    other=client.post('/api/worlds',json={'name':'另一世界'}).json()['id']
    char=client.post('/api/characters',json={'name':'林汐','world_id':other}).json()['id']
    chosen=decisions(d);chosen[0]['existing_id']=char
    assert client.post(url+'/apply',json={'characters':chosen}).status_code==422
    client.patch(f'/api/assets/{body["asset_id"]}',json={'content':TEXT+'\n新版追加。'})
    assert client.post(url+'/apply',json={'characters':decisions(d)}).status_code==409
    assert client.get(url).json()['characters'] # old evidence is retained


def test_no_provider_does_not_send_and_parser_rejects_false_quotes(client):
    body=setup(client)
    assert client.post('/api/ai/extract/characters',json=body).status_code==503
    assert client.get('/api/ai/extract/reviews',params={'world_id':body['world_id']}).json()['total']==0


def test_queued_cancel_reconciles_and_resume_is_explicit(client,app):
    from threading import Event
    from front_api import jobs
    p=Provider();app.dependency_overrides[provider_dep]=lambda:p
    body=setup(client);gate=Event()
    blockers=[jobs.start('test','generated blocker',1,lambda job:gate.wait(3)) for _ in range(2)]
    try:
        j=client.post('/api/ai/extract/characters',json=body).json()
        client.post('/api/jobs/'+j['id']+'/cancel')
    finally:gate.set()
    assert wait(client,j)['status']=='cancelled'
    assert p.calls==0
    url='/api/ai/extract/reviews/'+j['batch_id']
    assert client.get(url).json()['status']=='cancelled'
    resumed=client.post(url+'/resume',json={'confirm_send':True});assert resumed.status_code==200,resumed.text
    assert wait(client,resumed.json())['status']=='done'


def test_large_generated_chapters_have_exact_chunk_offsets(client,app):
    p=Provider();app.dependency_overrides[provider_dep]=lambda:p
    body=setup(client)
    text='\n'.join(f'第{i}章 样本\n'+('林汐称陈舟为老师。'*120)+'\n' for i in range(1,31))
    client.patch(f'/api/assets/{body["asset_id"]}',json={'content':text})
    plan=client.get(f'/api/assets/{body["asset_id"]}/chapter-plan').json()
    saved=client.put(f'/api/assets/{body["asset_id"]}/chapter-plan',json={k:plan[k] for k in ('text_hash','base_revision','chapters')}).json()
    body|={'chapter_revision':saved['revision'],'chapter_indices':list(range(30)),'max_chunks':200}
    j=client.post('/api/ai/extract/characters',json=body).json();assert wait(client,j)['status']=='done'
    detail=client.get('/api/ai/extract/reviews/'+j['batch_id']).json()
    assert len(detail['units'])>30 and p.calls==len(detail['units'])
    assert {c['name'] for c in detail['characters']}=={'林汐','陈舟'}
    assert any(e['ambiguous_location'] for c in detail['characters'] for e in c['evidence'])
    for c in detail['characters']:
        for e in c['evidence']:assert text[e['start']:e['end']]==e['quote']
