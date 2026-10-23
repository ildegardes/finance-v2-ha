"""Deterministic local source RC from committed Git blobs, never git archive EOL conversion."""
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import zipfile

root=Path(__file__).resolve().parents[1]
target=Path(sys.argv[1]).resolve()
if target.exists():
    raise SystemExit('NEW_ARTIFACT_DIRECTORY_REQUIRED')
target.mkdir()
def git(*args):
    return subprocess.check_output(['git','-c','safe.directory='+root.as_posix(),*args],cwd=root)
assert not git('status','--porcelain'), 'CLEAN_COMMITTED_BRANCH_REQUIRED'
commit=git('rev-parse','HEAD').decode().strip()
manifest=json.loads(git('show','HEAD:docs/open-finance/RELEASE_0.1.23_MANIFEST.json'))
files={name:git('show','HEAD:'+name) for name in manifest['product_files_sha256']}
for name,pin in manifest['product_files_sha256'].items():
    assert hashlib.sha256(files[name]).hexdigest().upper()==pin
for name in ('repository.yaml','.gitattributes','docs/open-finance/RELEASE_0.1.23_MANIFEST.json','docs/open-finance/FULL_COVERAGE_CONTRACTS.md','docs/open-finance/FULL_COVERAGE_DEPLOYMENT.md','docs/open-finance/FULL_COVERAGE_VALIDATION.md','docs/open-finance/FULL_COVERAGE_EVIDENCE.json'):
    files[name]=git('show','HEAD:'+name)
def pack():
    out=io.BytesIO()
    with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED,compresslevel=9) as archive:
        for name in sorted(files):
            info=zipfile.ZipInfo(name,(1980,1,1,0,0,0))
            info.compress_type=zipfile.ZIP_DEFLATED
            info.external_attr=0o100644<<16
            archive.writestr(info,files[name])
    return out.getvalue()
first=pack()
assert first==pack(),'NONDETERMINISTIC_PACKAGE'
with zipfile.ZipFile(io.BytesIO(first)) as archive:
    assert archive.testzip() is None
    for name,pin in manifest['protected_files'].items():
        assert hashlib.sha256(archive.read(name)).hexdigest().upper()==pin
artifact=target/'finance-v17-0.1.23-open-finance.1-source-rc.zip'
artifact.write_bytes(first)
report={'version':manifest['version'],'commit':commit,'source_product_tree':manifest['source_product_tree'],
    'archive':artifact.name,'sha256':hashlib.sha256(first).hexdigest().upper(),'bytes':len(first),
    'files':len(files),'product_files':len(manifest['product_files_sha256']),'protected':len(manifest['protected_files']),
    'deterministic_repeat':True,'stable_channel_published':False,'production_deployment_authorized':False}
(target/'ARTIFACT_MANIFEST.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
print(json.dumps(report))
