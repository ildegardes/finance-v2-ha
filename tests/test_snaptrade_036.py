"""Only synthetic brokerage and FX transport, including the actual SDK boundary."""
import io
import json
import os
from contextlib import closing
from dataclasses import replace
from datetime import date,datetime,timezone
from decimal import Decimal
from hashlib import sha256
from unittest.mock import patch
import unittest

from finance_v2 import migrations
from finance_v2.api import Application
from finance_v2.db import connect
from finance_v2.domain.clock import FixedClock
from finance_v2.open_finance import OpenFinanceService, SyncError
from finance_v2.open_finance_wealth import report
from finance_v2.portfolio_fx import refresh
from finance_v2.snaptrade_read import ProviderFailure, SnapTradeReader, validate_read_request
from finance_v2.snaptrade_sync import connection_policy, configure, status, sync
import test_open_finance_classification as fixtures

AUTH='51000000-0000-4000-8000-000000000001'
AUTH2='51000000-0000-4000-8000-000000000002'
ACCOUNT='62000000-0000-4000-8000-000000000001'
ACCOUNT2='62000000-0000-4000-8000-000000000002'
STOCK='73000000-0000-4000-8000-000000000001'
FUND='73000000-0000-4000-8000-000000000002'
ALT='73000000-0000-4000-8000-000000000003'
CLIENT='canary-fixture-client-036-not-a-real-key'
SECRET='canary-fixture-consumer-036-not-a-real-key'
FULL_NUMBER='901938475612'
TODAY='2026-10-20'
STAMP=TODAY+'T17:00:00Z'


class Broker:
    def __init__(self):
        self.visited=[]
        self.fault=None
        self.disabled=False
        self.second=True
        self.second_active=False
        self.reference=STAMP
        self.balance='20000.00'
        self.activities=[{'id':f'activity-{n}','type':nature,'trade_date':'2026-10-20',
                         'currency':{'code':'USD'},'amount':amount,'symbol':{'id':STOCK,'symbol':'ACME'},
                         'description':description}
            for n,(nature,amount,description) in enumerate((
                ('DIVIDEND','8.50','Distribuição sintética'),('REI','-8.50','Reinvestimento'),
                ('INTEREST','1.50','Juros informados'),('TAX','-1.25','Retenção'),('BUY','-25','Compra'),
                ('SELL','27','Venda'),('CONTRIBUTION','500','Depósito externo'),
                ('TRANSFER','300','Transferência'),('FEE','-0.65','Taxa'),
                ('SPLIT','0','Desdobramento'),('PRIVATE_UNKNOWN','0',SECRET)))]

    def factory(self,client,secret):
        if client!=CLIENT or secret!=SECRET:
            raise ProviderFailure('SNAPTRADE_AUTH')
        return self

    def read(self,operation,**query):
        account=query.get('account_id')
        self.visited.append((operation,account,query.get('offset')))
        if self.fault and self.fault(operation,query):
            raise ProviderFailure('SNAPTRADE_RATE_LIMIT' if operation=='connections' else 'SNAPTRADE_TRANSPORT',660)
        if operation=='connections':
            result=[{'id':AUTH,'brokerage':{'name':'Charles Schwab','slug':'SCHWAB'},'type':'read','disabled':self.disabled}]
            if self.second:
                result.append({'id':AUTH2,'brokerage':{'name':'Outra corretora','slug':'OTHER'},'type':'read','disabled':not self.second_active})
            return result
        if operation=='accounts':
            result=[{'id':ACCOUNT,'kind':'investment','is_paper':False,'connection_id':AUTH,'status':'open',
                     'display_name':'Corretora '+FULL_NUMBER,'masked_account_number':'****5612',
                     'raw_type':'Individual','institution_account_id':'broker-external-1'}]
            if self.second:
                result.append({'id':ACCOUNT2,'kind':'investment','is_paper':False,'connection_id':AUTH2,
                               'status':'open','display_name':'Conta internacional 2','masked_account_number':'****4567'})
            return {'results':result}
        if operation=='balances':
            return {'account_id':account,'data_freshness':{'as_of':self.reference},
                    'net_value':{'amount':'20500','currency':'USD'},
                    'cash':[{'currency':'USD','amount':'500' if account==ACCOUNT else '0'}],
                    'buying_power':[{'currency':'USD','amount':'30000'}],
                    'margin':{'loan_balances':[]}}
        if operation=='positions':
            return {'data_freshness':{'as_of':self.reference}, 'results':[
                {'instrument':{'id':STOCK if account==ACCOUNT else ALT,'kind':'stock','symbol':'ACME',
                               'description':'Ação sintética','exchange':'XNAS' if account==ACCOUNT else 'XNYS'},
                 'currency':'USD','price':self.balance if account==ACCOUNT else '400.00','units':'1','cost_basis':'12000',
                 'tax_lots':[{'acquisition_date':'2026-02-06','units':'1','cost_basis':'12000'}]},
                {'instrument':{'id':FUND,'kind':'mutualfund','symbol':'CASH-XX'},'currency':'USD',
                 'units':'500','price':'1','cash_equivalent':True}]}
        if operation=='activities':
            rows=self.activities if account==ACCOUNT else []
            if query.get('start_date'):
                rows=[row for row in rows if row['trade_date']>=str(query['start_date'])]
            offset,limit=query['offset'],query['limit']
            return {'data':rows[offset:offset+limit],'pagination':{'total':len(rows),'offset':offset,'limit':limit}}
        raise AssertionError(operation)


