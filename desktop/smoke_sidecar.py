"""Run a frozen sidecar with isolated generated data. No Python needed by the executable."""
import argparse
import json
from pathlib import Path
import subprocess
import time
import httpx

parser=argparse.ArgumentParser();parser.add_argument('binary');parser.add_argument('data');args=parser.parse_args()
data=Path(args.data).resolve();data.mkdir(parents=True,exist_ok=True)
process=subprocess.Popen([args.binary,'--data-dir',str(data)],stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True)
start=time.perf_counter()
try:
    ready=json.loads(process.stdout.readline())
    assert ready['pid']==process.pid and ready['port']>0
    url=f'http://127.0.0.1:{ready["port"]}'
    with httpx.Client(base_url=url,timeout=10) as client:
        assert client.get('/api/worlds').status_code==401
        assert client.get('/').status_code==401
        assert client.get('/_desktop/bootstrap').status_code==200
        assert client.post('/_desktop/session',headers={'Authorization':'Bearer wrong'}).status_code==401
        assert client.post('/_desktop/session',headers={'Authorization':'Bearer '+ready['token'],'Origin':'https://invalid.test'}).status_code==403
        response=client.post('/_desktop/session',headers={'Authorization':'Bearer '+ready['token']})
        assert response.status_code==200 and 'HttpOnly' in response.headers['set-cookie']
        assert client.get('/').status_code==200
        assert client.post('/api/worlds',json={'name':'Generated desktop smoke world'}).status_code==201
        assert client.get('/api/worlds').json()['total']==1
        assert client.post('/_desktop/shutdown').status_code==403
        assert client.post('/_desktop/shutdown',headers={'Authorization':'Bearer '+ready['token']}).status_code==200
    process.wait(timeout=15)
    assert process.returncode==0
    try:
        httpx.get(url,timeout=1)
    except httpx.TransportError:
        pass
    else:
        raise AssertionError('Sidecar port remains open')
    print(json.dumps({'frozen':True,'isolated':True,'authentication':True,'stopped':True,'elapsed_seconds':round(time.perf_counter()-start,3)}))
finally:
    if process.poll() is None:process.kill();process.wait()
