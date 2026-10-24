"""Whitelist a portable test package; never archives the checkout or a user data directory."""
from pathlib import Path
import shutil
import uuid
from archive_tools import portable_zip
from artifact_integrity import source_identity, executable_version, write_manifest, verify

root=Path(__file__).resolve().parents[1];stage=root/'.cache/desktop-stage';out=stage/'artifacts'
version,revision=source_identity(root)
executable_version(root/'desktop/src-tauri/target/release/front-desktop.exe',version)
assert stage.resolve().is_relative_to(root), 'Package staging must stay inside the project'
if out.exists():
    retired=stage/('artifacts-retired-'+uuid.uuid4().hex)
    assert out.resolve().is_relative_to(stage.resolve()) and retired.resolve().is_relative_to(stage.resolve())
    out.rename(retired)
out.mkdir()
bundle=stage/('portable-'+uuid.uuid4().hex);bundle.mkdir()
shutil.copy2(root/'desktop/src-tauri/target/release/front-desktop.exe',bundle/'Front.exe')
shutil.copytree(stage/'backend',bundle/'backend',dirs_exist_ok=True)
(bundle/'Front.portable').write_text('Use a writable folder. Personal data is stored in FrontData.\n',encoding='utf-8')
shutil.copy2(root/'desktop/README.md',bundle/'README.md')
shutil.copy2(root/'LICENSE',bundle/'LICENSE')
shutil.copy2(stage/'THIRD_PARTY_NOTICES.json',bundle/'THIRD_PARTY_NOTICES.json')
portable_zip(bundle,out/f'Front-{version}-windows-x64-portable.zip')
installers=[p for p in (root/'desktop/src-tauri/target/release/bundle/nsis').glob('*.exe') if f'_{version}_' in p.name]
assert len(installers)==1, 'Exactly one installer for this build version is required'
for installer in installers:
    shutil.copy2(installer,out/installer.name)
shutil.copy2(root/'desktop/src-tauri/Cargo.lock',out/'Cargo.lock')
shutil.copy2(stage/'THIRD_PARTY_NOTICES.json',out/'THIRD_PARTY_NOTICES.json')
write_manifest(out,version,revision)
verify(out)
print('Created and independently verified internal preview artifacts; no Release or updater feed published.')