class SnapTradeTests(unittest.TestCase):
    def setUp(self):
        self.case=fixtures.ClassificationTest('test_automatic_investment_example_and_coverage')
        self.addCleanup(self.case.doCleanups)
        self.case.setUp()
        self.settings=replace(self.case.settings,snaptrade_enabled=True,snaptrade_client_id=CLIENT,snaptrade_consumer_key=SECRET)
        self.settings=replace(self.settings,pluggy_connections=tuple(replace(conn,institution='Itaú') for conn in self.settings.pluggy_connections))
        self.case.write("UPDATE of_connections SET institution='Itaú' WHERE id='bank-test'")
        self.case.write("UPDATE of_connection_registry SET label='Itaú' WHERE connection_id='bank-test'")
        self.case.write("UPDATE of_resource_records SET payload_json=replace(payload_json,'sintÃ©tica','sintética')")
        self.broker=Broker()
        self.clock=FixedClock(datetime(2026,10,20,19,tzinfo=timezone.utc),'UTC')
        self.service=OpenFinanceService(self.settings,self.clock)
        self.case.write("""UPDATE of_resource_records SET payload_json=json_set(payload_json,'$.currencyCode','BRL',
          '$.balance',100000,'$.date',?,'$.name','Título do Tesouro','$.type','TREASURY')
          WHERE resource='investments'""",(TODAY,))

    def run_sync(self,**kwargs):
        return sync(self.service,reader_factory=self.broker.factory,**kwargs)

    def view(self,**kwargs):
        with closing(connect(self.case.db)) as db:
            return report(db,self.settings,{key:[str(value)] for key,value in kwargs.items()},TODAY)

    def test_discovery_currency_and_cash_once(self):
        self.assertEqual(self.run_sync(discover=True)['state'],'AVAILABLE')
        self.assertEqual({row[0] for row in self.broker.visited},{'connections','accounts'})
        self.assertEqual(self.run_sync()['state'],'AVAILABLE')
        refresh(self.service,date(2026,10,16),date(2026,10,20),
                transport=lambda *_:[{'dataHoraCotacao':'2026-10-16 13:00:00','cotacaoVenda':Decimal('5')}])
        data=self.view(presentation='BRL')
        summary=data['summary']
        self.assertEqual(Decimal(summary['original']['BRL']['positions']),100000)
        self.assertEqual(Decimal(summary['original']['USD']['positions']),20000)
        self.assertEqual(Decimal(summary['original']['USD']['cash']),500)
        self.assertEqual(Decimal(summary['converted']['positions']),200000)
        self.assertEqual(Decimal(summary['converted']['cash']),2500)
        self.assertEqual(summary['quote_dates'][0]['date'],'2026-10-16')
        self.assertEqual(Decimal(self.view(presentation='USD')['summary']['converted']['positions']),40000)
        self.assertEqual(self.view(currency='USD',provider='SNAPTRADE')['total'],1)
        self.assertNotIn(FULL_NUMBER,json.dumps(data))
        self.assertNotIn(SECRET,json.dumps(self.view(view='activities')))
        self.assertEqual(self.case.sql("SELECT count(*) FROM st_snapshots"),[(1,)])
        self.assertEqual(self.run_sync()['state'],'AVAILABLE')
        self.assertEqual(self.case.sql("SELECT count(*) FROM st_snapshots"),[(1,)])
        self.assertEqual(self.case.sql("SELECT count(*) FROM st_positions"),[(2,)])

    def test_missing_fx_optional_resources_and_income(self):
        self.assertEqual(self.run_sync()['state'],'AVAILABLE')
        data=self.view(presentation='BRL')
        self.assertIsNone(data['summary']['converted']['positions'])
        self.assertEqual(Decimal(data['summary']['converted_subtotal']['positions']),100000)
        activity_data=self.view(view='activities',provider='SNAPTRADE')
        self.assertEqual(activity_data['total'],11)
        self.assertTrue(any(row['kind']=='CORPORATE_ACTION' for row in activity_data['items']))
        self.assertTrue(any(row['kind']=='REVIEW' for row in activity_data['items']))
        income=self.view(view='income')['income'][0]['components']
        self.assertEqual({key:Decimal(value) for key,value in income.items()},
                         {'DIVIDEND':Decimal('8.50'),'INTEREST':Decimal('1.50'),'TAX':Decimal('-1.25'),'FEE':Decimal('-.65')})
        asset=self.view(provider='SNAPTRADE')['items'][0]
        self.assertTrue(asset['lots'])
        self.assertEqual(self.view(view='activities',asset=asset['instrument_id'])['total'],11)

    def test_partial_pagination_durable_resume_and_archive(self):
        with patch('finance_v2.snaptrade_sync.PAGE_SIZE',2):
            self.broker.fault=lambda op,q:op=='activities' and q.get('offset')==2
            self.assertEqual(self.run_sync()['state'],'PARTIAL')
            self.assertEqual(self.case.sql("SELECT state,next_offset FROM st_checkpoints WHERE resource='activities'"),[('FAILED',2)])
            self.broker.fault=None
            self.assertEqual(self.run_sync()['state'],'AVAILABLE')
        self.assertEqual(self.view(view='activities')['total'],11)
        self.assertIn(('activities',ACCOUNT,1),self.broker.visited)
        connection=self.view(provider='SNAPTRADE')['accounts'][0]['connection_id']
        connection_policy(self.service,{'connection_id':connection,'archived':True,'paused':False,'excluded':False})
        self.assertEqual(self.view(provider='SNAPTRADE')['total'],0)
        self.assertEqual(self.view(provider='SNAPTRADE',history=1)['total'],1)
        self.assertEqual(self.case.sql("SELECT count(*) FROM st_activities"),[(11,)])

    def test_read_timeout_retains_local_assets_and_disabled_connection_excludes_current(self):
        self.assertEqual(self.run_sync()['state'],'AVAILABLE')
        self.broker.fault=lambda op,q:op=='positions'
        outcome=self.run_sync()
        self.assertEqual((outcome['state'],outcome['error_code']),('PARTIAL','SNAPTRADE_TRANSPORT'))
        self.assertEqual(self.view(provider='SNAPTRADE')['total'],1)
        self.broker.fault=None
        self.broker.disabled=True
        self.assertEqual(self.run_sync()['state'],'AVAILABLE')
        self.assertEqual(self.view(provider='SNAPTRADE')['total'],0)
        self.assertEqual(self.view(provider='SNAPTRADE',history=1)['total'],1)

    def test_multiple_brokers_same_ticker_and_exact_history_dates(self):
        self.broker.second_active=True
        self.assertEqual(self.run_sync()['state'],'AVAILABLE')
        data=self.view(provider='SNAPTRADE')
        self.assertEqual({row['ticker'] for row in data['items']},{'ACME'})
        self.assertEqual(len({row['instrument_id'] for row in data['items']}),2)
        self.assertEqual(self.view(view='history',provider='SNAPTRADE')['state'],'FORMING')
        self.broker.reference='2026-10-19T17:00:00Z'
        self.broker.balance='19500'
        self.assertEqual(self.run_sync()['state'],'AVAILABLE')
        historical=self.view(view='history',provider='SNAPTRADE',currency='USD')
        self.assertEqual([row['date'] for row in historical['points']],['2026-10-19','2026-10-20'])
        self.assertEqual(self.view(view='history',presentation='BRL')['points'],[])
        asset=next(row for row in data['items'] if row['institution']=='Charles Schwab')
        specific=self.view(view='history',account_id=asset['account_id'],asset=asset['instrument_id'])
        self.assertEqual([Decimal(row['original']['USD']) for row in specific['points']],[19500,20000])

    def test_preferences_disabled_mode_and_provider_retry(self):
        with closing(connect(self.case.db)) as db:
            state=status(db,self.settings,self.clock.now_utc().timestamp())
        self.assertEqual(state['interval_hours'],24)
        self.assertEqual(self.run_sync(automatic=True)['state'],'NOT_DUE')
        configure(self.service,{'auto_enabled':True,'interval_hours':6,'revision':state['revision']})
        self.broker.fault=lambda op,q:op=='connections'
        self.assertEqual(self.run_sync(automatic=True)['error_code'],'SNAPTRADE_RATE_LIMIT')
        with self.assertRaisesRegex(SyncError,'SNAPTRADE_RATE_LIMIT'):
            self.run_sync()
        with closing(connect(self.case.db)) as db:
            restarted=status(db,self.settings,self.clock.now_utc().timestamp())
            self.assertEqual(restarted['next_attempt'],'2026-10-20T19:11:00Z')
        disabled=replace(self.settings,snaptrade_enabled=False)
        self.assertNotIn(SECRET,repr(disabled))
        with closing(connect(self.case.db)) as db:
            self.assertFalse(status(db,disabled,self.clock.now_utc().timestamp())['configured'])

    def test_owner_only_read_and_post_via_wsgi(self):
        app=Application(replace(self.settings,ui_token='synthetic-session-token'),self.clock)
        def request(path,method='GET',token=None,body=None):
            raw=json.dumps(body).encode() if body else b''
            status_code=[]
            env={'REQUEST_METHOD':method,'PATH_INFO':'/api/v2/open-finance/'+path,'QUERY_STRING':'',
                 'wsgi.input':io.BytesIO(raw),'CONTENT_LENGTH':str(len(raw)),
                 'CONTENT_TYPE':'application/json','HTTP_AUTHORIZATION':'Bearer '+token if token else ''}
            answer=b''.join(app(env,lambda status,headers:status_code.append(int(status.split()[0]))))
            self.assertNotIn(SECRET.encode(),answer)
            self.assertNotIn(CLIENT.encode(),answer)
            return status_code[0]
        self.assertIn(request('portfolio'),(401,403))
        self.assertEqual(request('portfolio',token='synthetic-session-token'),200)
        self.assertEqual(request('snaptrade/sync','POST','synthetic-session-token'),403)
        self.assertEqual(request('snaptrade/credentials','POST','synthetic-session-token',
                                 {'client_id':CLIENT,'consumer_key':SECRET}),403)

    def test_schema_15_is_preserved(self):
        with closing(connect(self.case.db)) as db:
            baseline={line for line in db.iterdump() if 'st_' not in line and 'portfolio_fx' not in line}
            for name in ('st_position_snapshots','st_snapshots','st_checkpoints','st_activity_rules','st_activities','st_positions','st_balances',
                         'st_accounts','st_connections','st_events','st_credentials','st_state','portfolio_fx_rates'):
                db.execute('DROP TABLE '+name)
            db.execute('DELETE FROM _finance_v2_schema_migrations WHERE version=16')
            db.execute('PRAGMA user_version=15')
            db.commit()
        self.assertEqual(migrations.migrate(self.case.db),[16])
        self.assertEqual(migrations.migrate(self.case.db),[])
        with closing(connect(self.case.db)) as db:
            self.assertEqual(db.execute('PRAGMA integrity_check').fetchone()[0],'ok')
            self.assertEqual(db.execute('PRAGMA foreign_key_check').fetchall(),[])
            current=set(db.iterdump())
            self.assertTrue({line for line in baseline if '_finance_v2_schema_migrations' not in line}<=current)

    def test_confirmed_review_rule_is_account_and_type_scoped(self):
        from finance_v2.open_finance_wealth import classify_activity
        self.broker.activities[-1].update(description='Distribuição teste de outra origem',amount='7.50')
        self.assertEqual(self.run_sync()['state'],'AVAILABLE')
        review=self.view(view='activities',kind='OWNER_REVIEW')['items']
        self.assertEqual(len(review),1)
        sample=review[0]
        values={key:sample[key] for key in ('account_id','activity_id')}
        classify_activity(self.service,{**values,'kind':'DIVIDEND'})
        revised=self.view(view='income',group='year',account_id=sample['account_id'])
        self.assertEqual(revised['income'][0]['month'],'2026')
        self.assertEqual(Decimal(revised['income'][0]['components']['DIVIDEND']),16)
        rule=self.view(view='activities',kind='OWNER_REVIEW')['items'][0]
        self.assertEqual((rule['provider_kind'],rule['classification_source']),('PRIVATE_UNKNOWN','OWNER_RULE'))
        classify_activity(self.service,{**values,'kind':'REVIEW'})
        self.assertEqual(self.view(view='activities',kind='OWNER_REVIEW')['items'][0]['kind'],'REVIEW')

    def test_encrypted_credentials_and_invalid_credentials(self):
        from finance_v2.pluggy_credential_protection import CredentialProtector
        from finance_v2.snaptrade_sync import credentials,update_credentials
        cipher=CredentialProtector('synthetic',{'synthetic':os.urandom(32)})
        with patch('finance_v2.snaptrade_sync.load_keyring',return_value=cipher):
            update_credentials(self.service,{'client_id':CLIENT,'consumer_key':SECRET})
            with closing(connect(self.case.db)) as db:
                self.assertEqual(credentials(db,self.settings),(CLIENT,SECRET))
                dump=' '.join(db.iterdump())
                self.assertNotIn(CLIENT,dump)
                self.assertNotIn(SECRET,dump)
            wrong=CredentialProtector('synthetic',{'synthetic':os.urandom(32)})
            with patch('finance_v2.snaptrade_sync.load_keyring',return_value=wrong):
                self.assertEqual(self.run_sync()['error_code'],'SNAPTRADE_CREDENTIALS_LOCKED')
            update_credentials(self.service,{'client_id':CLIENT,'consumer_key':'synthetic-invalid'})
            self.assertEqual(self.run_sync()['error_code'],'SNAPTRADE_AUTH')

    def test_account_throttle_preserves_other_brokers(self):
        from finance_v2.snaptrade_read import _status
        self.assertEqual(_status(429,{'X-RateLimit-Account-Remaining':'0'}),'SNAPTRADE_ACCOUNT_RATE_LIMIT')
        self.assertEqual(_status(429,{'X-RateLimit-Account-Remaining':'0','X-RateLimit-Remaining':'0'}),'SNAPTRADE_RATE_LIMIT')
        self.broker.second_active=True
        transport=self.broker.read
        def limited(operation,**query):
            if operation=='positions' and query.get('account_id')==ACCOUNT:
                raise ProviderFailure('SNAPTRADE_ACCOUNT_RATE_LIMIT',660)
            return transport(operation,**query)
        with patch.object(self.broker,'read',side_effect=limited):
            result=self.run_sync()
            self.assertEqual((result['state'],result['error_code']),('PARTIAL','SNAPTRADE_ACCOUNT_RATE_LIMIT'))
            self.assertIn(('positions',ACCOUNT2,None),self.broker.visited)
            self.broker.visited.clear()
            self.assertEqual(self.run_sync()['state'],'PARTIAL')
            self.assertTrue(all(account!=ACCOUNT for _,account,_ in self.broker.visited))
        with closing(connect(self.case.db)) as db:
            state=status(db,self.settings,self.clock.now_utc().timestamp())
        coverage=next(row for row in state['connections'] if row['institution']=='Charles Schwab')['accounts'][0]['coverage']
        self.assertEqual(next(row for row in coverage if row['resource']=='positions')['retry_at'],'2026-10-20T19:11:00Z')

    def test_legacy_snapshot_run_must_have_one_financial_date(self):
        run=self.case.next_run()
        self.case.write("""INSERT INTO of_portfolio_snapshots VALUES
          (?,'bank-test','asset-first','BRL','100','2026-10-19',?),
          (?,'bank-test','asset-second','BRL','200','2026-10-20',?)""",(run,STAMP,run,STAMP))
        data=self.view(view='history',provider='PLUGGY',currency='BRL',start='2026-10-19',end='2026-10-19')
        self.assertEqual(data['points'],[])

    def test_large_activity_and_position_projection(self):
        import time
        import tracemalloc
        item=self.broker.activities[0]
        self.broker.activities=[dict(item,id=f'access-{index}') for index in range(12000)]
        self.assertEqual(self.run_sync()['state'],'PARTIAL')
        self.assertEqual(self.run_sync()['state'],'AVAILABLE')
        asset=self.view(provider='SNAPTRADE')['items'][0]
        with closing(connect(self.case.db)) as db:
            seed=tuple(db.execute('SELECT * FROM st_positions WHERE account_id=? AND instrument_id=?',
                                  (asset['account_id'],asset['instrument_id'])).fetchone())
            db.executemany('INSERT INTO st_positions VALUES ('+','.join('?' for _ in seed)+')',
                [(seed[0],f'fixture-instrument-{index:04}',*seed[2:]) for index in range(5000)])
            db.commit()
            statements=[]
            db.set_trace_callback(statements.append)
            trace_allocations=not os.environ.get('OF_TEST_NO_MEMORY_TRACE')
            if trace_allocations:
                tracemalloc.start()
            start=time.perf_counter()
            try:
                rows=report(db,self.settings,{'view':['activities'],'page_size':['250'],'page':['48']},TODAY)
                positions=report(db,self.settings,{'provider':['SNAPTRADE'],'page_size':['250'],'page':['20']},TODAY)
                elapsed=time.perf_counter()-start
                peak=tracemalloc.get_traced_memory()[1]
            finally:
                tracemalloc.stop()
            self.assertEqual((rows['total'],len(rows['items']),positions['total']),(12000,250,5001))
            self.assertLess(len(statements),45)
            self.assertLess(elapsed,60)
            self.assertLess(peak,60*1024*1024)
            memory=f'{peak/1024/1024:.1f} MiB, ' if trace_allocations else ''
            print(f'SnapTrade volume: {elapsed:.3f} s, {memory}{len(statements)} SQLite commands')

    def test_sdk_13_4_4_signs_personal_reads_and_bounds_routes(self):
        from snaptrade_client import __version__
        import urllib3
        from urllib.parse import parse_qs,urlsplit
        self.assertEqual(__version__,'13.4.4')
        calls=[]
        def transport(pool,method,url,*args,**kwargs):
            calls.append((method,url,kwargs))
            result={'data':[],'pagination':{'total':0}} if '/activities' in url else []
            return urllib3.HTTPResponse(body=json.dumps(result).encode(),status=200,
                                       headers={'Content-Type':'application/json'},preload_content=True)
        with patch.object(urllib3.PoolManager,'request',transport):
            reader=SnapTradeReader(CLIENT,SECRET)
            for action in ('connections','accounts','balances','positions','activities'):
                reader.read(action,**({'account_id':ACCOUNT} if action in ('balances','positions','activities') else {}))
            with self.assertRaisesRegex(ProviderFailure,'SNAPTRADE_OPERATION_DENIED'):
                reader.read('create_order')
        self.assertEqual(len(calls),5)
        for method,url,kwargs in calls:
            self.assertEqual(method,'GET')
            args=parse_qs(urlsplit(url).query)
            self.assertEqual(args['clientId'],[CLIENT])
            self.assertFalse({'userId','userSecret'} & args.keys())
            self.assertNotIn(SECRET,url)
            self.assertIn('signature',{k.lower() for k in kwargs['headers']})
            self.assertFalse(kwargs['redirect'])
        for method,path in [('POST','/authorizations'),('GET','/orders'),('GET','/accounts/'+ACCOUNT+'/orders')]:
            with self.assertRaises(ProviderFailure):
                validate_read_request(method,'https://api.snaptrade.com'+path)
