import importlib.util
import os
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location('front_profiling', Path(__file__).resolve().parents[2] / 'desktop' / 'profiling.py')
profiling = importlib.util.module_from_spec(spec)
spec.loader.exec_module(profiling)


def test_missing_process_measurement_is_unknown_not_zero(monkeypatch):
    monkeypatch.setattr(profiling, 'process_tree', lambda pid: [{'pid': pid}])
    monkeypatch.setattr(profiling, 'working_set', lambda pid: {'available': False})
    result = profiling.snapshot(100, include_gpu=False)
    assert all(value is None for value in result['totals'].values())
    assert result['coverage']['working_set'] == {'measured': 0, 'expected': 1}


def test_partial_resident_measurement_does_not_hide_valid_commit(monkeypatch):
    monkeypatch.setattr(profiling, 'process_tree', lambda pid: [{'pid': pid}])
    monkeypatch.setattr(profiling, 'working_set', lambda pid: {'available': True, 'working_set': 4096, 'private_commit': 8192})
    result = profiling.snapshot(100, include_gpu=False)
    assert result['totals']['private_commit'] == 8192
    assert result['totals']['private_resident'] is None


@pytest.mark.skipif(os.name != 'nt', reason='requires real Windows process memory API')
def test_windows_current_process_memory_is_measured():
    result = profiling.working_set(os.getpid())
    assert result['available'] and result['working_set'] > 0 and result['private_commit'] > 0
    assert result['resident_split_available']
    assert result['private_resident'] + result['shareable_resident'] > 0
