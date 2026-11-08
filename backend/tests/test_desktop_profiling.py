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


def row(pid,parent,born):
    return {'pid':pid,'parent':parent,'name':'generated.exe','role':'helper','created_filetime':born}


def test_reused_parent_pid_excludes_older_child_and_its_later_descendants():
    rows=[row(10,1,200),row(11,10,100),row(12,11,300),row(13,10,201),row(14,13,202)]
    result=profiling.verified_tree(10,rows)
    assert [r['pid'] for r in result]==[10,13,14]
    assert result[0]['pid_reuse_exclusions']==1


def test_missing_or_ambiguous_root_never_adopts_orphans():
    assert profiling.verified_tree(10,[row(11,10,200)])==[]
    assert profiling.verified_tree(10,[row(10,1,None),row(11,10,200)])==[]
    assert profiling.verified_tree(10,[row(10,1,100),row(10,1,200)])==[]


def test_unknown_or_duplicate_child_identity_marks_lineage_incomplete(monkeypatch):
    rows=[row(10,1,100),row(11,10,None),row(12,10,200),row(12,10,300),row(13,10,100)]
    result=profiling.verified_tree(10,rows)
    assert [r['pid'] for r in result]==[10,13]
    assert result[0]['unverified_children']==2
    monkeypatch.setattr(profiling,'process_tree',lambda pid:result)
    monkeypatch.setattr(profiling,'working_set',lambda *args:{'available':True,'working_set':100,'private_commit':200})
    snapshot=profiling.snapshot(10,include_gpu=False)
    assert snapshot['lineage']['unverified_children']==2
    assert all(v is None for v in snapshot['totals'].values())


def test_gpu_identity_change_is_unknown_not_another_process_counter(monkeypatch):
    calls=iter([[row(10,1,100)],[row(10,1,200)]])
    monkeypatch.setattr(profiling,'process_tree',lambda pid:next(calls))
    monkeypatch.setattr(profiling,'working_set',lambda *args:{'available':True,'working_set':100})
    monkeypatch.setattr(profiling,'gpu_memory',lambda pids:{'available':True,'samples':[{'pid':10,'bytes':999}]})
    snapshot=profiling.snapshot(10)
    assert snapshot['totals']['working_set']==100
    assert snapshot['gpu']=={'available':False,'error':'process_identity_changed_during_gpu_sample'}


def test_failed_inventory_is_unknown(monkeypatch):
    import subprocess
    def failed(*args,**kwargs):raise subprocess.TimeoutExpired('generated',20)
    monkeypatch.setattr(profiling.subprocess,'check_output',failed)
    result=profiling.snapshot(10)
    assert result['processes']==[] and all(v is None for v in result['totals'].values())
    assert result['gpu'] is None and not result['lineage']['root_observed']


@pytest.mark.skipif(os.name!='nt',reason='requires real Windows creation time and process handle')
def test_windows_process_handle_matches_inventory_and_rejects_wrong_birth():
    rows=profiling.process_tree(os.getpid())
    assert rows and rows[0]['pid']==os.getpid()
    birth=rows[0]['created_filetime']
    measured=profiling.working_set(os.getpid(),birth)
    assert measured['available'] and measured['working_set']>0
    assert profiling.working_set(os.getpid(),birth+10_000_000)=={'available':False,'error':'process_identity_changed'}
