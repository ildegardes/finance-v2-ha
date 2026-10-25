"""D02 diagnostic origins, redaction, API and persistence invariants."""
from contextlib import contextmanager, closing
from dataclasses import replace
from hashlib import sha256
import json
import logging
import time
import unittest
from unittest.mock import patch
from urllib.parse import urlsplit

from support import settings, CLOCK, request, Providers
from test_sqlite_validation import DatabaseCase
from finance_v2.api import Application
from finance_v2.db import connect
from finance_v2.pluggy_client import PluggyClient, PluggyError, ExternalAccount
from finance_v2.pluggy_config import PluggyConnection
from finance_v2.open_finance import OpenFinanceService, SyncError
from finance_v2.open_finance_auto import CoverageWorkers
from finance_v2.open_finance_coverage import sync_full_automatic
from finance_v2 import open_finance_diagnostics as diag

ITEM='D02_SYNTHETIC_ITEM_CANARY'
ACCOUNT='D02_SYNTHETIC_ACCOUNT_CANARY'
SECRET='D02_SYNTHETIC_SECRET_CANARY'
CLIENT='D02_SYNTHETIC_CLIENT_CANARY'
TOKEN='D02_SYNTHETIC_TOKEN_CANARY'
RUN='0123456789abcdef0123456789abcdef'
CANARIES=(ITEM,ACCOUNT,SECRET,CLIENT,TOKEN,'D02_PAYLOAD_PRIVATE','D02_HEADER_PRIVATE')
CONFIG=PluggyConnection('itau','D02_PRIVATE_INSTITUTION_LABEL',CLIENT,SECRET,ITEM,True,True)
EXPECTED_KEYS={'event','version','institution','correlation_id','error_code','resource','operation','stage','category','http_status'}

class Capture(logging.Handler):
    def __init__(self):super().__init__();self.messages=[]
    def emit(self,record):self.messages.append(record.getMessage())
    def events(self):
        return [json.loads(m.removeprefix('OPEN_FINANCE_DIAGNOSTIC ')) for m in self.messages]
@contextmanager
def logs():
    handler=Capture();diag.LOGGER.addHandler(handler)
    try:yield handler
    finally:diag.LOGGER.removeHandler(handler)

def collection(rows):return {'results':rows,'total':len(rows),'totalPages':1,'page':1}
class Fake:
    def __init__(self,*,status_path=None,status=200,auth_status=200,resource=None,row=None,item=None):
        self.status_path,self.status,self.auth_status=status_path,status,auth_status
        self.resource,self.row,self.item=resource,row,item
        self.calls=[]
    def send(self,method,path,headers,body,timeout):
        self.calls.append((method,path))
        if method=='POST':return self.auth_status,{'apiKey':TOKEN}
        base=urlsplit(path).path
        if base==self.status_path:return self.status,{'error':'D02_PAYLOAD_PRIVATE'}
        if base=='/items/'+ITEM:return 200,self.item if self.item is not None else {'id':ITEM,'status':'UPDATED'}
        mapping={'/items/'+ITEM+'/resources':'resources','/accounts':'accounts','/consents':'consents','/investments':'investments','/loans':'loans'}
        rows=[self.row] if mapping.get(base)==self.resource and self.row is not None else []
        if base=='/v2/transactions':return 200,{'results':[],'next':None}
        return 200,collection(rows)
    def client(self):return PluggyClient(CONFIG,send=self.send,sleep=lambda _:None,max_attempts=1)

