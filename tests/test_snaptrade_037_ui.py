"""The proxy fallback is exercised with real WSGI, SQLite and the signed SDK."""
import subprocess
import threading
import unittest
from wsgiref.simple_server import make_server

import test_snaptrade_037 as fixtures
from test_open_finance_integrated_ui import Quiet


class SnapTradeDiagnosticsBrowser(unittest.TestCase):
    def test_proxy_can_replace_the_failure_body(self):
        case=fixtures.PersonalContract('test_sdk_discovery_and_import_official_contract')
        case.setUp()
        self.addCleanup(case.doCleanups)
        self.assertEqual(case.run_sdk()['state'],'AVAILABLE')
        case.overrides['accounts']=(200,{},b'{"results":null}')
        server=make_server('127.0.0.1',0,case.app(),handler_class=Quiet)
        thread=threading.Thread(target=server.serve_forever,daemon=True)
        thread.start()
        try:
            browser=subprocess.run(['node','tests/open_finance_snaptrade_diagnostics_ui.cjs',
                                    f'http://127.0.0.1:{server.server_port}'],
                                   capture_output=True,text=True,encoding='utf-8',timeout=60)
            self.assertEqual(browser.returncode,0,browser.stderr+browser.stdout)
            self.assertIn('PASS:',browser.stdout)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(5)


if __name__=='__main__':
    unittest.main()
