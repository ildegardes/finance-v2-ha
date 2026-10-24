"""Owned Docker resources only; real wrapper/API/scheduler, artificial empty data."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
target = Path(sys.argv[1]).resolve()
if target.exists():
    raise SystemExit('NEW_EVIDENCE_DIRECTORY_REQUIRED')
target.mkdir()


def docker(*args, check=True, timeout=30):
    result = subprocess.run(['docker',*args],capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=timeout)
    if check and result.returncode:
        raise RuntimeError('DOCKER_COMMAND_FAILED '+args[0]+' '+result.stderr[:500])
    return result


probe = '''import json,urllib.request
r=urllib.request.urlopen('http://127.0.0.1:8766/api/v2/health',timeout=2)
print(json.dumps({'status':r.status}))
'''
inventory = '''import hashlib,json,sqlite3,sys
from pathlib import Path
p=Path('/data/finance_v2.sqlite3')
c=sqlite3.connect(p.as_uri()+'?mode=ro',uri=True)
names=[r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'of_%' AND name NOT LIKE 'sqlite_%' AND name<>'_finance_v2_schema_migrations' ORDER BY name")]
data={n:[list(r) for r in c.execute('SELECT * FROM "'+n+'" ORDER BY rowid')] for n in names}
print(json.dumps({'schema':c.execute('PRAGMA user_version').fetchone()[0],'integrity':c.execute('PRAGMA integrity_check').fetchone()[0],'fk_violations':len(c.execute('PRAGMA foreign_key_check').fetchall()),'official_tables':len(names),'official_fingerprint':hashlib.sha256(json.dumps(data,sort_keys=True,separators=(',',':')).encode()).hexdigest(),'migrations':[r[0] for r in c.execute('SELECT version FROM _finance_v2_schema_migrations ORDER BY version')]}))
c.close()
'''
rows = []
for arch in ('amd64','arm64'):
    token=uuid.uuid4().hex[:12]
    name='finance-full-smoke-'+arch+'-'+token
    volume=name+'-data'
    label='finance.validation='+name
    image='finance-v17-full-coverage:0.1.23-open-finance.1-'+arch
    directory=target/arch
    directory.mkdir()
    options=directory/'options.json'
    options.write_text(json.dumps({'timezone':'UTC','ui_token':'synthetic-smoke-only','external_clients':'{}','oauth_clients':'{}','open_finance_enabled':False,'open_finance_auto_sync_enabled':False}),encoding='utf-8')
    created=False
    volume_created=False
    row={'architecture':arch,'container':name,'network':'none','read_only_root':True,'external_credentials':False,'synthetic_only':True}
    rows.append(row)
    try:
        if docker('inspect',name,check=False).returncode==0 or docker('volume','inspect',volume,check=False).returncode==0:
            raise RuntimeError('RESOURCE_NAME_COLLISION')
        docker('volume','create','--label',label,volume)
        volume_created=True
        docker('create','--name',name,'--platform','linux/'+arch,'--label',label,'--network','none','--read-only',
               '--cap-drop','ALL','--security-opt','no-new-privileges','--memory','768m','--cpus','2','--pids-limit','128',
               '--tmpfs','/tmp:rw,nosuid,size=64m','--mount','type=volume,source='+volume+',target=/data',
               '--mount','type=bind,source='+str(options)+',target=/data/options.json,readonly',image)
        created=True
        initial=json.loads(docker('inspect',name).stdout)[0]
        assert initial['HostConfig']['NetworkMode']=='none' and initial['HostConfig']['ReadonlyRootfs']
        assert not initial['HostConfig']['PortBindings']
        assert len(initial['Mounts'])==2
        assert all(m['Destination'] in ('/data','/data/options.json') for m in initial['Mounts'])
        times=[]
        snapshots=[]
        for cycle in range(2):
            started=time.monotonic()
            docker('start',name)
            # OF-L3-24 measured 49.25 s under emulation; 120 s is an external
            # observation ceiling, not an application timeout change.
            while time.monotonic()-started<120:
                response=docker('exec',name,'python','-B','-c',probe,check=False,timeout=10)
                if response.returncode==0:
                    break
                if not json.loads(docker('inspect',name).stdout)[0]['State']['Running']:
                    raise RuntimeError('APPLICATION_EXITED_BEFORE_READY')
                time.sleep(1)
            else:
                raise RuntimeError('READINESS_NOT_CONFIRMED')
            times.append(round(time.monotonic()-started,3))
            snapshot=json.loads(docker('exec',name,'python','-B','-c',inventory).stdout)
            assert snapshot['schema']==10 and snapshot['integrity']=='ok' and snapshot['fk_violations']==0
            assert snapshot['migrations']==list(range(1,11))
            snapshots.append(snapshot)
            docker('stop','--time','15',name,timeout=25)
            state=json.loads(docker('inspect',name).stdout)[0]['State']
            assert state['ExitCode']==0 and not state['OOMKilled'] and not state['Running'] and state['Pid']==0
        assert snapshots[0]==snapshots[1]
        logs=docker('logs',name)
        (directory/'stdout.log').write_text(logs.stdout,encoding='utf-8')
        (directory/'stderr.log').write_text(logs.stderr,encoding='utf-8')
        assert 'forced KILL' not in logs.stderr and 'lifecycle: stopped status=0' in logs.stderr
        row.update(status='PASS',readiness_seconds=times,inventory=snapshots,exit_code=state['ExitCode'],remaining_pid=state['Pid'])
    except Exception as error:
        row.update(status='FAIL',error=str(error))
        if created:
            logs=docker('logs',name,check=False)
            (directory/'failure.stdout.log').write_text(logs.stdout,encoding='utf-8')
            (directory/'failure.stderr.log').write_text(logs.stderr,encoding='utf-8')
    finally:
        if created:
            inspected=json.loads(docker('inspect',name).stdout)[0]
            assert inspected['Config']['Labels'].get('finance.validation')==name
            if inspected['State']['Running']:
                docker('stop','--time','15',name,check=False,timeout=25)
                row['unexpected_cleanup_required']=True
            final=json.loads(docker('inspect',name).stdout)[0]
            (directory/'STATE.json').write_text(json.dumps({'State':final['State'],'NetworkMode':final['HostConfig']['NetworkMode'],'ReadonlyRootfs':final['HostConfig']['ReadonlyRootfs'],'Memory':final['HostConfig']['Memory'],'NanoCpus':final['HostConfig']['NanoCpus']},indent=2)+'\n',encoding='utf-8')
            docker('rm',name)
        if volume_created:
            v=json.loads(docker('volume','inspect',volume).stdout)[0]
            assert v['Labels'].get('finance.validation')==name
            docker('volume','rm',volume)
        row['container_removed']=docker('inspect',name,check=False).returncode!=0
        row['volume_removed']=docker('volume','inspect',volume,check=False).returncode!=0
        (target/'RESULTS.json').write_text(json.dumps(rows,indent=2)+'\n',encoding='utf-8')
        print(json.dumps(row),flush=True)
    if row['status']!='PASS':
        break
(target/'EVIDENCE_MANIFEST.json').write_text(json.dumps({str(p.relative_to(target)):hashlib.sha256(p.read_bytes()).hexdigest().upper() for p in target.rglob('*') if p.is_file() and p.name!='options.json'},indent=2)+'\n',encoding='utf-8')
raise SystemExit(0 if len(rows)==2 and all(r['status']=='PASS' and not r.get('unexpected_cleanup_required') and r['container_removed'] and r['volume_removed'] for r in rows) else 1)
