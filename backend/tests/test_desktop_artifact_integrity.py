from pathlib import Path
import importlib.util,json,zipfile
import pytest
spec=importlib.util.spec_from_file_location('integrity',Path(__file__).resolve().parents[2]/'desktop/artifact_integrity.py')
integrity=importlib.util.module_from_spec(spec);spec.loader.exec_module(integrity)

def fixture(folder, extra=None):
    folder.mkdir()
    with zipfile.ZipFile(folder/'Front-0.7.0-preview.1-windows-x64-portable.zip','w') as z:
        for name in integrity.ROOT_FILES:z.writestr(name,b'MZgenerated' if name=='Front.exe' else b'generated')
        z.writestr('backend/front-backend.exe',b'MZgenerated');z.writestr('backend/_internal/python312.dll',b'generated')
        z.writestr('backend/_internal/vcruntime140.dll',b'generated')
        for name,body in (extra or {}).items():z.writestr(name,body)
    (folder/'Front_0.7.0-preview.1_x64-setup.exe').write_bytes(b'MZgenerated')
    (folder/'Cargo.lock').write_text('generated');(folder/'THIRD_PARTY_NOTICES.json').write_text('{}')
    return folder

def test_artifact_manifest_and_hashes_bind_all_generated_files(tmp_path):
    folder=fixture(tmp_path/'build');integrity.write_manifest(folder,'0.7.0-preview.1','a'*40)
    assert integrity.verify(folder)['publication']=='internal-artifact-only'
    (folder/'Front_0.7.0-preview.1_x64-setup.exe').write_bytes(b'MZtampered')
    with pytest.raises(ValueError,match='manifest_mismatch'):integrity.verify(folder)

@pytest.mark.parametrize('name,body',[
    ('../outside',b'x'),('backend/../outside',b'x'),('FrontData/front.db',b'x'),
    ('backend/api.key',b'private'),('backend/private.pem',b'-----BEGIN PRIVATE KEY-----'),
    ('backend/USER.LOG',b'private'),('backend/.env',b'private'),('Front.EXE',b'MZduplicate'),
])
def test_portable_rejects_unsafe_private_and_duplicate_entries(tmp_path,name,body):
    folder=fixture(tmp_path/'build',{name:body})
    with pytest.raises(ValueError):integrity.make_manifest(folder,'0.7.0-preview.1','b'*40)

def test_portable_public_ca_bundle_is_not_a_private_key(tmp_path):
    folder=fixture(tmp_path/'build',{'backend/certifi/cacert.pem':b'-----BEGIN CERTIFICATE-----'})
    assert integrity.make_manifest(folder,'0.7.0-preview.1','c'*40)['portable_contract']['embedded_python']

def test_wrong_version_and_unknown_outputs_cannot_be_uploaded(tmp_path):
    folder=fixture(tmp_path/'build')
    with pytest.raises(ValueError,match='version_mismatch'):integrity.make_manifest(folder,'0.7.1','a'*40)
    (folder/'extra.txt').write_text('not allowed')
    with pytest.raises(ValueError,match='allowlist'):integrity.make_manifest(folder,'0.7.0-preview.1','a'*40)

def test_manifest_cannot_promote_a_preview_or_drop_hashes(tmp_path):
    folder=fixture(tmp_path/'build');integrity.write_manifest(folder,'0.7.0-preview.1','a'*40)
    path=folder/integrity.MANIFEST;data=json.loads(path.read_text());data['publication']='release';path.write_text(json.dumps(data))
    with pytest.raises(ValueError,match='manifest_mismatch'):integrity.verify(folder)

def test_hash_list_cannot_omit_a_file_even_when_manifest_is_untouched(tmp_path):
    folder=fixture(tmp_path/'build');integrity.write_manifest(folder,'0.7.0-preview.1','a'*40)
    path=folder/integrity.SUMS;path.write_text('\n'.join(path.read_text().splitlines()[:-1])+'\n')
    with pytest.raises(ValueError,match='hash_mismatch'):integrity.verify(folder)

def test_desktop_source_and_tag_versions_are_checked_before_build(tmp_path,monkeypatch):
    root=tmp_path/'repo';(root/'desktop/src-tauri').mkdir(parents=True)
    (root/'desktop/src-tauri/tauri.conf.json').write_text('{"version":"0.7.0-preview.1"}')
    (root/'desktop/package.json').write_text('{"version":"0.7.0-preview.1"}')
    cargo=root/'desktop/src-tauri/Cargo.toml';cargo.write_text('[package]\nversion="0.7.0-preview.1"')
    monkeypatch.setattr(integrity.subprocess,'check_output',lambda *a,**k:'a'*40)
    monkeypatch.delenv('FRONT_UPDATE_PUBLIC_KEY',raising=False);monkeypatch.setenv('GITHUB_REF','refs/tags/v0.7.0-preview.1')
    assert integrity.source_identity(root)==('0.7.0-preview.1','a'*40)
    monkeypatch.setenv('GITHUB_REF','refs/tags/v0.7.1')
    with pytest.raises(ValueError,match='tag_version_mismatch'):integrity.source_identity(root)
    monkeypatch.setenv('GITHUB_REF','refs/pull/1/merge');cargo.write_text('[package]\nversion="0.7.1"')
    with pytest.raises(ValueError,match='desktop_version_mismatch'):integrity.source_identity(root)

def test_preview_pipeline_cannot_silently_become_a_signed_release(tmp_path,monkeypatch):
    root=tmp_path/'repo';(root/'desktop/src-tauri').mkdir(parents=True)
    (root/'desktop/src-tauri/tauri.conf.json').write_text('{"version":"0.7.0-preview.1"}')
    (root/'desktop/package.json').write_text('{"version":"0.7.0-preview.1"}')
    (root/'desktop/src-tauri/Cargo.toml').write_text('[package]\nversion="0.7.0-preview.1"')
    monkeypatch.setenv('GITHUB_REF','refs/pull/1/merge');monkeypatch.setenv('FRONT_UPDATE_PUBLIC_KEY','generated-test-public-key')
    with pytest.raises(ValueError,match='preview_pipeline'):integrity.source_identity(root)
