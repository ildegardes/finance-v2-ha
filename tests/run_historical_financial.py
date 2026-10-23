"""Run existing synthetic financial/OAuth/scheduler suites against this product.

The historical test source stays external/read-only and is never copied into this public repository.
Schema expectations may be requalified explicitly by prepare_historical_schema10.py;
the adaptation ledger records every changed assertion. Product behavior is never replaced.
"""
import importlib
import io
import json
import os
from pathlib import Path
import socket
import re
import uuid
import threading
import subprocess
import sys
import tempfile
import time
import traceback
import unittest

ROOT = Path(__file__).resolve().parents[1]
historical, target = (Path(arg).resolve() for arg in sys.argv[1:3])
if not (historical / 'tests' / 'support.py').is_file() or target.exists():
    raise SystemExit('EXISTING_SYNTHETIC_TEST_SOURCE_AND_NEW_TARGET_REQUIRED')
target.mkdir()
fixtures = Path(os.environ.get('FINANCE_SYNTHETIC_TEMP_ROOT', str(target / 'fixtures')))
fixtures.mkdir()
tempfile.tempdir = str(fixtures)
product = historical / 'src'
sys.path[:0] = [str(product), str(historical)]
os.environ['PYTHONPATH'] = str(product) + os.pathsep + str(historical)
os.environ['PYTHONDONTWRITEBYTECODE'] = '1'
# Legacy scheduler test forbids the literal path fragment "v1". Hex-only unique
# fixture names prevent an unrelated random basename from impersonating that path.
tempfile._RandomNameSequence.__next__ = lambda self: uuid.uuid4().hex
os.environ['APP_TIMEZONE'] = 'America/Sao_Paulo'
for name in tuple(os.environ):
    if 'PLUGGY' in name.upper():
        del os.environ[name]


def inside(path, parent):
    try:
        Path(path).resolve().relative_to(parent)
        return True
    except (ValueError, TypeError):
        return False


def audit(event, args):
    if event == 'sqlite3.connect':
        raw = os.fsdecode(args[0])
        if raw == ':memory:':
            return
        if raw.startswith('file:'):
            from urllib.parse import unquote, urlsplit
            raw = unquote(urlsplit(raw).path)
            if os.name == 'nt' and raw.startswith('/'):
                raw = raw[1:]
        if not inside(raw, fixtures):
            raise PermissionError('EXISTING_DATABASE_ACCESS_FORBIDDEN')
    elif event == 'socket.connect':
        addr = args[1]
        if not isinstance(addr, tuple) or addr[0] != '127.0.0.1':
            raise PermissionError('EXTERNAL_NETWORK_FORBIDDEN')
    elif event == 'subprocess.Popen':
        executable, argv, cwd, env = args
        actual = executable or ((re.match(r'^"([^"]+)"',argv).group(1) if argv.startswith('"') else argv.split(' ',1)[0]) if isinstance(argv,str) else argv[0])
        if Path(actual).resolve() != Path(sys.executable).resolve() or '-c' not in argv:
            raise PermissionError('ONLY_REVIEWED_SYNTHETIC_PYTHON_CHILDREN')
        # The reviewed child programs reopen only their disposable fixtures or
        # intentionally damaged Unicode copies. No production storage is mounted.
    elif event in ('sqlite3.load_extension', 'sqlite3.enable_load_extension'):
        raise PermissionError('EXTERNAL_PROCESS_OR_SQLITE_EXTENSION_FORBIDDEN')


sys.addaudithook(audit)
children = []
native_popen = subprocess.Popen
class ObservedPopen(native_popen):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        children.append(self)
subprocess.Popen = ObservedPopen


class Result(unittest.TextTestResult):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.rows = []

    def addSuccess(self, test):
        super().addSuccess(test)
        self.rows.append({'id': test.id(), 'status': 'PASS'})

    def addFailure(self, test, err):
        super().addFailure(test, err)
        self.rows.append({'id': test.id(), 'status': 'FAIL', 'detail': ''.join(traceback.format_exception(*err))})

    def addError(self, test, err):
        super().addError(test, err)
        self.rows.append({'id': test.id(), 'status': 'ERROR', 'detail': ''.join(traceback.format_exception(*err))})


modules = ('test_http_api', 'test_oauth_stage1', 'test_oauth_stage2', 'test_oauth_refresh', 'test_scheduler', 'test_open_finance_sync', 'test_open_finance_query', 'test_open_finance_unicode_http', 'test_pluggy_client')
suite = unittest.TestSuite()
for name in modules:
    suite.addTests(unittest.defaultTestLoader.loadTestsFromModule(importlib.import_module('tests.' + name)))
started = time.monotonic()
stream = io.StringIO()
result = unittest.TextTestRunner(stream=stream, verbosity=2, resultclass=Result).run(suite)
child_results = []
for child in children:
    alive = child.poll() is None
    if alive:
        child.terminate()
        child.wait(timeout=10)
    child_results.append({'pid':child.pid,'exit_code':child.returncode,'forced_harness_cleanup':alive})
(target / 'tests.log').write_text(stream.getvalue(), encoding='utf-8')
report = {'tests': result.testsRun, 'failures': len(result.failures), 'errors': len(result.errors), 'skips': len(result.skipped),
          'seconds': round(time.monotonic() - started, 3), 'individual': result.rows,
          'product': str(product), 'modules': modules, 'python': sys.version,
          'schema_expectations_requalified': (historical.parent/'SCHEMA10_EXPECTATION_ADAPTATIONS.json').is_file(),
          'children':child_results,'non_daemon_threads':[t.name for t in threading.enumerate() if t is not threading.main_thread() and not t.daemon],
          'fixture_files_remaining': [p.name for p in fixtures.iterdir()]}
(target / 'RESULTS.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
print(json.dumps({k: v for k, v in report.items() if k != 'individual'}), flush=True)
raise SystemExit(0 if result.wasSuccessful() and not result.skipped and not any(p['forced_harness_cleanup'] for p in child_results) and not report['non_daemon_threads'] else 1)
