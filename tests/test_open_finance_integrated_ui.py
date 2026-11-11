"""Real WSGI and disposable synthetic SQLite, never production data."""
import subprocess
from dataclasses import replace
import threading
import unittest
from wsgiref.simple_server import make_server, WSGIRequestHandler
import test_full_coverage as fixture
from finance_v2.api import Application
from finance_v2.open_finance import OpenFinanceService
from finance_v2.pluggy_client import PluggyClient

class Quiet(WSGIRequestHandler):
    def log_message(self, *args): pass

class BrowserIntegration(unittest.TestCase):
    def test_synthetic_real_backend(self):
        case=fixture.CoverageTests(methodName='test_all_products_projection_history_and_financial_preservation')
        case.setUp()
        try:
            case.config=replace(case.config,institution='Banco sintético')
            case.settings=replace(case.settings,pluggy_connections=(case.config,))
            original_send=case.provider.send
            def repair(value):
                if isinstance(value,str) and 'Ã' in value:
                    try: return value.encode('latin-1').decode('utf-8')
                    except UnicodeError: return value
                if isinstance(value,list): return [repair(x) for x in value]
                if isinstance(value,dict): return {k:repair(v) for k,v in value.items()}
                return value
            def synthetic_send(*args):
                status, payload=original_send(*args)
                return status, repair(payload)
            case.service=OpenFinanceService(case.settings,client_factory=lambda config: PluggyClient(config,send=synthetic_send,sleep=lambda _:None))
            case.sync()
            case.no_network.stop()  # The browser and server communicate only on loopback.
            server=make_server('127.0.0.1',0,Application(case.settings),handler_class=Quiet)
            thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            try:
                proc=subprocess.run(['node','tests/open_finance_integrated_ui.cjs',f'http://127.0.0.1:{server.server_port}'],capture_output=True,text=True,timeout=40)
                self.assertEqual(proc.returncode,0,proc.stderr)
                self.assertIn('PASS:',proc.stdout)
            finally:
                server.shutdown();server.server_close();thread.join(5)
        finally:
            case.doCleanups()

if __name__=='__main__': unittest.main()
