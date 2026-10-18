import hashlib
import json
import time
import zipfile

from front_api.live2dscan import scan


def fixture(path, missing=False):
    path.mkdir(parents=True)
    desc = {'Version': 3, 'FileReferences': {'Moc': 'avatar.moc3', 'Textures': ['texture.png'],
        'Physics': 'physics.json', 'Pose': 'pose.json', 'DisplayInfo': 'display.json',
        'Expressions': [{'Name': 'Smile', 'File': 'smile.exp3.json'}],
        'Motions': {'Idle': [{'File': 'idle.motion3.json', 'Sound': 'sound.wav'}]}}}
    files = {'avatar.model3.json': desc, 'physics.json': {}, 'pose.json': {},
        'display.json': {'Parameters': [{'Id': 'CustomHead'}]},
        'smile.exp3.json': {'Parameters': [{'Id': 'CustomSmile'}]},
        'idle.motion3.json': {'Curves': [{'Target': 'Parameter', 'Id': 'CustomBreath'}]}}
    for name, data in files.items():
        (path / name).write_text(json.dumps(data), encoding='utf-8')
    (path / 'avatar.moc3').write_bytes(b'MOC3\x05\0\0\0generated fixture, not renderable')
    if not missing:
        (path / 'texture.png').write_bytes(b'placeholder: existence-only fixture')
        (path / 'sound.wav').write_bytes(b'placeholder')
    return path


def wait(client, job):
    for _ in range(300):
        result = client.get('/api/jobs/' + job['id']).json()
        if result['status'] not in ('queued', 'running'):
            return result
        time.sleep(.01)
    raise AssertionError('scan timeout')


def test_all_dependencies_and_custom_parameters(tmp_path):
    path = fixture(tmp_path / 'model', missing=True)
    data = scan(path)['models'][0]
    assert {d['kind'] for d in data['dependencies']} == {'moc','texture','physics','pose','displayinfo','expression','motion','sound'}
    assert {d['file'] for d in data['diagnostics'] if d['code'] == 'missing_file'} == {'texture.png','sound.wav'}
    assert data['parameters'] == ['CustomBreath', 'CustomHead', 'CustomSmile']
    assert not data['runtime_verified']
    assert scan(tmp_path)['models'][0]['identity'] == data['identity']


def test_multiple_zip_models_do_not_extract_and_unsafe_refs(tmp_path):
    source = fixture(tmp_path / 'loose')
    archive = tmp_path / 'models.zip'
    with zipfile.ZipFile(archive, 'w') as z:
        for prefix in ['one', 'two']:
            for fp in source.iterdir():
                z.write(fp, f'{prefix}/{fp.name}')
        z.writestr('unsafe.model3.json', json.dumps({'FileReferences': {'Moc': '../outside.moc3', 'Textures': []}}))
    before = hashlib.sha256(archive.read_bytes()).hexdigest()
    result = scan(archive)
    assert len(result['models']) == 3
    assert len({m['identity'] for m in result['models']}) == 3
    assert any(d['code'] == 'unsafe_reference' for d in result['models'][2]['diagnostics'])
    assert hashlib.sha256(archive.read_bytes()).hexdigest() == before
    assert sorted(p.name for p in tmp_path.iterdir()) == ['loose','models.zip']


def test_profile_rescan_preserves_preferences_and_originals(client, tmp_path):
    path = fixture(tmp_path / 'test-avatar')
    payload = {'path': str(path), 'creator': 'Generated fixture', 'source_url': 'https://example.invalid', 'license_notes': 'Test only'}
    result = wait(client, client.post('/api/live2d/scan', json=payload).json())
    assert result['status'] == 'done' and result['result']['created'] == 1
    pid = result['result']['profile_ids'][0]
    patch = {'title': 'Renamed', 'favorite': True, 'preference': 88, 'stars': 4, 'labels': ['test'], 'notes': 'keep'}
    assert client.patch(f'/api/live2d/profiles/{pid}', json=patch).status_code == 200
    result = wait(client, client.post('/api/live2d/scan', json=payload | {'creator':'must not replace'}).json())
    assert result['result']['updated'] == 1
    detail = client.get(f'/api/live2d/profiles/{pid}').json()
    assert all(detail[k] == v for k, v in patch.items())
    assert detail['creator'] == 'Generated fixture'
    assert client.patch(f'/api/live2d/profiles/{pid}', json={'preference':101}).status_code == 422
    assert client.get('/api/live2d/profiles?q=Renamed').json()['total'] == 1
    assert (path / 'avatar.moc3').is_file()
    assert not list((path / 'avatar.model3.json').parent.glob('*.bak'))
    assert client.delete(f'/api/live2d/profiles/{pid}').status_code == 204
    assert (path / 'avatar.moc3').is_file()
    assert (path / 'avatar.model3.json').is_file()
    assert client.get('/api/live2d/profiles').json()['total'] == 0


def test_invalid_json_and_oversized_config(tmp_path):
    path = tmp_path / 'bad'
    path.mkdir()
    (path / 'bad.model3.json').write_text('{broken')
    (path / 'big.model3.json').write_bytes(b' ' * (2 * 1024 * 1024 + 1))
    result = scan(path)
    assert len(result['models']) == 2
    assert all(any(d['code'] == 'invalid_model' for d in m['diagnostics']) for m in result['models'])
