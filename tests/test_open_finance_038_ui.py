import subprocess
import threading
import unittest
from wsgiref.simple_server import make_server

from finance_v2.api import Application
from test_open_finance_integrated_ui import Quiet
import test_open_finance_038 as features


class DashboardBrowser(unittest.TestCase):
    def test_currency_navigation_history_and_privacy(self):
        self.exercise_dashboard()

    def test_native_amounts_when_fx_is_absent(self):
        self.exercise_dashboard(missing_fx=True)

    def exercise_dashboard(self,missing_fx=False):
        scenario=features.DashboardTests('test_original_and_converted_kpis_card_dedup_and_economic_income')
        scenario.setUp()
        self.addCleanup(scenario.doCleanups)
        case=scenario.fixture
        if missing_fx:
            case.case.write('DELETE FROM portfolio_fx_rates')
            case.case.write('UPDATE st_balances SET reference_at=NULL')
        case.case.fixture.no_network.stop()
        app=Application(case.settings,case.clock)
        app.snaptrade_reader_factory=case.broker.factory
        server=make_server('127.0.0.1',0,app,handler_class=Quiet)
        thread=threading.Thread(target=server.serve_forever,daemon=True)
        thread.start()
        try:
            args=['node','tests/open_finance_consolidation_ui.cjs',f'http://127.0.0.1:{server.server_port}']
            if missing_fx:
                args.append('--missing-fx')
            test=subprocess.run(args,capture_output=True,encoding='utf-8',timeout=95)
            self.assertEqual(test.returncode,0,test.stderr+test.stdout)
            self.assertIn('PASS:',test.stdout)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(5)


if __name__=='__main__':
    unittest.main()
