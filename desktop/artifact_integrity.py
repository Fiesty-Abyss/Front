"""Internal Windows artifact contract. Does not sign, publish or run installers."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import stat
import os
import subprocess
import tomllib
import zipfile

MANIFEST = 'BUILD_MANIFEST.json'
SUMS = 'SHA256SUMS.txt'
ROOT_FILES = {'Front.exe','Front.portable','README.md','LICENSE','THIRD_PARTY_NOTICES.json'}

def source_identity(root: Path) -> tuple[str,str]:
    config=json.loads((root/'desktop/src-tauri/tauri.conf.json').read_text('utf-8'))
    version=config['version']
    rust=tomllib.loads((root/'desktop/src-tauri/Cargo.toml').read_text('utf-8'))['package']['version']
    node=json.loads((root/'desktop/package.json').read_text('utf-8'))['version']
    if version!=rust or version!=node: raise ValueError('desktop_version_mismatch')
    ref=os.environ.get('GITHUB_REF','')
    if ref.startswith('refs/tags/') and ref.removeprefix('refs/tags/')!='v'+version: raise ValueError('tag_version_mismatch')
    if os.environ.get('FRONT_UPDATE_PUBLIC_KEY') or config.get('plugins',{}).get('updater',{}).get('pubkey'):
        raise ValueError('preview_pipeline_does_not_publish_signed_updates')
    source=subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True,timeout=10).strip()
    if not re.fullmatch(r'[0-9a-f]{40}',source): raise ValueError('invalid_source_revision')
    return version,source

def executable_version(path: Path, expected: str) -> None:
    if os.name!='nt': raise ValueError('windows_resource_version_check_required')
    literal=str(path.resolve()).replace("'","''")
    script="(Get-Item -LiteralPath '"+literal+"').VersionInfo | Select-Object ProductVersion,FileVersion | ConvertTo-Json -Compress"
    info=json.loads(subprocess.check_output(['powershell.exe','-NoProfile','-NonInteractive','-Command',script],text=True,timeout=20))
    file_versions={expected,expected.split('-')[0],expected.split('-')[0]+'.0'}
    if info.get('ProductVersion')!=expected or info.get('FileVersion') not in file_versions: raise ValueError('executable_version_mismatch')

def digest(path: Path) -> str:
    value=hashlib.sha256()
    with path.open('rb') as stream:
        while chunk:=stream.read(4*1024*1024): value.update(chunk)
    return value.hexdigest()

def portable_contract(path: Path) -> dict:
    names=set(); total=0; python_dll=False; runtime=False
    with zipfile.ZipFile(path) as archive:
        for item in archive.infolist():
            name=item.filename; parts=PurePosixPath(name).parts
            if '\\' in name or ':' in name or not parts or name.startswith('/') or '..' in parts:
                raise ValueError('unsafe_archive_path')
            if any(p.endswith((' ','.')) or any(ord(c)<32 or c in '<>\"|?*' for c in p) for p in parts): raise ValueError('invalid_windows_path')
            folded=name.rstrip('/').casefold()
            if folded in names: raise ValueError('duplicate_archive_path')
            names.add(folded)
            if stat.S_ISLNK(item.external_attr>>16): raise ValueError('archive_link')
            if parts[0]!='backend' and name.rstrip('/') not in ROOT_FILES: raise ValueError('unexpected_portable_file')
            if any(p.casefold() in {'frontdata','media','thumbs','webview','.git','.env','ai-providers.json','desktop-updates.json'} for p in parts):
                raise ValueError('private_data_directory')
            if name.lower().endswith(('.db','.sqlite','.sqlite3','.key','.log')): raise ValueError('private_data_file')
            if item.is_dir(): continue
            total+=item.file_size
            if total>1024**3: raise ValueError('archive_size_limit')
            if name in {'Front.exe','backend/front-backend.exe'}:
                with archive.open(item) as stream:
                    if stream.read(2)!=b'MZ': raise ValueError('missing_pe_header')
            if re.fullmatch(r'backend/.*python3\d+\.dll',name,re.I): python_dll=True
            if name.lower().endswith('/vcruntime140.dll'): runtime=True
            # certifi's public CA bundle is allowed; private PEM material is never allowed.
            if name.lower().endswith(('.pem','.p12','.pfx')):
                if name.lower().endswith(('.p12','.pfx')): raise ValueError('private_certificate_file')
                with archive.open(item) as stream:
                    tail=b''
                    while chunk:=stream.read(65536):
                        if b'PRIVATE KEY' in tail+chunk: raise ValueError('private_key_material')
                        tail=chunk[-32:]
        required={p.casefold() for p in ROOT_FILES}|{'backend/front-backend.exe'}
        if not required<=names or not python_dll or not runtime: raise ValueError('incomplete_portable_runtime')
        bad=archive.testzip()
        if bad: raise ValueError('archive_crc_failed')
    return {'members':len(names),'uncompressed_bytes':total,'embedded_python':True,'known_user_data_paths_absent':True}

def make_manifest(folder: Path, version: str, source: str) -> dict:
    if not re.fullmatch(r'[0-9a-f]{40}',source): raise ValueError('invalid_source_revision')
    if not re.fullmatch(r'\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?',version): raise ValueError('invalid_version')
    files=sorted(p for p in folder.iterdir() if p.name not in {MANIFEST,SUMS})
    if any(not p.is_file() or p.is_symlink() for p in files): raise ValueError('artifact_must_be_regular_file')
    zips=[p for p in files if p.suffix=='.zip']; installers=[p for p in files if p.suffix=='.exe']
    if len(zips)!=1 or zips[0].name!=f'Front-{version}-windows-x64-portable.zip': raise ValueError('portable_version_mismatch')
    if len(installers)!=1 or f'_{version}_' not in installers[0].name: raise ValueError('installer_version_mismatch')
    allowed={zips[0].name,installers[0].name,'Cargo.lock','THIRD_PARTY_NOTICES.json'}
    if {p.name for p in files}!=allowed: raise ValueError('artifact_allowlist_mismatch')
    with installers[0].open('rb') as stream:
        if stream.read(2)!=b'MZ': raise ValueError('missing_installer_pe_header')
    contract=portable_contract(zips[0])
    return {'format':1,'version':version,'source_revision':source,'platform':'windows-x86_64',
        'publication':'internal-artifact-only','updater_enabled':False,'signature_status':'unsigned-preview',
        'installation_verified':False,'portable_contract':contract,
        'artifacts':[{'name':p.name,'size':p.stat().st_size,'sha256':digest(p)} for p in files]}

def write_manifest(folder: Path, version: str, source: str) -> None:
    manifest=make_manifest(folder,version,source)
    (folder/MANIFEST).write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    (folder/SUMS).write_text(''.join(f'{digest(p)}  {p.name}\n' for p in sorted(folder.iterdir()) if p.name!=SUMS),encoding='utf-8')

def verify(folder: Path) -> dict:
    manifest=json.loads((folder/MANIFEST).read_text('utf-8'))
    expected=make_manifest(folder,manifest['version'],manifest['source_revision'])
    if manifest!=expected: raise ValueError('build_manifest_mismatch')
    hashes=(folder/SUMS).read_text('utf-8').splitlines()
    expected_hashes=[f'{digest(p)}  {p.name}' for p in sorted(folder.iterdir()) if p.name!=SUMS]
    if hashes!=expected_hashes: raise ValueError('artifact_hash_mismatch')
    return manifest

if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('folder',type=Path,nargs='?');parser.add_argument('--source-check',action='store_true')
    args=parser.parse_args()
    if args.source_check:
        version,revision=source_identity(Path(__file__).resolve().parents[1]);print(json.dumps({'version':version,'source_revision':revision,'publication':'internal-artifact-only'}))
    else:
        if args.folder is None:parser.error('folder is required for artifact verification')
        result=verify(args.folder)
        print(json.dumps({'version':result['version'],'source_revision':result['source_revision'],'artifacts_verified':len(result['artifacts']),'publication':result['publication']}))
