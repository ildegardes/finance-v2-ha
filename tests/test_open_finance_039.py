"""Financial and operational acceptance fixtures for Finance V17 0.1.39."""
from contextlib import closing
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
import json
import unittest

from finance_v2.db import connect
from finance_v2.open_finance_analytics import analytics
from finance_v2.open_finance_auto import CoverageWorkers
from finance_v2.open_finance_schedule import report
from finance_v2.open_finance_wealth import report as unified_portfolio
from finance_v2.pluggy_coverage import project
from finance_v2.portfolio_fx_worker import PortfolioFXWorker

import test_open_finance_038 as portfolio_fixture
import test_open_finance_registry_admin as registry_fixture


class FinancialParity(unittest.TestCase):
    def setUp(self):
        self.dashboard=portfolio_fixture.DashboardTests('test_original_and_converted_kpis_card_dedup_and_economic_income')
        self.dashboard.setUp()
        self.addCleanup(self.dashboard.doCleanups)
        self.fixture=self.dashboard.fixture
        self.case=self.fixture.case

    def view(self,target='BRL'):
        return self.dashboard.view(target)

    def write_card(self,external,modify):
        payload,=self.case.sql('SELECT payload_json FROM of_resource_records WHERE resource=? AND external_id=?',('accounts',external))[0]
        payload=json.loads(payload)
        modify(payload)
        self.case.write("UPDATE of_resource_records SET payload_json=? WHERE resource='accounts' AND external_id=?",
                        (json.dumps(payload,ensure_ascii=False),external))

    @staticmethod
    def totals(metric):
        return {key:Decimal(value) for key,value in metric['amounts'].items()}

    def test_independent_equal_limits_used_and_zero_are_reconciled(self):
        cards=self.view()['cards']
        self.assertEqual(cards['basis'],'CREDIT_USED')
        self.assertEqual(self.totals(cards['metric']),{'BRL':500})
        self.assertEqual(self.totals(cards['limit_metric']),{'BRL':4000})
        used=[Decimal(row['used']) for row in cards['items'] if row['included']]
        self.assertEqual(sorted(used),[0,0,180,320])
        self.assertEqual(sum(used),500)
        self.assertEqual(cards['utilization_by_currency'],{'BRL':'0.125'})
        self.assertEqual({row['tail'] for row in cards['items']},{'9400','9401','9402','9403'})
        self.assertTrue(all(row['used_basis']=='REGULATED_BALANCE' for row in cards['items']))
        usd=self.view('USD')['cards']
        self.assertEqual(self.totals(usd['metric']),{'USD':100})
        self.assertEqual(self.totals(usd['limit_metric']),{'USD':800})

    def test_partial_used_and_partial_limit_are_independent(self):
        self.write_card('card-extra',lambda row:row['creditData']['disaggregatedCreditLimits'][0].pop('limitAmount'))
        cards=self.view()['cards']
        self.assertEqual(self.totals(cards['metric']),{'BRL':500})
        self.assertEqual(self.totals(cards['limit_metric']),{'BRL':3000})
        self.assertTrue(cards['limit_metric']['partial'])
        self.assertEqual(cards['utilization_by_currency'],{})
        self.write_card('card-repeat',lambda row:row.update(balance=None))
        self.write_card('card-missing',lambda row:row.update(balance=-5))
        cards=self.view()['cards']
        reasons={row['account_id']:row['consolidation_reason'] for row in cards['items']}
        self.assertEqual(reasons['card-repeat'],'AMOUNT_UNAVAILABLE')
        self.assertEqual(reasons['card-missing'],'NEGATIVE_REPORTED')
        self.assertTrue(cards['metric']['partial'])

    def test_shared_line_is_counted_once_and_unverified_overlap_is_excluded(self):
        def shared(row,holder,amount):
            row['creditData']['holderType']=holder
            row['creditData']['disaggregatedCreditLimits'][0].update(
                consolidationType='CONSOLIDATED',identificationNumber='pool-synthetic',usedAmount=amount,limitAmount=1800)
        self.write_card('account-CREDIT',lambda row:shared(row,'MAIN',500))
        self.write_card('card-extra',lambda row:shared(row,'ADDITIONAL',500))
        for card in ('card-repeat','card-missing'):
            self.write_card(card,lambda row:row['creditData'].update(status='CANCELLED'))
        cards=self.view()['cards']
        self.assertEqual(self.totals(cards['metric']),{'BRL':500})
        self.assertEqual(self.totals(cards['limit_metric']),{'BRL':1800})
        self.assertEqual(sum(row['included'] for row in cards['items']),1)
        self.assertIn('ALREADY_IN_SHARED_LINE',{row['consolidation_reason'] for row in cards['items']})
        self.assertTrue(cards['utilization_by_currency'])
        self.write_card('card-extra',lambda row:shared(row,'ADDITIONAL',501))
        cards=self.view()['cards']
        self.assertEqual(cards['metric']['amounts'],{})
        self.assertEqual(cards['limit_metric']['amounts'],{})
        self.assertEqual(cards['utilization_by_currency'],{})

    def test_consent_and_binding_fail_closed_and_exact_reassociation_recovers(self):
        self.write_card('account-CREDIT',lambda row:row.update(itemId='foreign-item-synthetic'))
        cards=self.view()['cards']
        self.assertEqual(self.totals(cards['metric']),{'BRL':180})
        self.assertIn('ACCOUNT_ITEM_MISMATCH',{row['consolidation_reason'] for row in cards['items']})
        self.case.write("UPDATE of_collection_checkpoints SET state='FAILED',error_code='ITEM_ID_DIFFERENT' WHERE resource='consents'")
        cards=self.view()['cards']
        self.assertEqual(cards['metric']['amounts'],{})
        self.assertTrue(all(row['used'] is None for row in cards['items']))
        self.case.write("UPDATE of_collection_checkpoints SET state='COMPLETE',error_code=NULL WHERE resource='consents'")
        self.case.write("""UPDATE of_resource_records SET payload_json=json_set(payload_json,'$.products',json('["ACCOUNTS"]'))
                           WHERE resource='consents' AND external_id='consent-039'""")
        self.assertEqual(self.view()['cards']['metric']['amounts'],{})
        self.assertIn('CONSENT_NO_CARD_SCOPE',{row['consolidation_reason'] for row in self.view()['cards']['items']})
        current=self.fixture.settings.pluggy_connections[0].item_id
        self.write_card('account-CREDIT',lambda row:row.update(itemId=current))
        self.case.write("""UPDATE of_resource_records SET payload_json=json_set(payload_json,'$.products',json('["CREDIT_CARDS"]'))
                           WHERE resource='consents' AND external_id='consent-039'""")
        self.assertEqual(self.totals(self.view()['cards']['metric']),{'BRL':500})
        self.assertEqual(self.case.sql("SELECT count(*) FROM of_resource_records WHERE resource='accounts' AND external_id='account-CREDIT'"),[(1,)])

    def test_alternate_source_uses_only_the_documented_used_amount(self):
        self.case.write("""UPDATE of_resource_records SET payload_json=json_set(payload_json,'$.connector.isOpenFinance',json('false'))
                           WHERE resource='item' AND connection_id='bank-test'""")
        self.write_card('account-CREDIT',lambda row:row.update(balance=9999))
        cards=self.view()['cards']
        self.assertEqual(self.totals(cards['metric']),{'BRL':500})
        self.assertTrue(all(row['used_basis']=='PROVIDER_USED_AMOUNT' for row in cards['items']))
        payload,serialized,_,_=project('accounts',{'type':'CREDIT','number':'5555555555555555','cardLastFour':'5678'})
        self.assertNotIn('number',payload)
        self.assertNotIn('cardLastFour',payload)
        self.assertNotIn('5555',serialized)

    def test_native_fallback_and_incremental_fx_match_the_unified_portfolio(self):
        self.case.write('DELETE FROM portfolio_fx_rates')
        self.case.write("UPDATE st_balances SET reference_at=NULL")
        self.case.write("UPDATE st_positions SET reference_at='2026-08-19T16:00:00Z'")
        missing=self.view()
        broker=next(row for row in missing['institutions'] if row['provider']=='SNAPTRADE')
        self.assertEqual(Decimal(broker['investments']['original']['USD']),23400)
        self.assertEqual(broker['investments']['amounts'],{})
        self.assertEqual(Decimal(broker['liquid']['original']['USD']),500)
        self.assertEqual(broker['investments']['missing_reasons'],{'RATE_UNAVAILABLE':4})
        self.assertEqual(broker['liquid']['missing_reasons'],{'REFERENCE_UNAVAILABLE':1})
        self.assertEqual(self.totals(missing['investments']),{'BRL':150000})
        calls=[]
        quotes={'2026-08-18':4,'2026-10-19':4,'2026-10-20':5,'2026-10-21':99}
        def transport(start,end):
            calls.append((start,end))
            return [{'dataHoraCotacao':key+' 13:00:00','cotacaoVenda':value} for key,value in quotes.items()
                    if start.isoformat()<=key<=end.isoformat()]
        worker=PortfolioFXWorker(self.fixture.settings,clock=self.fixture.clock,transport=transport)
        worker.tick()
        self.assertEqual(len(calls),2)
        self.assertTrue(any(start<=date(2026,8,18)<=end for start,end in calls))
        self.assertTrue(all(end<=self.fixture.clock.today() for _,end in calls))
        self.assertEqual(self.case.sql("SELECT count(*) FROM portfolio_fx_rates"),[(3,)])
        worker.tick()
        self.assertEqual(len(calls),2)
        self.case.write("UPDATE st_activities SET date='2026-07-01' WHERE rowid=(SELECT min(rowid) FROM st_activities)")
        quotes['2026-07-01']=3
        worker.tick()
        self.assertEqual(len(calls),3)
        worker.tick()
        self.assertEqual(len(calls),3)
        after=self.view()
        with closing(connect(self.case.db)) as db:
            summary=unified_portfolio(db,self.fixture.settings,{'presentation':['BRL']},portfolio_fixture.DATE)['summary']
        self.assertEqual(self.totals(after['investments']),{'BRL':243600})
        self.assertEqual(self.totals(summary['investment_metric']),self.totals(after['investments']))
        self.assertEqual(sum(self.totals(row['metric']).get('BRL',0) for row in after['composition']),243600)
        self.assertEqual(sum(self.totals(row['investments']).get('BRL',0) for row in after['institutions']),243600)
        self.assertEqual(self.case.sql('SELECT reference_at FROM st_balances'),[(None,)])

    def test_fx_failure_backs_off_then_retries_without_erasing_cached_quotes(self):
        self.case.write("DELETE FROM portfolio_fx_rates WHERE quote_date='2026-10-20'")
        calls=[]
        def transport(start,end):
            calls.append((start,end))
            if len(calls)==1:
                raise TimeoutError
            return [{'dataHoraCotacao':'2026-10-20 13:00:00','cotacaoVenda':5}] if (
                start<=date(2026,10,20)<=end) else []
        worker=PortfolioFXWorker(self.fixture.settings,clock=self.fixture.clock,transport=transport)
        with self.assertLogs('finance_v2.portfolio_fx_worker',level='WARNING'):
            worker.tick()
        worker.tick()
        self.assertEqual(len(calls),1)
        self.assertEqual(self.case.sql('SELECT quote_date FROM portfolio_fx_rates'),[('2026-10-19',)])
        worker.service.clock=replace(self.fixture.clock,instant=self.fixture.clock.instant+timedelta(minutes=31))
        worker.tick()
        self.assertEqual(self.case.sql('SELECT quote_date FROM portfolio_fx_rates ORDER BY quote_date'),
                         [('2026-10-19',),('2026-10-20',)])

    def test_pluggy_grouping_matches_the_legacy_analytics_contract(self):
        with closing(connect(self.case.db)) as db:
            legacy=analytics(db,self.fixture.settings,{'currency':['BRL']},portfolio_fixture.DATE)
        old={row['type']:Decimal(row['value']) for row in legacy['positions']['investments']['by_class']}
        national={row['class'].split(':',1)[1]:self.totals(row['metric'])['BRL'] for row in self.view()['composition']
                  if row['class'].startswith('PLUGGY:')}
        self.assertEqual(old,national)
        self.assertEqual(national['EQUITY'],50000)


