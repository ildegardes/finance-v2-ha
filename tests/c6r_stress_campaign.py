"""Run the four-connection synthetic C6R scenario with sanitized failure traces.

Writes one JSON object per iteration to stdout. No provider payload, exception
message, identifier, credential or database content is included in the report.
"""
import argparse
import json
import sqlite3
import threading
import time
import traceback
import unittest
from pathlib import Path

from test_gate_c6r import ConcurrencyTests


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--iterations', type=int, default=100)
    args = parser.parse_args()
    if not 1 <= args.iterations <= 10000:
        parser.error('iterations must be between 1 and 10000')
    failures = 0
    for number in range(1, args.iterations + 1):
        caught = []
        lock = threading.Lock()

        def trace_frame(frame, event, arg):
            if event == 'exception':
                cls, exc, tb = arg
                if issubclass(cls, (sqlite3.Error, ValueError, RuntimeError)):
                    stack = [f'{Path(x.filename).name}:{x.name}:{x.lineno}'
                             for x in traceback.extract_tb(tb)
                             if 'finance_v2' in x.filename]
                    with lock:
                        caught.append({'type': cls.__name__, 'sqlite_code': getattr(exc, 'sqlite_errorcode', None),
                                       'stack': stack})
            return trace_frame

        def trace_calls(frame, event, arg):
            return trace_frame if event == 'call' and frame.f_code.co_name == '_sync_full' else None

        threading.settrace(trace_calls)
        case = ConcurrencyTests('test_four_concurrent_items_and_idempotent_reimport')
        result = unittest.TestResult()
        start = time.monotonic()
        try:
            case.run(result)
        finally:
            threading.settrace(None)
        success = result.wasSuccessful()
        failures += not success
        failures_text = '\n'.join(text for _, text in result.failures + result.errors)
        timeout = 'TimeoutError' in failures_text
        codes = [code for code in ('COVERAGE_INVALID_OR_STORAGE_FAILURE', 'STORAGE_BUSY',
                                    'COVERAGE_INTERNAL_FAILURE', 'SYNC_BUSY') if code in failures_text]
        report = {'iteration': number, 'result': 'PASS' if success else 'TIMEOUT' if timeout else 'FAIL',
                  'duration_seconds': round(time.monotonic() - start, 3),
                  'integrity_and_idempotence': 'PASS' if success else 'NOT_ESTABLISHED',
                  'error_codes': codes,
                  'sanitized_exceptions': [] if success else caught,
                  'failure_count': len(result.failures), 'error_count': len(result.errors)}
        print(json.dumps(report, sort_keys=True), flush=True)
    print(json.dumps({'summary': True, 'iterations': args.iterations,
                      'pass': args.iterations - failures, 'fail': failures}, sort_keys=True), flush=True)
    return 1 if failures else 0


if __name__ == '__main__':
    raise SystemExit(main())
