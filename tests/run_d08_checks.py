"""D08 local suites. Only temporary synthetic databases and loopback are allowed."""
from pathlib import Path
import hashlib
import importlib
import json
import os
import sys
import tempfile
import types
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
# Discard inherited application configuration without reading its values.
for name in tuple(os.environ):
    if name.startswith('FINANCE_V2_') or 'PLUGGY' in name.upper():
        del os.environ[name]
os.environ['APP_TIMEZONE'] = 'America/Sao_Paulo'
mode = sys.argv[1]
suite = unittest.TestSuite()
with tempfile.TemporaryDirectory(prefix='d08-synthetic-') as directory:
    os.environ['VALIDATION_FIXTURE_ROOT'] = directory
    tempfile.tempdir = directory
    sys.path[:0] = [str(ROOT/'finance-v17/src'), str(ROOT/'tests/auto_sync')]
    import support
    class FixtureBoundaryTests(unittest.TestCase):
        def test_native_bytes_inside_new_fixture_are_allowed(self):
            support.audit('sqlite3.connect',(os.fsencode(Path(directory)/'synthetic.sqlite3'),))
        def test_native_bytes_outside_fixture_remain_rejected(self):
            with self.assertRaisesRegex(AssertionError,'DATABASE_OUTSIDE_NEW_SYNTHETIC_FIXTURES'):
                support.audit('sqlite3.connect',(os.fsencode(Path(directory).parent/'never-open.sqlite3'),))
        def test_text_outside_fixture_remains_rejected(self):
            with self.assertRaisesRegex(AssertionError,'DATABASE_OUTSIDE_NEW_SYNTHETIC_FIXTURES'):
                support.audit('sqlite3.connect',(str(Path(directory).parent/'never-open.sqlite3'),))
    suite.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(FixtureBoundaryTests))
    if mode == 'open-finance':
        for name in ('test_sqlite_validation','test_cancellation','test_release_policy','test_diagnostics'):
            suite.addTests(unittest.defaultTestLoader.loadTestsFromModule(importlib.import_module(name)))
        suite.addTests(unittest.defaultTestLoader.loadTestsFromModule(support.STOCK))
    elif mode == 'financial':
        tests = Path(sys.argv[2]).resolve()
        package = types.ModuleType('tests'); package.__path__ = [str(tests)];sys.modules['tests'] = package
        for name in ('test_domain','test_revenues_v17','test_scheduler'):
            suite.addTests(unittest.defaultTestLoader.loadTestsFromModule(importlib.import_module('tests.'+name)))
    else:
        raise SystemExit('UNKNOWN_SUITE')
    class Result(unittest.TextTestResult):
        def __init__(self,*args,**kwargs): super().__init__(*args,**kwargs); self.individual=[]
        def addSuccess(self,test): super().addSuccess(test); self.individual.append([test.id(),'PASS'])
        def addFailure(self,test,error): super().addFailure(test,error); self.individual.append([test.id(),'FAIL'])
        def addError(self,test,error): super().addError(test,error); self.individual.append([test.id(),'ERROR'])
    result=unittest.TextTestRunner(verbosity=2,resultclass=Result).run(suite)
    print(json.dumps({'suite':mode,'run':result.testsRun,'pass':result.testsRun-len(result.failures)-len(result.errors)-len(result.skipped),
        'fail':len(result.failures),'error':len(result.errors),'skip':len(result.skipped),'individual':result.individual},ensure_ascii=True))
    if not result.wasSuccessful() or result.skipped: raise SystemExit(1)
