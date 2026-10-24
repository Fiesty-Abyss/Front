"""Read-only Windows process-tree telemetry. No page contents, command lines or credentials exported."""
from __future__ import annotations

import argparse
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import subprocess


def process_tree(pid: int):
    script = r'''
$all=Get-CimInstance Win32_Process
$ids=@(ROOTPID)
do {$new=@($all | Where-Object {$_.ParentProcessId -in $ids -and $_.ProcessId -notin $ids} | ForEach-Object ProcessId);$ids+=$new} while($new.Count)
@($all | Where-Object {$_.ProcessId -in $ids} | ForEach-Object {
 $role=if($_.Name -eq 'msedgewebview2.exe'){if($_.CommandLine -match '--type=([^ ]+)'){$matches[1]}else{'browser'}}elseif($_.Name -eq 'front-backend.exe'){'backend'}elseif($_.ProcessId -eq ROOTPID){'shell'}else{'helper'}
 [pscustomobject]@{pid=$_.ProcessId;parent=$_.ParentProcessId;name=$_.Name;role=$role}
}) | ConvertTo-Json -Compress
'''.replace('ROOTPID', str(int(pid)))
    raw = subprocess.check_output(['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', script], text=True, encoding='utf-8', timeout=20)
    rows = json.loads(raw or '[]')
    return rows if isinstance(rows, list) else [rows]


def working_set(pid: int):
    if os.name != 'nt':
        raise RuntimeError('Windows telemetry only')
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    psapi = ctypes.WinDLL('psapi', use_last_error=True)
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD]
    psapi.QueryWorkingSet.argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD]
    class Counters(ctypes.Structure):
        _fields_ = [('cb', wintypes.DWORD), ('PageFaultCount', wintypes.DWORD),
                    *[(name, ctypes.c_size_t) for name in ('PeakWorkingSetSize','WorkingSetSize','QuotaPeakPagedPoolUsage','QuotaPagedPoolUsage','QuotaPeakNonPagedPoolUsage','QuotaNonPagedPoolUsage','PagefileUsage','PeakPagefileUsage','PrivateUsage')]]
    handle = kernel.OpenProcess(0x0400 | 0x0010, False, int(pid))
    if not handle:
        return {'available': False, 'error': 'process_exited_or_access_denied'}
    try:
        counters = Counters(); counters.cb = ctypes.sizeof(counters)
        if not psapi.GetProcessMemoryInfo(handle, ctypes.byref(counters), counters.cb):
            return {'available': False, 'error': 'memory_query_failed'}
        # QueryWorkingSet reports only resident pages; it does not read their contents.
        count = max(4096, counters.WorkingSetSize // 4096 + 2048)
        pages = None
        for _ in range(3):
            buf = (ctypes.c_size_t * (count + 1))()
            if psapi.QueryWorkingSet(handle, buf, ctypes.sizeof(buf)):
                pages = list(buf[1:int(buf[0])+1]); break
            count = max(count*2, int(buf[0])+1024)
            if count > 4_000_000: break
        result = {'available': True, 'working_set': int(counters.WorkingSetSize), 'private_commit': int(counters.PrivateUsage)}
        if pages is None:
            result['resident_split_available'] = False
        else:
            # ShareCount is capped at 7 by Windows. This proportional estimate is NOT exact PSS.
            shareable = [p for p in pages if p & (1 << 8)]
            shared = [p for p in shareable if ((p >> 5) & 7) > 1]
            result.update(resident_split_available=True, private_resident=(len(pages)-len(shareable))*4096,
                          shareable_resident=len(shareable)*4096, currently_shared_resident=len(shared)*4096,
                          proportional_resident_estimate=round(sum(4096/max(1,(p >> 5)&7) if p & (1 << 8) else 4096 for p in pages)))
        return result
    finally:
        kernel.CloseHandle(handle)


def gpu_memory(pids):
    ids = ','.join(str(int(pid)) for pid in pids)
    script = r'''
$ids=@(PIDLIST)
try {
 $data=Get-Counter -Counter '\GPU Process Memory(*)\Dedicated Usage','\GPU Process Memory(*)\Shared Usage' -ErrorAction Stop
 $rows=@($data.CounterSamples | Where-Object {$_.InstanceName -match '^pid_(\d+)_' -and [int]$matches[1] -in $ids} | ForEach-Object {
  $_.InstanceName -match '^pid_(\d+)_' | Out-Null
  [pscustomobject]@{pid=[int]$matches[1];kind=if($_.Path -like '*\Dedicated Usage'){'dedicated'}else{'shared'};bytes=[long]$_.CookedValue}
 })
 [pscustomobject]@{available=$true;samples=$rows} | ConvertTo-Json -Compress -Depth 4
} catch {[pscustomobject]@{available=$false;error='gpu_counter_unavailable'} | ConvertTo-Json -Compress}
'''.replace('PIDLIST', ids)
    raw = subprocess.check_output(['powershell.exe','-NoProfile','-NonInteractive','-Command',script],text=True,encoding='utf-8',timeout=25)
    return json.loads(raw)


def snapshot(pid: int, include_gpu=True):
    rows = process_tree(pid)
    for row in rows: row.update(working_set(row['pid']))
    fields = ('working_set','private_commit','private_resident','shareable_resident','currently_shared_resident','proportional_resident_estimate')
    coverage = {name: {'measured': sum(name in row for row in rows), 'expected': len(rows)} for name in fields}
    totals = {name: sum(row[name] for row in rows) if rows and coverage[name]['measured'] == len(rows) else None for name in fields}
    return {'processes': rows, 'totals': totals, 'coverage': coverage, 'gpu': gpu_memory([r['pid'] for r in rows]) if include_gpu and rows else None,
            'notes': ['working_set sum double-counts shared pages', 'private_commit is not physical RAM',
                      'resident split sampled independently', 'proportional estimate overstates pages shared by more than 7 processes',
                      'GPU dedicated/shared counters are separate from CPU process accounting; do not add them to working sets']}


if __name__ == '__main__':
    parser=argparse.ArgumentParser();parser.add_argument('pid',type=int);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();result=snapshot(args.pid);args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps({'processes':len(result['processes']),'MiB':{k:round(v/1024**2,2) if v is not None else None for k,v in result['totals'].items()},'coverage':result['coverage'],'gpu':result['gpu']}))
