"""Read-only Windows process-tree telemetry. No page contents, command lines or credentials exported."""
from __future__ import annotations

import argparse
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import subprocess


def verified_tree(pid: int, rows: list[dict]):
    """A parent PID alone is not ownership: Windows reuses IDs after exit."""
    grouped={}
    children={}
    for row in rows:
        if not isinstance(row,dict):continue
        key=row.get('pid');parent=row.get('parent')
        if type(key) is not int or key<=0 or type(parent) is not int:continue
        grouped.setdefault(key,[]).append(row)
        children.setdefault(parent,[]).append(row)
    roots=grouped.get(pid,[])
    def born(row):
        value=row.get('created_filetime')
        return value if type(value) is int and value>0 else None
    if len(roots)!=1 or born(roots[0]) is None:return []
    result=[];pending=[roots[0]];seen={pid}
    while pending:
        row=pending.pop(0);item=dict(row)
        item['unverified_children']=0;item['pid_reuse_exclusions']=0
        unknown=set()
        for child in sorted(children.get(row['pid'],[]),key=lambda r:r['pid']):
            key=child['pid']
            if key in seen:continue
            created=born(child)
            if len(grouped[key])!=1 or created is None:
                unknown.add(key);continue
            if created<born(row):
                item['pid_reuse_exclusions']+=1;continue
            seen.add(key);pending.append(child)
        item['unverified_children']=len(unknown)
        result.append(item)
    return result


def process_tree(pid: int):
    script = r'''
[Console]::OutputEncoding=[System.Text.UTF8Encoding]::new($false)
$ErrorActionPreference='Stop'
@(Get-CimInstance Win32_Process | ForEach-Object {
 $role=if($_.Name -eq 'msedgewebview2.exe'){if($_.CommandLine -match '--type=([^ ]+)'){$matches[1]}else{'browser'}}elseif($_.Name -eq 'front-backend.exe'){'backend'}elseif($_.ProcessId -eq ROOTPID){'shell'}else{'helper'}
 [pscustomobject]@{pid=[int]$_.ProcessId;parent=[int]$_.ParentProcessId;name=$_.Name;role=$role;created_filetime=if($_.CreationDate){$_.CreationDate.ToUniversalTime().ToFileTimeUtc()}else{$null}}
}) | ConvertTo-Json -Compress
'''.replace('ROOTPID', str(int(pid)))
    try:
        raw = subprocess.check_output(['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', script], text=True, encoding='utf-8', timeout=20,stderr=subprocess.DEVNULL)
        rows = json.loads(raw or '[]')
        if isinstance(rows,dict):rows=[rows]
        result = verified_tree(pid,rows) if isinstance(rows,list) else []
        if result:
            return [dict(row, inventory_method='cim') for row in result]
    except (subprocess.SubprocessError,OSError,ValueError):
        pass
    try:
        return verified_tree(pid, _toolhelp_process_rows(pid))
    except OSError:
        return []  # Unknown, never a fabricated zero-memory process tree.


def _stamp_toolhelp(root, entries, snapshot_time, birth):
    """Open handles only for the requested candidate tree, not every system PID.

    A PID born after snapshot creation could refer to a replacement process;
    its old parent edge must not be trusted, even if its handle is readable.
    """
    rows = [r for r in entries if isinstance(r, dict) and type(r.get('pid')) is int
            and r['pid'] > 0 and type(r.get('parent')) is int]
    if sum(r['pid'] == root for r in rows) != 1:
        return []
    children = {}
    for row in rows:
        children.setdefault(row['parent'], []).append(row['pid'])
    pending = [root]; wanted = set()
    while pending:
        pid = pending.pop()
        if pid in wanted:
            continue
        wanted.add(pid); pending.extend(children.get(pid, []))
    result = []
    for row in rows:
        if row['pid'] not in wanted:
            continue
        created = birth(row['pid'])
        if type(created) is not int or created <= 0 or created > snapshot_time:
            created = None
        name = str(row.get('name', ''))
        role = ('shell' if row['pid'] == root else 'backend' if name.lower() == 'front-backend.exe'
                else 'webview2_unknown' if name.lower() == 'msedgewebview2.exe' else 'helper')
        result.append({'pid': row['pid'], 'parent': row['parent'], 'name': name,
                       'role': role, 'created_filetime': created, 'inventory_method': 'toolhelp',
                       'role_detail_available': role != 'webview2_unknown'})
    return result


