"""Exercise the real application with a synthetic provider, WSGI and SQLite."""
import os
import subprocess
import threading
import unittest
from wsgiref.simple_server import make_server

from finance_v2.api import Application
from test_open_finance_integrated_ui import Quiet
import test_open_finance_classification as fixture


class BrowserClassification(unittest.TestCase):
    def test_owner_workflow(self):
        data=fixture.ClassificationTest('test_automatic_investment_example_and_coverage')
        self.addCleanup(data.doCleanups)
        data.setUp()
        provider=data.fixture.provider
        original=provider.send
        reference='2026-09-25'
        position=201
        def send(method,path,*args):
            status,payload=original(method,path,*args)
            if path.startswith('/investments?') and status==200:
                payload['results'][0].update(date=reference,balance=position)
            return status,payload
        provider.send=send
        self.assertEqual(data.fixture.sync()['state'],'SUCCEEDED')
        reference='2026-10-25'
        position=235
        self.assertEqual(data.fixture.sync()['state'],'SUCCEEDED')
        data.write("UPDATE of_connection_registry SET label='Itaú' WHERE connection_id='bank-test'")
        for id,desc,value,direction in [
            ('apply-auto','Aplicação APL APLIC AUT MAIS',10000,'DEBIT'),
            ('redeem-auto','Resgate RES APLIC AUT MAIS',2500,'CREDIT'),
            ('income-auto','Rendimentos REND PAGO APLIC AUT MAIS','3.75','CREDIT'),
            ('income-div','Entrada COR DIVIDENDOS ABCD3','18.59','CREDIT'),
            ('income-jscp','Entrada COR JSCP WXYZ11','29.70','CREDIT'),
            ('shop','Compra de mercado confirmada','1005.55','DEBIT'),
            ('b3','Saída COR OPERACOES B3','41.25','DEBIT'),
        ]:
            data.tx(id,desc,value,direction)
        for n in range(12):
            data.tx(f'pay-{n:02}','Crédito de empregador fictício','2015.55')
        data.label('shop','EXPENSE','Mercado')
        data.write("""UPDATE of_resource_records SET payload_json=json_set(payload_json,'$.name','Cartão sintético 4111 2222 3333 4444',
            '$.creditData.status','ACTIVE','$.creditData.creditLimit',9999.00) WHERE resource='accounts' AND external_id='account-CREDIT'""")
        data.fixture.no_network.stop()
        server=make_server('127.0.0.1',0,Application(data.settings),handler_class=Quiet)
        thread=threading.Thread(target=server.serve_forever,daemon=True)
        thread.start()
        try:
            run=subprocess.run(['node','tests/open_finance_classification_ui.cjs',f'http://127.0.0.1:{server.server_port}'],
                               capture_output=True,text=True,encoding='utf-8',
                               timeout=120 if os.environ.get('OF_CLASSIFICATION_SHOTS') else 60)
            self.assertEqual(run.returncode,0,run.stderr)
            self.assertIn('PASS:',run.stdout)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(5)
