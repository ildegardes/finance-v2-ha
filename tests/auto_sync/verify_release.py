"""Exact publication allowlist. Raw protected bytes are never normalized."""
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[2]
BASE='7bec77f6dcff63f9a66f3c408d19c887febff690'
ALLOWED={
    'finance-v17/'+p for p in (
        'CHANGELOG.md','DOCS.md','Dockerfile','config.yaml','src/finance_v2/__init__.py',
        'src/finance_v2/__main__.py','src/finance_v2/ha_pluggy_options.py',
        'src/finance_v2/open_finance.py','src/finance_v2/open_finance_coverage.py',
        'src/finance_v2/open_finance_http.py','src/finance_v2/pluggy_client.py',
        'src/finance_v2/pluggy_config.py','src/finance_v2/pluggy_coverage.py',
        'src/finance_v2/http_runtime.py','src/finance_v2/open_finance_auto.py')}
EXTRA={'tests/release_mcp.py','docs/open-finance/RELEASE_0.1.24.md',
       'docs/open-finance/RELEASE_0.1.24_MANIFEST.json',
       'docs/open-finance/RELEASE_0.1.24_VALIDATION.json'}
PROTECTED={'finance-v17/run.sh'}|{'finance-v17/src/finance_v2/'+p for p in (
    'PYTHON_REFERENCE_LICENSE.txt','UNICODE13_NOTICES.md','UNICODE_DATA_LICENSE_2020.txt',
    'UNICODE_LICENSE_V3.txt','unicode13_f06.py','unicode13_manifest.json','unicode13_primitives.json')}
def git(*args):
    return subprocess.check_output(['git','-c','safe.directory='+ROOT.as_posix(),'-C',str(ROOT),*args])
def validate(tree,base,manifest):
    product={p for p in tree if p.startswith('finance-v17/')}
    assert product==set(manifest['files']),'PRODUCT_INVENTORY'
    for path,metadata in manifest['files'].items():
        assert sha256(tree[path]).hexdigest().upper()==metadata['sha256'], 'FILE_HASH '+path
    assert set(manifest['protected_files'])==PROTECTED
    for path,expected in manifest['protected_files'].items():
        assert sha256(tree[path]).hexdigest().upper()==expected,'PROTECTED '+path
        assert tree[path]==base[path],'PROTECTED_BASE '+path
    changed={p for p in set(tree)|set(base) if tree.get(p)!=base.get(p)}
    assert all(p in ALLOWED|EXTRA or p.startswith('tests/auto_sync/') for p in changed), 'CHANGE_ALLOWLIST'
    config=base['finance-v17/config.yaml'].replace(b'0.1.23-open-finance.1',b'0.1.24-open-finance.1')
    config=config.replace(b'  open_finance_auto_sync_enabled: false\n',b'  open_finance_auto_sync_enabled: true\n')
    assert tree['finance-v17/config.yaml']==config,'EXACT_CONFIG'
    for path in ('finance-v17/Dockerfile','finance-v17/src/finance_v2/__init__.py'):
        assert tree[path]==base[path].replace(b'0.1.23-open-finance.1',b'0.1.24-open-finance.1'),'VERSION_ONLY '+path
    for path in base:
        if path.startswith('finance-v17/migrations/') or path in (
            'BUILD_LOCK.json','finance-v17/requirements-deploy.txt','repository.yaml'):
            assert tree[path]==base[path],'IMMUTABLE '+path
    migrations={p for p in product if p.startswith('finance-v17/migrations/')}
    assert len(migrations)==10
    assert sha256(tree['docs/open-finance/BUILD_LOCK.json']).hexdigest().upper()==manifest['historical_build_lock_sha256']
    for path in tree:
        assert not path.lower().endswith(('.sqlite','.sqlite3','.db','.tar','.zip','.pyc','.pem','.key')), 'FORBIDDEN_ARTIFACT '+path
    return changed
def main():
    basepaths=git('ls-tree','-r','--name-only',BASE).decode().splitlines()
    base={p:git('show',BASE+':'+p) for p in basepaths}
    staged=git('ls-files','--stage','-z').decode().split('\0')
    entries=[s.split('\t',1) for s in staged if s]
    tree={p:git('show',':'+p) for meta,p in entries}
    manifest=json.loads(tree['docs/open-finance/RELEASE_0.1.24_MANIFEST.json'])
    assert manifest['base_commit']==BASE and manifest['schema']==10 and manifest['new_migrations']==[]
    changed=validate(tree,base,manifest)
    for meta,path in entries:
        assert (ROOT/path).read_bytes()==tree[path],'INDEX_WORKTREE '+path
        if path in manifest['files']:
            assert meta.split()[0]==manifest['files'][path]['git_mode'],'GIT_MODE '+path
    git('diff','--cached','--check')
    negative=[]
    for label,path,payload in (
        ('protected-byte','finance-v17/run.sh',tree['finance-v17/run.sh']+b'\n'),
        ('config-change','finance-v17/config.yaml',tree['finance-v17/config.yaml'].replace(b'8766',b'8767')),
        ('new-migration','finance-v17/migrations/011_UNAUTHORIZED.sql',b'SELECT 1;\n'),
        ('undeclared-product','finance-v17/unauthorized.txt',b'no\n')):
        altered=dict(tree);altered[path]=payload
        try:validate(altered,base,manifest)
        except AssertionError:negative.append({'case':label,'rejected':True})
        else:raise AssertionError('FALSE_GREEN '+label)
    report={'result':'PASS','base_commit':BASE,'version':manifest['version'],'schema':10,
        'product_files':len(manifest['files']),'protected_files':8,'migrations':10,
        'changed_files':sorted(changed),'negative_controls':negative,
        'staged_tree':git('write-tree').decode().strip(),'working_tree_matches_index':True}
    print(json.dumps(report,indent=2))
if __name__=='__main__':main()