def _toolhelp_process_rows(root):
    """Toolhelp metadata + limited-query creation time; no process memory reads.

    No WMI repair, elevated access, command-line scraping or process control.
    Detailed WebView2 subroles require CIM and remain explicitly unknown here.
    """
    if os.name != 'nt':
        return []
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)

    class ProcessEntry(ctypes.Structure):
        _fields_ = [('dwSize', wintypes.DWORD), ('cntUsage', wintypes.DWORD),
                    ('th32ProcessID', wintypes.DWORD), ('th32DefaultHeapID', ctypes.c_size_t),
                    ('th32ModuleID', wintypes.DWORD), ('cntThreads', wintypes.DWORD),
                    ('th32ParentProcessID', wintypes.DWORD), ('pcPriClassBase', wintypes.LONG),
                    ('dwFlags', wintypes.DWORD), ('szExeFile', wintypes.WCHAR * 260)]

    kernel.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
    kernel.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    for name in ('Process32FirstW', 'Process32NextW'):
        fn = getattr(kernel, name)
        fn.argtypes = [wintypes.HANDLE, ctypes.POINTER(ProcessEntry)]
        fn.restype = wintypes.BOOL
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.CloseHandle.restype = wintypes.BOOL
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    # Use precise UTC for a strict comparison with process creation FILETIME.
    # A tick-rounded wall clock can predate a just-created, already-live child.
    kernel.GetSystemTimePreciseAsFileTime.argtypes = [ctypes.POINTER(wintypes.FILETIME)]
    kernel.GetSystemTimePreciseAsFileTime.restype = None
    kernel.GetProcessTimes.argtypes = [wintypes.HANDLE, *([ctypes.POINTER(wintypes.FILETIME)] * 4)]
    kernel.GetProcessTimes.restype = wintypes.BOOL
    before = wintypes.FILETIME()
    kernel.GetSystemTimePreciseAsFileTime(ctypes.byref(before))
    snapshot_time = (before.dwHighDateTime << 32) | before.dwLowDateTime
    snapshot = kernel.CreateToolhelp32Snapshot(0x00000002, 0)  # TH32CS_SNAPPROCESS only
    if not snapshot or snapshot == ctypes.c_void_p(-1).value:
        return []
    entries = []
    try:
        entry = ProcessEntry(); entry.dwSize = ctypes.sizeof(entry)
        if not kernel.Process32FirstW(snapshot, ctypes.byref(entry)):
            return []
        while True:
            entries.append({'pid': int(entry.th32ProcessID), 'parent': int(entry.th32ParentProcessID),
                            'name': entry.szExeFile})
            if len(entries) >= 100_000:
                return []
            if not kernel.Process32NextW(snapshot, ctypes.byref(entry)):
                if ctypes.get_last_error() != 18:  # ERROR_NO_MORE_FILES
                    return []  # Partial inventory cannot support complete totals.
                break
    finally:
        kernel.CloseHandle(snapshot)

    def birth(pid):
        handle = kernel.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not handle:
            return None
        try:
            created, exited, kernel_time, user_time = (wintypes.FILETIME() for _ in range(4))
            if not kernel.GetProcessTimes(handle, ctypes.byref(created), ctypes.byref(exited),
                                          ctypes.byref(kernel_time), ctypes.byref(user_time)):
                return None
            return (created.dwHighDateTime << 32) | created.dwLowDateTime
        finally:
            kernel.CloseHandle(handle)

    return _stamp_toolhelp(root, entries, snapshot_time, birth)


def working_set(pid: int, expected_created: int | None = None):
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
        if expected_created is not None:
            created,exited,kernel_time,user_time=(wintypes.FILETIME() for _ in range(4))
            kernel.GetProcessTimes.argtypes=[wintypes.HANDLE,*([ctypes.POINTER(wintypes.FILETIME)]*4)]
            kernel.GetProcessTimes.restype=wintypes.BOOL
            if not kernel.GetProcessTimes(handle,ctypes.byref(created),ctypes.byref(exited),ctypes.byref(kernel_time),ctypes.byref(user_time)):
                return {'available':False,'error':'process_identity_unavailable'}
            actual=(created.dwHighDateTime<<32)|created.dwLowDateTime
            # CIM CreationDate has microsecond precision, FILETIME has 100ns.
            if abs(actual-expected_created)>10:
                return {'available':False,'error':'process_identity_changed'}
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
    for row in rows:
        row.update(working_set(row['pid'],row['created_filetime']) if 'created_filetime' in row else working_set(row['pid']))
    fields = ('working_set','private_commit','private_resident','shareable_resident','currently_shared_resident','proportional_resident_estimate')
    coverage = {name: {'measured': sum(name in row for row in rows), 'expected': len(rows)} for name in fields}
    totals = {name: sum(row[name] for row in rows) if rows and coverage[name]['measured'] == len(rows) else None for name in fields}
    uncertain=sum(r.get('unverified_children',0) for r in rows)
    if uncertain:totals={name:None for name in fields}
    gpu=None
    if include_gpu and rows:
        gpu=gpu_memory([r['pid'] for r in rows]) if all(r.get('available') for r in rows) else {'available':False,'error':'process_measurement_unavailable'}
        after={r['pid']:r.get('created_filetime') for r in process_tree(pid)}
        if any(type(r.get('created_filetime')) is not int or type(after.get(r['pid'])) is not int
               or abs(after[r['pid']]-r['created_filetime'])>10 for r in rows):
            gpu={'available':False,'error':'process_identity_changed_during_gpu_sample'}
    lineage={'root_observed':bool(rows),'creation_time_verified':bool(rows) and all('created_filetime' in r for r in rows),
        'unverified_children':uncertain,'pid_reuse_exclusions':sum(r.get('pid_reuse_exclusions',0) for r in rows)}
    return {'processes': rows, 'totals': totals, 'coverage': coverage, 'gpu':gpu,'lineage':lineage,
            'notes': ['only creation-time-verified parent edges are included; missing lineage means unknown totals', 'working_set sum double-counts shared pages', 'private_commit is not physical RAM',
                      'resident split sampled independently', 'proportional estimate overstates pages shared by more than 7 processes',
                      'GPU dedicated/shared counters are separate from CPU process accounting; do not add them to working sets']}


if __name__ == '__main__':
    parser=argparse.ArgumentParser();parser.add_argument('pid',type=int);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();result=snapshot(args.pid);args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps({'processes':len(result['processes']),'MiB':{k:round(v/1024**2,2) if v is not None else None for k,v in result['totals'].items()},'coverage':result['coverage'],'gpu':result['gpu']}))
