"""Targeted Gate C counterexamples; synthetic fixtures and no network."""
from contextlib import closing
import json
import unittest
from finance_v2.db import connect
from finance_v2.open_finance_domain import field
import test_gate_b as old


class TemporalTests(unittest.TestCase):
    setUp=old.GateBTests.setUp
    sync=old.GateBTests.sync
    financial=old.GateBTests.financial
    domain=old.GateBTests.domain
    rows=old.GateBTests.rows

    def position(self,currency='USD'):
        self.provider.overrides['/investments?itemId=item-test&page=1&pageSize=500']=(200,old.prior.collection([
            {'id':'investment-test','itemId':'item-test','name':'Synthetic position','type':'FIXED_INCOME','currencyCode':currency,'balance':200}]))

    def money(self,row,key='amount'):
        return next(f for f in row['fields'] if f['key']==key)

    def test_original_currency_counterexample_history_and_current(self):
        self.position();self.assertEqual(self.sync()['state'],'SUCCEEDED')
        before=self.domain('investment_transactions',history=1)['items'][0]
        self.assertEqual(self.money(before)['currency'],'USD')
        self.position('BRL');self.assertEqual(self.sync()['state'],'SUCCEEDED')
        after=self.domain('investment_transactions',history=1)['items'][0]
        self.assertEqual(after['fields'],before['fields'])
        self.assertEqual(self.money(self.domain('investment_transactions')['items'][0])['currency'],'USD')
        self.assertEqual(self.domain('investment_transactions')['total'],1)

    def test_missing_parent_currency_never_invented_later(self):
        self.position(None);self.sync()
        self.position('BRL');self.sync()
        for history in (0,1):
            row=self.domain('investment_transactions',history=history)['items'][0]
            self.assertIsNone(self.money(row)['currency'])
            self.assertEqual(row['currency_context']['source'],'NOT_PROVIDED')

    def test_explicit_currency_across_money_domains_survives_replay(self):
        paths={
            '/accounts?itemId=item-test':None,
            '/v2/transactions?accountId=account-BANK':None,
            '/v2/transactions?accountId=account-CREDIT':None,
            '/investments?itemId=item-test&page=1&pageSize=500':None,
            '/loans?itemId=item-test':None,
            '/bills?accountId=account-CREDIT&page=1&pageSize=500':None}
        domains=('accounts','transactions','investments','loans','bills')
        for path in paths:
            status,body=self.provider.send('GET',path,{},None,1)
            for row in body['results']:
                if 'totalAmountCurrencyCode' in row:row['totalAmountCurrencyCode']='USD'
                else:row['currencyCode']='USD'
            self.provider.overrides[path]=(status,body)
        self.assertEqual(self.sync()['state'],'SUCCEEDED')
        before={d:self.domain(d,history=1)['items'] for d in domains}
        self.assertEqual(self.sync()['state'],'SUCCEEDED')
        for d in domains:
            after=self.domain(d,history=1)['items']
            self.assertEqual([r['fields'] for r in after],[r['fields'] for r in before[d]])
            for row in after:self.assertEqual(row['currency_context']['currency'],'USD',d)

    def test_account_currency_at_origin_and_provider_currency_are_distinct(self):
        path='/v2/transactions?accountId=account-BANK'
        _,body=self.provider.send('GET',path,{},None,1)
        body['results'][0].update(currencyCode='USD',amountInAccountCurrency=12)
        self.provider.overrides[path]=(200,body);self.sync()
        _,accounts=self.provider.send('GET','/accounts',{},None,1)
        for row in accounts['results']:row['currencyCode']='EUR'
        self.provider.overrides['/accounts?itemId=item-test']=(200,accounts);self.sync()
        row=next(r for r in self.domain('transactions',history=1)['items'] if r['identity']['parent_id']=='account-BANK')
        self.assertEqual(self.money(row)['currency'],'USD')
        self.assertEqual(self.money(row,'amountInAccountCurrency')['currency'],'BRL')

    def test_explicit_null_currency_does_not_inherit(self):
        spec={'properties':{'amount':{'type':'number'}}}
        result=field('payment',spec,{'amount':5,'currencyCode':None},True,'BRL')
        self.assertIsNone(result['children'][0]['currency'])

    def test_nested_explicit_currency_overrides_parent(self):
        spec={'properties':{'amount':{'type':'number'}}}
        result=field('payment',spec,{'amount':5,'currencyCode':'USD'},True,'BRL')
        self.assertEqual(result['children'][0]['currency'],'USD')

    def test_missing_revision_context_fails_to_unknown_not_current_parent(self):
        self.position();self.sync()
        with closing(connect(self.db)) as c:
            # Synthetic legacy/incomplete evidence. Never fabricate a current fallback.
            c.execute("DELETE FROM of_resource_revisions WHERE resource='investment_transactions'")
        row=self.domain('investment_transactions')['items'][0]
        self.assertIsNone(self.money(row)['currency'])
        self.assertIsNone(row['temporal']['content_first_collected_at'])

    def test_absence_and_reappearance_do_not_relabel_old_movement(self):
        self.position('USD');self.sync()
        path='/investments/investment-test/transactions?page=1&pageSize=500'
        self.provider.overrides[path]=(200,old.prior.collection([]))
        self.position('BRL');self.sync()
        row=self.domain('investment_transactions')['items'][0]
        self.assertEqual(row['record_state'],'NOT_SEEN')
        self.assertEqual(self.money(row)['currency'],'USD')
        self.assertIsNone(row['temporal']['last_seen_at'])
        self.assertIsNotNone(row['temporal']['absence_observed_at'])
        del self.provider.overrides[path];self.sync()
        self.assertEqual(self.money(self.domain('investment_transactions')['items'][0])['currency'],'USD')
        for row in self.domain('investment_transactions',history=1)['items']:
            self.assertEqual(self.money(row)['currency'],'USD')

    def item(self,updated,execution='SUCCESS'):
        self.provider.overrides['/items/item-test']=(200,{'id':'item-test','status':'UPDATED',
            'executionStatus':execution,'updatedAt':'2026-10-29T00:00:00Z',
            'statusDetail':{'investments':{'isUpdated':updated}}})

    def test_original_freshness_counterexample_stable_history(self):
        self.item(False);self.sync();before=self.domain('investments',history=1)['items'][0]
        self.item(True);self.provider.balance=300;self.sync()
        after=self.domain('investments',history=1)['items'][0]
        self.assertEqual(after['freshness'],before['freshness'])
        self.assertEqual(after['temporal']['provider_execution_at_collection'],before['temporal']['provider_execution_at_collection'])
        self.assertEqual(after['freshness']['state'],'STALE')

    def test_new_collection_is_not_new_financial_observation(self):
        self.item(True);self.sync();row=self.domain('investment_transactions')['items'][0]
        self.assertEqual(row['temporal']['financial_observation'],{'date':'2026-10-20'})
        self.assertIsNotNone(row['temporal']['collected_at'])
        self.assertIsNone(row['temporal']['provider_updated_at'])
        self.assertEqual(row['temporal']['effective_freshness'],'NOT_ESTABLISHED')
        self.assertNotEqual(row['freshness']['state'],'UPDATED_IN_LAST_EXECUTION')

    def test_partial_success_does_not_relabel_historical_success(self):
        self.item(True);self.sync();before=self.domain('investments',history=1)['items'][0]
        self.item(False,'PARTIAL_SUCCESS');self.sync()
        after=self.domain('investments',history=1)['items'][0]
        self.assertFalse(after['freshness']['provider_execution_partial'])
        self.assertEqual(after['temporal']['provider_execution_at_collection'],before['temporal']['provider_execution_at_collection'])

    def test_partial_success_at_origin_remains_auditable(self):
        self.item(False,'PARTIAL_SUCCESS');self.sync();row=self.domain('investments')['items'][0]
        self.assertTrue(row['freshness']['provider_execution_partial'])
        self.assertEqual(row['temporal']['provider_execution_at_collection']['status'],'PARTIAL_SUCCESS')
        self.assertEqual(row['temporal']['effective_freshness'],'STALE')

    def test_failed_current_sync_separate_from_historical_quality(self):
        self.item(True);self.sync()
        self.provider.overrides['/items/item-test']=(401,{})
        self.assertEqual(self.sync()['state'],'FAILED')
        row=self.domain('investments',history=1)['items'][0]
        self.assertEqual(row['temporal']['current_sync']['state'],'FAILED')
        self.assertEqual(row['temporal']['provider_execution_at_collection']['status'],'SUCCESS')

    def test_read_projection_and_replay_preserve_official_tables(self):
        self.sync();before=self.financial()
        for resource in old.CONTRACT['resources']:
            for history in (0,1):self.domain(resource,history=history)
        self.sync()
        self.assertEqual(self.financial(),before)
        with closing(connect(self.db)) as c:
            self.assertEqual(c.execute('PRAGMA integrity_check').fetchone()[0],'ok')
            self.assertEqual(c.execute('PRAGMA foreign_key_check').fetchall(),[])
            self.assertEqual(c.execute('PRAGMA user_version').fetchone()[0],11)


if __name__=='__main__':unittest.main()
