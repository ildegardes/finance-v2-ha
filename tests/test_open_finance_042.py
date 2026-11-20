"""Synthetic acceptance of native open balances and local scheduling."""
from contextlib import closing
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit
import unittest

from finance_v2.db import connect
from finance_v2.open_finance import OpenFinanceService, SyncError
from finance_v2.open_finance_auto import CoverageWorkers
from finance_v2.open_finance_registry_admin import RegistryAdmin
from finance_v2.open_finance_schedule import report, save
from test_open_finance_041 import RecoveryFixture


class OpenBalanceFixture(RecoveryFixture):
    def setUp(self):
        super().setUp()
        self.missing_balance = False

    def send(self, config, method, path, headers, body, timeout):
        status, payload = super().send(config, method, path, headers, body, timeout)
        if urlsplit(path).path == '/accounts':
            positive = config.id == self.connections[0].id
            for index, account in enumerate(payload['results'][1:]):
                account.update(updatedAt=f'2026-10-{19+index}T13:00:00-03:00',
                               balance=(123.45,241.55)[index] if positive else 0)
                if self.missing_balance and positive and index==1:
                    account.pop('balance')
                account['creditData'].pop('disaggregatedCreditLimits')
        return status,payload

    def rates(self):
        with closing(connect(self.case.db)) as db:
            db.executemany('INSERT INTO portfolio_fx_rates VALUES (?,?,?,?)',
                [(day,rate,'2026-10-25T12:00:00Z','BCB_PTAX_SELL')
                 for day,rate in [('2026-10-19','5'),('2026-10-20','4')]])


class OpenBalanceTests(OpenBalanceFixture, unittest.TestCase):
    def test_open_balance_is_independent_of_used_credit_and_bills(self):
        self.assertEqual([run['state'] for run in self.sync()], ['SUCCEEDED','SUCCEEDED'])
        self.rates()
        cards=self.request('analytics?presentation=BRL')['presentation_view']['cards']
        self.assertEqual(cards['metric']['amounts'],{})
        self.assertEqual(cards['preserved']['limit_metric']['amounts'],{})
        self.assertEqual(cards['preserved']['metric']['amounts'],{})
        metric=cards['open_balance']
        self.assertEqual(metric['amounts'],{'BRL':'365.00'})
        self.assertEqual(metric['dates'],['2026-10-19','2026-10-20'])
        self.assertTrue(metric['mixed_dates'] and metric['partial'] and metric['preserved'])
        self.assertCountEqual([card['reported_balance'] for card in cards['items']],['123.45','241.55','0','0'])
        detailed=self.request('domain?resource=accounts&type=CREDIT')['items']
        self.assertCountEqual([row['credit_position']['reported_balance'] for row in detailed],['123.45','241.55','0','0'])
        usd=self.request('analytics?presentation=USD')['presentation_view']['cards']['open_balance']
        self.assertEqual(usd['amounts'],{'USD':'85.0775'})
        santander=self.request('analytics?presentation=BRL&connection_id=synthetic-bank-2')['presentation_view']['cards']
        self.assertEqual(santander['open_balance']['amounts'],{'BRL':'0'})
        self.assertEqual(santander['open_balance']['included'],2)

    def test_missing_and_wrong_item_never_become_zero(self):
        self.missing_balance=True
        self.sync()
        cards=self.request('analytics?presentation=BRL')['presentation_view']['cards']
        self.assertEqual(cards['open_balance']['amounts'],{'BRL':'123.45'})
        self.assertEqual(cards['open_balance']['included'],3)
        self.assertIn(None,[card['reported_balance'] for card in cards['items']])
        first=self.connections[0]
        with closing(connect(self.case.db)) as db:
            db.execute("UPDATE of_resource_records SET payload_json=json_set(payload_json,'$.itemId',?) "
                       "WHERE connection_id=? AND resource='accounts' AND external_id='card-test-1'",
                       (self.connections[1].item_id,first.id))
        cards=self.request('analytics?presentation=BRL&connection_id='+first.id)['presentation_view']['cards']
        self.assertEqual(cards['open_balance']['amounts'],{})
        self.assertFalse(any(card['reported_balance'] is not None for card in cards['items']))
        row=self.request('domain?resource=accounts&type=CREDIT&connection_id='+first.id+'&external_id=card-test-1')['items'][0]
        self.assertIsNone(row['credit_position'])
        self.assertEqual(row['fields'],[])


