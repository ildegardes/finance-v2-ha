"""Regression fixtures with two independent synthetic Personal Items."""
from contextlib import closing
from dataclasses import replace
from urllib.parse import parse_qs, urlsplit
import unittest

from finance_v2.db import connect
from finance_v2.open_finance import OpenFinanceService
from finance_v2.open_finance_coverage import sync_full
from finance_v2.pluggy_client import PluggyClient
import test_full_coverage as fixture


class RecoveryFixture:
    def setUp(self):
        self.case = fixture.CoverageTests()
        self.case.setUp()
        self.addCleanup(self.case.doCleanups)
        self.connections = tuple(
            replace(self.case.config, id='synthetic-bank-' + str(number), institution=bank,
                    item_id='00000000-0000-4000-8000-00000000000' + str(number),
                    access_mode='meupluggy_personal')
            for number, bank in enumerate(('Itaú', 'Santander'), 1)
        )
        self.case.settings = replace(self.case.settings, pluggy_connections=self.connections)
        self.case.service = OpenFinanceService(self.case.settings, client_factory=lambda config:
            PluggyClient(config, send=lambda *args: self.send(config, *args), sleep=lambda _: None))
        self.consent = 'foreign'
        self.bad_account = False
        self.shared_limits = False

    def send(self, config, method, path, headers, body, timeout):
        parsed = urlsplit(path)
        query = parse_qs(parsed.query)
        item = config.item_id
        first = config.id == self.connections[0].id
        if parsed.path == '/items/' + item:
            return 200, {'id': item, 'status': 'UPDATED', 'connector': {
                'id': 200, 'isOpenFinance': False, 'isSandbox': False}}
        if parsed.path == '/consents':
            assert query['itemId'] == [item]
            consent = {'id': 'consent-synthetic', 'itemId': item}
            if self.consent != 'incomplete':
                consent['products'] = ['CREDIT_CARDS', 'ACCOUNTS']
            if self.consent == 'foreign':
                consent['itemId'] = '00000000-0000-4000-8000-000000000009'
            return 200, fixture.collection([consent])
        if parsed.path == '/accounts':
            assert query['itemId'] == [item]
            accounts = [{'id': 'cash-test', 'itemId': item, 'type': 'BANK', 'name': 'Conta de teste',
                         'balance': 50, 'currencyCode': 'BRL'}]
            for index, amount in enumerate((276.25, 413.75) if first else (0, 0), 1):
                shared = self.shared_limits and not first
                accounts.append({'id': 'card-test-' + str(index), 'itemId': item, 'type': 'CREDIT',
                    'name': 'Cartão de teste ' + str(index), 'number': 'XXXX ' + str(5700 + index),
                    'balance': 52 + index, 'currencyCode': 'BRL', 'updatedAt': '2026-10-20T10:00:00-03:00',
                    'creditData': {'status': 'ACTIVE', 'holderType': 'ADDITIONAL' if shared and index == 2 else 'MAIN',
                        'brand': 'VISA', 'disaggregatedCreditLimits': [{
                            'creditLineLimitType': 'LIMITE_CREDITO_TOTAL',
                            'consolidationType': 'CONSOLIDATED' if shared else 'INDIVIDUAL',
                            'identificationNumber': str(5701 if shared else 5700 + index),
                            'usedAmount': amount, 'usedAmountCurrencyCode': 'BRL',
                            'limitAmount': 3000 if shared else 1000, 'limitAmountCurrencyCode': 'BRL'}]}})
            if self.bad_account:
                accounts[1]['itemId'] = self.connections[1].item_id
            return 200, fixture.collection(accounts)
        if parsed.path == '/bills':
            return 200, fixture.collection([{'id': 'bill-test', 'dueDate': '2026-11-07T21:00:00-03:00',
                'billClosingDate': '2026-10-30T23:00:00-03:00', 'totalAmount': 343,
                'totalAmountCurrencyCode': 'BRL', 'payments': [{'amount': 104, 'currencyCode': 'BRL'}]}])
        if parsed.path == '/v2/transactions':
            account = query['accountId'][0]
            records = [{'id': 'tx-test-' + str(index), 'accountId': account, 'type': 'DEBIT',
                'description': ('Lote nove' if index < 9 else 'Lote extra') + f' {index:02}',
                'amount': -(12.25 + index), 'currencyCode': 'BRL', 'date': f'2026-10-{1 + index % 6:02}',
                'category': 'Food' if index < 9 else 'Health', 'categoryId': '1' if index < 9 else '2', 'status': 'POSTED'}
                for index in range(36)] if first and account == 'cash-test' else []
            return 200, {'results': records, 'next': None}
        if parsed.path in ('/investments','/loans'):
            return 200, fixture.collection([])
        return self.case.provider.send(method,path.replace(item,'item-test'),headers,body,timeout)

    def sync(self, *connections):
        return [sync_full(self.case.service, cfg.id, actor='UI:local') for cfg in connections or self.connections]

    def request(self, path):
        status, data = self.case.request('/api/v2/open-finance/' + path)
        self.assertEqual(status, 200, data)
        return data


