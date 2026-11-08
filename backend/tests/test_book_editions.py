"""Generated edition/HTTP samples, never private books or text."""
import copy
import time

import httpx
import pytest

from front_api import bookmeta, metadata as md


RAW = {'key': '/books/OL7353617M', 'title': 'Generated edition',
       'isbn_10': ['0140328726'], 'isbn_13': ['9780140328721'],
       'publishers': ['Generated publisher'], 'publish_date': 'April 1, 2001',
       'edition_name': 'Second generated edition', 'languages': [{'key': '/languages/eng'}],
       'works': [{'key': '/works/OL10W'}], 'authors': [{'key': '/authors/OL1A'}], 'covers': [5]}


@pytest.mark.parametrize('value,expected', [('0140328726','9780140328721'),('ISBN-10: 0-140-32872-6','9780140328721'),
    ('978-0-14-032872-1','9780140328721'),('080442957X','9780804429573'),('A real title',None)])
def test_isbn_checksums_and_equivalent_identifiers(value,expected):
    assert bookmeta.isbn(value)==expected


@pytest.mark.parametrize('value',['ISBN: abc','ISBN: ９７８０１４０３２８７２１',' ISBN: bad','ISBN: 123', '9780140328722','1234567890','0804429571','1234567890128'])
def test_invalid_explicit_identifiers_never_fall_back_to_title_search(client,monkeypatch,value):
    def forbidden():raise AssertionError('must not contact remote')
    monkeypatch.setattr(md,'client_factory',forbidden)
    assert client.post('/api/metadata/search',json={'online':True,'kind':'book','title':value,'providers':['openlibrary']}).status_code==422


def test_edition_does_not_invent_author_or_merge_works():
    row=bookmeta.edition(RAW,requested_isbn='9780140328721')
    assert row['sid']=='OL7353617M' and row['record_type']=='edition'
    assert row['authors']==[] and row['work_ids']==['OL10W'] and row['languages']==['eng']
    assert row['year']==2001 and row['publish_date']=='April 1, 2001'
    for expected in ['OL1M','OL10W']:
        with pytest.raises(ValueError):bookmeta.edition(RAW,expected=expected)
    with pytest.raises(ValueError):bookmeta.edition(RAW,requested_isbn='9780804429573')
    with pytest.raises(ValueError):bookmeta.edition({'key':'/works/OL10W','title':'Same name'})


@pytest.mark.parametrize('location',['https://evil.invalid/books/OL1M.json','//openlibrary.org/books/OL1M.json',
    'https://openlibrary.org@evil.invalid/books/OL1M.json','https://openlibrary.org/books/OL1M.json?token=x',
    '/isbn/9780140328721.json','/works/OL10W.json'])
def test_isbn_redirects_reject_other_hosts_paths_and_loops(monkeypatch,location):
    requests=[]
    def handler(r):requests.append(r);return httpx.Response(302,headers={'Location':location})
    monkeypatch.setattr(md,'client_factory',lambda:httpx.Client(transport=httpx.MockTransport(handler)))
    with pytest.raises(ValueError):md.OpenLibrary().search({'title':'0140328726'})
    assert len(requests)==1


def test_one_official_redirect_and_no_html_or_cover_fetch(monkeypatch):
    requests=[]
    def handler(r):
        requests.append(r)
        return httpx.Response(302,headers={'Location':'https://openlibrary.org/books/OL7353617M.json'}) if len(requests)==1 else httpx.Response(200,json=RAW)
    monkeypatch.setattr(md,'client_factory',lambda:httpx.Client(transport=httpx.MockTransport(handler)))
    started=time.monotonic()
    assert md.OpenLibrary().search({'title':'0140328726'})[0]['sid']=='OL7353617M'
    assert md._last['openlibrary']-started>=1.0  # the redirected request advances the next job's rate gate
    assert [r.url.path for r in requests]==['/isbn/9780140328721.json','/books/OL7353617M.json']


def wait(client,response):
    assert response.status_code==202,response.text
    for _ in range(500):
        state=client.get('/api/jobs/'+response.json()['id']).json()
        if state['status'] not in ('queued','running'):return state
        time.sleep(.02)
    pytest.fail('bounded metadata job did not complete')


