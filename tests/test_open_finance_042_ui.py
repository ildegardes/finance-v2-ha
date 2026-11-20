"""Loopback browser qualification with disposable synthetic SQLite."""
from contextlib import closing
from dataclasses import replace
from pathlib import Path
import subprocess
import threading
import unittest
from wsgiref.simple_server import make_server

from finance_v2.api import Application
from finance_v2.db import connect
from test_open_finance_042 import OpenBalanceFixture
from test_open_finance_integrated_ui import Quiet


class OpenBalanceBrowser(OpenBalanceFixture, unittest.TestCase):
    def test_open_balances_policy_and_brand(self):
        self.assertEqual([run['state'] for run in self.sync()], ['SUCCEEDED','SUCCEEDED'])
        self.rates()
        with closing(connect(self.case.db)) as db:
            db.execute("INSERT INTO of_connections(id,institution,enabled,binding_hash,updated_at) VALUES (?, ?, 0, ?, ?)",
                       ('archived-fixture','Arquivo sintético','f'*64,'2026-10-21T12:00:00Z'))
            db.execute("INSERT INTO of_connection_registry(connection_id,source,lifecycle,label,updated_at) "
                       "VALUES (?,'LEGACY','ARCHIVED',?,?)",
                       ('archived-fixture','Arquivo sintético','2026-10-21T12:00:00Z'))
        self.case.no_network.stop()
        server=make_server('127.0.0.1',0,Application(self.case.settings),handler_class=Quiet)
        origin=f'http://127.0.0.1:{server.server_port}'
        settings=replace(self.case.settings,pluggy_admin_origin=origin,open_finance_auto_sync_allowed=True)
        server.set_app(Application(settings))
        thread=threading.Thread(target=server.serve_forever,daemon=True)
        thread.start()
        try:
            run=subprocess.run(['node',str(Path(__file__).with_suffix('.cjs')),origin],capture_output=True,
                               text=True,encoding='utf-8',timeout=90)
            self.assertEqual(run.returncode,0,run.stdout+run.stderr)
            self.assertIn('PASS:',run.stdout)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(5)
