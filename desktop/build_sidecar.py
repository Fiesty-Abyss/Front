"""Build only the public Python package and production Vue assets; no workspace-wide collection."""
from pathlib import Path
import shutil
import subprocess
import sys
import uuid

root=Path(__file__).resolve().parents[1]
stage=root/'.cache/desktop-stage'
assert stage.resolve().is_relative_to(root), 'Build staging must stay inside the project'
subprocess.run([sys.executable,'-m','PyInstaller','--noconfirm','--clean','--onedir','--console',
    '--name','front-backend','--distpath',str(stage/'dist'),'--workpath',str(stage/'build'),
    '--specpath',str(stage),'--paths',str(root/'backend'),
    '--add-data',f'{root / "frontend/dist"}:frontend/dist',
    '--collect-all','pypdfium2','--collect-all','pypdfium2_raw','--collect-submodules','uvicorn',
    '--hidden-import','sqlalchemy.dialects.sqlite','--copy-metadata','front-api',
    str(root/'desktop/sidecar_entry.py')],check=True,cwd=root)
source=stage/'dist/front-backend';target=stage/'backend'
if target.exists():
    retired=stage/('backend-retired-'+uuid.uuid4().hex)
    assert target.resolve().is_relative_to(stage.resolve()) and retired.resolve().is_relative_to(stage.resolve())
    target.rename(retired)  # Preserve previous staged output; never merge unknown files into a package.
shutil.copytree(source,target)
assert (target/'front-backend.exe').is_file()
assert not any(p.name in ('front.db','.env','ai-providers.json') for p in target.rglob('*'))
print('Sidecar staged; user data is not part of the build inputs.')
