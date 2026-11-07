"""Run the real generated matrix at a small scale, including child-process crash.

Latency has no brittle CI threshold. This checks dataset isolation and invariants,
not real inference, device memory, an installer or a clean Windows system.
"""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys


def test_generated_mixed_probe_and_existing_output_refusal(tmp_path):
    project = Path(__file__).resolve().parents[2]
    output = tmp_path / 'generated-matrix'
    env = {k: v for k, v in os.environ.items() if not k.startswith('FRONT_')}
    env['PYTHONPATH'] = str(project / 'backend')
    command = [sys.executable, str(project / 'desktop/benchmark_mixed.py'), str(output), '--smoke']
    result = subprocess.run(command, env=env, cwd=project, capture_output=True, text=True, timeout=90)
    assert result.returncode == 0, result.stderr
    report_path = output / 'report.json'
    report = json.loads(report_path.read_text(encoding='utf-8'))
    assert [s['positive_hierarchical_tags']['total'] for s in report['scales']] == [16, 83, 166]
    assert report['generated']['characters'] == 20 and report['generated']['relations'] == 32
    assert report['generated']['png_uploads'] == 2 and report['generated']['wav_uploads'] == 4
    assert report['queue']['peak_active_workers'] == 2
    assert report['queue']['statuses'] == {'done': 32, 'cancelled': 2, 'error': 0}
    assert report['queue']['actual_process_crash_recovered'] == 8
    assert 'browser Heap and FPS' in report['unverified']
    before = hashlib.sha256(report_path.read_bytes()).hexdigest()
    result = subprocess.run(command, env=env, cwd=project, capture_output=True, text=True, timeout=20)
    assert result.returncode != 0  # cannot overwrite test or real existing libraries
    assert hashlib.sha256(report_path.read_bytes()).hexdigest() == before
