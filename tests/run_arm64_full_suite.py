"""Isolated ARM64 execution: immutable candidate/test mounts, only synthetic tmpfs data."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time
import uuid

root=Path(__file__).resolve().parents[1]
suite,target=(Path(p).resolve() for p in sys.argv[1:3])
if target.exists() or not (suite/'source/src/finance_v2').is_dir():
    raise SystemExit('QUALIFIED_SUITE_AND_NEW_EVIDENCE_DIRECTORY_REQUIRED')
manifest=json.loads((root/'docs/open-finance/RELEASE_0.1.23_MANIFEST.json').read_bytes())
for name,pin in manifest['product_files_sha256'].items():
    assert hashlib.sha256((suite/'source'/name).read_bytes()).hexdigest().upper()==pin, ('SUITE_PRODUCT_MIRROR_MISMATCH',name)
target.mkdir()
name='finance-full-arm64-regression-'+uuid.uuid4().hex[:12]
image='finance-v17-full-coverage:0.1.23-open-finance.1-arm64'
program='''import json,platform,subprocess,sys,oauthlib,sqlite3
print(json.dumps({'architecture':platform.machine(),'python':platform.python_version(),'oauthlib':oauthlib.__version__,'sqlite':sqlite3.sqlite_version}),flush=True)
for cmd in ([sys.executable,'-B','/candidate/tests/test_full_coverage.py'],[sys.executable,'-B','/candidate/tests/release_mcp.py'],[sys.executable,'-B','/suite/run_historical_financial.py','/suite/source','/evidence/historical']):
    result=subprocess.run(cmd)
    if result.returncode:raise SystemExit(result.returncode)
'''


def docker(*args,check=True,timeout=30):
    r=subprocess.run(['docker',*args],capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=timeout)
    if check and r.returncode:
        raise RuntimeError('DOCKER_OPERATION_FAILED '+args[0]+' '+r.stderr[:500])
    return r


created=False
report={'name':name,'image':image,'network':'none','read_only_root':True,'source_product_tree':manifest['source_product_tree'],'synthetic_only':True}
try:
    assert docker('inspect',name,check=False).returncode!=0
    docker('create','--name',name,'--platform','linux/arm64','--label','finance.validation='+name,'--network','none','--read-only',
        '--cap-drop','ALL','--security-opt','no-new-privileges','--memory','1536m','--cpus','2','--pids-limit','256',
        '--tmpfs','/tmp:rw,nosuid,size=512m','--env','FINANCE_SYNTHETIC_TEMP_ROOT=/tmp/finance-fixtures',
        '--mount','type=bind,source='+str(suite)+',target=/suite,readonly',
        '--mount','type=bind,source='+str(root)+',target=/candidate,readonly',
        '--mount','type=bind,source='+str(target)+',target=/evidence','--entrypoint','python',image,'-B','-c',program)
    created=True
    inspect=json.loads(docker('inspect',name).stdout)[0]
    assert inspect['HostConfig']['NetworkMode']=='none' and inspect['HostConfig']['ReadonlyRootfs'] and not inspect['HostConfig']['PortBindings']
    assert all(m['Destination'] in ('/suite','/candidate','/evidence') for m in inspect['Mounts'])
    assert all(not m['RW'] for m in inspect['Mounts'] if m['Destination']!='/evidence')
    start=time.monotonic()
    r=docker('start','-a',name,check=False,timeout=900)
    report.update(exit_code=r.returncode,seconds=round(time.monotonic()-start,3))
    (target/'stdout.log').write_text(r.stdout,encoding='utf-8')
    (target/'stderr.log').write_text(r.stderr,encoding='utf-8')
    state=json.loads(docker('inspect',name).stdout)[0]['State']
    report['state']=state
    report['status']='PASS' if r.returncode==0 and state['ExitCode']==0 and state['Pid']==0 and not state['OOMKilled'] else 'FAIL'
finally:
    if created:
        info=json.loads(docker('inspect',name).stdout)[0]
        assert info['Config']['Labels']['finance.validation']==name
        if info['State']['Running']:
            docker('stop','--time','15',name,check=False,timeout=25)
            report['unexpected_cleanup_required']=True
        docker('rm',name)
    report['container_removed']=docker('inspect',name,check=False).returncode!=0
    (target/'RESULTS.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report),flush=True)
raise SystemExit(0 if report.get('status')=='PASS' and not report.get('unexpected_cleanup_required') else 1)
