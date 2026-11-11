"""Gate B: disposable synthetic SQLite, injected transport, external networking forbidden."""
from contextlib import closing
from dataclasses import replace
from decimal import Decimal
from hashlib import sha256
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
from unittest.mock import patch
import unittest
import test_full_coverage as prior
from finance_v2 import migrations
from finance_v2.db import connect
from finance_v2.open_finance import OpenFinanceService,SyncError
from finance_v2.open_finance_coverage import sync_domain,_sync_full
from finance_v2.open_finance_domain import query_domain,query_relations,field,decimal_text
from finance_v2.pluggy_client import PluggyClient,PluggyError
from finance_v2.pluggy_coverage import _whole_number,CONTRACT


class GateBTests(unittest.TestCase):
    setUp=prior.CoverageTests.setUp
    sync=prior.CoverageTests.sync
    financial=prior.CoverageTests.financial
    request=prior.CoverageTests.request

    def domain(self,resource,**kwargs):
        with closing(connect(self.db)) as c:return query_domain(c,self.settings,{'resource':[resource],**{k:[str(v)] for k,v in kwargs.items()}})

    def rows(self,sql,args=()):
        with closing(connect(self.db)) as c:return [tuple(r) for r in c.execute(sql,args)]

    def card_transaction(self,**metadata):
        return {'id':'card-transaction','accountId':'account-CREDIT','amount':Decimal('10.00000000001'),
            'date':'2026-10-23','type':'DEBIT','status':'PENDING','currencyCode':'BRL','creditCardMetadata':metadata}

    def card_override(self,rows):
        self.provider.overrides['/v2/transactions?accountId=account-CREDIT']=(200,{'results':rows,'next':None})

    def test_all_ten_domains_have_typed_views_and_completed_checkpoints(self):
        self.assertEqual(self.sync()['state'],'SUCCEEDED')
        for resource in CONTRACT['resources']:
            with self.subTest(resource=resource):
                result=self.domain(resource)
                self.assertGreater(result['total'],0)
                self.assertEqual(result['source'],'EXTERNAL_STAGING')
                self.assertTrue(all(r['fields'] and r['kind'] and r['source']=='EXTERNAL_STAGING' for r in result['items']))
                self.assertTrue(all(c['state']=='COMPLETE' for c in result['checkpoints']))
        self.assertEqual(self.domain('accounts')['net_worth']['state'],'NOT_ESTABLISHED')
        self.assertEqual(self.domain('statements')['document_download'],'NOT_ENABLED')

    def test_exact_bill_relationship_no_pending_inference_and_replay(self):
        self.card_override([self.card_transaction(billId='bill-test'),{**self.card_transaction(billForecastDate='2026-11-01'),'id':'pending-no-bill'}])
        self.assertEqual(sync_domain(self.service,self.config.id,actor='UI:local')['state'],'SUCCEEDED')
        with closing(connect(self.db)) as c:
            result=query_relations(c,self.settings,{})
        self.assertEqual({r['source_external_id']:r['state'] for r in result['items']},{'card-transaction':'MATCHED','pending-no-bill':'MISSING_REFERENCE'})
        before=self.financial();revisions=self.rows('SELECT count(*) FROM of_resource_link_revisions')
        self.assertEqual(sync_domain(self.service,self.config.id,actor='UI:local',mode='INCREMENTAL')['state'],'SUCCEEDED')
        self.assertEqual(self.rows('SELECT count(*) FROM of_resource_link_revisions'),revisions)
        self.assertEqual(self.financial(),before)
        self.assertEqual(self.rows('SELECT mode,strategy FROM of_domain_sync_audit ORDER BY rowid')[-1],('INCREMENTAL','BOUNDED_FULL_RECONCILIATION'))

    def test_unknown_bill_reference_is_unresolved_not_fabricated(self):
        self.card_override([self.card_transaction(billId='not-yet-seen')]);self.sync()
        self.assertEqual(self.rows('SELECT state,target_external_id FROM of_resource_links'),[('UNRESOLVED',None)])
        self.assertEqual(self.rows("SELECT count(*) FROM of_resource_records WHERE resource='bills' AND external_id='not-yet-seen'"),[(0,)])
        self.provider.overrides['/bills?accountId=account-CREDIT&page=1&pageSize=500']=(200,prior.collection([{'id':'not-yet-seen','totalAmount':10}]))
        self.assertEqual(self.sync()['state'],'SUCCEEDED')
        self.assertEqual(self.rows('SELECT state,target_external_id FROM of_resource_links'),[('MATCHED','not-yet-seen')])

    def test_foreign_card_reference_rejected_and_fk_enforces_parent(self):
        self.card_override([self.card_transaction(billId='bill-test')]);self.sync()
        with closing(connect(self.db)) as c:
            with self.assertRaises(sqlite3.IntegrityError):
                c.execute("UPDATE of_resource_links SET target_parent_id='account-BANK'")
        before=self.financial()
        accounts=self.provider.send('GET','/accounts',{},None,1)[1]['results']
        accounts.append({**accounts[1],'id':'other-card'})
        self.provider.overrides['/accounts?itemId=item-test']=(200,prior.collection(accounts))
        self.provider.overrides['/v2/transactions?accountId=other-card']=(200,{'results':[{**self.card_transaction(billId='bill-test'),'accountId':'other-card'}],'next':None})
        run=self.sync();self.assertEqual(run['state'],'FAILED');self.assertEqual(run['error_code'],'BILL_SCOPE_MISMATCH')
        self.assertEqual(self.financial(),before)

    def test_optional_empty_unavailable_unauthorized_and_not_collected_distinct(self):
        cases=[('statements','/accounts/account-BANK/statements',200,prior.collection([]),'EMPTY'),
            ('statements','/accounts/account-BANK/statements',404,None,'NOT_AVAILABLE'),
            ('investments','/investments?itemId=item-test&page=1&pageSize=500',403,None,'NOT_AUTHORIZED')]
        for resource,path,status,body,state in cases:
            with self.subTest(state=state):
                self.provider.overrides[path]=(status,body)
                self.assertEqual(self.sync()['state'],'SUCCEEDED')
                self.assertEqual(self.domain(resource)['checkpoints'][0]['state'],state)
                self.provider.overrides.clear()
        self.assertEqual(self.domain('statements',parent_id='not-consulted')['checkpoints'],[])
        self.provider.overrides['/items/item-test']=(200,{'id':'item-test','status':'UPDATED'})
        self.provider.overrides['/items/item-test/resources?page=1&pageSize=500']=(200,prior.collection([]))
        self.sync();self.assertEqual(self.domain('resources')['checkpoints'][0]['state'],'NOT_COLLECTED')

    def test_stale_and_partial_provider_quality_never_claims_fresh(self):
        self.provider.overrides['/items/item-test']=(200,{'id':'item-test','status':'UPDATED','executionStatus':'PARTIAL_SUCCESS',
            'statusDetail':{'investments':{'isUpdated':False,'warnings':[{'code':'SYNTHETIC_WARNING'}]}},'resourcesCollectedAt':'2026-10-23T00:00:00Z'})
        self.sync();quality=self.domain('investments')['items'][0]['freshness']
        self.assertEqual(quality,{'state':'STALE','source':'PROVIDER_CACHE','provider_execution_partial':True,'warning_count':1})

    def test_position_empty_movements_different_from_not_queried(self):
        self.provider.overrides['/investments/investment-test/transactions?page=1&pageSize=500']=(200,prior.collection([]))
        self.assertEqual(self.sync()['state'],'SUCCEEDED')
        self.assertEqual(self.domain('investment_transactions')['checkpoints'][0]['state'],'EMPTY')
        self.assertEqual(self.domain('investment_transactions',parent_id='new-unqueried')['checkpoints'],[])

    def test_all_documented_investment_classes_roundtrip_without_aggregation(self):
        classes=CONTRACT['resources']['investments']['schema']['properties']['type']['enum']
        rows=[{'id':'position-'+kind,'itemId':'item-test','name':'Synthetic '+kind,'type':kind,'currencyCode':'BRL','balance':0} for kind in classes]
        self.provider.overrides['/investments?itemId=item-test&page=1&pageSize=500']=(200,prior.collection(rows))
        self.assertEqual(self.sync()['state'],'SUCCEEDED')
        self.assertEqual(self.domain('investments')['total'],len(classes))
        for kind in classes:
            result=self.domain('investments',type=kind)
            self.assertEqual(result['total'],1)
            self.assertEqual(result['items'][0]['kind'],'INVESTMENT_POSITION')
            self.assertEqual(result['net_worth']['state'],'NOT_ESTABLISHED')

    def test_intermediate_failure_resume_preserves_last_complete_and_no_absence(self):
        self.assertEqual(self.sync()['state'],'SUCCEEDED');complete=self.domain('investments')['checkpoints'][0]['last_complete_run_id']
        row={'id':'investment-new','itemId':'item-test','currencyCode':'BRL','balance':4}
        first='/investments?itemId=item-test&page=1&pageSize=500';second='/investments?itemId=item-test&page=2&pageSize=500'
        self.provider.overrides[first]=(200,{'results':[row],'page':1,'total':2,'totalPages':2})
        self.provider.overrides[second]=(500,{})
        failed=sync_domain(self.service,self.config.id,actor='UI:local')
        self.assertEqual(failed['state'],'FAILED');cp=self.domain('investments')['checkpoints'][0]
        self.assertEqual((cp['state'],cp['last_complete_run_id']),('FAILED',complete))
        self.assertEqual(self.rows("SELECT state FROM of_resource_records WHERE resource='investments' AND external_id='investment-test'"),[('PRESENT',)])
        self.provider.overrides[second]=(200,{'results':[{**row,'id':'investment-test'}],'page':2,'total':2,'totalPages':2})
        resumed=sync_domain(self.service,self.config.id,actor='UI:local',mode='RESUME')
        self.assertEqual(resumed['state'],'SUCCEEDED')
        self.assertEqual(self.rows('SELECT resumed_from_run_id FROM of_domain_sync_audit WHERE run_id=?',(resumed['id'],)),[(failed['id'],)])
        self.assertEqual(self.rows("SELECT count(*) FROM of_resource_records WHERE resource='investments'"),[(2,)])
        self.assertEqual(self.rows('PRAGMA foreign_key_check'),[])

    def test_cancel_during_page_rolls_back_and_resume(self):
        before=self.financial();send=self.provider.send;cancelled=[False]
        def sender(*args):
            result=send(*args)
            if args[1].startswith('/v2/transactions'):cancelled[0]=True
            return result
        config=replace(self.config,auto_sync_enabled=True)
        service=OpenFinanceService(replace(self.settings,pluggy_connections=(config,)),
            client_factory=lambda cfg:PluggyClient(cfg,send=sender,sleep=lambda _:None))
        def check():
            if cancelled[0]:raise PluggyError('AUTO_SYNC_CANCELLED')
        run=_sync_full(service,self.config.id,actor='AUTO:coverage',check=check)
        self.assertEqual(run['state'],'INTERRUPTED')
        self.assertEqual(self.rows('SELECT count(*) FROM of_transactions'),[(0,)])
        self.assertEqual(self.rows("SELECT state FROM of_collection_checkpoints WHERE resource='transactions'"),[('INTERRUPTED',)])
        self.assertEqual(self.financial(),before)
        self.assertEqual(sync_domain(self.service,self.config.id,actor='UI:local',mode='RESUME')['state'],'SUCCEEDED')

    def test_two_connections_same_provider_identifiers_stay_separate(self):
        other=replace(self.config,id='other-test',client_id='other-synthetic-client',client_secret='other-synthetic-secret')
        settings=replace(self.settings,pluggy_connections=(self.config,other))
        providers={self.config.id:self.provider,other.id:prior.Provider()}
        providers[other.id].balance=42
        service=OpenFinanceService(settings,client_factory=lambda cfg:PluggyClient(cfg,send=providers[cfg.id].send,sleep=lambda _:None))
        for cfg in settings.pluggy_connections:self.assertEqual(sync_domain(service,cfg.id,actor='UI:local')['state'],'SUCCEEDED')
        with closing(connect(self.db)) as c:
            values=query_domain(c,settings,{'resource':['accounts']})
        self.assertEqual(values['total'],4)
        self.assertEqual({r['identity']['connection_id'] for r in values['items']},{self.config.id,other.id})
        self.assertEqual(self.rows('PRAGMA foreign_key_check'),[])

    def test_foreign_consent_failed_import_preserves_readable_historical_data(self):
        self.sync();before=self.rows("SELECT payload_hash FROM of_resource_records WHERE resource='accounts' ORDER BY external_id")
        self.provider.overrides['/consents?itemId=item-test']=(200,prior.collection([{'id':'foreign','itemId':'other-item'}]))
        run=self.sync();self.assertEqual((run['state'],run['error_code']),('FAILED','ACCOUNT_SCOPE_MISMATCH'))
        self.assertEqual(self.rows("SELECT payload_hash FROM of_resource_records WHERE resource='accounts' ORDER BY external_id"),before)
        result=self.domain('accounts');self.assertEqual(result['total'],2)
        self.assertEqual(result['consent_diagnostics'][0]['state'],'ASSOCIATION_INCONSISTENT')
        self.assertTrue(result['consent_diagnostics'][0]['new_import_requires_valid_scope'])
        self.assertEqual(self.rows("SELECT count(*) FROM of_resource_records WHERE resource='consents' AND external_id='foreign'"),[(0,)])

    def test_new_routes_owner_only_gets_do_not_authenticate_and_closed_modes(self):
        self.sync();self.provider.calls.clear()
        for path in ('domain?resource=investments','relations'):
            with self.subTest(path=path):
                status,result=self.request('/api/v2/open-finance/'+path);self.assertEqual(status,200)
                self.assertEqual(self.request('/api/v2/open-finance/'+path,token=None)[0],401)
                self.assertEqual(self.request('/api/v2/open-finance/'+path,token='synthetic-external-only')[0],403)
        self.assertEqual(self.provider.calls,[])
        self.assertEqual(self.request('/api/v2/open-finance/domain-sync',method='POST',body={'connection_id':self.config.id,'mode':'unsafe'})[0],422)
        for malformed in ([],{},None,True):
            self.assertEqual(self.request('/api/v2/open-finance/domain-sync',method='POST',body={'connection_id':self.config.id,'mode':malformed})[0],422)
        with self.assertRaises(SyncError):sync_domain(self.service,self.config.id,actor='EXTERNAL:client')
        status,schema=self.request('/api/v2/openapi.json');self.assertEqual(status,200)
        for suffix in ('domain','relations','domain-sync'):self.assertIn('/api/v2/open-finance/'+suffix,schema['paths'])

    def test_domain_pagination_and_filters_preserve_connection_parent_scope(self):
        self.sync()
        result=self.domain('accounts',type='CREDIT',currency='BRL',page=2)
        self.assertEqual((result['total'],result['items'],result['has_more']),(1,[],False))
        self.assertEqual(self.domain('transactions',parent_id='account-CREDIT')['total'],1)
        for values in ({'resource':['bad']},{'resource':['accounts'],'page':['0']},{'resource':['accounts'],'unknown':['x']}):
            with closing(connect(self.db)) as c,self.assertRaises(SyncError):query_domain(c,self.settings,values)

    def test_decimal_date_null_absent_zero_and_nested_contracts(self):
        money={'type':'number'}
        self.assertEqual(field('balance',money,None,False,'BRL')['state'],'ABSENT')
        self.assertEqual(field('balance',money,None,True,'BRL')['state'],'NULL')
        self.assertEqual(field('balance',money,0,True,'BRL')['value'],'0')
        self.assertEqual(field('balance',money,'123.000000000001',True,'BRL')['value'],'123.000000000001')
        self.assertEqual(field('balance',money,'123.45000000000001',True,'BRL')['value'],'123.45000000000001')
        self.assertEqual(decimal_text(Decimal('1E-40')),'0.'+'0'*39+'1')
        self.assertEqual(field('balance',money,'1E999999',True,'BRL')['state'],'UNSUPPORTED')
        date={'type':'string','format':'date-time'}
        instant=field('date',date,'2026-10-23T23:30:00-03:00',True,None)
        self.assertEqual(instant['value'],'2026-10-23T23:30:00-03:00');self.assertTrue(instant['utc'].startswith('2026-10-24'))
        self.assertEqual(field('dueDate',{'format':'date'},'2026-10-23',True,None)['kind'],'CIVIL_DATE')
        self.assertEqual(field('dueDate',{'format':'date'},'2026-02-30',True,None)['state'],'UNSUPPORTED')
        self.assertEqual(field('balance',money,'NaN',True,'BRL')['state'],'UNSUPPORTED')
        self.assertIsNone(field('balanceForeignCurrency',money,100,True,'BRL')['currency'])
        spec={'properties':{'usedAmount':money,'usedAmountCurrencyCode':{'type':'string'}}}
        nested=field('limit',spec,{'usedAmount':10,'usedAmountCurrencyCode':'USD'},True,'BRL')
        self.assertEqual(nested['children'][0]['currency'],'USD')
        self.sync();loan=self.domain('loans')['items'][0];self.assertTrue(any(f['key']=='CET' and f['kind']=='RATE' for f in loan['fields']))
        self.assertNotIn('private-signed-url',json.dumps(self.domain('statements')))

    def test_all_documented_nested_components_preserve_decimal_and_scope(self):
        def synthetic(spec,key=''):
            if 'properties' in spec:return {k:synthetic(s,k) for k,s in spec['properties'].items()}
            if 'items' in spec:return [synthetic(spec['items'],key)]
            kinds=spec.get('type');kinds=kinds if isinstance(kinds,list) else [kinds]
            if 'number' in kinds:return Decimal('123.45000000001')
            if 'integer' in kinds:return 1
            if 'boolean' in kinds:return True
            if spec.get('format') in ('date','date-time'):return '2026-10-23' if spec['format']=='date' else '2026-10-23T23:30:00-03:00'
            if spec.get('enum'):return next(v for v in spec['enum'] if v is not None and v!='null')
            return 'BRL' if 'CurrencyCode' in key or key=='currencyCode' else 'synthetic'
        from finance_v2.pluggy_coverage import project
        for resource,contract in CONTRACT['resources'].items():
            with self.subTest(resource=resource):
                payload,encoded,digest,omitted=project(resource,synthetic(contract['schema']))
                self.assertEqual(omitted,0)
                self.assertEqual(digest,sha256(encoded.encode()).hexdigest())
                for key,spec in contract['schema']['properties'].items():
                    if key in {'id','itemId','accountId','resourceId','providerId','providerCode','order','categoryId','billId','transactions'}:continue
                    node=field(key,spec,payload.get(key),key in payload,'BRL')
                    def check(n):
                        self.assertEqual(n['state'],'VALUE')
                        for child in n.get('children',[])+n.get('items',[]):check(child)
                    # Identifier-only fields are intentionally absent from typed child nodes.
                    check(node)

    def test_reviewed_d09_integral_metadata_real_paginator(self):
        for value in (1,1.0,Decimal('1.00')):self.assertTrue(_whole_number(value))
        for value in (True,False,'1',None,1.2,float('nan'),float('inf'),Decimal('NaN'),Decimal('1.01')):self.assertFalse(_whole_number(value))
        path='/investments?itemId=item-test&page=1&pageSize=500'
        self.provider.overrides[path]=(200,{'results':[],'page':Decimal('1'),'total':Decimal('0'),'totalPages':Decimal('0')})
        self.assertEqual(self.sync()['state'],'SUCCEEDED')
        self.provider.overrides[path]=(200,{'results':[],'page':True,'total':0,'totalPages':0})
        self.assertEqual(self.sync()['state'],'FAILED')

    def test_migration011_atomic_failure_reapply_and_coordinated_synthetic_restore(self):
        path=Path(self.temp.name)/'schema10-only.sqlite3';backup=Path(self.temp.name)/'rollback-schema10.sqlite3'
        with patch.object(migrations,'MIGRATIONS',migrations.MIGRATIONS[:10]):migrations.migrate(path)
        with closing(connect(path)) as c:
            c.execute("INSERT INTO accounts(name,active) VALUES('Preserved synthetic',1)")
            snapshot=[tuple(row) for row in c.execute('SELECT * FROM accounts')]
            with closing(sqlite3.connect(backup)) as target:c.backup(target)
        original=Path.read_text
        def broken(file,*args,**kw):
            text=original(file,*args,**kw)
            return text+'\nINSERT INTO missing_synthetic_table VALUES(1);' if file.name.startswith('011_') else text
        with patch.object(Path,'read_text',broken),self.assertRaises(migrations.MigrationError):migrations.migrate(path)
        with closing(connect(path)) as c:
            self.assertEqual(c.execute('PRAGMA user_version').fetchone()[0],10)
            self.assertIsNone(c.execute("SELECT name FROM sqlite_master WHERE name='of_resource_links'").fetchone())
            self.assertEqual([tuple(row) for row in c.execute('SELECT * FROM accounts')],snapshot)
        self.assertEqual(migrations.migrate(path),[11,12]);self.assertEqual(migrations.migrate(path),[])
        with closing(connect(path)) as c:
            self.assertEqual(c.execute('PRAGMA integrity_check').fetchone()[0],'ok')
            self.assertEqual(c.execute('PRAGMA foreign_key_check').fetchall(),[])
            self.assertEqual([tuple(row) for row in c.execute('SELECT * FROM accounts')],snapshot)
        # Restore only this private synthetic DB, with schema10 code gate paired to it.
        with closing(sqlite3.connect(backup)) as source,closing(sqlite3.connect(path)) as target:source.backup(target)
        with patch.object(migrations,'MIGRATIONS',migrations.MIGRATIONS[:10]):migrations.require_current_schema(path)
        with self.assertRaises(migrations.MigrationError):migrations.require_current_schema(path)
        self.assertEqual(self.rows('PRAGMA integrity_check'),[('ok',)])
        baseline=Path(os.environ.get('FINANCE_SCHEMA10_BASELINE_SRC',
            Path(__file__).resolve().parents[2]/'baseline/finance-v17/src'))
        program='''
import io,json,sys,socket,os
from pathlib import Path
from urllib.parse import unquote,urlsplit
request=json.load(sys.stdin);database=Path(request['database']).resolve()
def audit(event,args):
 if event=='sqlite3.connect':
  raw=os.fsdecode(args[0])
  if raw.startswith('file:'):raw=unquote(urlsplit(raw).path).lstrip('/') if sys.platform=='win32' else unquote(urlsplit(raw).path)
  if Path(raw).resolve()!=database:raise PermissionError('ONLY_DECLARED_SYNTHETIC_DB')
 if event.startswith('socket.'):raise PermissionError('NO_NETWORK')
sys.addaudithook(audit)
sys.path.insert(0,request['baseline'])
from finance_v2 import __version__
from finance_v2.api import Application
from finance_v2.config import Settings
from finance_v2.migrations import require_current_schema
require_current_schema(database)
assert __version__=='0.1.26-open-finance.1'
app=Application(Settings(database_path=database,timezone='UTC',host='127.0.0.1',port=8766,busy_timeout_ms=500))
status=[]
response=b''.join(app({'REQUEST_METHOD':'GET','PATH_INFO':'/api/v2/health','QUERY_STRING':'','CONTENT_LENGTH':'0','wsgi.input':io.BytesIO()},lambda s,h:status.append(s)))
assert status[0].startswith('200'),response
data=json.loads(response)
assert data['database']=='ok' and data['migrations']['current_version']==10,data
print('BASELINE_SCHEMA10_RUNTIME_RECOVERY_PASS')
'''
        result=subprocess.run([sys.executable,'-B','-E','-c',program],input=json.dumps({'database':str(path),'baseline':str(baseline)}),capture_output=True,text=True,timeout=15)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(result.stdout.strip(),'BASELINE_SCHEMA10_RUNTIME_RECOVERY_PASS')


if __name__=='__main__':unittest.main(verbosity=2)
