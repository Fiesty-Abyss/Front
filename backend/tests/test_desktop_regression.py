import importlib.util
import os
from pathlib import Path
import sys
import threading
from types import SimpleNamespace

import pytest

from front_api.desktop import prepare_folder

spec = importlib.util.spec_from_file_location('desktop_regression', Path(__file__).resolve().parents[2]/'desktop'/'regression_sidecar.py')
regression = importlib.util.module_from_spec(spec)
spec.loader.exec_module(regression)


def test_startup_handshake_has_bounded_wait():
    release=threading.Event()
    def blocked_read(): release.wait(1); return ''
    try:
        with pytest.raises(RuntimeError,match='handshake_timeout_or_invalid'):
            regression.handshake(SimpleNamespace(stdout=SimpleNamespace(readline=blocked_read)),timeout=.02)
    finally: release.set()


def test_desktop_folder_preflight_retains_existing_files(tmp_path, monkeypatch):
    root = tmp_path/'generated'; root.mkdir(); sentinel=root/'keep.bin'; sentinel.write_bytes(b'generated original')
    prepare_folder(root)
    assert sentinel.read_bytes() == b'generated original'
    assert not list(root.rglob('.front-write-check-*'))
    with pytest.raises(RuntimeError, match='data_directory_unwritable'):
        prepare_folder(sentinel)
    calls = []
    original_open = Path.open
    def denied(path, *args, **kwargs):
        if path.name.startswith('.front-write-check-'):
            calls.append(path)
            raise PermissionError('generated permission fault')
        return original_open(path, *args, **kwargs)
    monkeypatch.setattr(Path, 'open', denied)
    with pytest.raises(RuntimeError, match='data_directory_unwritable'):
        prepare_folder(root)
    assert sentinel.read_bytes() == b'generated original'
    assert len(calls) == 1  # bounded denial, not hundreds of thousands of retries


def test_preflight_collision_and_fsync_failure_preserve_originals(tmp_path, monkeypatch):
    collision = tmp_path / '.front-write-check-generated-collision'
    collision.write_bytes(b'pre-existing generated original')
    monkeypatch.setattr('front_api.desktop.secrets.token_hex', lambda _: 'generated-collision')
    with pytest.raises(RuntimeError, match='data_directory_unwritable'):
        prepare_folder(tmp_path)
    assert collision.read_bytes() == b'pre-existing generated original'
    monkeypatch.setattr('front_api.desktop.secrets.token_hex', lambda _: 'generated-fsync-fault')
    def failed_sync(*args): raise OSError('generated full disk or device fault')
    monkeypatch.setattr('front_api.desktop.os.fsync', failed_sync)
    with pytest.raises(RuntimeError, match='data_directory_unwritable'):
        prepare_folder(tmp_path)
    assert not (tmp_path / '.front-write-check-generated-fsync-fault').exists()
    assert collision.read_bytes() == b'pre-existing generated original'


def test_source_startup_matrix_with_generated_media(tmp_path):
    env={k:v for k,v in os.environ.items() if not k.startswith('FRONT_')}
    env['PYTHONPATH']=os.pathsep.join(str(Path(p).resolve()) for p in sys.path if p)
    report=regression.run([getattr(sys,'_base_executable',sys.executable),'-m','front_api.desktop'],tmp_path/'new-matrix',env,frozen=False)
    assert not report['frozen'] and not report['clean_vm']
    assert report['cases']['old_schema_full_media_backup_and_isolated_restore']
    assert report['cases']['corrupt_database_refused_without_rewrite']
    assert report['cases']['future_schema_refused_without_rewrite']
    assert report['cases']['second_instance_refused_owner_alive']