class RecoveryTests(RecoveryFixture, unittest.TestCase):
    def test_native_positions_and_isolation(self):
        self.assertEqual([run['state'] for run in self.sync()], ['SUCCEEDED'] * 2)
        cards = self.request('analytics?presentation=BRL')['presentation_view']['cards']
        self.assertEqual(cards['metric']['amounts'], {})
        self.assertEqual(cards['preserved']['metric']['amounts'], {'BRL':'690.00'})
        self.assertEqual(cards['preserved']['limit_metric']['amounts'], {'BRL':'4000'})
        self.assertEqual(cards['preserved']['utilization_by_currency'], {'BRL':'0.1725'})
        self.assertEqual(cards['diagnostics'], [{'usage':'CONSENT_ITEM_MISMATCH','limit':'CONSENT_ITEM_MISMATCH','count':4}])
        items = {(card['connection_id'], card['account_id']): card for card in cards['items']}
        self.assertCountEqual([card['preserved_used'] for card in items.values()], ['276.25', '413.75', '0', '0'])
        self.assertEqual(sum(card['limit'] is not None for card in items.values()), 4)
        domain = self.request('domain?resource=accounts&type=CREDIT')
        for row in domain['items']:
            identity = row['identity']
            self.assertEqual(row['credit_position'], items[(identity['connection_id'],identity['external_id'])])
        with closing(connect(self.case.db)) as db:
            self.assertEqual(db.execute("SELECT count(*) FROM of_resource_records WHERE resource='consents'").fetchone()[0], 0)
        for token in ('synthetic-external-only',None):
            for route in ('analytics?presentation=BRL','domain?resource=accounts&type=CREDIT'):
                status, response = self.case.request('/api/v2/open-finance/' + route, token=token)
                self.assertIn(status,(401,403))
                self.assertNotIn('276.25',str(response))

    def test_current_incomplete_and_account_mismatch(self):
        self.consent = 'valid'
        self.assertEqual(self.sync()[0]['state'], 'SUCCEEDED')
        control = self.request('analytics?presentation=BRL')['presentation_view']['cards']
        self.assertEqual(control['metric']['amounts'], {'BRL':'690.00'})
        self.assertEqual(control['preserved']['metric']['amounts'], {})
        self.consent = 'incomplete'
        self.assertEqual(self.sync(self.connections[0])[0]['state'], 'SUCCEEDED')
        mixed = self.request('analytics?presentation=BRL')['presentation_view']['cards']
        self.assertEqual(mixed['metric']['amounts'], {'BRL':'0'})
        self.assertEqual(mixed['preserved']['metric']['amounts'], {'BRL':'690.00'})
        self.bad_account = True
        self.assertEqual(self.sync(self.connections[0])[0]['error_code'], 'ACCOUNT_SCOPE_MISMATCH')
        filtered = self.request('analytics?presentation=BRL&connection_id=' + self.connections[0].id)['presentation_view']['cards']
        self.assertEqual(filtered['preserved']['metric']['amounts'], {})
        self.assertFalse(any(card.get('preserved_used') for card in filtered['items']))

    def test_preserved_shared_limit_is_counted_once(self):
        self.shared_limits = True
        self.sync()
        cards = self.request('analytics?presentation=BRL')['presentation_view']['cards']
        self.assertEqual(cards['preserved']['metric']['amounts'], {'BRL':'690.00'})
        self.assertEqual(cards['preserved']['limit_metric']['amounts'], {'BRL':'5000'})
        self.assertEqual(cards['preserved']['utilization_by_currency'], {'BRL':'0.138'})
        self.assertEqual(sum(card['limit'] is not None for card in cards['items']), 3)

    def test_currency_and_bill_provenance(self):
        self.sync()
        bills = self.request('domain?resource=bills&connection_id=' + self.connections[0].id + '&parent_id=card-test-1')
        self.assertEqual(bills['total'], 1)
        bill = bills['items'][0]
        self.assertEqual(bill['name'], 'Fatura de cartão')
        self.assertEqual(bill['temporal']['financial_observation'],
                         {'dueDate':'2026-11-07T21:00:00-03:00','billClosingDate':'2026-10-30T23:00:00-03:00'})
        transactions = self.request('analytics?start=2026-10-01&end=2026-10-31&search=Lote+nove&sort=value_asc')
        self.assertEqual(transactions['total'], 9)
        self.assertEqual(len(transactions['items']), 9)
        self.assertEqual({row['currency'] for row in transactions['items']}, {'BRL'})
