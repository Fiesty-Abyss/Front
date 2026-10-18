import io
import json
import zipfile

import pytest

from front_api.chapters import split_chapters, chapter_text


@pytest.mark.parametrize('heading',['第一章 起点','第123章 起点','第１２章 起点','第十二回 起点','序章','楔子','番外一','后记','终章','Chapter 12 Start','###### 自定义章节'])
def test_heading_variants(heading):
    text = heading + '\r\n正文。\r\n'
    toc = split_chapters(text)
    assert len(toc) == 1 and chapter_text(text,toc[0]) == '正文。'


def test_volumes_fences_and_leading_whitespace():
    text = '\n第一卷 云\n第一章 甲\n正文\n```md\n# 代码不是章节\n```\n第二部 海\n第一章 乙\n结尾'
    toc = split_chapters(text)
    assert len(toc) == 4
    assert toc[0]['start'] == 0 and toc[-1]['end'] == len(text)
    assert toc[1]['end'] == toc[2]['start']


def test_plan_save_restore_stale_and_coverage(client):
    text = '第一章 开始\n正文甲。\n第二章 后续\n正文乙。'
    aid = client.post('/api/assets',json={'title':'Boundary fixture','kind':'novel','content':text}).json()['id']
    url = f'/api/assets/{aid}/chapter-plan'
    plan = client.get(url).json()
    request = {k:plan[k] for k in ('text_hash','base_revision','chapters')}
    request['chapters'][0]['title'] = '改名'
    saved = client.put(url,json=request).json()
    assert 'revision' in saved
    assert client.get(f'/api/assets/{aid}/chapters/0').json()['content'] == '正文甲。'
    assert client.put(url,json=request).status_code == 409
    request['base_revision'] = saved['revision']
    request['chapters'] = list(reversed(request['chapters']))
    second = client.put(url,json=request).json()['revision']
    assert client.get(f'/api/assets/{aid}/chapters/0').json()['title'] == '第二章 后续'
    history = client.get(url + f'/history/{saved["revision"]}').json()
    request['base_revision'] = second
    request['chapters'] = history['chapters']
    assert client.put(url,json=request).status_code == 200
    assert len(client.get(url).json()['history']) == 3
    broken = client.get(url).json()
    broken['chapters'][0]['end'] -= 1
    assert client.put(url,json={k:broken[k] for k in ('text_hash','base_revision','chapters')}).status_code == 422
    hidden = client.get(url).json()
    hidden['chapters'][0]['body_start'] = hidden['chapters'][0]['start'] + 2
    assert client.put(url,json={k:hidden[k] for k in ('text_hash','base_revision','chapters')}).status_code == 422
    client.patch(f'/api/assets/{aid}',json={'content':text+'\n新正文'})
    assert client.get(url).json()['stale']
    assert client.put(url,json=request).status_code == 409


def test_full_long_text_not_preview_and_original_preserved(client, data_dir):
    text = '第一章 起点\n' + '长篇内容。' * 300000 + '\n第二章 末尾\n真实结尾'
    original = text.encode('utf-8')
    asset = client.post('/api/assets/upload',files={'file':('long.txt',original)}).json()
    assert asset['meta']['text_truncated']
    plan = client.get(f'/api/assets/{asset["id"]}/chapter-plan').json()
    assert plan['length'] == len(text) and len(plan['chapters']) == 2
    assert '真实结尾' in client.get(f'/api/assets/{asset["id"]}/chapters/1').json()['content']
    assert (data_dir / asset['file_path']).read_bytes() == original
    assert client.post('/api/assets/upload',files={'file':('again.txt',original)}).status_code == 409


def test_utf16_and_gbk(client):
    for encoding in ('utf-16','gb18030'):
        raw = ('第一章 '+encoding+'\n异常编码测试正文').encode(encoding)
        asset = client.post('/api/assets/upload',files={'file':('encoded.txt',raw)}).json()
        assert '异常编码测试正文' in client.get(f'/api/assets/{asset["id"]}/chapters/0').json()['content']


def test_epub_full_spine_and_broken_reference(client):
    def book(broken=False):
        stream = io.BytesIO()
        with zipfile.ZipFile(stream,'w') as z:
            z.writestr('book.opf','<package><manifest><item id="b" href="two.xhtml"/><item id="a" href="one.xhtml"/></manifest><spine><itemref idref="a"/><itemref idref="b"/></spine></package>')
            z.writestr('one.xhtml','<h1>第一章 开始</h1><p>'+ '内容。'*12000 +'</p>')
            if not broken:
                z.writestr('two.xhtml','<h1>第二章 结束</h1><p>最后 &amp; 完结</p>')
        return stream.getvalue()
    asset = client.post('/api/assets/upload',files={'file':('book.epub',book())}).json()
    assert '最后 & 完结' in client.get(f'/api/assets/{asset["id"]}/chapters/1').json()['content']
    bad = client.post('/api/assets/upload',files={'file':('broken.epub',book(True))}).json()
    assert client.get(f'/api/assets/{bad["id"]}/chapter-plan').status_code == 422
