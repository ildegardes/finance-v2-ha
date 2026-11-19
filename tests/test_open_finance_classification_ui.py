"""Exercise the real application with a synthetic provider, WSGI and SQLite."""
import os
import json
from dataclasses import replace
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
        data.write("""UPDATE of_resource_records SET payload_json=json_set(payload_json,'$.name','Itaú Personnalité The One Mastercard 4111 2222 3333 4444',
            '$.creditData.status','ACTIVE','$.creditData.creditLimit',9999.00) WHERE resource='accounts' AND external_id='account-CREDIT'""")
        data.write("""WITH RECURSIVE n(x) AS (SELECT 1 UNION ALL SELECT x+1 FROM n WHERE x<119)
            INSERT INTO of_resource_records(connection_id,resource,parent_id,external_id,payload_json,payload_hash,
                state,first_run_id,last_run_id,observed_at)
            SELECT r.connection_id,'transactions',r.external_id,'evidence-'||n.x,
              json_object('id','evidence-'||n.x,'description','Movimento de evidência '||n.x,'type','DEBIT',
              'status','POSTED','date','2026-10-20','currencyCode','BRL','category','Livrarias','amount',printf('%.2f',n.x)),
              r.payload_hash,'PRESENT',r.first_run_id,r.last_run_id,r.observed_at
            FROM of_resource_records r CROSS JOIN n WHERE r.resource='accounts' AND r.external_id='account-BANK'""")
        instant='2026-10-25T12:00:00Z'
        data.write("INSERT INTO of_connections(id,institution,enabled,binding_hash,updated_at) VALUES ('other-bank','Santander',1,?,?)",
                   ('f'*64,instant))
        data.write("INSERT INTO of_sync_runs(id,connection_id,actor,started_at,finished_at,state) VALUES ('ba25eb61ceff44bd98586f55b0c90392','other-bank','UI:local',?,?,'SUCCEEDED')",
                   (instant,instant))
        for index,name in enumerate(('Itaú Personnalité The One Mastercard 4111 2222 3333 4444','Azul Itaú Visa Infinite',
                                     'Santander Unlimited Mastercard Black','Santander Unlimited Visa Infinite')):
            credit={'status':'ACTIVE','holderType':'MAIN','brand':'VISA' if 'Visa' in name else 'MASTERCARD',
                    'disaggregatedCreditLimits':[{'identificationNumber':str(index),'creditLineLimitType':'LIMITE_CREDITO_TOTAL',
                    'consolidationType':'INDIVIDUAL','usedAmount':125.5+index,'usedAmountCurrencyCode':'BRL',
                    'limitAmount':4000,'limitAmountCurrencyCode':'BRL','isLimitFlexible':False}]}
            if index==0:
                data.write("UPDATE of_resource_records SET observed_at=?,payload_json=json_set(payload_json,'$.creditData',json(?)) WHERE resource='accounts' AND external_id='account-CREDIT'",
                           (instant,json.dumps(credit)))
                continue
            payload=json.dumps({'type':'CREDIT','currencyCode':'BRL','name':name,'date':'2026-10-25','balance':125.5+index,'creditData':credit})
            if index==1:
                data.write("""INSERT INTO of_resource_records SELECT connection_id,resource,parent_id,'test-card-extra',?,
                    payload_hash,'PRESENT',first_run_id,last_run_id,? FROM of_resource_records WHERE external_id='account-CREDIT'""",(payload,instant))
            else:
                data.write("""INSERT INTO of_resource_records VALUES
                    ('other-bank','accounts','',?,?,?,'PRESENT','ba25eb61ceff44bd98586f55b0c90392','ba25eb61ceff44bd98586f55b0c90392',?)""",(f'card-{index}',payload,'a'*64,instant))
        original_settings=data.settings
        settings=replace(original_settings,pluggy_connections=(
            replace(original_settings.pluggy_connections[0],auto_sync_enabled=True),
            replace(original_settings.pluggy_connections[0],id='other-bank',institution='Santander',auto_sync_enabled=True)))
        data.fixture.no_network.stop()
        server=make_server('127.0.0.1',0,Application(settings),handler_class=Quiet)
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
