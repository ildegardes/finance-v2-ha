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
            result = analytics(c, self.settings, {'start':['2026-10-01'], 'end':['2026-10-31']})
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

    def test_invalid_filters_rejected(self):
        self.sync()
        for query in ('start=2026-10-31&end=2026-10-01', 'page_size=3', 'currency=XYZ1'):
            status, _ = self.request('/api/v2/open-finance/analytics?' + query)
            self.assertEqual(status, 422)

if __name__ == '__main__':
    unittest.main()
