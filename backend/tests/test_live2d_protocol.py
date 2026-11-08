"""No SDK, source model, GPU or service: generated protocol + actual owned CLI child."""
import json
import os
from pathlib import Path
import subprocess
import sys
import uuid

import pytest

from front_api.live2d_protocol import MAX_LINE, PreviewSession, NullRenderer


def raw(op,payload=None,id=None,**changes):
    return json.dumps({'version':1,'id':id or uuid.uuid4().hex,'op':op,'payload':payload or {}}|changes).encode()+b'\n'


def manifest(**changes):
    return {'identity':'a'*64,'kind':'generated-protocol-only','parameters':{'GeneratedMouth':{'min':-1,'max':3,'default':0}},'mouth_parameter':'GeneratedMouth','motions':['Generated wave'],'expressions':['Generated smile']}|changes


def start():
    renderer=NullRenderer();session=PreviewSession(renderer)
    assert session.receive(raw('hello'))['ok']
    result=session.receive(raw('load',{'catalog':manifest()}));assert result['ok'],result
    return session,renderer


def test_no_default_engine_handshake_or_real_model_loading():
    session=PreviewSession()
    assert session.status()['graphics_contexts']==session.status()['frames']==0
    assert not session.receive(raw('load',{'catalog':manifest()}))['ok']
    session.receive(raw('hello'))
    for kind in ('cubism3','neocari','actual-model'):
        result=session.receive(raw('load',{'catalog':manifest(kind=kind)}));assert not result['ok']
    assert session.status()['model_identity'] is None and not session.status()['runtime_verified']
    assert not session.receive(raw('load',{'path':'/never-read/model.model3.json'}))['ok']


def test_load_controls_declared_actions_and_mouth_mapping():
    session,renderer=start()
    assert session.receive(raw('update',{'generation':1,'values':{'fps':15,'scale':1.3,'x':.5,'transparent':True,'parameters':{'GeneratedMouth':2}}}))['ok']
    result=session.receive(raw('motion',{'generation':1,'name':'Generated wave'}));assert result['ok']
    result=session.receive(raw('expression',{'generation':1,'name':'Generated smile'}));assert result['result']['state']['expressions']==['Generated smile']
    result=session.receive(raw('expression',{'generation':1,'name':'Generated smile'}));assert result['result']['state']['expressions']==[]
    result=session.receive(raw('mouth',{'generation':1,'amplitude':.5}));assert result['result']['state']['parameters']['GeneratedMouth']==1
    assert renderer.loads==1 and renderer.actions==3
    assert session.receive(raw('update',{'generation':1,'values':{'visible':False}}))['ok']
    result=session.receive(raw('unload',{'generation':1}));assert result['ok'] and result['result']['model_identity'] is None
    session.dispose();assert renderer.releases==renderer.loads==1


@pytest.mark.parametrize('values',[{'fps':120},{'fps':True},{'x':float('nan')},{'scale':0},{'parameters':{'ParamMouthOpenY':1}},{'parameters':{'GeneratedMouth':4}},{'transparent':1},{'background_url':'https://never-fetch.invalid'}])
def test_controls_are_atomic_and_bounded(values):
    session,renderer=start();before=session.status()
    result=session.receive(raw('update',{'generation':1,'values':values}));assert not result['ok']
    assert session.status()==before
    session.dispose();assert renderer.loads==renderer.releases


def test_generation_guards_invalid_load_preserves_current_and_no_assumed_parameters():
    session,renderer=start()
    result=session.receive(raw('load',{'catalog':manifest(parameters={'unknown':{'min':2,'max':1,'default':0}})}));assert not result['ok']
    assert renderer.loads==1 and renderer.releases==0 and session.generation==1
    session.receive(raw('load',{'catalog':manifest(identity='b'*64,mouth_parameter=None)}))
    assert not session.receive(raw('update',{'generation':1,'values':{'x':1}}))['ok']
    assert not session.receive(raw('motion',{'generation':2,'name':'not provided'}))['ok']
    assert not session.receive(raw('mouth',{'generation':2,'amplitude':.5}))['ok']
    session.dispose();assert renderer.loads==renderer.releases==2


