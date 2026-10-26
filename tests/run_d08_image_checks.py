"""Own ARM64 containers only; network none, tmpfs synthetic data, no host mounts."""
from pathlib import Path
import hashlib
import json
import subprocess
import sys
import time
import uuid

ROOT=Path(__file__).resolve().parents[1]
IMAGE=sys.argv[1]
owned=[]
def docker(*args,timeout=120,input=None):
    r=subprocess.run(['docker',*args],input=input,capture_output=True,text=True,encoding='utf-8',timeout=timeout)
    if r.returncode:raise RuntimeError('DOCKER_FAILED '+args[0]+' '+r.stderr[-1500:])
    return (r.stdout+r.stderr).strip() if args[0]=='logs' else r.stdout.strip()
flags=['--platform','linux/arm64','--network','none','--read-only','--cap-drop','ALL',
       '--security-opt','no-new-privileges','--memory','512m','--cpus','2','--pids-limit','96',
       '--tmpfs','/tmp:rw,nosuid,nodev,size=64m','--tmpfs','/data:rw,nosuid,nodev,size=64m']
def create(code):
    cid=docker('create','--name','finance-d08-'+uuid.uuid4().hex[:12],*flags,'--entrypoint','python',IMAGE,'-B','-c',code)
    owned.append(cid)
    inspect=json.loads(docker('inspect',cid))[0]
    assert inspect['HostConfig']['NetworkMode']=='none' and inspect['HostConfig']['ReadonlyRootfs']
    assert not inspect['HostConfig']['PortBindings'] and not inspect['Mounts']
    docker('start',cid)
    return cid

results=[]
try:
    product=ROOT/'finance-v17'
    expected={str(p.relative_to(product)).replace('\\','/'):hashlib.sha256(p.read_bytes()).hexdigest()
        for d in ('src','migrations') for p in (product/d).rglob('*') if p.is_file() and '__pycache__' not in p.parts}
    for name in ('run.sh','migrate.sh','requirements-deploy.txt'):
        expected[name]=hashlib.sha256((product/name).read_bytes()).hexdigest()
    code="import pathlib,hashlib,json,platform; expected="+repr(expected)+"; root=pathlib.Path('/opt/finance-v2'); assert platform.machine()=='aarch64'; assert all(hashlib.sha256((root/p).read_bytes()).hexdigest()==v for p,v in expected.items()); print(json.dumps({'image_files_verified':len(expected),'architecture':platform.machine()}))"
    cid=create(code);assert docker('wait',cid)=='0';print(docker('logs',cid),flush=True)
    code="__file__='/tmp/test_d08_auth.py';\n"+(ROOT/'tests/test_d08_auth.py').read_text(encoding='utf-8')
    cid=create(code);assert docker('wait',cid)=='0';print(docker('logs',cid),flush=True)
    results.append({'case':'ARM64_auth','pass':8})
    options={'timezone':'UTC','ui_token':'synthetic-owner-only-token','external_clients':'{}','oauth_clients':'{}',
             'open_finance_enabled':False,'open_finance_auto_sync_enabled':False}
    bootstrap="from pathlib import Path; import os; Path('/data/options.json').write_text("+repr(json.dumps(options))+"); os.execv('/opt/finance-v2/run.sh',['/opt/finance-v2/run.sh'])"
    probe="import urllib.request,json; r=urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:8766/api/v2/health',headers={'Authorization':'Bearer synthetic-owner-only-token'}),timeout=2); print(r.status)"
    for signal in ('TERM','INT'):
        cid=create(bootstrap);start=time.monotonic();ready=False
        while time.monotonic()-start<90:
            r=subprocess.run(['docker','exec',cid,'python','-B','-c',probe],capture_output=True,text=True,timeout=8)
            if r.returncode==0 and r.stdout.strip()=='200':ready=True;break
            time.sleep(1)
        assert ready,'ARM64_READINESS_TIMEOUT'
        verify="import sqlite3,json; c=sqlite3.connect('file:/data/finance_v2.sqlite3?mode=ro',uri=True); assert c.execute('pragma user_version').fetchone()[0]==10; assert c.execute('pragma integrity_check').fetchone()[0]=='ok'; assert c.execute('pragma foreign_key_check').fetchall()==[]; print('SCHEMA10_INTEGRITY_PASS'); c.close()"
        assert docker('exec',cid,'python','-B','-c',verify)=='SCHEMA10_INTEGRITY_PASS'
        seconds=round(time.monotonic()-start,3);stop=time.monotonic()
        if signal=='TERM':docker('stop','--time','8',cid,timeout=15)
        else:docker('kill','--signal','INT',cid)
        exit_code=int(docker('wait',cid,timeout=15))
        state=json.loads(docker('inspect',cid))[0]['State']
        logs=docker('logs',cid)
        assert exit_code==0 and state['Pid']==0 and not state['Running'] and not state['OOMKilled']
        assert 'forced KILL' not in logs
        record={'case':'ARM64_wrapper_'+signal,'exit_code':exit_code,'ready_seconds':seconds,
                'shutdown_seconds':round(time.monotonic()-stop,3),'schema':10,'integrity':'ok','fk_violations':0,'pid_after':state['Pid']}
        results.append(record);print(json.dumps(record),flush=True)
finally:
    for cid in owned:
        state=json.loads(docker('inspect',cid))[0]['State']
        if state['Running']:docker('stop','--time','8',cid,timeout=15)
        docker('rm',cid)
    print(json.dumps({'owned_containers_removed':len(owned),'host_mounts':0,'real_requests':0}),flush=True)
print(json.dumps({'result':'PASS','cases':results}),flush=True)
