"""Browser against the real WSGI app and a disposable synthetic database."""
from dataclasses import replace
import os
import subprocess
import threading
import unittest
from wsgiref.simple_server import make_server

import test_snaptrade_036 as fixtures
from test_open_finance_integrated_ui import Quiet
from finance_v2.api import Application


class SnapTradeBrowser(unittest.TestCase):
    def test_unified_portfolio_and_connections(self):
        case=fixtures.SnapTradeTests('test_discovery_currency_and_cash_once')
        self.addCleanup(case.doCleanups)
        case.setUp()
        case.test_discovery_currency_and_cash_once()
        app=Application(replace(case.settings,ui_token='synthetic-snaptrade-browser-owner'),case.clock)
        app.snaptrade_reader_factory=case.broker.factory
        case.case.fixture.no_network.stop()
        server=make_server('127.0.0.1',0,app,handler_class=Quiet)
        thread=threading.Thread(target=server.serve_forever,daemon=True)
        thread.start()
        try:
            proc=subprocess.run(['node','tests/open_finance_snaptrade_ui.cjs',f'http://127.0.0.1:{server.server_port}'],
                capture_output=True,text=True,encoding='utf-8',timeout=120 if os.environ.get('OF_SNAPTRADE_SHOTS') else 75)
            self.assertEqual(proc.returncode,0,proc.stdout+proc.stderr)
            self.assertIn('PASS:',proc.stdout)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(5)

if __name__=='__main__':
    unittest.main()