class PolicyTests(OpenBalanceFixture, unittest.TestCase):
    def test_legacy_policy_restart_precedence_and_archive(self):
        self.sync()
        settings=replace(self.case.settings,open_finance_auto_sync_allowed=True)
        service=OpenFinanceService(settings)
        admin=RegistryAdmin(service)
        owner={'actor':'UI:local','confirmed':True}
        connection=self.connections[1]
        cid=connection.id
        now=datetime.now(timezone.utc)
        def row(config=settings):
            with closing(connect(self.case.db)) as db:
                return next(item for item in report(db,config,now)['connections'] if item['connection_id']==cid)
        self.assertEqual(row()['reason'],'CONNECTION_AUTO_DISABLED')
        with self.assertRaisesRegex(SyncError,'OWNER_REQUIRED'):
            admin.set_auto_sync(cid,revision=0,enabled=True,actor='CLIENT:external',confirmed=True)
        saved=admin.set_auto_sync(cid,revision=0,enabled=True,**owner)
        self.assertEqual(saved['revision'],1)
        self.assertTrue(OpenFinanceService(settings).resolve_config(cid).auto_sync_enabled)
        with self.assertRaisesRegex(SyncError,'CONNECTION_CONFIGURATION_CHANGED'):
            admin.set_auto_sync(cid,revision=0,enabled=False,**owner)
        info=row()
        self.assertTrue(info['effective'])
        last=datetime.fromisoformat(info['last_success'].replace('Z','+00:00'))
        self.assertEqual(info['next_attempt'],(last+timedelta(hours=24)).isoformat(timespec='seconds').replace('+00:00','Z'))
        self.assertEqual(row(replace(settings,open_finance_auto_sync_allowed=False))['reason'],'SUPERVISOR_DISABLED')
        save(service,{'enabled':False,'interval_hours':6,'revision':0})
        self.assertTrue(row()['requested_enabled'])
        self.assertEqual(row()['reason'],'GLOBAL_PREFERENCE_DISABLED')
        save(service,{'enabled':True,'interval_hours':6,'revision':1})
        calls=[]
        class Recorder(CoverageWorkers):
            def _loop(self, config):
                self.stop_event.wait()
            def _run_one(self,*args,**kwargs):
                calls.append('unexpected-provider-contact')
        worker=Recorder(settings)
        worker.start()
        self.addCleanup(worker.stop)
        self.assertEqual(worker._planned,{cid})
        self.assertEqual(calls,[])
        admin.set_auto_sync(cid,revision=1,enabled=False,**owner)
        self.assertFalse(OpenFinanceService(settings).resolve_config(cid).auto_sync_enabled)
        self.assertEqual(row()['reason'],'CONNECTION_AUTO_DISABLED')
        # Existing archival needs no policy update or automatic reactivation.
        with closing(connect(self.case.db)) as db:
            db.execute("UPDATE of_connection_registry SET lifecycle='ARCHIVED',revision=revision+1 WHERE connection_id=?",(cid,))
        self.assertEqual(row()['reason'],'ARCHIVED')
        self.assertFalse(row()['policy_editable'])
        with self.assertRaisesRegex(SyncError,'CONNECTION_CONFIGURATION_CHANGED'):
            admin.set_auto_sync(cid,revision=3,enabled=True,**owner)
        self.assertEqual(row()['lifecycle'],'ARCHIVED')

    def test_initial_legacy_override_is_bound_and_leaves_other_defaults_alone(self):
        settings=replace(self.case.settings,open_finance_auto_sync_allowed=True)
        service=OpenFinanceService(settings)
        admin=RegistryAdmin(service)
        cid=self.connections[1].id
        admin.set_auto_sync(cid,actor='UI:local',revision=0,enabled=True,confirmed=True)
        self.assertTrue(service.resolve_config(cid).auto_sync_enabled)
        other=service.resolve_config(self.connections[0].id)
        self.assertFalse(other.auto_sync_enabled)
        with closing(connect(self.case.db)) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM of_sync_runs').fetchone()[0],0)
            config=replace(self.connections[1],item_id='fixture-other-item')
            db.execute('UPDATE of_connections SET binding_hash=? WHERE id=?',(service._binding(config),cid))
        replacement=OpenFinanceService(replace(settings,pluggy_connections=(other,config)))
        self.assertFalse(replacement.resolve_config(cid).auto_sync_enabled)