class OriginTests(unittest.TestCase):
    def error(self,function):
        try:function()
        except PluggyError as error:
            self.assertEqual(str(error),error.code)
            self.assertEqual(error.args,(error.code,))
            return error
        self.fail('EXPECTED_ORIGINAL_ERROR')
    def event(self,error,category,resource,operation,http=None,stage='SCOPE_CHECK'):
        with logs() as captured:self.assertTrue(diag.emit('itau',RUN,error))
        self.assertEqual(len(captured.messages),1)
        for value in CANARIES:self.assertNotIn(value,captured.messages[0])
        event=captured.events()[0]
        self.assertEqual(set(event),EXPECTED_KEYS)
        self.assertEqual((event['category'],event['resource'],event['operation'],event['http_status'],event['stage']),
            (category,resource,operation,http,stage))
        self.assertEqual(event['correlation_id'],'ofdiag-'+sha256(RUN.encode()).hexdigest()[:24])
        return event
    def coverage_scope(self,resource,row,category):
        fake=Fake(resource=resource,row=row)
        error=self.error(lambda:list(fake.client().coverage_pages()))
        self.assertEqual(error.code,'ACCOUNT_SCOPE_MISMATCH')
        self.event(error,category,resource,diag.OPERATIONS[resource])
    def test_scope_item_missing_id(self):
        error=self.error(lambda:list(Fake(item={'status':'UPDATED'}).client().coverage_pages()))
        self.event(error,'RESPONSE_ID_MISSING','item','ITEM_GET')
    def test_scope_item_null_id(self):
        error=self.error(lambda:list(Fake(item={'id':None}).client().coverage_pages()))
        self.event(error,'RESPONSE_ID_NULL','item','ITEM_GET')
    def test_scope_item_foreign_id(self):
        error=self.error(lambda:list(Fake(item={'id':'OTHER_SYNTHETIC_ITEM'}).client().coverage_pages()))
        self.event(error,'RESPONSE_ID_DIFFERENT','item','ITEM_GET')
    def test_scope_consent_missing_item(self):self.coverage_scope('consents',{'id':'synthetic-consent'},'ITEM_ID_MISSING')
    def test_scope_consent_null_item(self):self.coverage_scope('consents',{'id':'synthetic-consent','itemId':None},'ITEM_ID_NULL')
    def test_scope_consent_foreign_item(self):self.coverage_scope('consents',{'id':'synthetic-consent','itemId':'OTHER_SYNTHETIC_ITEM'},'ITEM_ID_DIFFERENT')
    def test_scope_account_missing_item(self):self.coverage_scope('accounts',{'id':ACCOUNT},'ITEM_ID_MISSING')
    def test_scope_account_foreign_item(self):self.coverage_scope('accounts',{'id':ACCOUNT,'itemId':'OTHER_SYNTHETIC_ITEM'},'ITEM_ID_DIFFERENT')
    def test_scope_investment_missing_item(self):self.coverage_scope('investments',{'id':'synthetic-investment'},'ITEM_ID_MISSING')
    def test_scope_loan_foreign_item(self):self.coverage_scope('loans',{'id':'synthetic-loan','itemId':'OTHER_SYNTHETIC_ITEM'},'ITEM_ID_DIFFERENT')
    def test_scope_second_guard_optional_resource(self):self.coverage_scope('resources',{'resourceId':'synthetic-resource','itemId':'OTHER_SYNTHETIC_ITEM'},'ITEM_ID_DIFFERENT')
    def test_scope_legacy_account_response(self):
        error=self.error(lambda:Fake(resource='accounts',row={'id':ACCOUNT}).client().accounts())
        self.event(error,'ITEM_ID_MISSING','accounts','ACCOUNTS_LIST')
    def test_scope_legacy_transaction_membership(self):
        client=Fake().client();client.accounts()
        error=self.error(lambda:list(client.transaction_pages(ACCOUNT)))
        self.event(error,'ACCOUNT_MEMBERSHIP_MISS','transactions','TRANSACTION_ACCOUNT_SCOPE')
    def test_auth_creation_refusal_origin(self):
        fake=Fake(auth_status=401)
        error=self.error(lambda:fake.client().coverage_get('/items/'+ITEM))
        self.assertEqual(fake.calls,[('POST','/auth')])
        self.event(error,'AUTH_REQUEST_REJECTED','other','AUTH_CREATE',401,'TOKEN_ACQUISITION')
    def test_auth_coverage_repeated_401_origin(self):
        fake=Fake(status_path='/items/'+ITEM,status=401)
        error=self.error(lambda:fake.client().coverage_get('/items/'+ITEM))
        self.assertEqual(len(fake.calls),4)
        self.event(error,'REPEATED_401','item','ITEM_GET',401,'RESOURCE_QUERY')
    def test_auth_coverage_required_403_origin(self):
        fake=Fake(status_path='/accounts',status=403)
        error=self.error(lambda:fake.client().coverage_get('/accounts?itemId='+ITEM))
        self.assertEqual(len(fake.calls),2)
        self.event(error,'REQUIRED_RESOURCE_403','accounts','ACCOUNTS_LIST',403,'RESOURCE_QUERY')
    def test_auth_legacy_repeated_401_origin(self):
        fake=Fake(status_path='/v2/transactions',status=401)
        error=self.error(lambda:fake.client()._get('/v2/transactions?accountId='+ACCOUNT))
        self.event(error,'REPEATED_401','transactions','TRANSACTIONS_LIST',401,'RESOURCE_QUERY')
    def test_auth_legacy_required_403_origin(self):
        fake=Fake(status_path='/accounts',status=403)
        error=self.error(lambda:fake.client()._get('/accounts?itemId='+ITEM))
        self.event(error,'REQUIRED_RESOURCE_403','accounts','ACCOUNTS_LIST',403,'RESOURCE_QUERY')
    def test_optional_403_behavior_and_no_diagnostic_preserved(self):
        fake=Fake(status_path='/consents',status=403)
        with logs() as captured:
            self.assertEqual(fake.client().coverage_get('/consents?itemId='+ITEM,optional=True),({},'NOT_AUTHORIZED'))
        self.assertEqual(captured.messages,[])
    def test_non_target_error_not_annotated_or_logged(self):
        error=PluggyError('PROVIDER_HTTP_ERROR')
        self.assertIs(diag.annotate(error,category=SECRET),error)
        self.assertFalse(hasattr(error,'_of_diagnostic'))
        with logs() as captured:self.assertFalse(diag.emit('itau',RUN,error))
        self.assertEqual(captured.messages,[])
    def test_path_classifier_never_returns_identifiers_or_query(self):
        paths={'/accounts/'+ACCOUNT+'/statements?secret='+SECRET:'statements',
            '/investments/'+ACCOUNT+'/transactions?after='+TOKEN:'investment_transactions',
            '/consents?itemId='+ITEM:'consents','/loans?itemId='+ITEM:'loans',
            '/bills?accountId='+ACCOUNT:'bills','/items/'+ITEM+'/resources':'resources'}
        for path,resource in paths.items():
            self.assertEqual(diag.describe_path(path)['resource'],resource)
            for value in CANARIES:self.assertNotIn(value,json.dumps(diag.describe_path(path)))
    def test_adversarial_metadata_is_strictly_reallowlisted_at_emit(self):
        error=PluggyError('AUTH_FAILED')
        error._of_diagnostic={k:SECRET for k in ('resource','operation','stage','category','http_status')}
        error._of_diagnostic.update({'headers':TOKEN,'body':'D02_PAYLOAD_PRIVATE','itemId':ITEM})
        with logs() as captured:self.assertTrue(diag.emit('D02_PRIVATE_INSTITUTION_LABEL',SECRET,error))
        event=captured.events()[0]
        self.assertEqual(event['institution'],'OTHER');self.assertEqual(event['correlation_id'],'UNAVAILABLE')
        self.assertEqual(set(event),EXPECTED_KEYS)
        self.assertLess(len(captured.messages[0]),600)
        for value in (*CANARIES,'D02_PRIVATE_INSTITUTION_LABEL'):self.assertNotIn(value,captured.messages[0])
    def test_bool_status_and_foreign_context_types_cannot_leak(self):
        error=diag.annotate(PluggyError('AUTH_FAILED'),http_status=True)
        with logs() as captured:diag.emit('santander',RUN,error)
        self.assertIsNone(captured.events()[0]['http_status'])
        error._of_diagnostic=SECRET
        with logs() as captured:diag.emit('santander',RUN,error)
        self.assertEqual(captured.events()[0]['category'],'OTHER_CONDITION')
    def test_correlation_consistent_per_run_distinct_between_runs(self):
        error=PluggyError('AUTH_FAILED')
        with logs() as captured:
            diag.emit('itau',RUN,error);diag.emit('itau',RUN,error);diag.emit('santander','f'*32,error)
        events=captured.events()
        self.assertEqual(events[0]['correlation_id'],events[1]['correlation_id'])
        self.assertNotEqual(events[0]['correlation_id'],events[2]['correlation_id'])

