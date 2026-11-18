"""Synthetic SQLite, migration, classification and financial invariants."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from dataclasses import replace
from decimal import Decimal
from hashlib import sha256
import io
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from wsgiref.util import setup_testing_defaults

import test_full_coverage as fixtures
from finance_v2 import migrations
from finance_v2.api import Application
from finance_v2.db import connect
from finance_v2.open_finance import SyncError
from finance_v2.open_finance_analytics import analytics
from finance_v2.open_finance_classification import Facts, native, normalize
from finance_v2.open_finance_classification_admin import ClassificationAdmin

OWNER='UI:local'
START='2026-10-01'
END='2026-10-31'
SCOPE={'start':START,'end':END,'currency':'BRL','history':False}
QUERY={'start':[START],'end':[END]}


class ClassificationTest(unittest.TestCase):
    def setUp(self):
        self.fixture=fixtures.CoverageTests(methodName='test_all_products_projection_history_and_financial_preservation')
        self.addCleanup(self.fixture.doCleanups)
        self.fixture.setUp()
        self.fixture.sync()
        self.settings=self.fixture.settings
        self.admin=ClassificationAdmin(self.fixture.service)
        self.db=self.fixture.db

    def write(self, sql, args=()):
        with closing(connect(self.db)) as db:
            db.execute(sql,args)
            db.commit()

    def sql(self,sql,args=()):
        with closing(connect(self.db)) as db:
            return [tuple(row) for row in db.execute(sql,args)]

    def tx(self,id,description,amount,direction='CREDIT',*,currency='BRL',run=None):
        with closing(connect(self.db)) as db:
            source=db.execute("""SELECT * FROM of_resource_records
                WHERE resource='transactions' AND parent_id='account-BANK' LIMIT 1""").fetchone()
            body={**json.loads(source['payload_json']),'description':description,'id':id,'amount':amount,'type':direction,'currencyCode':currency}
            payload=json.dumps(body)
            db.execute("""INSERT INTO of_resource_records(connection_id,resource,parent_id,external_id,payload_json,payload_hash,
                state,first_run_id,last_run_id,observed_at) VALUES (?,'transactions',?,?,?,?,?,?,?,?)
                ON CONFLICT(connection_id,resource,parent_id,external_id) DO UPDATE SET
                  payload_json=excluded.payload_json,payload_hash=excluded.payload_hash,last_run_id=excluded.last_run_id""",
                (source['connection_id'],source['parent_id'],id,payload,sha256(payload.encode()).hexdigest(),
                 'PRESENT',run or source['first_run_id'],run or source['last_run_id'],source['observed_at']))
            db.commit()

    def next_run(self):
        from uuid import uuid4
        run=uuid4().hex
        self.write("""INSERT INTO of_sync_runs(id,connection_id,actor,started_at,finished_at,state)
                      VALUES (?,'bank-test','UI:local','2026-10-26T00:00:00Z','2026-10-26T00:00:01Z','SUCCEEDED')""",(run,))
        return run

    def request(self,action,body={},query={}):
        return self.admin.dispatch(action,body,query,OWNER)

    def report(self,query=None):
        with closing(connect(self.db)) as db:
            return analytics(db,self.settings,{**QUERY,**(query or {})},today='2026-10-01')

    def customize(self,term,category='Salário',nature='SALARY',priority=100,**control):
        return {'name':category,'description':'Regra sintética','priority':priority,'enabled':True,
                'conditions':{'connection_id':'bank-test','account_id':'account-BANK','match':'exact',
                              'description':term,'direction':'incoming','product':'BANK','currency':'BRL'},
                'result':{'category':category,'nature':nature},**control}

    def identity(self,id):
        return {'connection_id':'bank-test','account_id':'account-BANK','transaction_id':id}

    def label(self,id,nature,category,*,event=None,**extra):
        return self.request('manual',{'identity':self.identity(id),'event':event,
                            'decision':{'category':category,'nature':nature,**extra}})

    def test_native_scope_exact_patterns_and_currency(self):
        cases=[
            ('Débito automático Cartao Itau The One','DEBIT','CARD_PAYMENT',None),
            ('Débito automático Itau Visa 0900-0040','DEBIT','CARD_PAYMENT',None),
            ('Saída COR ITAUCOR COMPRA TD','DEBIT','APPLICATION',None),
            ('Saída COR OPERACOES B3','DEBIT','INVESTMENT_SETTLEMENT',None),
            ('Entrada COR RENDIMENTO RBVA11','CREDIT','INVESTMENT_INCOME','RBVA11'),
            ('Entrada COR JSCP LREN3','CREDIT','INVESTMENT_INCOME','LREN3'),
            ('COR dividendos ABCD3','CREDIT','INVESTMENT_INCOME','ABCD3'),
            ('COR amortização ABCD3','CREDIT','CAPITAL_RETURN','ABCD3'),
            ('IR sobre APLIC AUT MAIS','DEBIT','TAX',None),
            ('COR COMPRA TDA','DEBIT',None,None),
            ('COR RENDIMENTO parcelado RBVA11','CREDIT',None,None),
            ('RES APLIC AUT MAIS','DEBIT',None,None),
            ('Compra APL APLIC AUT MAIS Loja','DEBIT',None,None),
            ('TED RECEBIDA REMETENTE SINTÉTICO','CREDIT',None,None),
        ]
        for description,direction,nature,asset in cases:
            row={'connection_id':'itau','parent_id':'synthetic-account','external_id':'synthetic-transaction',
                 'data':{'description':description,'type':direction,'currencyCode':'BRL'}}
            facts=Facts.from_row(row,'Itaú - itau','BANK','missing')
            result=native(facts)
            self.assertEqual(result and result['nature'],nature,description)
            self.assertEqual(result and result.get('asset'),asset,description)
            self.assertIsNone(native(replace(facts,institution='Santander')))
            self.assertIsNone(native(replace(facts,currency='USD')))
        self.assertEqual(normalize('  Débito/automático—CARTÃO  '),'debito automatico cartao')

    def test_bulk_preview_audit_concurrency_and_undo(self):
        for index in range(320):
            self.tx(f'repeated-{index:03}', 'TED recebida de empregador fictício', '10.25')
        initial = self.report({'center':['1']})['classification_center']
        self.assertEqual(initial['groups'][0]['count'],320)
        original=self.sql("SELECT external_id,payload_hash FROM of_resource_records ORDER BY resource,parent_id,external_id")
        self.label('repeated-000','INCOME','Exceção manual')
        definition=self.customize('TED RECEBIDA DE EMPREGADOR FICTICIO')
        rule=self.request('rule',{'revision':0,'rule':definition})
        payload={**rule,'scope':SCOPE}
        preview=self.request('preview',payload)
        self.assertEqual(preview['counts'],{'matched':320,'manual':1,'apply':319})
        self.assertEqual(self.sql('SELECT count(*) FROM of_classification_batches'),[(0,)])
        self.assertEqual(self.sql('SELECT count(*) FROM of_classification_events'),[(1,)])
        with self.assertRaisesRegex(SyncError,'CLASSIFICATION_CONFIRMATION_REQUIRED'):
            self.request('apply',{**payload,'confirmed':False,'digest':preview['digest']})
        self.label('repeated-001','INCOME','Classificação posterior')
        with self.assertRaisesRegex(SyncError,'CLASSIFICATION_STALE'):
            self.request('apply',{**payload,'confirmed':True,'digest':preview['digest']})
        preview=self.request('preview',payload)
        body={**payload,'confirmed':True,'digest':preview['digest']}
        with ThreadPoolExecutor(max_workers=2) as executor:
            results=list(executor.map(lambda _:self.request('apply',body),range(2)))
        original_result, replay = sorted(results,key=lambda r:r['replayed'])
        self.assertEqual(original_result['applied'],318)
        self.assertTrue(replay['replayed'])
        self.assertEqual(replay['id'],original_result['id'])
        self.assertEqual(original,self.sql("SELECT external_id,payload_hash FROM of_resource_records ORDER BY resource,parent_id,external_id"))
        labels=self.report({'nature':['SALARY']})
        self.assertEqual(labels['total'],318)
        self.assertEqual(labels['flow']['BANK']['incoming'],'3259.50')
        old_event=self.sql("SELECT id FROM of_classification_current WHERE transaction_id='repeated-002'")[0][0]
        self.label('repeated-002','INCOME','Preservar alteração posterior',event=old_event)
        run=self.next_run()
        self.tx('repeated-002','TED recebida reformulada','10.25',run=run)
        self.tx('future-pay','TED recebida de empregador fictício','15.25',run=run)
        self.assertEqual(self.report({'search':['reformulada']})['items'][0]['classification']['origin'],'MANUAL')
        self.assertEqual(self.report({'nature':['SALARY']})['total'],318)
        undone=self.request('undo',{'id':original_result['id'],'confirmed':True})
        self.assertEqual(undone,{'restored':317,'conflicts':1})
        second=self.request('undo',{'id':original_result['id'],'confirmed':True})
        self.assertEqual(second,{'already_restored':317,'conflicts':1})
        self.assertEqual(self.report({'nature':['SALARY']})['total'],1)
        self.assertEqual(self.request('audit')['events'][0]['action'],'UNDO')
        self.assertEqual(self.sql('PRAGMA foreign_key_check'),[])

    def test_rule_revisions_prospective_conflict_and_manual_precedence(self):
        one=self.request('rule',{'revision':0,'rule':self.customize('Recebimento fictício')})
        old=self.next_run()
        self.tx('salary-facts','Recebimento fictício',15,run=old)
        two=self.request('rule',{'revision':0,'rule':self.customize('Recebimento fictício','Reembolso','INCOME')})
        new=self.next_run()
        self.tx('conflicting','Recebimento fictício',20,run=new)
        items={r['external_id']:r for r in self.report()['items']}
        self.assertEqual(items['salary-facts']['classification']['rule_id'],one['id'])
        self.assertEqual(items['conflicting']['classification']['review'],'CONFLICT')
        manual=self.label('conflicting','SALARY','Salário confirmado')
        payload={**two,'rule':self.customize('Recebimento fictício','Reembolso','INCOME',priority=105)}
        updated=self.request('rule',payload)
        self.assertEqual(updated['revision'],2)
        self.tx('after-change','Recebimento fictício',23,run=self.next_run())
        items={r['external_id']:r for r in self.report()['items']}
        self.assertEqual(items['after-change']['classification']['rule_revision'],2)
        self.assertEqual(items['conflicting']['classification']['event'],manual['event'])
        with self.assertRaisesRegex(SyncError,'CLASSIFICATION_STALE'):
            self.request('rule',payload)
        with self.assertRaisesRegex(SyncError,'CLASSIFICATION_SCOPE_REQUIRED'):
            ruled=self.customize('Genérica')
            ruled['conditions'].pop('connection_id')
            self.request('rule',{'revision':0,'rule':ruled})

    def test_automatic_investment_example_and_coverage(self):
        self.write("UPDATE of_connection_registry SET label='Itaú' WHERE connection_id='bank-test'")
        self.tx('application','Aplicação APL APLIC AUT MAIS','20000','DEBIT')
        self.tx('redemption','Resgate RES APLIC AUT MAIS','5000')
        self.tx('credited','Rendimentos REND PAGO APLIC AUT MAIS','2')
        self.tx('salary','Crédito de empregador fictício','20000')
        self.tx('expense','Despesa comprovada','5000','DEBIT')
        self.tx('foreign','COR dividendos ABCD3','93','CREDIT',currency='USD')
        old=self.sql("SELECT external_id FROM of_resource_records WHERE resource='transactions' AND parent_id='account-BANK' AND external_id NOT IN ('application','redemption','credited','salary','expense','foreign')")[0][0]
        self.write("UPDATE of_resource_records SET state='NOT_SEEN' WHERE resource='transactions' AND external_id=?",(old,))
        self.label('salary','SALARY','Salário')
        self.label('expense','EXPENSE','Despesas')
        result=self.report()
        self.assertEqual(result['flow']['BANK']['incoming'],'25002')
        self.assertEqual(result['flow']['BANK']['outgoing'],'25000')
        self.assertEqual(result['insights']['coverage'],'PARTIAL')
        self.assertEqual(result['insights']['bridge']['pending']['incoming'],'5000')
        self.assertEqual(result['insights']['income']['value'],'2')
        self.assertEqual(result['insights']['automatic']['value']['capital_flow'],'-15000')
        self.write("UPDATE of_sync_runs SET date_from=?, date_to=?",(START,END))
        self.write("UPDATE of_resource_coverage SET omitted_field_count=0 WHERE resource IN ('accounts','transactions')")
        self.label('redemption','REDEMPTION','Resgate de principal',investment='Aplic Aut Mais',principal_only=True)
        result=self.report()
        self.assertEqual(result['flow']['BANK']['net'],'2')
        self.assertEqual(result['insights']['coverage'],'COMPLETE_BANK_SCOPE')
        self.assertEqual(result['insights']['known'],{'incoming':'20002','outgoing':'5000','net':'15002'})
        for direction in ('incoming','outgoing'):
            contents=[Decimal(bucket[direction]) for bucket in result['insights']['bridge'].values() if bucket[direction] is not None]
            self.assertEqual(sum(contents),Decimal(result['flow']['BANK'][direction]))

    def test_card_projection_keeps_shared_limits_and_unknown_values_separate(self):
        with closing(connect(self.db)) as db:
            original=db.execute("SELECT * FROM of_resource_records WHERE resource='accounts' AND external_id='account-CREDIT'").fetchone()
            base=json.loads(original['payload_json'])
            for index,status,balance in [(1,'ACTIVE',0),(2,'ACTIVE',None),(3,'ACTIVE',44),(4,'CANCELLED',700)]:
                data={**base,'id':f'credit-{index}','name':f'Cartão teste {index} 4000 0000 0000 0002',
                      'balance':balance,'creditData':{'status':status,'creditLimit':1000,'disaggregatedCreditLimits':[
                          {'consolidationType':'CONSOLIDATED','creditLineLimitType':'LIMITE_CREDITO_TOTAL',
                           'usedAmount':44,'limitAmount':1000,'usedAmountCurrencyCode':'BRL','limitAmountCurrencyCode':'BRL'}]}}
                db.execute("""INSERT INTO of_resource_records VALUES (?,?,?,?,?,?,?,?,?,?)""",
                           (original['connection_id'],'accounts','',data['id'],json.dumps(data),original['payload_hash'],
                            'PRESENT',original['first_run_id'],original['last_run_id'],original['observed_at']))
            db.commit()
        result=self.report()['cards']
        self.assertEqual(result['active_count'],3)
        self.assertIsNone(result['limit'])
        self.assertIsNone(result['utilization'])
        rows={row['account_id']:row for row in result['items']}
        self.assertEqual(rows['credit-1']['balance'],'0')
        self.assertIsNone(rows['credit-2']['balance'])
        self.assertNotIn('credit-4',rows)
        self.assertIn('•••• 0002',rows['credit-1']['name'])
        self.assertIsNone(rows['credit-3']['utilization'])

    def test_large_history_and_no_materialization_on_read(self):
        import time
        self.write("""WITH RECURSIVE n(x) AS (SELECT 1 UNION ALL SELECT x+1 FROM n WHERE x<3200)
            INSERT INTO of_resource_records(connection_id,resource,parent_id,external_id,payload_json,payload_hash,
                                           state,first_run_id,last_run_id,observed_at)
            SELECT t.connection_id,t.resource,t.parent_id,'perf-'||n.x,
                   json_set(t.payload_json,'$.description','Crédito repetido para medição','$.type','CREDIT','$.amount',0.01),
                   t.payload_hash,t.state,t.first_run_id,t.last_run_id,t.observed_at
            FROM n CROSS JOIN (SELECT * FROM of_resource_records WHERE resource='transactions'
                               AND parent_id='account-BANK' LIMIT 1) t""")
        stamp=time.monotonic()
        report=self.report({'center':['1']})
        self.assertEqual(report['classification_center']['groups'][0]['count'],3200)
        self.assertEqual(report['flow']['BANK']['incoming'],'32.00')
        rule=self.request('rule',{'revision':0,'rule':self.customize('Crédito repetido para medição')})
        payload={**rule,'scope':SCOPE}
        preview=self.request('preview',payload)
        self.assertEqual(preview['counts']['apply'],3200)
        self.assertEqual(self.sql('SELECT count(*) FROM of_classification_events'),[(0,)])
        result=self.request('apply',{**payload,'digest':preview['digest'],'confirmed':True})
        self.assertEqual(result['applied'],3200)
        self.assertLess(time.monotonic()-stamp,25)
        self.assertEqual(self.report({'nature':['SALARY']})['total'],3200)

    def test_http_session_csrf_and_no_external_access(self):
        app=Application(self.settings)
        def call(path,method='GET',body=None,token=None,cookie=None,csrf=None):
            env={};setup_testing_defaults(env)
            raw=json.dumps(body).encode() if body is not None else b''
            env.update(REQUEST_METHOD=method,PATH_INFO=path,CONTENT_LENGTH=str(len(raw)),CONTENT_TYPE='application/json',
                       **{'wsgi.input':io.BytesIO(raw)})
            if token:env['HTTP_AUTHORIZATION']='Bearer '+token
            if cookie:env['HTTP_COOKIE']=cookie
            if csrf:env['HTTP_X_CSRF_TOKEN']=csrf
            status=[]
            payload=b''.join(app(env,lambda value,headers:status.append(value)))
            return int(status[0][:3]),json.loads(payload)
        import hmac
        csrf='synthetic-test-csrf'
        signature=hmac.new(self.settings.ui_token.encode(),csrf.encode(),sha256).hexdigest()
        cookie=f'finance_v2_session={csrf}.{signature}'
        base='/api/v2/open-finance/classification/'
        self.assertEqual(call(base+'catalog',token=self.settings.ui_token)[0],403)
        self.assertEqual(call(base+'audit',token='synthetic-external-only')[0],403)
        body={'rule':self.customize('Uma descrição específica'),'revision':0}
        self.assertEqual(call(base+'rule','POST',body,cookie=cookie)[0],403)
        self.assertEqual(call(base+'rule','POST',body,cookie=cookie,csrf=csrf)[0],200)
        self.assertEqual(len(call(base+'catalog',cookie=cookie)[1]['rules']),1)
        self.assertEqual(call(base+'manual','POST',{'identity':self.identity('unknown'),'event':None,
            'decision':{'category':'Teste','nature':'UNKNOWN'}},cookie=cookie,csrf=csrf)[0],404)


class ClassificationMigrationTest(unittest.TestCase):
    def test_schema_12_snapshot_migrates_idempotently_and_failed_ddl_rolls_back(self):
        with tempfile.TemporaryDirectory() as path:
            all_migrations=migrations.MIGRATIONS[:13]
            legacy=fixtures.CoverageTests(methodName='test_all_products_projection_history_and_financial_preservation')
            self.addCleanup(legacy.doCleanups)
            with patch.object(migrations,'MIGRATIONS',all_migrations[:-1]):
                legacy.setUp()
                with patch('finance_v2.open_finance_portfolio.capture_snapshot'):
                    legacy.sync()
            db=legacy.db
            with closing(connect(db)) as c:
                c.execute("INSERT INTO categories(name,normalized_name,active) VALUES ('Exemplo sintético','exemplo sintetico',1)")
                c.execute("UPDATE of_connection_registry SET lifecycle='ARCHIVED' WHERE connection_id='bank-test'")
                self.assertGreater(c.execute('SELECT count(*) FROM of_resource_records').fetchone()[0],0)
                c.commit()
                before=[row for row in c.iterdump() if 'schema_migrations' not in row]
            migration=all_migrations[-1]
            broken=Path(path)/'broken.sql'
            broken.write_bytes(migration.path.read_bytes()+b'\nSELECT * FROM table_that_does_not_exist;\n')
            with patch.object(migrations,'MIGRATIONS',all_migrations[:-1]+(
                replace(migration,path=broken,expected_sha256=sha256(broken.read_bytes()).hexdigest()),)):
                with self.assertRaises((sqlite3.Error,migrations.MigrationError)):
                    migrations.migrate(db)
            with closing(connect(db)) as c:
                self.assertEqual(c.execute('PRAGMA user_version').fetchone()[0],12)
                self.assertEqual(c.execute("SELECT count(*) FROM sqlite_master WHERE name LIKE 'of_classification_%'").fetchone()[0],0)
            with patch.object(migrations,'MIGRATIONS',all_migrations):
                self.assertEqual(migrations.migrate(db),[13])
                self.assertEqual(migrations.migrate(db),[])
            with closing(connect(db)) as c:
                self.assertEqual(c.execute('PRAGMA user_version').fetchone()[0],13)
                self.assertEqual(c.execute('PRAGMA integrity_check').fetchone()[0],'ok')
                self.assertTrue(set(before)<=set(c.iterdump()))
