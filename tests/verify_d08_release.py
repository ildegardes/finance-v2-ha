"""Exact D08 scope and protected-byte validator; no remote operations."""
from pathlib import Path
import hashlib
import json
import subprocess

ROOT=Path(__file__).resolve().parents[1]
BASE='bd8477e429fa8408c11b4b2d2b551666a2359a97'
VERSION='0.1.26-open-finance.1'
def git(*args):
    return subprocess.check_output(['git','-c','safe.directory='+ROOT.as_posix(),'-C',str(ROOT),*args])
def digest(data):return hashlib.sha256(data).hexdigest().upper()
def product():return {p.relative_to(ROOT).as_posix():p.read_bytes() for p in (ROOT/'finance-v17').rglob('*') if p.is_file()}
def validate(files):
    paths=git('ls-tree','-r','--name-only',BASE).decode().splitlines()
    baseline={p:git('show',BASE+':'+p) for p in paths if p.startswith('finance-v17/')}
    protected=json.loads(git('show',BASE+':docs/open-finance/RELEASE_0.1.25_MANIFEST.json'))['protected_files']
    for p,sha in protected.items():assert digest(files[p])==sha,'PROTECTED '+p
    editable={'finance-v17/'+p for p in ('CHANGELOG.md','DOCS.md','config.yaml','Dockerfile','src/finance_v2/__init__.py',
        'src/finance_v2/pluggy_client.py','src/finance_v2/web/app.js','src/finance_v2/web/open-finance.js','src/finance_v2/web/open-finance-coverage.js')}
    added={'finance-v17/src/finance_v2/web/open-finance-errors.js'}
    assert set(files)==set(baseline)|added,'PRODUCT_FILE_SET'
    for p,blob in baseline.items():
        if p not in editable:assert files[p]==blob,'UNAUTHORIZED_PRODUCT_CHANGE '+p
    for rel in ('config.yaml','Dockerfile','src/finance_v2/__init__.py'):
        p='finance-v17/'+rel
        assert files[p]==baseline[p].replace(b'0.1.25-open-finance.1',VERSION.encode()),'VERSION_METADATA '+p
    for p in files:
        assert not p.endswith(('.sqlite','.sqlite3','.db','.pyc','.env','.tar','.zip')),'UNEXPECTED_ARTIFACT'
    assert git('show',BASE+':repository.yaml')==(ROOT/'repository.yaml').read_bytes()
    assert len([p for p in files if p.startswith('finance-v17/migrations/')])==10
    return {'version':VERSION,'schema':10,'product_files':len(files),'protected_files':len(protected),
        'changed_product_files':sorted(p for p in files if files[p]!=baseline.get(p)),
        'sha256':{p:digest(data) for p,data in sorted(files.items())}}

if __name__=='__main__':
    files=product();result=validate(files)
    for p in ('finance-v17/run.sh','finance-v17/migrations/010_open_finance_coverage.sql','finance-v17/src/finance_v2/domain/expenses.py'):
        corrupt=dict(files);corrupt[p]+=b'\n'
        try:validate(corrupt)
        except AssertionError:pass
        else:raise AssertionError('FALSE_GREEN '+p)
    git('diff','--check')
    print(json.dumps({'result':'PASS','negative_controls':3,**result},indent=2))
