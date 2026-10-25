"""0.1.25 exact D02 code + release metadata, staged-tree publication gate."""
from hashlib import sha256
import json
from pathlib import Path
import subprocess

ROOT=Path(__file__).resolve().parents[2]
BASE='0ed53d32e7a7c57f3f37a7fd239d4582854e4032'
APPROVED={
    "finance-v17/src/finance_v2/open_finance.py": "EA455DEBBDB8AC43DF66635539FFCEC6A8C726C50EA496FFD9EA46C6713EC74A",
    "finance-v17/src/finance_v2/open_finance_coverage.py": "D4E4D2496D5C46B0CDC4AC12ADEE22D178702943B4527D748669730C54B572F3",
    "finance-v17/src/finance_v2/open_finance_diagnostics.py": "8B75668A8BAEB29AF8D62061F4193B4703EEF1342DF7A98DCE97C82E4BC51CFE",
    "finance-v17/src/finance_v2/pluggy_client.py": "78481B69558A8554E3CD992B39FA9096EA369217D7BAFA745F901CBD09223DBC",
    "finance-v17/src/finance_v2/pluggy_coverage.py": "2A94A93584805E8CE9CAC052741730AB0E47ACCD5A32772E783C742CE4A54A7C"
}
PROTECTED={
    "finance-v17/run.sh": "7FBDCE1C1A73A97AD757042956512D76BC3FB0DF6BDB023E17CB7F06BEC0B070",
    "finance-v17/src/finance_v2/PYTHON_REFERENCE_LICENSE.txt": "023163D4252112720E12757861BDD0272105EE1F67ED6A44130E652189A2F7AB",
    "finance-v17/src/finance_v2/UNICODE13_NOTICES.md": "86FCFFEA7F6E15385B93E7BB390CD44CD7BB65D05F672C68E8D556EE88679134",
    "finance-v17/src/finance_v2/UNICODE_DATA_LICENSE_2020.txt": "0EFACA9742A27A3F5A7F6F2B5C40A1D227295246E2483308BF83E05871FA202A",
    "finance-v17/src/finance_v2/UNICODE_LICENSE_V3.txt": "E7A93B009565CFCE55919A381437AC4DB883E9DA2126FA28B91D12732BC53D96",
    "finance-v17/src/finance_v2/unicode13_f06.py": "6C7EC1703A30FE81A9D577604DFC1B999D9AE48BF78B1318C20DE8E9662CBCD9",
    "finance-v17/src/finance_v2/unicode13_manifest.json": "9A279ACA79B09F3CE3C49EEA630619BED88115F416F81A97324093B4D856F07A",
    "finance-v17/src/finance_v2/unicode13_primitives.json": "DE81088662045384D1F0B07FDF53A40BEE297843782FE80BF1AAEA94383BAAA4"
}
METADATA={'finance-v17/'+p for p in ('config.yaml','Dockerfile','CHANGELOG.md','DOCS.md','src/finance_v2/__init__.py')}
OTHER={'tests/auto_sync/run_validation.py','tests/auto_sync/test_diagnostics.py','tests/auto_sync/verify_release_0125.py',
    'tests/release_mcp.py','docs/open-finance/RELEASE_0.1.25.md','docs/open-finance/RELEASE_0.1.25_MANIFEST.json',
    'docs/open-finance/RELEASE_0.1.25_VALIDATION.json'}
