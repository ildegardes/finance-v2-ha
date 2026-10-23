"""Synthetic-only integration, no provider, environment credentials or existing database."""
from contextlib import closing
from dataclasses import replace
from datetime import date
from decimal import Decimal
from hashlib import sha256
import io
import json
from pathlib import Path
import socket
import sys
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'finance-v17' / 'src'))
from finance_v2 import migrations
from finance_v2.api import Application
from finance_v2.config import Settings, ExternalClientCredential
from finance_v2.db import connect
from finance_v2.open_finance import OpenFinanceService, SyncError
from finance_v2.open_finance_coverage import query, sync_full
from finance_v2.pluggy_client import PluggyClient, PluggyError, transport
from finance_v2.pluggy_config import PluggyConnection
from finance_v2.pluggy_coverage import CONTRACT, cached_path, contracts, project


def collection(rows):
    return {'results': rows, 'page': 1, 'total': len(rows), 'totalPages': 1}


class Provider:
    def __init__(self):
        self.calls = []
        self.overrides = {}
        self.balance = 125.50
        self.investments = True

    def send(self, method, path, headers, body, timeout):
        self.calls.append((method, path))
        if path in self.overrides:
            return self.overrides[path]
        if method == 'POST':
            assert path == '/auth'
            return 200, {'apiKey': 'synthetic-key-not-a-real-credential'}
        assert cached_path(path)
        base = urlsplit(path).path
        if base == '/items/item-test':
            return 200, {'id': 'item-test', 'status': 'UPDATED', 'executionStatus': 'SUCCESS',
                         'resourcesCollectedAt': '2026-10-23T12:00:00Z', 'connector': {'id': 600, 'name': 'Synthetic'}}
        if base == '/items/item-test/resources':
            return 200, collection([{'resourceId': 'resource-test', 'type': 'ACCOUNT', 'status': 'AVAILABLE'}])
        if base == '/consents':
            return 200, collection([{'id': 'consent-test', 'itemId': 'item-test', 'products': ['ACCOUNTS'], 'expiresAt': None}])
        if base == '/accounts':
            return 200, collection([{'id': 'account-' + kind, 'itemId': 'item-test', 'type': kind,
                'name': 'Conta sintética', 'balance': self.balance, 'number': 'PRIVATE-NOT-PERSISTED',
                'currencyCode': 'BRL', 'creditData': {'creditLimit': 1000, 'availableCreditLimit': 900} if kind == 'CREDIT' else None}
                for kind in ('BANK', 'CREDIT')])
        if base == '/v2/transactions':
            from urllib.parse import parse_qs
            account = parse_qs(urlsplit(path).query)['accountId'][0]
            return 200, {'results': [{'id': 'transaction-test', 'accountId': account,
                'description': 'Compra sintética', 'amount': 10, 'currencyCode': 'BRL', 'date': '2026-10-22',
                'type': 'DEBIT', 'status': 'POSTED', 'categoryId': '1', 'category': 'Food',
                'merchant': {'name': 'Sintético', 'cnpj': 'PRIVATE-NOT-PERSISTED'},
                'creditCardMetadata': {'installmentNumber': 1, 'totalInstallments': 2, 'cardNumber': 'PRIVATE-NOT-PERSISTED'}}], 'next': None}
        if base.endswith('/statements'):
            return 200, collection([{'id': 'statement-test', 'monthYear': '2026-10', 'url': 'https://invalid.example/private-signed-url'}])
        if base == '/bills':
            return 200, collection([{'id': 'bill-test', 'dueDate': '2026-11-10', 'totalAmount': 100,
                'totalAmountCurrencyCode': 'BRL', 'payments': [{'amount': 25, 'currencyCode': 'BRL'}]}])
        if base == '/investments':
            return 200, collection([{'id': 'investment-test', 'itemId': 'item-test', 'name': 'Ativo sintético',
                'type': 'FIXED_INCOME', 'currencyCode': 'BRL', 'balance': 200, 'quantity': 2, 'annualRate': 1.2}] if self.investments else [])
        if base.endswith('/transactions'):
            return 200, collection([{'id': 'movement-test', 'date': '2026-10-20', 'amount': 200, 'quantity': 2}])
        if base == '/loans':
            return 200, collection([{'id': 'loan-test', 'itemId': 'item-test', 'productName': 'Crédito sintético',
                'contractAmount': 500, 'currencyCode': 'BRL', 'contractNumber': 'PRIVATE-NOT-PERSISTED', 'CET': 2}])
        raise AssertionError('UNEXPECTED_ENDPOINT')


class CoverageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='finance-full-synthetic-')
        self.addCleanup(self.temp.cleanup)
        self.db = Path(self.temp.name) / 'new-synthetic.sqlite3'
        migrations.migrate(self.db)
        self.config = PluggyConnection('bank-test', 'Banco sintético', 'synthetic-client', 'synthetic-secret', 'item-test', True)
        self.settings = Settings(database_path=self.db, timezone='UTC', host='127.0.0.1', port=8766,
            busy_timeout_ms=500, ui_token='synthetic-owner-only', pluggy_connections=(self.config,),
            external_clients=(ExternalClientCredential('synthetic-client', 'synthetic-external-only', frozenset({'finance:read'})),))
        self.provider = Provider()
        self.service = OpenFinanceService(self.settings, client_factory=lambda c: PluggyClient(c, send=self.provider.send, sleep=lambda _: None))
        self.no_network = patch.object(socket.socket, 'connect', side_effect=AssertionError('NETWORK_FORBIDDEN'))
        self.no_network.start()
        self.addCleanup(self.no_network.stop)

    def sync(self):
        return sync_full(self.service, self.config.id, actor='UI:local')

    def financial(self):
        with closing(connect(self.db)) as c:
            names = [r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'of_%' AND name NOT LIKE 'sqlite_%' AND name<>'_finance_v2_schema_migrations' ORDER BY name")]
            return {name: ([tuple(r) for r in c.execute('SELECT * FROM "' + name + '" ORDER BY rowid')],
                           c.execute('SELECT sql FROM sqlite_master WHERE name=?', (name,)).fetchone()[0]) for name in names}

    def request(self, path, method='GET', token='synthetic-owner-only', body=None):
        raw = json.dumps(body).encode() if body is not None else b''
        url = urlsplit(path)
        env = {'REQUEST_METHOD': method, 'PATH_INFO': url.path, 'QUERY_STRING': url.query,
               'wsgi.input': io.BytesIO(raw), 'CONTENT_LENGTH': str(len(raw)), 'CONTENT_TYPE': 'application/json'}
        if token:
            env['HTTP_AUTHORIZATION'] = 'Bearer ' + token
        status = []
        payload = b''.join(Application(self.settings)(env, lambda s, h: status.append(int(s.split()[0]))))
        return status[0], json.loads(payload)

    def test_all_products_projection_history_and_financial_preservation(self):
        with closing(connect(self.db)) as c:
            c.execute("INSERT INTO accounts(name,active) VALUES('Conta financeira sintética',1)")
            category = c.execute("INSERT INTO categories(name,normalized_name,active) VALUES('Sintética','sintetica',1)").lastrowid
            from finance_v2.domain.expenses import create_expense
            create_expense(c, description='Despesa oficial sintética', amount_cents=12345,
                expense_date=date(2026,10,20),due_date=date(2026,10,25),planned_payment_method='CASH',
                category_id=category,account_id=None,card_id=None,notes=None,actor='UI:local',
                correlation_id='synthetic-official',clock=self.service.clock)
        before = self.financial()
        run = self.sync()
        self.assertEqual(run['state'], 'SUCCEEDED', run)
        self.assertEqual(self.financial(), before)
        with closing(connect(self.db)) as c:
            self.assertEqual(c.execute('PRAGMA user_version').fetchone()[0], 10)
            self.assertEqual({r[0] for r in c.execute('SELECT DISTINCT resource FROM of_resource_records')}, set(CONTRACT['resources']))
            self.assertEqual(c.execute('SELECT count(*) FROM of_transactions').fetchone()[0], 2)
            self.assertEqual(c.execute('SELECT count(*) FROM of_transaction_revisions').fetchone()[0], 2)
            self.assertNotIn('PRIVATE-NOT-PERSISTED', str([tuple(r) for r in c.execute('SELECT payload_json FROM of_resource_records')]))
            self.assertNotIn('private-signed-url', str([tuple(r) for r in c.execute('SELECT payload_json FROM of_resource_records')]))
            self.assertEqual(c.execute('PRAGMA integrity_check').fetchone()[0], 'ok')
            self.assertEqual(c.execute('PRAGMA foreign_key_check').fetchall(), [])
        self.assertTrue(all(method == 'GET' or path == '/auth' for method, path in self.provider.calls))

    def test_replay_does_not_duplicate_revisions(self):
        self.assertEqual(self.sync()['state'], 'SUCCEEDED')
        with closing(connect(self.db)) as c:
            first = c.execute('SELECT count(*) FROM of_resource_revisions').fetchone()[0]
        self.assertEqual(self.sync()['state'], 'SUCCEEDED')
        with closing(connect(self.db)) as c:
            self.assertEqual(c.execute('SELECT count(*) FROM of_resource_revisions').fetchone()[0], first)
            self.assertEqual(c.execute('SELECT count(*) FROM of_transaction_revisions').fetchone()[0], 2)

    def test_changed_balance_retains_original_history(self):
        self.sync()
        self.provider.balance = 0
        self.sync()
        with closing(connect(self.db)) as c:
            rows = query(c, self.settings, {'resource': ['accounts'], 'history': ['1']})
        self.assertEqual(rows['total'], 4)
        self.assertEqual({row['data']['balance'] for row in rows['items']}, {0, 125.50})

    def test_absence_is_not_asserted_as_deletion(self):
        self.sync()
        self.provider.investments = False
        self.sync()
        with closing(connect(self.db)) as c:
            row = c.execute("SELECT state FROM of_resource_records WHERE resource='investments'").fetchone()
            self.assertEqual(row[0], 'NOT_SEEN')
            self.assertEqual(c.execute("SELECT count(*) FROM of_resource_revisions WHERE resource='investments'").fetchone()[0], 2)

    def test_unavailable_and_unauthorized_preserve_previous_values(self):
        self.sync()
        self.provider.overrides['/investments?itemId=item-test&page=1&pageSize=500'] = (403, None)
        self.provider.overrides['/loans?itemId=item-test'] = (404, None)
        self.assertEqual(self.sync()['state'], 'SUCCEEDED')
        with closing(connect(self.db)) as c:
            self.assertEqual(c.execute("SELECT state FROM of_resource_coverage WHERE resource='investments'").fetchone()[0], 'NOT_AUTHORIZED')
            self.assertEqual(c.execute("SELECT state FROM of_resource_records WHERE resource='investments'").fetchone()[0], 'PRESENT')
            self.assertEqual(c.execute("SELECT state FROM of_resource_coverage WHERE resource='loans'").fetchone()[0], 'NOT_AVAILABLE')

    def test_corrupt_transaction_scope_fails_without_official_changes(self):
        before = self.financial()
        self.provider.overrides['/v2/transactions?accountId=account-BANK'] = (200, {'results': [{'id': 'x', 'accountId': 'different'}], 'next': None})
        self.assertEqual(self.sync()['state'], 'FAILED')
        self.assertEqual(self.financial(), before)

    def test_forbidden_live_endpoints_and_writes_fail_before_network(self):
        for path in ('/accounts/id/balance', '/items/item-test/scr', '/items/item-test/sync', '/payments', 'https://evil.example/accounts', '/accounts/../balance'):
            with self.subTest(path=path):
                self.assertFalse(cached_path(path))
                with self.assertRaises(PluggyError):
                    transport('GET', path, {}, None, 1)
        with self.assertRaises(PluggyError):
            transport('PATCH', '/items/item-test', {}, None, 1)

    def test_no_implicit_auth_or_network_on_get(self):
        for path in ('resources?resource=investments', 'coverage', 'resources?resource=bills'):
            self.assertEqual(self.request('/api/v2/open-finance/' + path)[0], 200)
        self.assertEqual(self.provider.calls, [])

    def test_http_auth_owner_and_validation(self):
        for path in ('resources', 'coverage', 'coverage-sync'):
            method = 'POST' if path == 'coverage-sync' else 'GET'
            self.assertEqual(self.request('/api/v2/open-finance/' + path, method, token=None)[0], 401)
            self.assertEqual(self.request('/api/v2/open-finance/' + path, method, token='synthetic-external-only')[0], 403)
        for suffix in ('resources?resource=unknown', 'resources?page=0', 'resources?page_size=26', 'resources?history=2', 'coverage?x=1'):
            self.assertEqual(self.request('/api/v2/open-finance/' + suffix)[0], 422)

    def test_http_manual_sync_and_resource_schema(self):
        with patch('finance_v2.open_finance.PluggyClient', self.service.client_factory):
            status, response = self.request('/api/v2/open-finance/coverage-sync', 'POST', body={'connection_id': 'bank-test'})
        self.assertEqual(status, 200, response)
        status, payload = self.request('/api/v2/open-finance/resources?resource=accounts&type=CREDIT')
        self.assertEqual(status, 200)
        self.assertEqual(payload['total'], 1)
        self.assertEqual(payload['items'][0]['data']['creditData']['creditLimit'], 1000)
        self.assertEqual(payload['net_worth']['state'], 'NOT_ESTABLISHED')

    def test_cursor_cycles_and_missing_next_rejected(self):
        for value in ({'results': []}, {'results': [], 'next': '?accountId=account-BANK&after=x'}):
            with self.subTest(value=value):
                provider = Provider()
                provider.overrides['/v2/transactions?accountId=account-BANK'] = (200, value)
                provider.overrides['/v2/transactions?accountId=account-BANK&after=x'] = (200, value)
                with self.assertRaises(PluggyError):
                    list(PluggyClient(self.config, send=provider.send).coverage_pages())

    def test_paged_collection_complete_and_partial_page_rejected(self):
        row = {'id': 'investment-1', 'itemId': 'item-test'}
        self.provider.overrides['/investments?itemId=item-test&page=1&pageSize=500'] = (200, {'results': [row], 'page': 1, 'total': 2, 'totalPages': 2})
        self.provider.overrides['/investments?itemId=item-test&page=2&pageSize=500'] = (200, {'results': [{**row, 'id': 'investment-2'}], 'page': 2, 'total': 2, 'totalPages': 2})
        self.assertEqual(self.sync()['state'], 'SUCCEEDED')
        self.provider.overrides['/investments?itemId=item-test&page=2&pageSize=500'] = (200, {'results': [], 'page': 2, 'total': 2, 'totalPages': 2})
        self.assertEqual(self.sync()['state'], 'FAILED')

    def test_duplicate_and_foreign_item_rejected(self):
        for rows in ([{'id': 'x', 'itemId': 'other'}], [{'id': 'x','itemId':'item-test'}, {'id': 'x','itemId':'item-test'}]):
            self.provider.overrides['/loans?itemId=item-test'] = (200, collection(rows))
            self.assertEqual(self.sync()['state'], 'FAILED')

    def test_zero_null_absent_and_projection_types(self):
        payload, encoded, digest, omitted = project('accounts', {'id': 'synthetic', 'balance': 0, 'owner': 'not persisted', 'unexpectedPrivate': 'not persisted', 'creditData': None})
        self.assertEqual(payload['balance'], 0)
        self.assertIsNone(payload['creditData'])
        self.assertNotIn('currencyCode', payload)
        self.assertEqual(omitted, 2)
        self.assertEqual(sha256(encoded.encode()).hexdigest(), digest)
        with self.assertRaises(ValueError):
            project('accounts', {'balance': 'not-a-number'})
        with self.assertRaises(ValueError):
            project('accounts', {'balance': float('nan')})
        exact = project('accounts', {'id':'synthetic','balance':Decimal('123.45000000000001')})[0]
        self.assertEqual(exact['balance'], '123.45000000000001')
        from finance_v2.pluggy_coverage import output_schema
        declared = output_schema(CONTRACT['resources']['accounts']['schema'])['properties']['balance']
        self.assertIn('anyOf',declared)

    def test_contract_integrity_fails_closed(self):
        with patch('finance_v2.pluggy_coverage.Path.read_bytes', return_value=b'{}'):
            with self.assertRaisesRegex(RuntimeError, 'INTEGRITY'):
                contracts()

    def test_payment_and_loan_details_keep_financial_fields_not_identifiers(self):
        value = {'id':'synthetic', 'paymentData':{'paymentMethod':'PIX','payer':{'name':'PRIVATE'},
            'authenticationCode':'PRIVATE','boletoMetadata':{'baseAmount':100,'barcode':'PRIVATE'}}}
        payload, encoded, _, omitted = project('transactions', value)
        self.assertEqual(payload['paymentData']['paymentMethod'], 'PIX')
        self.assertEqual(payload['paymentData']['boletoMetadata']['baseAmount'], 100)
        self.assertNotIn('PRIVATE', encoded)
        loan = project('loans', {'id':'synthetic','payments':{'contractOutstandingBalance':123.45,'releases':[{'paidAmount':20}]}})[0]
        self.assertEqual(loan['payments']['contractOutstandingBalance'], 123.45)
        self.assertGreater(omitted, 0)

    def test_malformed_page_rolls_back_legacy_and_extended_rows_together(self):
        rows = self.provider.send('GET','/accounts',{},None,1)[1]['results']
        rows[-1]['balance'] = 'invalid-number'
        self.provider.overrides['/accounts?itemId=item-test'] = (200, collection(rows))
        self.assertEqual(self.sync()['state'], 'FAILED')
        with closing(connect(self.db)) as c:
            self.assertEqual(c.execute('SELECT count(*) FROM of_accounts').fetchone()[0], 0)
            self.assertEqual(c.execute("SELECT count(*) FROM of_resource_records WHERE resource='accounts'").fetchone()[0], 0)

    def test_connection_disabled_binding_and_owner_guards(self):
        with self.assertRaises(SyncError):
            sync_full(self.service, 'bank-test', actor='EXTERNAL:x')
        with self.assertRaises(SyncError):
            sync_full(self.service, 'missing', actor='UI:local')
        self.sync()
        other = OpenFinanceService(replace(self.settings, pluggy_connections=(replace(self.config, item_id='different'),)))
        with self.assertRaisesRegex(SyncError, 'CONNECTION_BINDING_CHANGED'):
            sync_full(other, 'bank-test', actor='UI:local')

    def test_query_pagination_and_integrity(self):
        self.sync()
        with closing(connect(self.db)) as c:
            result = query(c, self.settings, {'resource': ['accounts'], 'page_size': ['25'], 'page': ['2']})
            self.assertEqual(result['items'], [])
            self.assertEqual(result['total'], 2)
            self.assertFalse(result['has_more'])
            self.assertEqual(c.execute('PRAGMA foreign_key_check').fetchall(), [])

    def test_schema8_to10_preservation_reapply_and_rollback(self):
        fresh = Path(self.temp.name) / 'fresh-schema8.sqlite3'
        with patch.object(migrations, 'MIGRATIONS', migrations.MIGRATIONS[:8]):
            self.assertEqual(migrations.migrate(fresh), list(range(1, 9)))
        with closing(connect(fresh)) as c:
            c.execute("INSERT INTO accounts(name,active) VALUES('Preservada sintética',1)")
            snapshot = list(c.execute('SELECT * FROM accounts'))
        self.assertEqual(migrations.migrate(fresh), [9, 10])
        self.assertEqual(migrations.migrate(fresh), [])
        with closing(connect(fresh)) as c:
            self.assertEqual([tuple(r) for r in c.execute('SELECT * FROM accounts')], [tuple(r) for r in snapshot])
            self.assertEqual(c.execute('PRAGMA integrity_check').fetchone()[0], 'ok')
            self.assertEqual(c.execute('SELECT count(*) FROM of_resource_records').fetchone()[0], 0)
        rollback = Path(self.temp.name) / 'rollback-synthetic.sqlite3'
        with patch.object(migrations, 'MIGRATIONS', migrations.MIGRATIONS[:9]):
            migrations.migrate(rollback)
        original = Path.read_text
        def broken(path, *args, **kwargs):
            text = original(path, *args, **kwargs)
            return text + '\nINSERT INTO missing_table VALUES(1);' if path.name.startswith('010_') else text
        with patch.object(Path, 'read_text', broken), self.assertRaises(migrations.MigrationError):
            migrations.migrate(rollback)
        with closing(connect(rollback)) as c:
            self.assertEqual(c.execute('PRAGMA user_version').fetchone()[0], 9)
            self.assertIsNone(c.execute("SELECT name FROM sqlite_master WHERE name='of_resource_records'").fetchone())


if __name__ == '__main__':
    unittest.main(verbosity=2)
