"""Abrupt synthetic interruption; the parent owns and bounds this process."""
import json
import os
from pathlib import Path
import sqlite3
import sys
from support import settings, Providers, connect
from finance_v2.open_finance import OpenFinanceService
from finance_v2.open_finance_coverage import sync_full_automatic

database = Path(sys.argv[1])
kind = sys.argv[2]
config = settings(database)
providers = Providers(config)
service = OpenFinanceService(config, client_factory=providers.factory)
checks = 0
def crash_marker(active_write):
    print(json.dumps({'phase':kind,'active_write_confirmed':active_write,'exit_code':71}), flush=True)
    os._exit(71)

def check():
    global checks
    checks += 1
    if kind == 'uncommitted-page' and checks == 3:
        probe = connect(database, 0)
        try:
            try:
                probe.execute('BEGIN IMMEDIATE')
            except sqlite3.OperationalError as exc:
                assert 'locked' in str(exc).lower()
                crash_marker(True)
            else:
                raise AssertionError('NO_ACTIVE_WRITE_LOCK')
        finally:
            probe.close()

if kind == 'committed-pages':
    provider = providers.banks['itau']
    original = provider.send
    def send(method, path, headers, body, timeout):
        if path.startswith('/loans'):
            crash_marker(False)
        return original(method, path, headers, body, timeout)
    provider.send = send

sync_full_automatic(service, 'itau', check=check)
raise AssertionError('INTERRUPTION_NOT_REACHED')