def test_api_preview_provenance_manual_protection_and_versions(client,monkeypatch):
    calls=[]
    def handler(r):calls.append(r);return httpx.Response(200,json=RAW)
    monkeypatch.setattr(md,'client_factory',lambda:httpx.Client(transport=httpx.MockTransport(handler)))
    md._last.clear()
    search=wait(client,client.post('/api/metadata/search',json={'online':True,'kind':'book','title':'ISBN: 0140328726','author':'Unverified Author','providers':['openlibrary']}))
    row=search['result']['results']['openlibrary']['items'][0]
    assert row['match']['tier']=='strong' and row['match']['requires_confirmation']
    assert row['isbn_13']==['9780140328721']
    detail=wait(client,client.post('/api/metadata/detail',json={'online':True,'kind':'book','provider':'openlibrary','sid':row['sid']}))['result']['results']['openlibrary']
    wid=client.post('/api/works',json={'title':'Manual title','kind':'novel','publisher':'My publisher'}).json()['id']
    endpoint=f'/api/metadata/targets/work/{wid}'
    state=client.get(endpoint).json()
    body={'expected':state['expected'],'receipt':detail['receipt'],'fields':['publisher','isbn_13','languages','record_type','work_ids'],'allow_refresh':['publisher']}
    assert client.post(endpoint+'/apply',json=body).status_code==409
    assert client.get(endpoint).json()['values']['isbn_13'] is None  # no partial writes
    body['replace']=['publisher'];result=client.post(endpoint+'/apply',json=body)
    assert result.status_code==200,result.text
    updated=result.json()
    assert updated['values']['title']=='Manual title' and updated['catalog']['fields']['isbn_13']['source_id']==row['sid']
    client.patch(f'/api/works/{wid}',json={'publisher':'Manual revision'}).raise_for_status()
    body.update(expected=client.get(endpoint).json()['expected'],fields=['publisher'],replace=[])
    assert client.post(endpoint+'/apply',json=body).status_code==409
    history=client.get(f'/api/versions/work/{wid}').json()
    assert history['total']>=2
    restored=client.post(f"/api/versions/work/{wid}/{history['items'][-1]['id']}/restore",json={'expected_latest':history['items'][0]['id']})
    assert restored.status_code==200,restored.text
    assert client.get(endpoint).json()['values']['isbn_13'] is None
    assert client.get(f'/api/versions/work/{wid}').json()['total']==history['total']+1
    assert all(r.url.host=='openlibrary.org' for r in calls)


def test_author_or_year_conflict_is_not_exact(client,monkeypatch):
    raw=copy.deepcopy(RAW);raw['authors']=[{'name':'Different author'}]
    monkeypatch.setattr(md,'client_factory',lambda:httpx.Client(transport=httpx.MockTransport(lambda r:httpx.Response(200,json=raw))))
    md._last.clear()
    state=wait(client,client.post('/api/metadata/search',json={'online':True,'kind':'book','title':'0140328726','author':'Chosen author','year':2026,'providers':['openlibrary']}))
    match=state['result']['results']['openlibrary']['items'][0]['match']
    assert match['tier']=='weak' and '作者不一致' in match['reasons'] and '年份不一致' in match['reasons']


def test_pre_upgrade_empty_title_cache_does_not_hide_new_isbn_lookup(client,monkeypatch):
    import hashlib
    import json
    query={'kind':'book','title':'0140328726','author':None,'year':None,'providers':['openlibrary']}
    old=hashlib.sha256(json.dumps(['search',query,'openlibrary',hashlib.sha256(b'').hexdigest()],sort_keys=True).encode()).hexdigest()
    md._save(old,{'items':[]})  # the old title-only adapter cached no matching works
    calls=[]
    def handler(r):calls.append(r);return httpx.Response(200,json=RAW)
    monkeypatch.setattr(md,'client_factory',lambda:httpx.Client(transport=httpx.MockTransport(handler)))
    md._last.clear()
    result=wait(client,client.post('/api/metadata/search',json={'online':True,**query}))
    assert len(result['result']['results']['openlibrary']['items'])==1
    assert len(calls)==1
