"""Retry only verified-origin Tauri bundler HTTP 502/503/504 failures.

Never changes a download URL, dependency, signature/hash check or release policy.
The caller's working directory must be desktop, just like the original CI step.
"""
from __future__ import annotations

import os
from pathlib import Path
import re
import subprocess
import sys
import time
from urllib.parse import urlsplit

MAX_TAIL = 64 * 1024
DELAYS = (5, 15)
ANSI = re.compile(r'\x1b\[[0-?]*[ -/]*[@-~]')


def build_command():
    if os.name == 'nt':
        # Fixed command only; no user-supplied shell interpolation or filesystem operation.
        return [str(Path(os.environ.get('SystemRoot', 'C:/Windows'))/'System32/cmd.exe'),
                '/d', '/c', 'npm run build -- --ci -- --locked']
    return ['npm', 'run', 'build', '--', '--ci', '--', '--locked']


def transient_bundle_failure(code, tail):
    if code == 0:
        return False
    text = ANSI.sub('', tail)
    if re.search(r'checksum.*(?:mismatch|fail|does not match)|hash.*(?:mismatch|fail|does not match)|invalid signature|signature verification.*fail|certificate|error\[E\d+\]|could not compile', text, re.I):
        return False
    failures = list(re.finditer(r'failed to bundle project:\s*`?http status:\s*(\d{3})`?', text))
    if not failures or failures[-1].group(1) not in ('502', '503', '504'):
        return False
    downloads = re.findall(r'Downloading\s+(https?://\S+)', text[:failures[-1].start()])
    if not downloads:
        return False
    try:
        url = urlsplit(downloads[-1])
        return (url.scheme == 'https' and url.hostname == 'github.com' and url.port in (None, 443)
                and not (url.username or url.password or url.query or url.fragment)
                and (url.path.startswith('/tauri-apps/binary-releases/releases/download/')
                     or url.path.startswith('/tauri-apps/nsis-tauri-utils/releases/download/')))
    except ValueError:
        return False


def invoke():
    tail = b''
    with subprocess.Popen(build_command(), stdout=subprocess.PIPE, stderr=subprocess.STDOUT) as proc:
        while True:
            chunk = proc.stdout.read1(8192)
            if not chunk:
                break
            sys.stdout.buffer.write(chunk)
            sys.stdout.buffer.flush()
            tail = (tail + chunk)[-MAX_TAIL:]
        code = proc.wait()
    return code, tail.decode('utf-8', errors='replace')


def build(runner=invoke, sleep=time.sleep):
    for attempt in range(1, len(DELAYS) + 2):
        code, tail = runner()
        if code == 0 or not transient_bundle_failure(code, tail) or attempt > len(DELAYS):
            return code
        delay = DELAYS[attempt-1]
        print(f'Tauri official tool download returned a transient gateway status; retry {attempt}/2 in {delay}s. All checks remain enabled.', flush=True)
        sleep(delay)
    raise AssertionError('unreachable')


if __name__ == '__main__':
    try:
        raise SystemExit(build())
    except OSError:
        print('Unable to start the existing build command; no retry.', file=sys.stderr)
        raise SystemExit(1)
