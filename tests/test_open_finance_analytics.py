"""Synthetic tests for read-only Open Finance analytics."""
import json
import unittest
from contextlib import closing
from decimal import Decimal

import test_full_coverage as fixtures
from finance_v2.db import connect
from finance_v2.open_finance_analytics import analytics


class AnalyticsTests(fixtures.CoverageTests):
    def test_analytics_owner_route_and_product_separation(self):
        self.sync()
        status, result = self.request('/api/v2/open-finance/analytics?start=2026-10-01&end=2026-10-31')
        self.assertEqual(status, 200, result)
        self.assertEqual(result['contract'], 'OF-ANALYTICS/1')
        self.assertEqual(result['positions']['accounts']['value'], '125.5')
        self.assertEqual(result['positions']['investments']['value'], '200')
        self.assertEqual(result['flow']['BANK']['outgoing'], '10')
        self.assertEqual(result['flow']['CREDIT']['outgoing'], '0')
        self.assertEqual(result['total'], 1)
        status, _ = self.request('/api/v2/open-finance/analytics', token='synthetic-external-only')
        self.assertIn(status, (401, 403))

    def test_current_records_currency_precision_and_pagination(self):
        self.sync()
        with closing(connect(self.db)) as c:
            row = c.execute("SELECT * FROM of_resource_records WHERE resource='transactions' AND parent_id='account-BANK'").fetchone()
            data = json.loads(row['payload_json'])
            for i in range(30):
                data.update(id='t'+str(i), amount='0.01', currencyCode='BRL')
                c.execute("INSERT INTO of_resource_records(connection_id,resource,parent_id,external_id,payload_json,payload_hash,state,first_run_id,last_run_id,observed_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
                          (row['connection_id'], row['resource'], row['parent_id'], 't'+str(i), json.dumps(data), row['payload_hash'], 'PRESENT', row['first_run_id'], row['last_run_id'], row['observed_at']))
            c.commit()
            result = analytics(c, self.settings, {'start':['2026-10-01'], 'end':['2026-10-31'],'page_size':['25']})
            self.assertEqual(result['total'], 31)
            self.assertEqual(Decimal(result['flow']['BANK']['outgoing']), Decimal('10.30'))
            self.assertEqual(len(result['items']), 25)
            self.assertTrue(result['has_more'])
            empty = analytics(c, self.settings, {'currency':['USD']})
            self.assertIsNone(empty['positions']['accounts']['value'])
            self.assertEqual(empty['total'], 0)

    def test_categories_keep_identity_and_translation(self):
        from finance_v2.open_finance_analytics import _category
        one = _category({'categoryId':'123', 'category':'Food'}, 'bank-a')
        two = _category({'categoryId':'123', 'category':'Alimentos'}, 'bank-b')
        other = _category({'categoryId':'456', 'category':'Food'}, 'bank-a')
        self.assertEqual(one['key'], two['key'])
        self.assertNotEqual(one['key'], other['key'])
        self.assertNotEqual(_category({'category':'Food'}, 'bank-a')['key'],
                            _category({'category':'Food'}, 'bank-b')['key'])
        self.assertEqual(_category({}, 'bank-a')['key'], 'missing')
        self.sync()
        with closing(connect(self.db)) as c:
            c.execute("UPDATE of_categories SET display_name_pt='Alimentação',translation_status='VERIFIED' WHERE external_id='1'")
            c.commit()
            result = analytics(c, self.settings, {})
            self.assertEqual(result['items'][0]['category']['name'], 'Alimentação')
            self.assertEqual(result['items'][0]['economic_classification'], 'NOT_ESTABLISHED')
            self.assertEqual(result['items'][0]['reconciliation'], 'UNRECONCILED')
            self.assertIsNone(result['flow']['BANK']['economic_totals']['outgoing'])

    def test_missing_values_and_partial_coverage_are_distinct(self):
        self.sync()
        with closing(connect(self.db)) as c:
            row = c.execute("SELECT payload_json FROM of_resource_records WHERE resource='accounts' AND external_id='account-BANK'").fetchone()
            data = json.loads(row['payload_json']); data.pop('balance', None)
            c.execute("UPDATE of_resource_records SET payload_json=? WHERE resource='accounts' AND external_id='account-BANK'", (json.dumps(data),))
            c.execute("UPDATE of_resource_coverage SET state='FAILED' WHERE resource='accounts'")
            c.commit()
            result = analytics(c, self.settings, {})
            self.assertIsNone(result['positions']['accounts']['value'])
            self.assertEqual(result['positions']['accounts']['unavailable'], 1)
            self.assertEqual(result['positions']['accounts']['coverage_state'], 'PARTIAL')
            self.assertTrue(any(r['state'] == 'FAILED' for r in result['coverage']))

    def test_authentication_and_unknown_account(self):
        self.sync()
        status, _ = self.request('/api/v2/open-finance/analytics', token=None)
        self.assertIn(status, (401, 403))
        status, _ = self.request('/api/v2/open-finance/analytics?connection_id=bank-test&account_id=unknown')
        self.assertEqual(status, 404)

    def test_category_ranking_reconciles_before_pagination(self):
        self.sync()
        with closing(connect(self.db)) as c:
            row = c.execute("SELECT * FROM of_resource_records WHERE resource='transactions' AND parent_id='account-BANK'").fetchone()
            data = json.loads(row['payload_json'])
            for i in range(7):
                data.update(id='rank-'+str(i), categoryId=str(i+10), category='Grupo '+str(i), amount=str(i+1))
                c.execute("INSERT INTO of_resource_records(connection_id,resource,parent_id,external_id,payload_json,payload_hash,state,first_run_id,last_run_id,observed_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (row['connection_id'], row['resource'], row['parent_id'], 'rank-'+str(i), json.dumps(data), row['payload_hash'], 'PRESENT', row['first_run_id'], row['last_run_id'], row['observed_at']))
            data.update(id='rank-missing', categoryId=None, category=None, amount='2')
            c.execute("INSERT INTO of_resource_records(connection_id,resource,parent_id,external_id,payload_json,payload_hash,state,first_run_id,last_run_id,observed_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (row['connection_id'], row['resource'], row['parent_id'], 'rank-missing', json.dumps(data), row['payload_hash'], 'PRESENT', row['first_run_id'], row['last_run_id'], row['observed_at']))
            c.commit()
            result = analytics(c, self.settings, {})
            ranking = result['category_ranking']['BANK']
            self.assertEqual(len([r for r in ranking if r['key'] not in ('missing','other')]), 5)
            self.assertEqual(sum(Decimal(r['value']) for r in ranking), Decimal(result['flow']['BANK']['outgoing']))
            self.assertIn('other', [r['key'] for r in ranking])
            self.assertIn('missing', [r['key'] for r in ranking])

    def test_unknown_currency_prevents_complete_coverage(self):
        self.sync()
        with closing(connect(self.db)) as c:
            row = c.execute("SELECT payload_json FROM of_resource_records WHERE resource='accounts' AND external_id='account-BANK'").fetchone()
            data = json.loads(row['payload_json']); data.pop('currencyCode', None)
            c.execute("UPDATE of_resource_records SET payload_json=? WHERE resource='accounts' AND external_id='account-BANK'", (json.dumps(data),))
            c.commit()
            result = analytics(c, self.settings, {})
            self.assertEqual(result['positions']['accounts']['unknown_currency'], 1)
            self.assertEqual(result['positions']['accounts']['coverage_state'], 'PARTIAL')

    def test_filter_matrix_and_no_financial_writes(self):
        self.sync()
        before = self.financial()
        with closing(connect(self.db)) as c:
            row = c.execute("SELECT * FROM of_resource_records WHERE resource='transactions' AND parent_id='account-BANK'").fetchone()
            base = json.loads(row['payload_json'])
            for ident, date, status, direction, currency in [('first','2026-10-01','POSTED','CREDIT','BRL'), ('last','2026-10-31','PENDING','DEBIT','BRL'), ('foreign','2026-10-15','POSTED','DEBIT','USD')]:
                data = {**base, 'id': ident, 'date': date, 'status': status, 'type': direction, 'currencyCode': currency, 'description': 'Consulta sintetica'}
                c.execute("INSERT INTO of_resource_records(connection_id,resource,parent_id,external_id,payload_json,payload_hash,state,first_run_id,last_run_id,observed_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (row['connection_id'], row['resource'], row['parent_id'], ident, json.dumps(data), row['payload_hash'], 'PRESENT', row['first_run_id'], row['last_run_id'], row['observed_at']))
            c.commit()
            params = {'connection_id':['bank-test'], 'account_id':['account-BANK'], 'start':['2026-10-01'], 'end':['2026-10-31'], 'status':['ALL'], 'currency':['BRL'], 'search':['sintetica']}
            result = analytics(c, self.settings, params)
            self.assertEqual(result['total'], 2)
            self.assertEqual({item['date'] for item in result['items']}, {'2026-10-01', '2026-10-31'})
            self.assertEqual(result['flow']['BANK']['incoming'], '10')
            self.assertEqual(result['flow']['BANK']['outgoing'], '10')
            pending = analytics(c, self.settings, {**params, 'status':['PENDING'], 'direction':['outgoing']})
            self.assertEqual(pending['total'], 1)
            self.assertEqual(pending['items'][0]['external_id'], 'last')
            foreign = analytics(c, self.settings, {**params, 'currency':['USD']})
            self.assertEqual(foreign['total'], 1)
            card = analytics(c, self.settings, {'product':['CREDIT']})
            self.assertEqual(card['total'], 1)
            self.assertEqual(card['flow']['BANK']['outgoing'], '0')
            self.assertEqual(card['items'][0]['bill_relation']['state'], 'MISSING_REFERENCE')
            c.execute('PRAGMA query_only=OFF')
            c.execute("UPDATE of_resource_links SET state='MATCHED',referenced_external_id='bill-test',target_external_id='bill-test' WHERE source_parent_id='account-CREDIT'")
            c.commit()
            card = analytics(c, self.settings, {'product':['CREDIT']})
            self.assertEqual(card['items'][0]['bill_relation']['state'], 'MATCHED')
            self.assertEqual(card['items'][0]['economic_classification'], 'NOT_ESTABLISHED')
        self.assertEqual(self.financial(), before)

    def test_persisted_disable_with_legacy_config_keeps_history_out_of_budget_and_current_totals(self):
        self.sync()
        with closing(connect(self.db)) as c:
            c.execute("UPDATE of_connections SET enabled=0 WHERE id='bank-test'")
            c.commit()
            before = list(c.iterdump())
            current = analytics(c, self.settings, {})
            self.assertEqual(current['institutions'], [])
            self.assertEqual(current['coverage'], [])
            self.assertEqual(current['series'], [])
            self.assertIsNone(current['positions']['accounts']['value'])
            historical = analytics(c, self.settings, {'history':['1'], 'connection_id':['bank-test']})
            self.assertGreater(historical['total'], 0)
            self.assertFalse(historical['institutions'][0]['current'])
            self.assertIsNone(historical['positions']['accounts']['value'])
            self.assertEqual(list(c.iterdump()), before)

    def test_current_positions_use_one_observation_and_respect_explicit_closure(self):
        self.sync()
        with closing(connect(self.db)) as c:
            source = c.execute("SELECT * FROM of_resource_records WHERE resource='accounts' AND external_id='account-BANK'").fetchone()
            base = json.loads(source['payload_json'])
            c.execute("""INSERT INTO of_resource_revisions
                (connection_id,resource,parent_id,external_id,run_id,observed_at,payload_json,payload_hash,state)
                VALUES (?,?,?,?,?,?,?,?,?)""",
                (source['connection_id'], 'accounts', '', source['external_id'], source['last_run_id'],
                 '2026-09-01T00:00:00Z', json.dumps({**base, 'balance': '800'}), source['payload_hash'], 'PRESENT'))
            c.execute("""INSERT INTO of_resource_records
                (connection_id,resource,parent_id,external_id,payload_json,payload_hash,state,first_run_id,last_run_id,observed_at)
                VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (source['connection_id'], 'accounts', '', 'closed',
                 json.dumps({**base, 'id': 'closed', 'balance': '900', 'status': 'CLOSED'}),
                 source['payload_hash'], 'PRESENT', source['first_run_id'], source['last_run_id'], source['observed_at']))
            c.commit()
            before = list(c.iterdump())
            result = analytics(c, self.settings, {})
            self.assertEqual(result['institutions'][0]['accounts']['value'], '125.5')
            self.assertEqual([row['external_id'] for row in result['positions']['accounts']['items']], ['account-BANK'])
            self.assertEqual(list(c.iterdump()), before)

    def test_period_evidence_controls_zero_net_and_comparison(self):
        self.sync()
        query = {'start':['2026-10-16'], 'end':['2026-10-31']}
        with closing(connect(self.db)) as c:
            result = analytics(c, self.settings, query)['flow']['BANK']
            self.assertIsNone(result['net'])
            self.assertIsNone(result['reported']['incoming'])
            self.assertIsNone(result['comparison'])
            c.execute('PRAGMA query_only=OFF')
            c.execute("UPDATE of_sync_runs SET date_from='2026-09-01', date_to='2026-10-31'")
            c.execute("UPDATE of_resource_coverage SET omitted_field_count=0 WHERE resource IN ('accounts','transactions')")
            c.commit()
            result = analytics(c, self.settings, query)['flow']['BANK']
            self.assertEqual(result['coverage_state'], 'COMPLETE')
            self.assertEqual(result['reported']['incoming'], '0')
            self.assertEqual(result['net'], '-10')
            self.assertEqual(result['comparison'], {'start':'2026-09-30','end':'2026-10-15','incoming':'0','outgoing':'10','net':'-10'})
            empty = analytics(c, self.settings, {'start':['2026-09-20'], 'end':['2026-09-25']})['flow']['BANK']
            self.assertEqual(empty['net'], '0')
            self.assertEqual(empty['reported'], {'incoming':'0','outgoing':'0'})

    def test_investment_classes_are_exact_and_position_ignores_flow_period(self):
        self.sync()
        with closing(connect(self.db)) as c:
            result = analytics(c, self.settings, {'start':['2020-01-01'], 'end':['2020-01-31']})
            self.assertEqual(result['total'], 0)
            self.assertEqual(result['positions']['investments']['value'], '200')
            classes = result['positions']['investments']['by_class']
            self.assertEqual(classes, [{'type':'FIXED_INCOME', 'known':1, 'unavailable':0, 'value':'200'}])

    def test_bill_filter_requires_scoped_proven_link(self):
        self.sync()
        with closing(connect(self.db)) as c:
            row = c.execute("SELECT * FROM of_resource_records WHERE resource='transactions' AND parent_id='account-CREDIT'").fetchone()
            data = json.loads(row['payload_json']); data['id']='unlinked'
            c.execute("INSERT INTO of_resource_records(connection_id,resource,parent_id,external_id,payload_json,payload_hash,state,first_run_id,last_run_id,observed_at) VALUES (?,?,?,?,?,?,?,?,?,?)", (row['connection_id'],row['resource'],row['parent_id'],'unlinked',json.dumps(data),row['payload_hash'],'PRESENT',row['first_run_id'],row['last_run_id'],row['observed_at']))
            c.execute("UPDATE of_resource_links SET state='MATCHED',referenced_external_id='bill-test',target_external_id='bill-test' WHERE source_parent_id='account-CREDIT'")
            c.commit()
            params={'connection_id':['bank-test'],'account_id':['account-CREDIT'],'product':['CREDIT'],'bill_id':['bill-test']}
            result=analytics(c,self.settings,params)
            self.assertEqual(result['total'],1)
            self.assertEqual(result['items'][0]['external_id'],'transaction-test')
            self.assertEqual(result['items'][0]['bill_relation']['state'],'MATCHED')
            self.assertEqual(result['items'][0]['economic_classification'],'NOT_ESTABLISHED')
        status,_=self.request('/api/v2/open-finance/analytics?bill_id=bill-test')
        self.assertEqual(status,422)
        status,_=self.request('/api/v2/open-finance/analytics?connection_id=bank-test&account_id=account-BANK&product=CREDIT&bill_id=bill-test')
        self.assertEqual(status,404)

    def test_invalid_filters_rejected(self):
        self.sync()
        for query in ('start=2026-10-31&end=2026-10-01', 'page_size=3', 'currency=XYZ1'):
            status, _ = self.request('/api/v2/open-finance/analytics?' + query)
            self.assertEqual(status, 422)

if __name__ == '__main__':
    unittest.main()
