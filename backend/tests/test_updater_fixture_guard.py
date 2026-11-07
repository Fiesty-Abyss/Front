"""No signer or private keys are used by these negative boundary checks."""
import importlib.util
from pathlib import Path
import pytest

spec = importlib.util.spec_from_file_location('front_updater_fixture', Path(__file__).resolve().parents[2] / 'desktop/test_updater.py')
fixture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixture)


def test_signing_fixture_refuses_external_directory_before_creating_files(tmp_path):
    outside = tmp_path / 'private-signing-output-must-not-exist'
    with pytest.raises(ValueError, match='inside checkout cache'):
        fixture.run(outside, transport_only=True)
    assert not outside.exists()


def test_signing_fixture_never_reuses_existing_cache_even_if_marked(tmp_path, monkeypatch):
    project = tmp_path / 'generated-checkout'
    monkeypatch.setattr(fixture, '__file__', str(project / 'desktop/test_updater.py'))
    existing = project / '.cache/existing'; existing.mkdir(parents=True)
    sentinel = existing / '.front-generated-updater-test'; sentinel.write_bytes(b'existing material')
    with pytest.raises(FileExistsError):
        fixture.run(existing, transport_only=True)
    assert list(existing.iterdir()) == [sentinel]
    assert sentinel.read_bytes() == b'existing material'
