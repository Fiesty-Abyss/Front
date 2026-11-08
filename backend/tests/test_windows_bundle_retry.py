"""Generated Tauri log/runner tests; no binary downloads or installer execution."""
import importlib.util
from pathlib import Path

import pytest

spec=importlib.util.spec_from_file_location('front_bundle_retry',Path(__file__).parents[2]/'desktop/bundle_retry.py')
retry=importlib.util.module_from_spec(spec);spec.loader.exec_module(retry)
ZIP='https://github.com/tauri-apps/binary-releases/releases/download/nsis-3.13/nsis-3.13.zip'
DLL='https://github.com/tauri-apps/nsis-tauri-utils/releases/download/nsis_tauri_utils-v0.5.3/nsis_tauri_utils.dll'


def failed(url=ZIP,status=504):
    return f'Info Verifying NSIS package\nDownloading {url}\nfailed to bundle project: `http status: {status}`\nError failed to bundle project: `http status: {status}`\n'


@pytest.mark.parametrize('url',[ZIP,DLL])
@pytest.mark.parametrize('status',[502,503,504])
def test_only_official_gateway_download_failures_retry(url,status):
    assert retry.transient_bundle_failure(1,failed(url,status))
    assert not retry.transient_bundle_failure(0,failed(url,status))
    assert retry.transient_bundle_failure(1,'\x1b[31m'+failed(url,status)+'\x1b[0m')


@pytest.mark.parametrize('tail',[
    failed(status=401),failed(status=404),failed(status=429),failed(status=500),
    failed('https://example.invalid/nsis.zip'),failed('https://github.com/other/repo/releases/download/tag/tool.zip'),
    failed('http://github.com/tauri-apps/binary-releases/releases/download/nsis/tool.zip'),
    failed('https://token@github.com/tauri-apps/binary-releases/releases/download/nsis/tool.zip'),
    failed(ZIP+'?unverified=1'),failed()+'checksum mismatch',failed()+'invalid signature',
    failed()+'signature verification failed',failed()+'certificate verification failed',
    failed()+'error[E0425]: not found',failed()+'could not compile front-desktop',
    'failed to bundle project: `http status: 504`',
    failed()+'Downloading https://other.invalid/tool\nfailed to bundle project: `http status: 504`',
])
def test_compiler_integrity_identity_and_other_http_errors_never_retry(tail):
    assert not retry.transient_bundle_failure(1,tail)


def test_success_after_transient_uses_same_runner_and_finite_backoff():
    results=iter([(1,failed()),(1,failed(DLL,503)),(0,'build complete')]);calls=[];delays=[]
    def run():calls.append(True);return next(results)
    assert retry.build(run,delays.append)==0 and len(calls)==3 and delays==[5,15]


def test_persistent_failure_remains_failure_and_never_retries_forever():
    calls=[];delays=[]
    def run():calls.append(True);return 7,failed()
    assert retry.build(run,delays.append)==7 and len(calls)==3 and delays==[5,15]
    calls.clear();delays.clear()
    def bad():calls.append(True);return 2,'compile failed'
    assert retry.build(bad,delays.append)==2 and len(calls)==1 and not delays


def test_command_keeps_existing_locked_build_and_workflow_integrity_steps():
    command=retry.build_command()
    assert '--ci -- --locked' in ' '.join(command)
    workflow=(Path(__file__).parents[2]/'.github/workflows/windows-preview.yml').read_text(encoding='utf-8')
    assert 'run: python bundle_retry.py' in workflow
    assert 'working-directory: desktop' in workflow
    assert 'run: python desktop/artifact_integrity.py .cache/desktop-stage/artifacts' in workflow
    assert 'continue-on-error' not in workflow


def test_real_owned_command_output_is_streamed_with_bounded_tail(monkeypatch,capsys):
    import sys
    script="import sys;print('x'*200000);print("+repr(failed())+");sys.exit(3)"
    monkeypatch.setattr(retry,'build_command',lambda:[sys.executable,'-c',script])
    code,tail=retry.invoke()
    assert code==3 and len(tail.encode())<=retry.MAX_TAIL
    assert retry.transient_bundle_failure(code,tail)
    assert len(capsys.readouterr().out)>200000
