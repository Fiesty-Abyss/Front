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


def test_gpu_identity_accepts_only_cim_microsecond_precision_difference(monkeypatch):
    calls = iter([[row(10, 1, 109)], [row(10, 1, 100)]])
    monkeypatch.setattr(profiling, 'process_tree', lambda pid: next(calls))
    monkeypatch.setattr(profiling, 'working_set', lambda *args: {'available': True, 'working_set': 100})
    monkeypatch.setattr(profiling, 'gpu_memory', lambda pids: {'available': True, 'samples': []})
    assert profiling.snapshot(10)['gpu'] == {'available': True, 'samples': []}


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


def test_cim_failure_uses_only_identity_verified_fallback(monkeypatch):
    import subprocess
    monkeypatch.setattr(profiling.subprocess, 'check_output', lambda *a, **k: (_ for _ in ()).throw(subprocess.TimeoutExpired('generated', 20)))
    monkeypatch.setattr(profiling, '_toolhelp_process_rows', lambda pid: [row(pid, 1, 100), row(11, pid, 99), row(12, pid, 101)])
    assert [r['pid'] for r in profiling.process_tree(10)] == [10, 12]


def test_valid_cim_keeps_detailed_roles_without_querying_native_fallback(monkeypatch):
    import json
    value = dict(row(10, 1, 100), role='gpu-process')
    monkeypatch.setattr(profiling.subprocess, 'check_output', lambda *a, **k: json.dumps(value))
    def unexpected(pid):
        raise AssertionError('a valid CIM inventory must not be replaced')
    monkeypatch.setattr(profiling, '_toolhelp_process_rows', unexpected)
    result = profiling.process_tree(10)
    assert result[0]['role'] == 'gpu-process' and result[0]['inventory_method'] == 'cim'


def test_native_stamping_marks_snapshot_race_unknown_and_ignores_unrelated_pids():
    entries = [row(10, 1, None), row(11, 10, None), row(12, 10, None), row(90, 1, None)]
    births = {10: 100, 11: 501, 12: 101}; requested = []
    def birth(pid):
        requested.append(pid); return births[pid]
    stamped = profiling._stamp_toolhelp(10, entries, 500, birth)
    assert requested == [10, 11, 12]
    result = profiling.verified_tree(10, stamped)
    assert [r['pid'] for r in result] == [10, 12]
    assert result[0]['unverified_children'] == 1
    assert not profiling._stamp_toolhelp(999, entries, 500, birth)


def test_native_webview_role_and_access_denial_are_not_fabricated():
    rows = [row(10, 1, None), dict(row(11, 10, None), name='msedgewebview2.exe'), row(12, 10, None)]
    result = profiling._stamp_toolhelp(10, rows, 500, lambda pid: {10: 100, 11: 110, 12: None}[pid])
    assert result[1]['role'] == 'webview2_unknown' and not result[1]['role_detail_available']
    assert result[2]['created_filetime'] is None
    assert all('CommandLine' not in r and 'path' not in r for r in result)


@pytest.mark.skipif(os.name != 'nt', reason='requires real Windows Toolhelp API')
def test_real_toolhelp_current_process_and_owned_child_without_cim(monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    import subprocess
    import sys
    # The base interpreter avoids a venv launcher creating an extra grandchild.
    child = subprocess.Popen([sys._base_executable, '-c', 'import time; print("ready", flush=True); time.sleep(15)'],
                             stdout=subprocess.PIPE, creationflags=subprocess.CREATE_NO_WINDOW)
    readiness = ThreadPoolExecutor(max_workers=1)
    try:
        # Wait for this exact child to execute, not an arbitrary timing sleep.
        assert readiness.submit(child.stdout.readline).result(timeout=5) == b'ready\r\n'
        monkeypatch.setattr(profiling.subprocess, 'check_output', lambda *a, **k: (_ for _ in ()).throw(OSError('generated CIM unavailable')))
        rows = profiling.process_tree(os.getpid())
        assert rows and rows[0]['pid'] == os.getpid()
        observed = {r['pid']: r for r in rows}
        assert child.pid in observed and observed[child.pid]['parent'] == os.getpid(), {'rows': rows, 'child': child.pid, 'returncode': child.poll()}
        assert all(r['inventory_method'] == 'toolhelp' for r in rows)
        birth = observed[child.pid]['created_filetime']
        assert profiling.working_set(child.pid, birth)['available']
        assert profiling.working_set(child.pid, birth+10_000_000)['error'] == 'process_identity_changed'
    finally:
        child.terminate(); child.wait(timeout=5)
        child.stdout.close(); readiness.shutdown(wait=True)
