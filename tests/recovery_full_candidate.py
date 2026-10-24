"""Actual baseline code + synthetic schema9 restore, never a Supervisor restore."""
import hashlib
import io
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile

root=Path(__file__).resolve().parents[1]
target=Path(sys.argv[1]).resolve()
if target.exists():
    raise SystemExit('NEW_EVIDENCE_DIRECTORY_REQUIRED')
target.mkdir()
base='a3dc38375af13d8e9d40402538bb02f1d238a334'
def git(*args):
    return subprocess.check_output(['git','-c','safe.directory='+root.as_posix(),*args],cwd=root)
archive=target/'baseline'
archive.mkdir()
for name in git('ls-tree','-r','--name-only',base,'--','finance-v17').decode().splitlines():
    if name.startswith('/') or '..' in Path(name).parts or not name.startswith('finance-v17/'):
        raise RuntimeError('UNSAFE_BASELINE_PATH')
    path=archive/name
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_bytes(git('show',base+':'+name))
lock=json.loads((root/'docs/open-finance/BUILD_LOCK.json').read_bytes())
for name,pin in lock['protected_files'].items():
    assert hashlib.sha256((archive/name).read_bytes()).hexdigest().upper()==pin
reference=target/'reference.sqlite3'
working=target/'working.sqlite3'
restored=target/'restored.sqlite3'
settings=target/'configuration.synthetic.json'
settings.write_text(json.dumps({'timezone':'UTC','ui_token':'SYNTHETIC-RESTORE-ONLY','open_finance_enabled':False,'open_finance_auto_sync_enabled':False}),encoding='utf-8')
baseline_src=archive/'finance-v17'/'src'
candidate_src=root/'finance-v17'/'src'


def run(src,code,*args):
    program='import sys;sys.path.insert(0,sys.argv.pop(1));\n'+code
    result=subprocess.run([sys.executable,'-B','-c',program,str(src),*map(str,args)],capture_output=True,text=True,encoding='utf-8',timeout=45)
    if result.returncode:
        raise RuntimeError('SYNTHETIC_RECOVERY_PROCESS_FAILED '+result.stderr)
    return result.stdout.strip()


seed='''from pathlib import Path
from finance_v2.migrations import migrate
from finance_v2.db import connect
from finance_v2 import __version__
import sqlite3,sys
p=Path(sys.argv[1]);assert migrate(p)==list(range(1,10))
c=connect(p);c.execute("INSERT INTO accounts(name,active) VALUES('Synthetic restore account',1)")
backup=sqlite3.connect(sys.argv[2]);c.backup(backup);backup.close();c.close()
assert __version__=='0.1.22-open-finance.1'
print('BASELINE_SCHEMA9_CAPTURED')
'''
assert run(baseline_src,seed,working,reference)=='BASELINE_SCHEMA9_CAPTURED'
reference_hash=hashlib.sha256(reference.read_bytes()).hexdigest().upper()
upgrade='''from pathlib import Path
from finance_v2.migrations import migrate,require_current_schema
import sys
p=Path(sys.argv[1]);assert migrate(p)==[10];require_current_schema(p)
print('CANDIDATE_SCHEMA10')
'''
assert run(candidate_src,upgrade,working)=='CANDIDATE_SCHEMA10'
reject='''from pathlib import Path
from finance_v2.migrations import require_current_schema,MigrationError
import sys
try:require_current_schema(Path(sys.argv[1]))
except MigrationError:print('DOWNGRADE_ALONE_REJECTED')
else:raise SystemExit(4)
'''
assert run(baseline_src,reject,working)=='DOWNGRADE_ALONE_REJECTED'
restore='''import sqlite3,sys
a=sqlite3.connect('file:'+sys.argv[1]+'?mode=ro',uri=True);b=sqlite3.connect(sys.argv[2]);a.backup(b);a.close();b.close()
print('RESTORED_COPY')
'''
assert run(baseline_src,restore,reference,restored)=='RESTORED_COPY'
shutil.copy2(settings,target/'configuration.restored.synthetic.json')
verify='''from pathlib import Path
from finance_v2.migrations import require_current_schema
from finance_v2.db import connect
import hashlib,json,sys
p=Path(sys.argv[1]);require_current_schema(p);c=connect(p)
names=[r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'of_%' AND name NOT LIKE 'sqlite_%' AND name<>'_finance_v2_schema_migrations' ORDER BY name")]
data={name:[list(r) for r in c.execute('SELECT * FROM "'+name+'" ORDER BY rowid')] for name in names}
assert c.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
assert not c.execute('PRAGMA foreign_key_check').fetchall()
print(json.dumps({'schema':c.execute('PRAGMA user_version').fetchone()[0],'official_tables':len(names),'fingerprint':hashlib.sha256(json.dumps(data,sort_keys=True).encode()).hexdigest()}));c.close()
'''
before=json.loads(run(baseline_src,verify,reference))
after=json.loads(run(baseline_src,verify,restored))
assert before==after and after['schema']==9
assert hashlib.sha256(reference.read_bytes()).hexdigest().upper()==reference_hash
assert settings.read_bytes()==(target/'configuration.restored.synthetic.json').read_bytes()
report={'status':'PASS','baseline_commit':base,'baseline_version':'0.1.22-open-finance.1','candidate_version':'0.1.23-open-finance.1',
    'reference_sha256':reference_hash,'reference_unchanged':True,'baseline_code_executed':True,'configuration_bytes_preserved':True,
    'downgrade_without_database_restore_rejected':True,'before':before,'after':after,'supervisor_restore':False,'real_data_used':False}
(target/'RESULTS.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
print(json.dumps(report))
