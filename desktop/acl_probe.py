"""Child used by validate_windows_acl.ps1; generated denied folder only."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('denied_folder', type=Path)
    parser.add_argument('--sidecar', type=Path)
    parser.add_argument('--worker-source', action='store_true', help=argparse.SUPPRESS)
    args = parser.parse_args()
    if not (args.denied_folder.parent / '.front-generated-acl-test').is_file():
        raise ValueError('refuse_unmarked_acl_test')
    if args.worker_source:
        from front_api.desktop import prepare_folder
        try:
            prepare_folder(args.denied_folder)
        except RuntimeError as exc:
            assert str(exc) == 'data_directory_unwritable'
            print(json.dumps({'error': str(exc)}), flush=True)
        else:
            raise AssertionError('write_protection_not_enforced')
        return
    env = {k: v for k, v in os.environ.items() if not k.startswith('FRONT_')}
    if args.sidecar:
        command = [str(args.sidecar.resolve()), '--data-dir', str(args.denied_folder)]
        env.pop('PYTHONPATH', None); env.pop('PYTHONHOME', None)
        env['PATH'] = str(Path(os.environ['SystemRoot']) / 'System32')
    else:
        env['PYTHONPATH'] = os.pathsep.join(str(Path(p).resolve()) for p in sys.path if p)
        command = [getattr(sys, '_base_executable', sys.executable), str(Path(__file__).resolve()), str(args.denied_folder), '--worker-source']
    started = time.perf_counter()
    # Exact child process owned here, bounded even if the permission regression recurs.
    result = subprocess.run(command, env=env, capture_output=True, text=True, timeout=15,
        creationflags=0x08000000 if os.name == 'nt' else 0)
    assert json.loads(result.stdout.strip()) == {'error': 'data_directory_unwritable'}
    assert result.returncode == (1 if args.sidecar else 0)
    assert not (args.denied_folder / 'front.db').exists()
    print(json.dumps({'real_acl_denial_detected': True, 'frozen': bool(args.sidecar),
        'process_seconds': round(time.perf_counter() - started, 3), 'clean_vm': False}), flush=True)


if __name__ == '__main__':
    main()
