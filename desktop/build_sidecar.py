"""Build only the public Python package and production Vue assets; no workspace-wide collection."""
from pathlib import Path
import shutil
import subprocess
import sys

root=Path(__file__).resolve().parents[1]
stage=root/'.cache/desktop-stage'
subprocess.run([sys.executable,'-m','PyInstaller','--noconfirm','--clean','--onedir','--console',
    '--name','front-backend','--distpath',str(stage/'dist'),'--workpath',str(stage/'build'),
    '--specpath',str(stage),'--paths',str(root/'backend'),
    '--add-data',f'{root / "frontend/dist"}:frontend/dist',
    '--collect-all','pypdfium2','--collect-all','pypdfium2_raw','--collect-submodules','uvicorn',
    '--hidden-import','sqlalchemy.dialects.sqlite','--copy-metadata','front-api',
    str(root/'desktop/sidecar_entry.py')],check=True,cwd=root)
source=stage/'dist/front-backend';target=stage/'backend'
target.mkdir(parents=True,exist_ok=True)
# This directory contains only this build's staged files, never an arbitrary user data directory.
shutil.copytree(source,target,dirs_exist_ok=True)
assert (target/'front-backend.exe').is_file()
assert not any(p.name in ('front.db','.env','ai-providers.json') for p in target.rglob('*'))
print('Sidecar staged; user data is not part of the build inputs.')