class ServiceDiagnosticTests(DatabaseCase):
    def check_event(self,captured,run,category,bank='itau'):
        self.assertEqual(len(captured.messages),1)
        event=captured.events()[0]
        self.assertEqual(event['category'],category)
        self.assertEqual(event['institution'],bank.upper())
        self.assertEqual(event['correlation_id'],'ofdiag-'+sha256(run['id'].encode()).hexdigest()[:24])
        self.assertEqual(event['error_code'],run['error_code'])
        return event
    def test_sixth_scope_origin_real_persistence_guard_legacy(self):
        class WrongClient:
            def accounts(self):return (ExternalAccount('santander','synthetic-account',None,None,None,None,None),)
        service=OpenFinanceService(self.config,CLOCK,client_factory=lambda _:WrongClient())
        with logs() as captured:run=service.sync_one('itau',actor='UI:local')
        self.assertEqual((run['state'],run['error_code']),('FAILED','ACCOUNT_SCOPE_MISMATCH'))
        event=self.check_event(captured,run,'LOCAL_CONNECTION_MISMATCH')
        self.assertEqual(event['operation'],'ACCOUNTS_PERSIST')
    def test_auto_service_emits_once_and_keeps_existing_run_shape(self):
        self.providers.banks['itau'].overrides['/consents?itemId=item-test']=(200,collection([{'id':'synthetic-consent'}]))
        with logs() as captured:run=CoverageWorkers(self.config,send=self.providers.send)._run_one(self.config.pluggy_connections[0])
        self.assertEqual(run['error_code'],'ACCOUNT_SCOPE_MISMATCH')
        self.check_event(captured,run,'ITEM_ID_MISSING')
        self.assertNotIn('diagnostic',json.dumps(run));self.assertNotIn('ofdiag-',json.dumps(run))
    def test_legacy_auth_failure_emits_once(self):
        self.providers.banks['santander'].mode='auth-failed'
        with logs() as captured:run=self.service.sync_one('santander',actor='UI:local')
        self.check_event(captured,run,'AUTH_REQUEST_REJECTED','santander')
    def test_logging_sink_failure_never_prevents_existing_finalization(self):
        self.providers.banks['itau'].mode='auth-failed'
        with patch.object(diag.LOGGER,'warning',side_effect=RuntimeError('D02_BROKEN_SINK')):
            run=CoverageWorkers(self.config,send=self.providers.send)._run_one(self.config.pluggy_connections[0])
        self.assertEqual((run['state'],run['error_code']),('FAILED','AUTH_FAILED'))
        with closing(connect(self.path)) as c:
            self.assertEqual(c.execute('SELECT count(*) FROM of_connections WHERE lease_token IS NOT NULL').fetchone()[0],0)
    def test_http_response_preserves_error_code_and_excludes_diagnostic(self):
        self.providers.banks['itau'].mode='auth-failed'
        app=Application(self.config,CLOCK)
        with patch('finance_v2.open_finance_http.OpenFinanceService',return_value=self.service):
            with logs() as captured:
                status,payload=request(app,'/api/v2/open-finance/coverage-sync',{'connection_id':'itau'},'POST')
        self.assertEqual(status,502);self.assertEqual(payload['run']['error_code'],'AUTH_FAILED')
        self.assertNotIn('OPEN_FINANCE_DIAGNOSTIC',json.dumps(payload));self.assertNotIn('ofdiag-',json.dumps(payload))
        self.check_event(captured,payload['run'],'AUTH_REQUEST_REJECTED')
    def test_concurrent_workers_emit_bank_local_context_and_stop(self):
        self.providers.banks['itau'].mode='auth-failed'
        self.providers.banks['santander'].overrides['/consents?itemId=item-test']=(200,collection([{'id':'synthetic-consent'}]))
        workers=CoverageWorkers(self.config,send=self.providers.send)
        try:
            with logs() as captured:
                workers.start();deadline=time.monotonic()+5
                while len(captured.messages)<2 and time.monotonic()<deadline:time.sleep(.02)
                self.assertTrue(workers.stop())
        finally:workers.stop()
        self.assertEqual(len(captured.messages),2)
        events={e['institution']:e for e in captured.events()}
        self.assertEqual(events['ITAU']['category'],'AUTH_REQUEST_REJECTED')
        self.assertEqual(events['SANTANDER']['category'],'ITEM_ID_MISSING')
        self.assertNotEqual(events['ITAU']['correlation_id'],events['SANTANDER']['correlation_id'])
        self.assertFalse(any(t.is_alive() for t in workers.threads))
