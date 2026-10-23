"""Compare every runtime-distributed file to the candidate manifest in both images."""
import json
from pathlib import Path
import subprocess
import sys
import uuid

root=Path(__file__).resolve().parents[1]
target=Path(sys.argv[1]).resolve()
if target.exists():
    raise SystemExit('NEW_EVIDENCE_DIRECTORY_REQUIRED')
target.mkdir()
manifest=json.loads((root/'docs/open-finance/RELEASE_0.1.23_MANIFEST.json').read_bytes())
expected={p.removeprefix('finance-v17/'):h for p,h in manifest['product_files_sha256'].items()
    if p.startswith(('finance-v17/src/','finance-v17/migrations/')) or p in ('finance-v17/run.sh','finance-v17/migrate.sh','finance-v17/requirements-deploy.txt')}
program='''import hashlib,json,platform,subprocess,sys,oauthlib,finance_v2
from pathlib import Path
expected=json.load(sys.stdin)
actual={str(p.relative_to('/opt/finance-v2')) for p in Path('/opt/finance-v2').rglob('*') if p.is_file()}
assert actual==set(expected),'UNEXPECTED_RUNTIME_FILES'
for name,pin in expected.items():
    assert hashlib.sha256((Path('/opt/finance-v2')/name).read_bytes()).hexdigest().upper()==pin,name
from finance_v2.pluggy_coverage import contracts
contracts()
pip=subprocess.run([sys.executable,'-m','pip','check'],capture_output=True,text=True)
assert pip.returncode==0,pip.stdout
print(json.dumps({'status':'PASS','runtime_files':len(expected),'python':platform.python_version(),'architecture':platform.machine(),'oauthlib':oauthlib.__version__,'version':finance_v2.__version__,'pip_check':'PASS'}))
'''
rows=[]
for arch in ('amd64','arm64'):
    name='finance-full-files-'+uuid.uuid4().hex[:12]
    argv=['docker','run','--rm','--name',name,'--platform','linux/'+arch,'--network','none','--read-only','--cap-drop','ALL',
        '--security-opt','no-new-privileges','--memory','256m','--cpus','1','-i','--entrypoint','python',
        'finance-v17-full-coverage:0.1.23-open-finance.1-'+arch,'-B','-c',program]
    result=subprocess.run(argv,input=json.dumps(expected),capture_output=True,text=True,encoding='utf-8',timeout=90)
    (target/(arch+'.stdout.txt')).write_text(result.stdout,encoding='utf-8')
    (target/(arch+'.stderr.txt')).write_text(result.stderr,encoding='utf-8')
    assert result.returncode==0,result.stderr
    row=json.loads(result.stdout)
    assert row['python']=='3.12.7' and row['oauthlib']=='3.3.1' and row['version']=='0.1.23-open-finance.1'
    rows.append(row)
(target/'RESULTS.json').write_text(json.dumps(rows,indent=2)+'\n',encoding='utf-8')
print(json.dumps(rows))
