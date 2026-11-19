import json
import time
import unittest
from contextlib import closing
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

from finance_v2.db import connect
from finance_v2 import migrations
from finance_v2.open_finance import OpenFinanceService, SyncError
from finance_v2.open_finance_analytics import _amount, analytics
from finance_v2.open_finance_coverage import sync_full_automatic
from finance_v2.open_finance_insights import card_insights
from finance_v2.open_finance_schedule import HOURS, report as schedule_report, save
from finance_v2.domain.clock import FixedClock
import test_open_finance_classification as fixtures


class Release35Tests(unittest.TestCase):
    def setUp(self):
        self.case=fixtures.ClassificationTest('test_automatic_investment_example_and_coverage')
        self.addCleanup(self.case.doCleanups)
        self.case.setUp()
        self.case.write("UPDATE of_connection_registry SET label='Itaú' WHERE connection_id='bank-test'")
        self.case.write("""UPDATE of_resource_records SET state='NOT_SEEN'
            WHERE resource='transactions'""")

    def provider_expense(self,key,label,amount,description):
        case=self.case
        case.tx(key,description,amount,'DEBIT')
        case.write("""UPDATE of_resource_records SET payload_json=json_set(json_remove(payload_json,'$.categoryId'),'$.category',?)
                      WHERE resource='transactions' AND external_id=?""",(label,key))

    def test_provider_expenses_are_economic_without_manual_review(self):
        case=self.case
        for key,label,amount in [('school','Educação infantil','51.25'),('books','Livrarias','19.75'),
                                 ('power','Energia elétrica','29.00'),('service','Serviços','50')]:
            self.provider_expense(key,label,amount,'Débito identificado '+key)
        self.provider_expense('school','Kindergarten','51.25','Débito identificado school')
        self.provider_expense('books','Bookstore','19.75','Débito identificado books')
        case.tx('payroll','Crédito de folha sintético','3500')
        case.label('payroll','SALARY','Salário')
        data=case.report()
        self.assertEqual(data['insights']['known']['outgoing'],'150.00')
        self.assertEqual(data['insights']['known']['net'],'3350.00')
        ranked=data['economic_category_ranking']
        self.assertEqual({r['name'] for r in ranked},{'Kindergarten','Bookstore','Energia elétrica','Serviços'})
        for row in ranked:
            scoped=case.report({'direction':['outgoing'],'bucket':['operating'],'effective_key':[row['key']]})
            self.assertEqual(scoped['total'],row['count'])
            self.assertEqual(scoped['flow']['BANK']['outgoing'],row['value'])
            self.assertTrue(all(item['classification']['review']=='UNCLASSIFIED' and
                item['economic_recognition']['source']=='PROVIDER_CATEGORY' for item in scoped['items']))

    def test_annual_gross_reconciliation_and_card_subtotals(self):
        case=self.case
        case.tx('salary','Crédito de salário','38000')
        self.provider_expense('power','Energia elétrica','150.33','Conta de energia')
        self.provider_expense('ambiguous-pix','Serviços','400.55','PIX enviado sem finalidade')
        case.tx('pix-credit','PIX recebido','999.00')
        case.tx('transfer','TED para conta sem vínculo','90.01','DEBIT')
        case.tx('investment','Saída COR OPERACOES B3','1234.80','DEBIT')
        case.tx('bill','Debito automatico cartao itau the one','3000.00','DEBIT')
        for month in range(1,13):
            case.tx(f'apply-{month}','Aplicação APL APLIC AUT MAIS','12000','DEBIT')
            case.tx(f'redeem-{month}','Resgate RES APLIC AUT MAIS','11800')
            case.write("UPDATE of_resource_records SET payload_json=json_set(payload_json,'$.date',?) WHERE external_id IN (?,?)",
                       (f'2026-{month:02d}-04',f'apply-{month}',f'redeem-{month}'))
        for n in range(35):
            case.tx(f'yield-{n}','Rendimentos REND PAGO APLIC AUT MAIS','1.62' if n<34 else '1.77')
        case.tx('purchase','Compra no cartão','120.75','DEBIT')
        case.tx('installment','Parcela no cartão','40.00','DEBIT')
        case.tx('credit','Crédito no cartão','-10.00')
        case.tx('card-payment','Pagamento lançado no cartão','-3000.00')
        for key,nature in [('purchase','EXPENSE'),('installment','EXPENSE'),('credit','REVERSAL'),('card-payment','CARD_PAYMENT')]:
            # Persist independent card evidence and its exact application identity.
            metadata = {'totalInstallments':3,'installmentNumber':1} if key=='installment' else {}
            case.write("""UPDATE of_resource_records SET parent_id='account-CREDIT',
                payload_json=json_set(payload_json,'$.accountId','account-CREDIT','$.creditCardMetadata',json(?))
                WHERE external_id=?""",(json.dumps(metadata),key))
            case.request('manual',{'identity':{'connection_id':'bank-test','account_id':'account-CREDIT','transaction_id':key},
                'event':None,'decision':{'category':'Categoria sintética','nature':nature}})
        report=case.report({'start':['2026-01-01'],'end':['2026-12-31'],'product':['ALL']})
        known=report['insights']['known']
        self.assertEqual(Decimal(known['incoming']),Decimal('38056.85'))
        self.assertEqual(Decimal(known['outgoing']),Decimal('150.33'))
        self.assertEqual(Decimal(known['net']),Decimal('37906.52'))
        automatic=report['insights']['automatic']
        self.assertEqual(automatic['counts']['credited'],35)
        self.assertEqual(automatic['value']['credited'],'56.85')
        self.assertEqual(automatic['value']['applied'],'144000')
        self.assertEqual(automatic['value']['redeemed'],'141600')
        self.assertEqual(report['insights']['card_activity']['purchases'],'160.75')
        self.assertEqual(report['insights']['card_activity']['credits'],'10.00')
        scoped=case.report({'product':['CREDIT'],'card_economic':['recognized_purchase']})
        self.assertEqual({row['external_id'] for row in scoped['items']},{'purchase','installment'})
        for direction in ('incoming','outgoing'):
            parts=[Decimal(row['value']) for row in report['insights']['breakdown'] if row['direction']==direction and row['value'] is not None]
            self.assertEqual(sum(parts),Decimal(report['flow']['BANK'][direction]))

    def test_four_card_balances_from_two_banks_and_partial_coverage(self):
        views={'itau':SimpleNamespace(institution='Itaú'),'santander':SimpleNamespace(institution='Santander')}
        accounts={}
        for index in range(4):
            bank='itau' if index<2 else 'santander'
            accounts[bank,str(index)]={'observed_at':'2026-10-20T10:10:10Z','last_run_id':bank+'run','data':{
                'type':'CREDIT','currencyCode':'BRL','name':'Cartão sintético','balance':index,
                'creditData':{'status':'ACTIVE','holderType':'MAIN','disaggregatedCreditLimits':[{
                    'creditLineLimitType':'LIMITE_CREDITO_TOTAL','consolidationType':'INDIVIDUAL',
                    'usedAmountCurrencyCode':'BRL','limitAmountCurrencyCode':'BRL','limitAmount':1000,
                    'usedAmount':index*100,'identificationNumber':str(index),'isLimitFlexible':False}]}}}
        def read():
            return card_insights(accounts,views.keys(),views,'BRL',_amount,'2026-11-01')
        self.assertEqual((read()['consolidated'],read()['included_count']),('600',4))
        accounts['santander','3']['data']['creditData']['holderType']='ADDITIONAL'
        data=read()
        self.assertEqual((data['consolidated'],data['included_count']),('300',3))
        self.assertEqual(data['items'][0]['used'],'0')
        self.assertIsNone(data['limit'])
        self.assertEqual(data['items'][3]['consolidation_reason'],'OBLIGATION_UNVERIFIED')
        accounts['itau','1']['data']['date']='2026-10-19'
        self.assertEqual(read()['items'][1]['consolidation_reason'],'REFERENCE_DATE_MISMATCH')
        accounts['santander','2']['data']['currencyCode']='USD'
        self.assertEqual((read()['consolidated'],read()['included_count']),('0',1))

    def test_shared_limits_can_have_independent_reported_account_balances(self):
        views={'itau':SimpleNamespace(institution='Itaú'),'santander':SimpleNamespace(institution='Santander')}
        accounts={}
        for bank,amount in (('itau','12.15'),('santander','0.00')):
            accounts[bank,'card']={'observed_at':'2026-10-20T10:10:10Z','last_run_id':bank+'run','data':{
                'type':'CREDIT','currencyCode':'BRL','name':'Cartão de teste','balance':amount,'number':'account-'+bank,
                'creditData':{'status':'ACTIVE','holderType':'MAIN','disaggregatedCreditLimits':[{
                    'creditLineLimitType':'LIMITE_CREDITO_TOTAL','consolidationType':'CONSOLIDATED',
                    'usedAmountCurrencyCode':'BRL','limitAmountCurrencyCode':'BRL','limitAmount':1000,'usedAmount':200}]}}}
        data=card_insights(accounts,views.keys(),views,'BRL',_amount,'2026-11-01')
        self.assertEqual((data['consolidated'],data['included_count'],data['basis']),('12.15',2,'ACCOUNT_BALANCE'))
        self.assertIsNone(data['limit'])
        self.assertIsNone(data['used'])
        self.assertNotIn('account-itau',json.dumps(data))

    def test_page_sizes_and_six_global_orders(self):
        case=self.case
        case.write("UPDATE of_resource_records SET state='NOT_SEEN' WHERE resource='transactions' AND parent_id='account-BANK'")
        self.seed_volume(119)
        seen={}
        for order in ('date_desc','date_asc','value_desc','value_asc','description_asc','description_desc'):
            rows=case.report({'sort':[order],'page_size':['250']})['items']
            seen[order]=[item['external_id'] for item in rows]
            self.assertEqual(len(set(seen[order])),119)
        self.assertEqual(seen['value_desc'][0],'bulk-119')
        self.assertEqual(seen['value_asc'][0],'bulk-1')
        self.assertEqual(seen['date_desc'],list(reversed(seen['date_asc'])))
        self.assertTrue(seen['description_asc'][0].startswith('bulk-'))
        self.assertTrue(int(seen['description_asc'][0].split('-')[1])%2==0)
        self.assertEqual(seen['date_asc'][0],'bulk-1')
        for size in (25,50,100,250,500):
            first=case.report({'page_size':[str(size)],'sort':['value_desc']})
            self.assertEqual(first['total'],119)
            self.assertEqual(len(first['items']),min(size,119))
            self.assertEqual(first['flow']['BANK']['outgoing'],'7140.00')
        first=case.report({'page_size':['100'],'sort':['value_desc']})
        second=case.report({'page_size':['100'],'page':['2'],'sort':['value_desc']})
        self.assertEqual(first['total_pages'],2)
        self.assertEqual([row['external_id'] for row in first['items']+second['items']],seen['value_desc'])
        self.assertEqual(case.report({'page':['200']})['items'],[])
        for unsafe in ({'sort':['unknown']},{'page_size':['501']},{'currency':['ALL_CURRENCIES']}):
            with self.assertRaises(SyncError):
                case.report(unsafe)

    def seed_volume(self,count):
        self.case.write("""WITH RECURSIVE n(x) AS (SELECT 1 UNION ALL SELECT x+1 FROM n WHERE x<?)
            INSERT INTO of_resource_records(connection_id,resource,parent_id,external_id,payload_json,payload_hash,
                state,first_run_id,last_run_id,observed_at)
            SELECT t.connection_id,'transactions',t.external_id,'bulk-'||n.x,
                json_object('id','bulk-'||n.x,'description',CASE WHEN n.x % 2=0 THEN 'Ábaco ' ELSE 'Zebra ' END||n.x,
                'type','DEBIT','status','POSTED','date','2026-10-20','currencyCode','BRL','category','Livrarias',
                'amount',printf('%.2f', n.x)),t.payload_hash,'PRESENT',t.first_run_id,t.last_run_id,t.observed_at
            FROM of_resource_records t CROSS JOIN n WHERE t.resource='accounts' AND t.external_id='account-BANK'""",(count,))

    def test_twenty_thousand_sorted_with_bounded_sqlite_calls(self):
        self.seed_volume(20000)
        with closing(connect(self.case.db)) as db:
            queries=[]
            db.set_trace_callback(queries.append)
            before=time.perf_counter()
            data=analytics(db,self.case.settings,{**fixtures.QUERY,'search':['zebra'],
                'sort':['value_desc'],'page_size':['500'],'bucket':['operating']})
            seconds=time.perf_counter()-before
        self.assertEqual(data['total'],10000)
        self.assertEqual(data['items'][0]['external_id'],'bulk-19999')
        self.assertEqual(len(data['items']),500)
        self.assertLess(len(queries),80)
        print(f'20.000 registros sintéticos: {seconds:.3f} s, {len(queries)} comandos SQLite')

    def test_preferences_and_restart_schedule(self):
        start=datetime(2026,11,19,12,tzinfo=timezone.utc)
        service=OpenFinanceService(replace(self.case.settings,pluggy_connections=tuple(
            replace(cfg,auto_sync_enabled=True) for cfg in self.case.settings.pluggy_connections)),
            clock=FixedClock(start,'UTC'),client_factory=self.case.fixture.service.client_factory)
        with closing(service._db()) as db:
            initial=schedule_report(db,service.settings,start)
        self.assertEqual(initial['interval_hours'],24)
        self.assertTrue(initial['effective_enabled'])
        revision=0
        for hours in HOURS:
            changed=save(service,{'enabled':True,'interval_hours':hours,'revision':revision})
            revision=changed['revision']
            self.assertEqual(changed['interval_hours'],hours)
        with self.assertRaisesRegex(SyncError,'SYNC_PREFERENCES_CHANGED'):
            save(service,{'enabled':True,'interval_hours':2,'revision':0})
        changed=save(service,{'enabled':True,'interval_hours':2,'revision':revision})
        first=sync_full_automatic(service,'bank-test',check=lambda:None,minimum_interval=None)
        self.assertEqual(first['state'],'SUCCEEDED')
        for minutes in (1,119,120):
            now=start+timedelta(minutes=minutes)
            restarted=OpenFinanceService(service.settings,clock=FixedClock(now,'UTC'),client_factory=service.client_factory)
            if minutes<120:
                with self.assertRaisesRegex(SyncError,'AUTO_SYNC_RECENT'):
                    sync_full_automatic(restarted,'bank-test',check=lambda:None,minimum_interval=None)
            else:
                self.assertEqual(sync_full_automatic(restarted,'bank-test',check=lambda:None,minimum_interval=None)['state'],'SUCCEEDED')
        off=save(service,{'enabled':False,'interval_hours':2,'revision':changed['revision']})
        self.assertFalse(off['effective_enabled'])
        locked=OpenFinanceService(replace(service.settings,open_finance_auto_sync_allowed=False),clock=service.clock)
        with self.assertRaisesRegex(SyncError,'AUTO_SYNC_DISABLED'):
            save(locked,{'enabled':True,'interval_hours':2,'revision':off['revision']})
        self.assertEqual(self.case.sql('SELECT count(*) FROM of_sync_preference_events'),[(revision+2,)])

    def test_portfolio_selects_the_only_available_connection_and_deduplicates(self):
        case=self.case
        provider=case.fixture.provider
        original=provider.send
        def send(method,path,*args):
            status,payload=original(method,path,*args)
            if path.startswith('/investments?') and status==200:
                payload['results'][0].update(date='2026-10-01',balance=235)
            return status,payload
        provider.send=send
        self.assertEqual(case.fixture.sync()['state'],'SUCCEEDED')
        count=case.sql('SELECT count(*) FROM of_portfolio_snapshots')
        self.assertEqual(case.fixture.sync()['state'],'SUCCEEDED')
        self.assertEqual(case.sql('SELECT count(*) FROM of_portfolio_snapshots'),count)
        settings=replace(case.settings,pluggy_connections=case.settings.pluggy_connections+(
            replace(case.settings.pluggy_connections[0],id='other-bank',institution='Santander'),))
        with closing(connect(case.db)) as db:
            args={**fixtures.QUERY,'portfolio_window':['1']}
            data=analytics(db,settings,args,today='2026-10-30')
            history=data['portfolio_history']
            self.assertEqual((history['connection_id'],history['state'],history['latest_position']),
                             ('bank-test','FORMING','235'))
            self.assertEqual(len(history['connections']),2)
            self.assertEqual(history['latest_point']['date'],'2026-10-01')
            independent=analytics(db,settings,{**args,'connection_id':['other-bank'],'portfolio_connection':['bank-test']},today='2026-10-30')
            self.assertEqual(independent['institutions'][0]['connection_id'],'other-bank')
            self.assertEqual(independent['portfolio_history']['latest_position'],'235')

    def test_forward_migration_preserves_existing_snapshot_rows(self):
        case=self.case
        with closing(connect(case.db)) as db:
            state={row for row in db.iterdump() if 'of_sync_pref' not in row and '_finance_v2_schema_migrations' not in row}
            self.assertTrue(any(row.startswith('INSERT INTO "of_portfolio_snapshots"') for row in state))
            db.execute('DROP TABLE of_sync_preferences')
            db.execute('DROP TABLE of_sync_preference_events')
            db.execute('DELETE FROM _finance_v2_schema_migrations WHERE version=15')
            db.execute('PRAGMA user_version=14')
            db.commit()
        self.assertEqual(migrations.migrate(case.db),[15])
        self.assertEqual(migrations.migrate(case.db),[])
        with closing(connect(case.db)) as db:
            self.assertTrue(state.issubset(set(db.iterdump())))
            self.assertEqual(db.execute('PRAGMA integrity_check').fetchone()[0],'ok')
            self.assertEqual(db.execute('PRAGMA foreign_key_check').fetchall(),[])
