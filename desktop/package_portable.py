"""Whitelist a portable test package; never archives the checkout or a user data directory."""
from pathlib import Path
import hashlib
import json
import shutil
import zipfile

root=Path(__file__).resolve().parents[1];stage=root/'.cache/desktop-stage';out=stage/'artifacts';out.mkdir(exist_ok=True)
bundle=stage/'portable';bundle.mkdir(exist_ok=True)
shutil.copy2(root/'desktop/src-tauri/target/release/front-desktop.exe',bundle/'Front.exe')
shutil.copytree(stage/'backend',bundle/'backend',dirs_exist_ok=True)
(bundle/'Front.portable').write_text('Use a writable folder. Personal data is stored in FrontData.\n',encoding='utf-8')
shutil.copy2(root/'desktop/README.md',bundle/'README.md')
shutil.copy2(root/'LICENSE',bundle/'LICENSE')
shutil.copy2(stage/'THIRD_PARTY_NOTICES.json',bundle/'THIRD_PARTY_NOTICES.json')
with zipfile.ZipFile(out/'Front-0.7.0-preview.1-windows-x64-portable.zip','w',zipfile.ZIP_DEFLATED) as archive:
    for p in bundle.rglob('*'):
        if p.is_file():archive.write(p,p.relative_to(bundle))
for installer in (root/'desktop/src-tauri/target/release/bundle/nsis').glob('*.exe'):
    shutil.copy2(installer,out/installer.name)
shutil.copy2(root/'desktop/src-tauri/Cargo.lock',out/'Cargo.lock')
shutil.copy2(stage/'THIRD_PARTY_NOTICES.json',out/'THIRD_PARTY_NOTICES.json')
lines=[]
for p in sorted(out.iterdir()):
    if not p.is_file() or p.name=='SHA256SUMS.txt':continue
    h=hashlib.sha256()
    with p.open('rb') as f:
        while chunk:=f.read(4*1024*1024):h.update(chunk)
    lines.append(f'{h.hexdigest()}  {p.name}')
(out/'SHA256SUMS.txt').write_text('\n'.join(lines)+'\n',encoding='utf-8')
print('Created preview installer/portable artifacts; no Release or updater published.')