def test_recent_idempotency_does_not_replay_motion_and_conflicts_are_explicit():
    session,renderer=start();identity=uuid.uuid4().hex
    command=raw('motion',{'generation':1,'name':'Generated wave'},id=identity)
    first=session.receive(command);assert session.receive(command)==first and renderer.actions==1
    assert not session.receive(raw('expression',{'generation':1,'name':'Generated smile'},id=identity))['ok']
    for _ in range(200):assert session.receive(raw('status'))['ok']
    assert len(session.receipts)==128
    session.dispose()


@pytest.mark.parametrize('command',[b'not json',b'\xff',b'[]',b'{"version":1}',b' '* (MAX_LINE+1)])
def test_malformed_protocol_and_budgets_fail_without_mutation(command):
    session,renderer=start();before=session.status()
    assert not session.receive(command)['ok'] and session.status()==before
    session.dispose()


def test_failed_adapter_is_closed_and_exception_is_not_echoed():
    class Failed(NullRenderer):
        def load(self,manifest):
            self.loaded=True;self.loads+=1
            raise RuntimeError('private-runtime-path-and-token')
    adapter=Failed();session=PreviewSession(adapter);session.receive(raw('hello'))
    result=session.receive(raw('load',{'catalog':manifest()}))
    assert not result['ok'] and 'private-runtime' not in json.dumps(result)
    assert session.closed and adapter.loads==adapter.releases==1


def test_repeated_switches_release_old_instances_and_shutdown_is_idempotent():
    session,renderer=start()
    for _ in range(100):assert session.receive(raw('load',{'catalog':manifest()}))['ok']
    command=raw('shutdown');first=session.receive(command);assert first['ok'] and session.receive(command)==first
    session.dispose();assert renderer.loads==renderer.releases==101
    assert not session.receive(raw('load',{'catalog':manifest()}))['ok']


def test_actual_null_cli_child_handshake_commands_eof_and_oversize():
    env=os.environ.copy();env['PYTHONPATH']=str(Path(__file__).parents[1])
    command=[sys.executable,'-m','front_api.live2d_protocol','--null-preview']
    flags={'creationflags':subprocess.CREATE_NO_WINDOW} if os.name=='nt' else {}
    data=raw('hello')+raw('load',{'catalog':manifest()})+raw('motion',{'generation':1,'name':'Generated wave'})+raw('shutdown')
    result=subprocess.run(command,input=data,capture_output=True,timeout=10,env=env,**flags)
    assert result.returncode==0 and result.stderr==b''
    replies=[json.loads(line) for line in result.stdout.splitlines()]
    assert len(replies)==4 and all(x['ok'] for x in replies) and replies[-1]['result']['closed']
    assert all(x['result']['renders'] is False and x['result']['graphics_contexts']==0 for x in replies)
    # EOF closes an owned child without a daemon, network service, model or task.
    eof=subprocess.run(command,input=raw('hello')+raw('load',{'catalog':manifest()}),capture_output=True,timeout=10,env=env,**flags)
    assert eof.returncode==0 and len(eof.stdout.splitlines())==2
    unicode_catalog=manifest(parameters={'生成🌟':{'min':0,'max':1,'default':.5}},mouth_parameter=None)
    unicode_child=subprocess.run(command,input=raw('hello')+raw('load',{'catalog':unicode_catalog}),capture_output=True,timeout=10,env=env,**flags)
    assert unicode_child.returncode==0 and '生成🌟' in unicode_child.stdout.decode('utf-8')
    assert b'\r\n' not in unicode_child.stdout
    oversized=subprocess.run(command,input=b'x'*(MAX_LINE+2),capture_output=True,timeout=10,env=env,**flags)
    assert oversized.returncode==0 and len(oversized.stdout.splitlines())==1 and not json.loads(oversized.stdout)['ok']


def test_duplicate_json_keys_versions_and_unknown_operations_are_rejected():
    session,renderer=start();before=session.status()
    duplicate=b'{"version":1,"version":2,"id":"'+b'a'*32+b'","op":"shutdown","payload":{}}'
    assert not session.receive(duplicate)['ok']
    assert not session.receive(raw('status',version=2))['ok']
    assert not session.receive(raw('status',version=True))['ok']
    assert not session.receive(raw('execute-file',{'path':'never-read.exe'}))['ok']
    assert session.status()==before
    session.dispose()
