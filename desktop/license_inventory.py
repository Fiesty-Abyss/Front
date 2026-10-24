"""Preserve dependency notices with the preview. Review inventory before any formal Release."""
from importlib import metadata
import json
from pathlib import Path
import re
import shutil
import subprocess

root=Path(__file__).resolve().parents[1];stage=root/'.cache/desktop-stage';notices=stage/'backend/licenses';notices.mkdir(parents=True,exist_ok=True)
rows=[]
def save(name,version,license,files):
    key=re.sub(r'[^a-zA-Z0-9_.-]','_',name+'-'+version)
    folder=notices/key;folder.mkdir(exist_ok=True)
    included=[]
    for i,path in enumerate(files):
        path=Path(path)
        if path.is_file() and path.stat().st_size<2*1024*1024:
            dest=f'{i}-{path.name}';shutil.copy2(path,folder/dest);included.append(f'{key}/{dest}')
    rows.append({'name':name,'version':version,'license':str(license or 'review required'),'notice_files':included})
for dist in metadata.distributions():
    files=[dist.locate_file(p) for p in (dist.files or []) if any(x in str(p).lower() for x in ('license','copying','notice')) and str(p).lower().endswith(('.txt','.md','.rst','license','copying','notice'))]
    save('python-'+dist.metadata['Name'],dist.version,dist.metadata.get('License-Expression') or dist.metadata.get('License'),files)
for project in ('frontend','desktop'):
    lock=json.loads((root/project/'package-lock.json').read_text(encoding='utf-8'))
    for name,info in lock.get('packages',{}).items():
        if not name:continue
        folder=root/project/name
        files=[p for p in folder.iterdir() if p.is_file() and any(p.name.lower().startswith(x) for x in ('license','notice','copying'))] if folder.is_dir() else []
        save('npm-'+name.split('node_modules/')[-1],info.get('version','unknown'),info.get('license'),files)
cargo=json.loads(subprocess.check_output(['cargo','metadata','--format-version','1','--manifest-path',str(root/'desktop/src-tauri/Cargo.toml')],text=True))
for pkg in cargo['packages']:
    folder=Path(pkg['manifest_path']).parent
    files=[p for p in folder.iterdir() if p.is_file() and any(p.name.lower().startswith(x) for x in ('license','notice','copying'))]
    if pkg.get('license_file'):files.append(folder/pkg['license_file'])
    save('cargo-'+pkg['name'],pkg['version'],pkg.get('license'),files)
path=stage/'THIRD_PARTY_NOTICES.json';path.write_text(json.dumps({'preview':True,'dependencies':rows},ensure_ascii=False,indent=2),encoding='utf-8')
shutil.copy2(path,stage/'backend/THIRD_PARTY_NOTICES.json')
print('Dependency inventory and available license texts preserved; formal release review remains separate.')
