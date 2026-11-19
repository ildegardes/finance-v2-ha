"""Official SnapTrade Personal response shape through SDK 13.4.4 and isolated transport."""
from contextlib import closing
from dataclasses import replace
import io
import json
from urllib.parse import parse_qs,urlsplit
import unittest
from unittest.mock import Mock,patch

import urllib3

from finance_v2.api import Application
from finance_v2.db import connect
from finance_v2.snaptrade_read import ProviderFailure,SnapTradeReader
from finance_v2.snaptrade_sync import status,sync
import test_snaptrade_036 as fixture

OWNER='synthetic-local-owner-037'
LEAK='private-fixture-value-037'
OTHER='62000000-0000-4000-8000-000000000099'


class PersonalContract(unittest.TestCase):
    def setUp(self):
        self.case=fixture.SnapTradeTests('test_discovery_currency_and_cash_once')
        self.case.setUp()
        self.addCleanup(self.case.doCleanups)
        self.broker=self.case.broker
        self.broker.second=False
        self.accounts=self.broker.read('accounts')['results']
        self.connections=self.broker.read('connections')
        self.accounts[0].update(sync_status={'positions':fixture.STAMP,'balances':None},
                                raw_type=None,display_name=None,institution_account_id=None)
        self.connections[0]['brokerage']['display_name']='Charles Schwab'
        self.requests=[]
        self.overrides={}
        transport=patch.object(urllib3.PoolManager,'request',side_effect=self.transport)
        transport.start()
        self.addCleanup(transport.stop)

    def transport(self,method,url,*args,**kwargs):
        path=urlsplit(url).path
        resource=path.rstrip('/').split('/')[-1]
        if path.endswith('/accounts/all'):
            operation,body='accounts',{'results':self.accounts}
        elif resource=='authorizations':
            operation,body='connections',self.connections
        else:
            operation={'v2':'balances','all':'positions','activities':'activities'}[resource]
            remote=path.split('/accounts/')[1].split('/')[0]
            query=parse_qs(urlsplit(url).query)
            body=self.broker.read(operation,account_id=remote,offset=int(query.get('offset',['0'])[0]),
                                  limit=int(query.get('limit',['1000'])[0]))
        self.requests.append((operation,method,url,kwargs))
        code,headers,raw=self.overrides.get(operation,(200,{},None))
        return urllib3.HTTPResponse(body=raw if raw is not None else json.dumps(body).encode(),status=code,
             headers={'Content-Type':'application/json',**headers},preload_content=True)

    def run_sdk(self,**options):
        return sync(self.case.service,**options)

    def get_status(self):
        with closing(connect(self.case.case.db)) as db:
            return status(db,self.case.settings,self.case.clock.now_utc().timestamp())

    def app(self):
        return Application(replace(self.case.settings,ui_token=OWNER),self.case.clock)

    def request(self,app,path,method='GET',body=None,cookie=None,csrf=None):
        encoded=body if isinstance(body,bytes) else json.dumps(body).encode() if body is not None else b''
        captured=[]
        env={'PATH_INFO':path,'REQUEST_METHOD':method,'QUERY_STRING':'','HTTP_HOST':'127.0.0.1',
             'wsgi.url_scheme':'http','wsgi.input':io.BytesIO(encoded),'CONTENT_LENGTH':str(len(encoded)),
             'CONTENT_TYPE':'application/x-www-form-urlencoded' if isinstance(body,bytes) else 'application/json',
             'HTTP_X_REQUEST_ID':LEAK}
        if cookie:
            env['HTTP_COOKIE']=cookie
        if csrf:
            env['HTTP_X_CSRF_TOKEN']=csrf
        raw=b''.join(app(env,lambda status,headers:captured.extend((int(status.split()[0]),dict(headers)))))
        return *captured,json.loads(raw) if raw else None

    def test_sdk_discovery_and_import_official_contract(self):
        from snaptrade_client import __version__
        self.assertEqual(__version__,'13.4.4')
        self.accounts.extend([
            {'kind':'deposit','id':OTHER,'connection_id':fixture.AUTH,'display_name':None,'masked_account_number':'****1122'},
            {'kind':'investment','id':fixture.ACCOUNT2,'connection_id':fixture.AUTH,'is_paper':True,'status':'open'}
        ])
        result=self.run_sdk()
        self.assertEqual(result['state'],'AVAILABLE')
        self.assertEqual([r[0] for r in self.requests],['connections','accounts','balances','positions','activities'])
        for _,method,url,options in self.requests:
            query=parse_qs(urlsplit(url).query)
            self.assertEqual(method,'GET')
            self.assertEqual(query['clientId'],[fixture.CLIENT])
            self.assertFalse({'userId','userSecret'} & query.keys())
            self.assertNotIn(fixture.SECRET,url)
            self.assertIn('signature',{name.lower() for name in options['headers']})
            self.assertEqual((options['timeout'].connect_timeout,options['timeout'].read_timeout),(4,8))
            self.assertFalse(options['redirect'])
            self.assertFalse(options['retries'])
        accounts=self.get_status()['connections'][0]['accounts']
        current=next(a for a in accounts if a['state']=='AVAILABLE')
        self.assertEqual((current['label'],current['suffix'],current['provider_updated_at']),
                         ('Conta de corretora','5612',fixture.STAMP))
        self.assertEqual(sum(a['state']=='INACTIVE' for a in accounts),2)
        self.assertEqual(len(self.case.view(provider='SNAPTRADE')['items']),1)
        self.assertEqual(self.case.view(view='activities')['total'],11)

    def test_missing_nullable_and_invalid_connections_and_accounts(self):
        self.assertEqual(self.run_sdk(discover=True)['state'],'AVAILABLE')
        for body,reason,field in (([], 'UNEXPECTED_ENVELOPE','results'),({},'MISSING_FIELD','results'),
                                  ({'results':None},'UNEXPECTED_FIELD_TYPE','results'),
                                  ({'results':[{'id':fixture.ACCOUNT,'brokerage_authorization':fixture.AUTH}]},
                                   'MISSING_FIELD','connection_id')):
            with self.subTest(reason=reason,body=body):
                self.overrides['accounts']=(200,{},json.dumps(body).encode())
                failure=self.run_sdk(discover=True)['diagnostic']
                self.assertEqual((failure['stage'],failure['resource'],failure['reason'],failure['field'],failure['remote_status']),
                                 ('STRUCTURE','ACCOUNTS',reason,field,200))
        self.overrides.clear()
        self.accounts[0]['connection_id']=fixture.AUTH2
        self.assertEqual(self.run_sdk()['diagnostic']['reason'],'UNMATCHED_CONNECTION')
        self.assertEqual(self.get_status()['connections'][0]['provider_state'],'AVAILABLE')
        self.accounts[0]['connection_id']=fixture.AUTH
        self.accounts[0]['is_paper']='false'
        self.assertEqual(self.run_sdk()['diagnostic']['field'],'is_paper')
        self.accounts[0]['is_paper']=False
        self.connections[0]['disabled']='false'
        self.assertEqual(self.run_sdk()['diagnostic']['resource'],'CONNECTIONS')
        del self.connections[0]['disabled']
        self.assertEqual(self.run_sdk()['state'],'AVAILABLE')
        self.assertEqual(self.get_status()['connections'][0]['provider_state'],'UNKNOWN')
        self.connections[0]['disabled']=None
        self.assertEqual(self.run_sdk()['state'],'AVAILABLE')
        self.connections[0]['disabled']=False
        self.assertEqual(self.run_sdk()['state'],'AVAILABLE')

    def test_sdk_invocation_response_and_decoding_are_distinct(self):
        reader=SnapTradeReader(fixture.CLIENT,fixture.SECRET)
        for side_effect,response,expected in (
            (TypeError(LEAK),None,'SNAPTRADE_SDK_CALL'),
            (ValueError(LEAK),None,'SNAPTRADE_SDK_CALL'),
            (None,object(),'SNAPTRADE_SDK_RESPONSE'),
            (urllib3.exceptions.ReadTimeoutError(None,None,LEAK),None,'SNAPTRADE_TRANSPORT')):
            with self.subTest(expected=expected),patch.dict(reader._reads,{'accounts':Mock(
                    side_effect=side_effect,return_value=response)}):
                with self.assertRaises(ProviderFailure) as error:
                    reader.read('accounts')
                self.assertEqual(error.exception.code,expected)
                self.assertNotIn(LEAK,json.dumps(error.exception.diagnostic()))
        self.overrides['accounts']=(200,{},('{'+LEAK).encode())
        detail=self.run_sdk(discover=True)['diagnostic']
        self.assertEqual((detail['error_code'],detail['stage'],detail['remote_status']),
                         ('SNAPTRADE_INVALID_JSON','JSON_DECODE',200))

    def test_remote_auth_signature_rate_limit_and_transport(self):
        for code,raw,expected in (
            (401,b'{invalid','SNAPTRADE_AUTH'),
            (401,b'{"detail":"Unable to verify signature sent"}','SNAPTRADE_SIGNATURE'),
            (429,b'<html>busy</html>','SNAPTRADE_RATE_LIMIT')):
            self.overrides['accounts']=(code,{'Retry-After':'660'},raw)
            detail=self.run_sdk(discover=True)['diagnostic']
            self.assertEqual((detail['error_code'],detail['stage'],detail['remote_status']),(expected,'REMOTE_HTTP',code))
        with self.assertRaisesRegex(fixture.SyncError,'SNAPTRADE_RATE_LIMIT'):
            self.run_sdk(discover=True)
        self.assertEqual(self.get_status()['next_attempt'],'2026-10-20T19:11:00Z')

    def test_cache_and_result_survive_remote_financial_data_and_persistence_failure(self):
        self.assertEqual(self.run_sdk()['state'],'AVAILABLE')
        before=self.case.view(provider='SNAPTRADE')['items'][0]['market_value']
        body=self.broker.read('positions',account_id=fixture.ACCOUNT)
        body['results'][0]['price']=LEAK
        self.overrides['positions']=(200,{},json.dumps(body).encode())
        failed=self.run_sdk()
        self.assertEqual((failed['state'],failed['diagnostic']['field']),('PARTIAL','price'))
        self.assertEqual(self.case.view(provider='SNAPTRADE')['items'][0]['market_value'],before)
        self.overrides.clear()
        self.case.case.write("CREATE TRIGGER fail_discovery BEFORE UPDATE ON st_connections BEGIN SELECT RAISE(ABORT,'private error'); END")
        failed=self.run_sdk(discover=True)
        self.assertEqual((failed['error_code'],failed['diagnostic']['stage']),('SNAPTRADE_STORAGE','PERSISTENCE'))
        self.assertEqual(self.case.view(provider='SNAPTRADE')['items'][0]['market_value'],before)
        self.case.case.write('DROP TRIGGER fail_discovery')
        self.assertEqual(self.run_sdk()['state'],'AVAILABLE')
        self.assertEqual(self.get_status()['last_result'],'AVAILABLE')

    def test_wsgi_logs_and_persisted_diagnostics_share_an_internal_id_without_secrets(self):
        app=self.app()
        endpoint='/api/v2/open-finance/snaptrade'
        self.assertEqual(self.request(app,endpoint)[0],401)
        _,headers,_=self.request(app,'/app/session','POST',('token='+OWNER).encode())
        cookie=headers['Set-Cookie'].split(';')[0]
        _,_,context=self.request(app,'/api/v2/context',cookie=cookie)
        remote={'code':LEAK,'signature':LEAK,'access_token':LEAK,'description':fixture.FULL_NUMBER,
                'clientId':fixture.CLIENT,'consumerKey':fixture.SECRET,'account':fixture.ACCOUNT}
        self.connections[0]['meta']={'private':LEAK}
        self.overrides['accounts']=(502,{},json.dumps(remote).encode())
        with self.assertLogs(level='DEBUG') as logs:
            code,_,posted=self.request(app,endpoint+'/discovery','POST',{},cookie,context['csrf_token'])
        self.assertEqual(code,502)
        self.assertRegex(posted['request_id'],r'^[a-f0-9]{32}$')
        self.assertEqual(posted['diagnostic']['request_id'],posted['request_id'])
        self.assertIn(posted['request_id'],' '.join(logs.output))
        _,_,saved=self.request(app,endpoint,cookie=cookie)
        self.assertEqual(saved['last_attempt_result'],posted['diagnostic'])
        self.assertEqual(saved['last_attempt'],saved['last_attempt_result']['attempted_at'])
        self.assertEqual(saved['last_result'],'FAILED')
        journal=self.case.case.sql("SELECT target FROM st_events WHERE action='ATTEMPT_RESULT'")
        evidence=json.dumps([posted,saved,logs.output,journal])
        signed=self.requests[0]
        signature=next(value for name,value in signed[3]['headers'].items() if name.lower()=='signature')
        for value in (fixture.FULL_NUMBER,fixture.CLIENT,fixture.SECRET,fixture.ACCOUNT,LEAK,OWNER,cookie,
                      context['csrf_token'],signed[2],signature):
            self.assertNotIn(value,evidence)
        self.overrides.clear()
        _,_,recovered=self.request(app,endpoint+'/sync','POST',{},cookie,context['csrf_token'])
        self.assertEqual(recovered['state'],'AVAILABLE')
        self.assertNotEqual(recovered['request_id'],posted['request_id'])
        self.assertEqual(recovered['diagnostic']['request_id'],recovered['request_id'])


if __name__=='__main__':
    unittest.main()
