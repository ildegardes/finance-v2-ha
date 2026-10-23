"""Exact release gate for extended staging, never interprets historical BUILD_LOCK as current."""
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
BASE = 'a3dc38375af13d8e9d40402538bb02f1d238a334'
VERSION = '0.1.23-open-finance.1'


def git(*args):
    return subprocess.check_output(['git','-c','safe.directory='+ROOT.as_posix(),*args],cwd=ROOT)


def digest(raw):
    return hashlib.sha256(raw).hexdigest().upper()


lock_path = 'docs/open-finance/BUILD_LOCK.json'
lock = json.loads(git('show',BASE+':'+lock_path))
assert git('show',':'+lock_path) == git('show',BASE+':'+lock_path), 'HISTORICAL_BUILD_LOCK_CHANGED'
for file, expected in lock['protected_files'].items():
    assert digest((ROOT/file).read_bytes()) == expected, ('WORKING_PROTECTED_BYTES', file)
    assert digest(git('show',':'+file)) == expected, ('STAGED_PROTECTED_BYTES', file)
baseline = set(git('ls-tree','-r','--name-only',BASE,'--','finance-v17').decode().splitlines())
product = set(git('ls-files','--','finance-v17').decode().splitlines())
modified = {
    'config.yaml','Dockerfile','src/finance_v2/__init__.py','src/finance_v2/migrations.py',
    'src/finance_v2/open_finance.py','src/finance_v2/open_finance_http.py','src/finance_v2/pluggy_client.py',
    'src/finance_v2/web/open-finance.js','src/finance_v2/web/open-finance.css','src/finance_v2/web/privacy.js',
    'CHANGELOG.md','DOCS.md',
}
added = {'migrations/010_open_finance_coverage.sql','src/finance_v2/pluggy_coverage.py',
    'src/finance_v2/pluggy_coverage_contracts.json','src/finance_v2/open_finance_coverage.py',
    'src/finance_v2/web/open-finance-coverage.js'}
assert product-baseline == {'finance-v17/'+p for p in added}, 'UNEXPECTED_PRODUCT_ADDITIONS'
assert not baseline-product, 'PRODUCT_REMOVALS'
for file in sorted(product & baseline):
    if file.removeprefix('finance-v17/') not in modified:
        assert git('show',':'+file) == git('show',BASE+':'+file), ('UNAUTHORIZED_PRODUCT_DIFF',file)
for file, old, new in (
    ('config.yaml','0.1.22-open-finance.1',VERSION),
    ('Dockerfile','0.1.22-open-finance.1',VERSION),
    ('src/finance_v2/__init__.py','0.1.22-open-finance.1',VERSION),
):
    original = git('show',BASE+':finance-v17/'+file).decode()
    expected = original.replace(old,new)
    if file == 'config.yaml':
        expected = expected.replace('stage: stable','stage: experimental')
    assert git('show',':finance-v17/'+file).decode() == expected, ('VERSION_OR_CONFIGURATION_DIFF',file)
for file in product:
    assert not re.search(r'\.(?:sqlite3?|db|tar|zip|pem|key)$|(?:^|/)\.env|(?:^|/)options\.json$',file,re.I), ('SENSITIVE_OR_GENERATED_ARTIFACT',file)
git('diff','--cached','--check')
product_hashes = {p:digest(git('show',':'+p)) for p in sorted(product)}
staged_tree = git('write-tree').decode().strip()
product_tree = git('rev-parse',staged_tree+':finance-v17').decode().strip()
manifest = {'contract':'FINANCE-EXTENDED-STAGING-RELEASE/1','version':VERSION,'base_commit':BASE,
    'source_product_tree':product_tree,'commit_binding':'Git commit containing this manifest; exact SHA is recorded in the PR and external evidence.',
    'schema':10,'new_migrations':[10],'protected_files':lock['protected_files'],
    'historical_build_lock_sha256':digest(git('show',BASE+':'+lock_path)),
    'product_files_sha256':product_hashes,'stable_promotion_authorized':False,
    'home_assistant_operations_executed':False}
manifest_path = ROOT/'docs/open-finance/RELEASE_0.1.23_MANIFEST.json'
if '--write-manifest' in sys.argv:
    if manifest_path.exists():
        raise SystemExit('MANIFEST_ALREADY_EXISTS')
    manifest_path.write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
else:
    assert json.loads(manifest_path.read_bytes()) == manifest, 'RELEASE_MANIFEST_MISMATCH'
print(json.dumps({'status':'PASS','product_files':len(product),'protected':len(lock['protected_files']),
    'product_tree':product_tree,'schema':10,'manifest':str(manifest_path)}))
