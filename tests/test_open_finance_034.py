from contextlib import closing
from decimal import Decimal
from hashlib import sha256
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from finance_v2 import migrations
from finance_v2.db import connect
from finance_v2.open_finance_analytics import _amount
from finance_v2.open_finance_insights import card_insights
from finance_v2.open_finance_portfolio import capture_snapshot, portfolio_history
from finance_v2.open_finance_registry import connection_views
import test_open_finance_classification as base


class Overview34Tests(unittest.TestCase):
    def setUp(self):
        self.case=base.ClassificationTest('test_automatic_investment_example_and_coverage')
        self.addCleanup(self.case.doCleanups)
        self.case.setUp()
        self.case.write("UPDATE of_connection_registry SET label='Itaú' WHERE connection_id='bank-test'")

    def test_rankings_reconcile_with_effective_identity_and_precedence(self):
        case=self.case
        for n in range(33):
            case.tx(f'auto-{n:02}','Aplicação APL APLIC AUT MAIS','1000.01','DEBIT')
        case.tx('b3','Saída COR OPERACOES B3','123.40','DEBIT')
        case.tx('market','Mercado fictício','56.01','DEBIT')
        case.label('market','EXPENSE','Mercado')
        # Simulate the absent original category on the two reported descriptions.
        case.write("""UPDATE of_resource_records SET payload_json=json_remove(payload_json,'$.category','$.categoryId')
            WHERE resource='transactions' AND (external_id LIKE 'auto-%' OR external_id='b3')""")
        provider_before=case.sql("""SELECT external_id,payload_json FROM of_resource_records WHERE resource='transactions'
                                      ORDER BY external_id""")
        result=case.report()
        ranking={entry['name']:entry for entry in result['category_ranking']['BANK']}
        self.assertEqual(ranking['Aplicação automática']['value'],'33000.33')
        self.assertEqual(ranking['Operações de investimento']['review'],['SUGGESTED'])
        self.assertEqual(result['economic_category_ranking'][0]['name'],'Mercado')
        self.assertEqual(result['insights']['bridge']['capital']['outgoing'],'33000.33')
        self.assertEqual(result['insights']['known']['outgoing'],'56.01')
        scoped=case.report({'effective_key':[ranking['Aplicação automática']['key']],'direction':['outgoing']})
        self.assertEqual(scoped['total'],33)
        self.assertEqual(scoped['flow']['BANK']['outgoing'],ranking['Aplicação automática']['value'])
        self.assertTrue(all(row['original_category']['key']=='missing' for row in scoped['items']))
        self.assertTrue(all(row['effective_category']['key']==ranking['Aplicação automática']['key'] for row in scoped['items']))
        case.label('auto-00','EXPENSE','Rubrica revisada')
        self.assertEqual(case.report({'effective_key':[ranking['Aplicação automática']['key']]})['total'],32)
        updated=case.report()
        self.assertEqual(sum(Decimal(r['value']) for r in updated['categories']),Decimal(result['flow']['BANK']['outgoing']))
        self.assertEqual(provider_before,case.sql("""SELECT external_id,payload_json FROM of_resource_records
                                                     WHERE resource='transactions' ORDER BY external_id"""))

    def test_automatic_position_requires_explicit_product_identity(self):
        case=self.case
        edit="""UPDATE of_resource_records SET payload_json=json_set(payload_json,'$.name',?)
                WHERE resource='investments'"""
        case.write(edit,(None,))
        self.assertIsNone(case.report()['insights']['automatic']['position'])
        case.write(edit,('Aplic Aut Mais',))
        self.assertIsNotNone(case.report()['insights']['automatic']['position'])

    def test_valuation_is_persisted_from_completed_synthetic_collections(self):
        case=self.case
        provider=case.fixture.provider
        original=provider.send
        reference='2026-09-25'
        balance=205
        def send(method,path,*args):
            status,payload=original(method,path,*args)
            if path.startswith('/investments?') and status==200:
                payload['results'][0].update(date=reference,balance=balance)
            return status,payload
        provider.send=send
        self.assertEqual(case.fixture.sync()['state'],'SUCCEEDED')
        reference='2026-10-23'
        balance=231
        self.assertEqual(case.fixture.sync()['state'],'SUCCEEDED')
        self.assertEqual(case.fixture.sync()['state'],'SUCCEEDED')
        with closing(connect(case.db)) as db:
            history=portfolio_history(db,{'bank-test'},'BRL','2026-11-01','6')
            self.assertEqual(history['points'],[{'date':'2026-09-25','value':'205'},{'date':'2026-10-23','value':'231'}])
            self.assertEqual(history['change'],'26')
            self.assertEqual(history['percent'],'12.68')
            self.assertEqual(portfolio_history(db,{'bank-test'},'USD','2026-11-01','6')['state'],'FORMING')
            self.assertEqual(portfolio_history(db,{'bank-test','another'},'BRL','2026-11-01','6')['state'],'SELECT_CONNECTION')
        with closing(connect(case.db)) as db:
            latest=db.execute("""SELECT run_id FROM of_resource_coverage
                WHERE resource='investments' AND connection_id='bank-test'""").fetchone()[0]
            count=db.execute('SELECT count(*) FROM of_portfolio_snapshots').fetchone()[0]
            capture_snapshot(db,'bank-test',latest,_amount)
            db.execute("UPDATE of_resource_coverage SET state='FAILED' WHERE run_id=? AND resource='investments'",(latest,))
            capture_snapshot(db,'bank-test',latest,_amount)
            self.assertEqual(db.execute('SELECT count(*) FROM of_portfolio_snapshots').fetchone()[0],count)
            db.commit()
        case.write("UPDATE of_connection_registry SET lifecycle='ARCHIVED' WHERE connection_id='bank-test'")
        self.assertEqual(case.report({'history':['1'],'portfolio_window':['6']})['portfolio_history']['points'],[])

    def test_balances_only_consolidate_distinct_obligations(self):
        with closing(connect(self.case.db)) as db:
            views=connection_views(db,self.case.settings)
        accounts={}
        for index in range(4):
            accounts['bank-test',f'card-{index}']={'observed_at':'2026-10-20T10:10:10Z','last_run_id':'run-current','data':{
                'type':'CREDIT','currencyCode':'BRL','name':f'Cartão fictício {index}',
                'creditData':{'status':'ACTIVE','holderType':'MAIN','disaggregatedCreditLimits':[{
                    'creditLineLimitType':'LIMITE_CREDITO_TOTAL','consolidationType':'INDIVIDUAL',
                    'usedAmountCurrencyCode':'BRL','limitAmountCurrencyCode':'BRL',
                    'limitAmount':1000,'usedAmount':100*index,'identificationNumber':str(index),
                    'isLimitFlexible':False}]}}}
        def read():
            return card_insights(accounts,{'bank-test'},views,'BRL',_amount,'2026-10-01')
        snap=read()
        self.assertEqual(snap['used'],'600')
        self.assertIsNone(snap['limit'])
        accounts['bank-test','card-1']['data']['creditData']['disaggregatedCreditLimits'][0]['identificationNumber']='0'
        self.assertIsNone(read()['used'])
        self.assertEqual(read()['items'][0]['used'],'0')

    def test_migration13_to14_preserves_classification_and_original_tables(self):
        # A schema 13 file seeded by the previous migration ledger and synthetic objects.
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'legacy.sqlite3'
            with patch.object(migrations,'MIGRATIONS',migrations.MIGRATIONS[:-1]):
                self.assertEqual(migrations.migrate(path),list(range(1,14)))
            with closing(connect(path)) as db:
                db.execute("INSERT INTO categories(name,normalized_name,active) VALUES ('Categoria original','categoria original',1)")
                db.execute("INSERT INTO of_classification_rules(id,revision) VALUES ('synthetic',1)")
                db.execute("""INSERT INTO of_classification_rule_revisions VALUES
                    ('synthetic',1,0,'2026-01-01T00:00:00Z','UI:local','{}')""")
                db.commit()
                prior={statement for statement in db.iterdump() if '_finance_v2_schema_migrations' not in statement}
            self.assertEqual(migrations.migrate(path),[14])
            self.assertEqual(migrations.migrate(path),[])
            with closing(connect(path)) as db:
                self.assertTrue(prior.issubset(set(db.iterdump())))
                self.assertEqual(db.execute('PRAGMA integrity_check').fetchone()[0],'ok')
                self.assertEqual(db.execute('PRAGMA foreign_key_check').fetchall(),[])
                self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0],14)
