"""Real browser against the disposable recovery fixture and WSGI."""
from pathlib import Path
import os
import subprocess
import threading
import unittest
from wsgiref.simple_server import make_server

from finance_v2.api import Application
from test_open_finance_041 import RecoveryFixture
from test_open_finance_integrated_ui import Quiet


class RecoveryBrowser(RecoveryFixture, unittest.TestCase):
    def test_cards_bills_and_movements(self):
        self.assertEqual([run['state'] for run in self.sync()], ['SUCCEEDED'] * 2)
        self.case.no_network.stop()
        server = make_server('127.0.0.1', 0, Application(self.case.settings), handler_class=Quiet)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            script = Path(__file__).with_suffix('.cjs')
            run = subprocess.run(['node', str(script), f'http://127.0.0.1:{server.server_port}'],
                                 capture_output=True, text=True, encoding='utf-8', timeout=130)
            self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
            self.assertIn('PASS:', run.stdout)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(5)