def git(*args):return subprocess.check_output(['git','-c','safe.directory='+ROOT.as_posix(),'-C',str(ROOT),*args])
def validate(tree,base,manifest):
    product={p for p in tree if p.startswith('finance-v17/')}
    assert len(product)==84 and product==set(manifest['files']),'PRODUCT_INVENTORY'
    assert product=={p for p in base if p.startswith('finance-v17/')}|{'finance-v17/src/finance_v2/open_finance_diagnostics.py'},'BASE_INVENTORY'
    assert manifest['version']=='0.1.25-open-finance.1' and manifest['schema']==10 and manifest['base_commit']==BASE
    assert manifest['new_migrations']==[]
    assert manifest['protected_files']==PROTECTED
    changed={p for p in set(tree)|set(base) if tree.get(p)!=base.get(p)}
    assert changed<=set(APPROVED)|METADATA|OTHER,'CHANGE_ALLOWLIST'
    assert OTHER<=set(tree),'MISSING_RELEASE_EVIDENCE'
    for p,expected in APPROVED.items():assert sha256(tree[p]).hexdigest().upper()==expected,'D02_CODE '+p
    for p,expected in PROTECTED.items():
        assert sha256(tree[p]).hexdigest().upper()==expected and tree[p]==base[p],'PROTECTED '+p
    for p,meta in manifest['files'].items():assert sha256(tree[p]).hexdigest().upper()==meta['sha256'],'FILE_HASH '+p
    for p in ('finance-v17/config.yaml','finance-v17/Dockerfile','finance-v17/src/finance_v2/__init__.py'):
        assert tree[p]==base[p].replace(b'0.1.24-open-finance.1',b'0.1.25-open-finance.1'),'VERSION_ONLY '+p
    assert tree['finance-v17/CHANGELOG.md'].startswith(b'# Finance V17\n\n## 0.1.25-open-finance.1\n')
    assert tree['finance-v17/CHANGELOG.md'].endswith(base['finance-v17/CHANGELOG.md'][len(b'# Finance V17\n\n'):])
    original=base['finance-v17/DOCS.md'].replace('Open Finance 0.1.24\n'.encode(),'Open Finance 0.1.25\n'.encode(),1)
    assert tree['finance-v17/DOCS.md'].startswith(original),'DOCS_HISTORY'
    for p in base:
        if p.startswith('finance-v17/migrations/') or p in ('finance-v17/requirements-deploy.txt','repository.yaml','docs/open-finance/BUILD_LOCK.json'):
            assert tree[p]==base[p],'IMMUTABLE '+p
    for p in tree:assert not p.lower().endswith(('.sqlite','.sqlite3','.db','.tar','.zip','.pem','.key','.pyc')),'FORBIDDEN_ARTIFACT '+p
    return changed
def main():
    base={p:git('show',BASE+':'+p) for p in git('ls-tree','-r','--name-only',BASE).decode().splitlines()}
    entries=[x.split('\t',1) for x in git('ls-files','--stage','-z').decode().strip('\0').split('\0')]
    tree={p:git('show',':'+p) for mode,p in entries}
    manifest=json.loads(tree['docs/open-finance/RELEASE_0.1.25_MANIFEST.json'])
    changed=validate(tree,base,manifest)
    assert not git('ls-files','--others','--exclude-standard','-z'),'UNTRACKED_FILES'
    for mode,p in entries:
        assert (ROOT/p).read_bytes()==tree[p],'INDEX_WORKTREE '+p
        if p in manifest['files']:assert mode.split()[0]==manifest['files'][p]['git_mode'],'GIT_MODE '+p
    git('diff','--cached',BASE,'--check')
    negative=[]
    for label,p in (('scope-guard-code','finance-v17/src/finance_v2/pluggy_client.py'),
            ('protected-bytes','finance-v17/run.sh'),('financial-code','finance-v17/src/finance_v2/domain/expenses.py'),
            ('migration','finance-v17/migrations/010_open_finance_coverage.sql')):
        altered=dict(tree);altered[p]=tree[p]+b'\n'
        modified=json.loads(json.dumps(manifest));modified['files'][p]['sha256']=sha256(altered[p]).hexdigest().upper()
        try:validate(altered,base,modified)
        except AssertionError:negative.append({'case':label,'rejected':True})
        else:raise AssertionError('FALSE_GREEN '+label)
    report={'result':'PASS','base':BASE,'product_files':84,'protected_files':8,'schema':10,
        'new_migrations':[],'changed_files':sorted(changed),'negative_controls':negative,
        'tree':git('write-tree').decode().strip(),'index_worktree_identical':True}
    print(json.dumps(report,indent=2))
if __name__=='__main__':main()
