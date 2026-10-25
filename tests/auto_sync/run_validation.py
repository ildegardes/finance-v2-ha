"""Evidence-producing test entry. No production paths or external sockets permitted."""
from hashlib import sha256
import importlib.util
import json
import os
from pathlib import Path
import platform
import sys
import tempfile
import time
import unittest

from support import ROOT, CANDIDATE, FIXTURES, STOCK
tempfile.tempdir = str(FIXTURES)
manifest = json.loads((CANDIDATE / 'docs/open-finance/RELEASE_0.1.24_MANIFEST.json').read_text(encoding='utf-8'))
def hashes():
    result = {p:sha256((CANDIDATE/p).read_bytes()).hexdigest().upper() for p in manifest['files']}
    assert all(result[p] == meta['sha256'] for p,meta in manifest['files'].items()), 'CANDIDATE_CHANGED'
    return result
before = hashes()
suite = unittest.defaultTestLoader.discover(str(ROOT),pattern='test_sqlite_validation.py')
suite.addTests(unittest.defaultTestLoader.discover(str(ROOT),pattern='test_cancellation.py'))
suite.addTests(unittest.defaultTestLoader.discover(str(ROOT),pattern='test_release_policy.py'))
suite.addTests(unittest.defaultTestLoader.loadTestsFromModule(STOCK))

class Result(unittest.TextTestResult):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs); self.individual=[]
    def addSuccess(self,test):
        super().addSuccess(test); self.individual.append({'test':test.id(),'result':'PASS'})
    def addFailure(self,test,err):
        super().addFailure(test,err); self.individual.append({'test':test.id(),'result':'FAIL'})
    def addError(self,test,err):
        super().addError(test,err); self.individual.append({'test':test.id(),'result':'ERROR'})

label = sys.argv[1]
assert label.replace('-','').isalnum()
output = Path(os.environ.get('VALIDATION_OUTPUT',str(FIXTURES/'evidence')))
output.mkdir(parents=True,exist_ok=True)
started=time.monotonic()
with (output/(label+'.log')).open('x',encoding='utf-8') as log:
    result = unittest.TextTestRunner(stream=log,verbosity=2,resultclass=Result).run(suite)
from test_sqlite_validation import EVIDENCE
after = hashes()
summary = {'platform':platform.platform(),'machine':platform.machine(),'python':sys.version,
    'run':result.testsRun,'pass':result.testsRun-len(result.errors)-len(result.failures)-len(result.skipped),
    'fail':len(result.failures),'error':len(result.errors),'skip':len(result.skipped),
    'elapsed_seconds':round(time.monotonic()-started,3),'candidate_unchanged':before==after,
    'protected_hashes':{p:after[p] for p in manifest['protected_files']},
    'individual':result.individual,'sqlite_evidence':EVIDENCE,
    'real_credentials_or_data_used':False,'external_network_allowed':False}
(output/(label+'.json')).write_text(json.dumps(summary,indent=2)+'\n',encoding='utf-8')
print(json.dumps({k:v for k,v in summary.items() if k not in ('individual','sqlite_evidence','protected_hashes')}))
if not result.wasSuccessful():
    for test,trace in (result.errors+result.failures)[:4]:
        print(test.id(),trace)
    raise SystemExit(1)
