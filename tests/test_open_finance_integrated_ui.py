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
from finance_v2.open_finance_coverage import sync_full
from finance_v2.db import connect
from contextlib import closing
from urllib.parse import urlsplit, parse_qs

class Quiet(WSGIRequestHandler):
    def log_message(self, *args): pass

class BrowserIntegration(unittest.TestCase):
    def test_synthetic_real_backend(self):
        case=fixture.CoverageTests(methodName='test_all_products_projection_history_and_financial_preservation')
        case.setUp()
        try:
            case.config=replace(case.config,institution='Banco sintético')
            second=replace(case.config,id='bank-other',institution='Outra instituição sintética',client_id='synthetic-other-client')
            archived=replace(case.config,id='bank-history',institution='Instituição arquivada sintética',client_id='synthetic-history-client')
            case.settings=replace(case.settings,pluggy_connections=(case.config,second,archived))
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
                payload=repair(payload)
                if args[1].startswith('/accounts?'):
                    extra=dict(payload['results'][1]);extra.update(id='account-CREDIT-2',name='Segundo cartão sintético',creditData=None)
                    payload['results'].append(extra);payload['total']=len(payload['results'])
                if args[1].startswith('/bills?'):
                    account=parse_qs(urlsplit(args[1]).query).get('accountId',[''])[0]
                    suffix='-second' if account=='account-CREDIT-2' else ''
                    payload['results'][0]['id']='bill-test'+suffix
                    extra=dict(payload['results'][0]);extra.update(id='bill-old'+suffix,dueDate='2026-09-10',totalAmount=50)
                    missing=dict(payload['results'][0]);missing.update(id='bill-no-date'+suffix);missing.pop('dueDate',None)
                    payload['results'].extend((extra,missing));payload['total']=len(payload['results'])
                if args[1].startswith('/investments?'):
                    first=payload['results'][0];first.update(date='2025-01-01',updatedAt='2026-10-01T12:00:00Z')
                    usd=dict(first);usd.update(id='investment-usd',type='STOCK',currencyCode='USD',balance=25)
                    missing=dict(first);missing.update(id='investment-missing',type='FUND');missing.pop('balance',None)
                    payload['results'].extend((usd,missing));payload['total']=len(payload['results'])
                if '/v2/transactions?' in args[1] and parse_qs(urlsplit(args[1]).query).get('accountId')==['account-CREDIT']:
                    payload['results'][0]['creditCardMetadata']['billId']='bill-test'
                    other=dict(payload['results'][0]);other['id']='unlinked-card-transaction';other['description']='Sem vínculo sintético';other['creditCardMetadata']={}
                    payload['results'].append(other)
                return status, payload
            case.service=OpenFinanceService(case.settings,client_factory=lambda config: PluggyClient(config,send=synthetic_send,sleep=lambda _:None))
            for connection in case.settings.pluggy_connections:
                run=sync_full(case.service,connection.id,actor='UI:local')
                self.assertEqual(run['state'],'SUCCEEDED',run)
            with closing(connect(case.db)) as db:
                db.execute("UPDATE of_connection_registry SET lifecycle='ARCHIVED' WHERE connection_id='bank-history'")
                db.commit()
            status, data=case.request('/api/v2/open-finance/analytics?currency=BRL')
            self.assertEqual(status,200,data)
            self.assertEqual(data['positions']['investments']['value'],'400')
            self.assertEqual(data['positions']['investments']['unavailable'],2)
            status, usd_data=case.request('/api/v2/open-finance/analytics?currency=USD&connection_id=bank-other')
            self.assertEqual(status,200,usd_data)
            self.assertEqual(usd_data['positions']['investments']['value'],'25')
            self.assertEqual(usd_data['positions']['investments']['items'][0]['institution'],'Outra instituição sintética')
            self.assertEqual(usd_data['positions']['investments']['items'][0]['reference_date'],'2025-01-01')
            self.assertEqual(usd_data['positions']['investments']['items'][0]['provider_updated_at'],'2026-10-01T12:00:00Z')
            status,catalog=case.request('/api/v2/open-finance/catalogs')
            self.assertEqual(status,200)
            self.assertTrue(next(c for c in catalog['connections'] if c['id']=='bank-history')['historical'])
            status,historical=case.request('/api/v2/open-finance/analytics?currency=BRL&history=1&connection_id=bank-history')
            self.assertEqual(status,200,historical)
            self.assertIsNone(historical['positions']['accounts']['value'])
            self.assertGreater(historical['total'],0)
            status,cards=case.request('/api/v2/open-finance/domain?resource=accounts&type=CREDIT&connection_id=bank-other')
            self.assertEqual(status,200,cards)
            self.assertEqual(cards['total'],2)
            status,bills=case.request('/api/v2/open-finance/domain?resource=bills&connection_id=bank-other&parent_id=account-CREDIT')
            self.assertEqual(status,200,bills)
            self.assertEqual(bills['total'],3)
            missing=next(item for item in bills['items'] if item['identity']['external_id']=='bill-no-date')
            self.assertTrue(any(field['key']=='dueDate' and field['state']=='ABSENT' for field in missing['fields']))
            status,old_bill=case.request('/api/v2/open-finance/analytics?connection_id=bank-other&account_id=account-CREDIT&product=CREDIT&status=ALL&bill_id=bill-old')
            self.assertEqual(status,200,old_bill)
            self.assertEqual(old_bill['total'],0)
            status,wrong_card=case.request('/api/v2/open-finance/analytics?connection_id=bank-other&account_id=account-CREDIT-2&product=CREDIT&bill_id=bill-old')
            self.assertEqual(status,404,wrong_card)
            status,all_card=case.request('/api/v2/open-finance/analytics?connection_id=bank-other&account_id=account-CREDIT&product=CREDIT&status=ALL')
            self.assertEqual(status,200,all_card)
            self.assertEqual(all_card['total'],2)
            self.assertTrue(any(item['description']=='Sem vínculo sintético' for item in all_card['items']))
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