class SantanderPolicy(unittest.TestCase):
    def test_managed_opt_in_suspend_and_restart_keep_the_original_guards(self):
        fixture=registry_fixture.RegistryEnrollmentTests('test_owner_confirms_item_before_activating_without_import')
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        service,admin=fixture.service,fixture.admin
        draft=admin.create_draft(actor='UI:local',label='Santander',environment='PERSONAL',
                                 client_id='fixture-client',client_secret='fixture-secret',item_id='fixture-item')
        cid=draft['id']
        admin.validate_and_activate(cid,actor='UI:local',revision=0,confirmed=True)
        def current(settings=service.settings):
            with closing(service._db()) as db:
                return report(db,settings,datetime.now(timezone.utc))['connections'][0]
        self.assertEqual(current()['reason'],'CONNECTION_AUTO_DISABLED')
        self.assertFalse(current()['effective'])
        settings=replace(service.settings,open_finance_auto_sync_allowed=True)
        starts=[]
        class ReceiptWorker(CoverageWorkers):
            def _loop(self,config):
                starts.append(config.id)
                self.stop_event.wait()
        worker=ReceiptWorker(settings)
        worker.start()
        self.addCleanup(worker.stop)
        self.assertEqual(worker.threads,[])
        saved=admin.set_auto_sync(cid,actor='UI:local',revision=1,confirmed=True,enabled=True)
        self.assertTrue(saved['auto_sync_enabled'])
        self.assertTrue(current(settings)['effective'])
        worker._start_eligible()
        self.assertEqual(starts,[cid])
        self.assertTrue(worker.stop())
        fresh=ReceiptWorker(settings)
        fresh.start()
        self.addCleanup(fresh.stop)
        self.assertTrue(current(settings)['effective'])
        self.assertEqual(starts,[cid,cid])
        self.assertEqual(current(replace(settings,open_finance_auto_sync_allowed=False))['reason'],'SUPERVISOR_DISABLED')
        admin.disable(cid,actor='UI:local',revision=2,confirmed=True)
        self.assertEqual(current(settings)['reason'],'CONNECTION_DISABLED')
        self.assertFalse(current(settings)['effective'])


if __name__=='__main__':
    unittest.main()
