from contextlib import closing
from dataclasses import replace
from datetime import datetime,timezone,timedelta
import unittest
from support import Providers, STOCK
from test_sqlite_validation import DatabaseCase
from finance_v2.db import connect
from finance_v2.domain.clock import FixedClock
from finance_v2.open_finance import OpenFinanceService,SyncError
from finance_v2.open_finance_auto import CoverageWorkers
from finance_v2.open_finance_coverage import sync_full,sync_full_automatic

class ReleasePolicyTests(DatabaseCase):
    def worker(self):return CoverageWorkers(self.config,send=self.providers.send)
    def test_restart_does_not_repeat_recent_automatic_success(self):
        first=self.worker()._run_one(self.config.pluggy_connections[0],respect_schedule=True)
        self.assertEqual(first['state'],'SUCCEEDED')
        calls=len(self.providers.banks['itau'].visited)
        for _ in range(3):
            with self.assertRaises(SyncError) as error:
                self.worker()._run_one(self.config.pluggy_connections[0],respect_schedule=True)
            self.assertEqual(error.exception.code,'AUTO_SYNC_RECENT')
            self.assertTrue(1 <= error.exception.retry_after <= 3600)
        self.assertEqual(len(self.providers.banks['itau'].visited),calls)
        with closing(connect(self.path)) as c:self.assertEqual(c.execute('SELECT count(*) FROM of_sync_runs').fetchone()[0],1)
    def test_failure_backoff_does_not_block_explicit_manual_collection(self):
        self.providers.banks['itau'].mode='unavailable'
        self.assertEqual(self.worker()._run_one(self.config.pluggy_connections[0],respect_schedule=True)['state'],'FAILED')
        with self.assertRaises(SyncError) as error:self.worker()._run_one(self.config.pluggy_connections[0],respect_schedule=True)
        self.assertEqual(error.exception.code,'AUTO_SYNC_BACKOFF')
        self.assertTrue(1 <= error.exception.retry_after <= 300)
        self.providers.banks['itau'].mode='ok'
        self.assertEqual(sync_full(self.service,'itau',actor='UI:local')['state'],'SUCCEEDED')
    def test_interrupted_run_can_resume_without_cooldown(self):
        calls=0
        from finance_v2.pluggy_client import PluggyError
        def check():
            nonlocal calls
            calls+=1
            if calls==3:raise PluggyError('AUTO_SYNC_CANCELLED')
        self.assertEqual(sync_full_automatic(self.service,'itau',check=check)['state'],'INTERRUPTED')
        self.assertEqual(self.worker()._run_one(self.config.pluggy_connections[0],respect_schedule=True)['state'],'SUCCEEDED')
    def test_schedule_becomes_due_without_changing_product_timeout(self):
        self.worker()._run_one(self.config.pluggy_connections[0],respect_schedule=True)
        with closing(connect(self.path)) as c:
            finished=c.execute('SELECT finished_at FROM of_sync_runs').fetchone()[0]
        future=datetime.fromisoformat(finished.replace('Z','+00:00'))+timedelta(seconds=3601)
        service=OpenFinanceService(self.config,clock=FixedClock(future,'UTC'),client_factory=self.providers.factory)
        self.assertEqual(sync_full_automatic(service,'itau',check=lambda:None,minimum_interval=3600)['state'],'SUCCEEDED')
    def test_binding_guard_precedes_schedule_optimization(self):
        self.worker()._run_one(self.config.pluggy_connections[0],respect_schedule=True)
        altered=replace(self.config,pluggy_connections=(replace(self.config.pluggy_connections[0],item_id='synthetic-other'),))
        with self.assertRaisesRegex(SyncError,'CONNECTION_BINDING_CHANGED'):
            CoverageWorkers(altered,send=self.providers.send)._run_one(altered.pluggy_connections[0],respect_schedule=True)
    def test_expired_item_preserves_previously_ingested_products(self):
        self.automatic('itau');before=self.counts()
        self.providers.banks['itau'].overrides['/items/item-test']=(200,{'id':'item-test','status':'UPDATED','consentExpiresAt':'2000-01-01T00:00:00Z'})
        result=self.automatic('itau')
        self.assertEqual((result['state'],result['error_code']),('FAILED','CONSENT_EXPIRED'))
        with closing(connect(self.path)) as c:
            self.assertEqual(c.execute("SELECT count(*) FROM of_resource_records WHERE connection_id='itau' AND resource='accounts' AND state='PRESENT'").fetchone()[0],2)
        self.assertEqual(self.counts()[:3],before[:3])
        self.assertEqual(self.automatic('santander')['state'],'SUCCEEDED')
    def test_revoked_consents_are_not_turned_into_empty_snapshots(self):
        self.automatic('itau')
        self.providers.banks['itau'].overrides['/consents?itemId=item-test']=(200,STOCK.collection([
            {'id':'consent-test','itemId':'item-test','revokedAt':'2000-01-01T00:00:00Z','expiresAt':None}]))
        result=self.automatic('itau')
        self.assertEqual((result['state'],result['error_code']),('FAILED','CONSENT_NOT_ACTIVE'))
        with closing(connect(self.path)) as c:
            self.assertEqual(c.execute("SELECT count(*) FROM of_resource_records WHERE connection_id='itau' AND resource='accounts' AND state='PRESENT'").fetchone()[0],2)
    def test_item_login_user_action_and_unknown_states_are_auditable(self):
        for status,code in (('LOGIN_ERROR','ITEM_REAUTH_REQUIRED'),('WAITING_USER_INPUT','ITEM_USER_ACTION_REQUIRED'),
                ('UPDATING','ITEM_UPDATING'),('UNRECOGNIZED','ITEM_STATUS_UNKNOWN')):
            with self.subTest(status=status):
                self.providers.banks['itau'].overrides['/items/item-test']=(200,{'id':'item-test','status':status})
                result=self.automatic('itau')
                self.assertEqual((result['state'],result['error_code']),('FAILED',code))
        self.assertEqual(self.automatic('santander')['state'],'SUCCEEDED')
    def test_optional_consent_unavailable_does_not_invent_denial_for_other_products(self):
        self.providers.banks['itau'].overrides['/consents?itemId=item-test']=(403,None)
        self.assertEqual(self.automatic('itau')['state'],'SUCCEEDED')
        with closing(connect(self.path)) as c:
            self.assertEqual(c.execute("SELECT state FROM of_resource_coverage WHERE resource='consents'").fetchone()[0],'NOT_AUTHORIZED')
    def test_historical_invalid_and_valid_consents_select_current_authorization(self):
        self.providers.banks['itau'].overrides['/consents?itemId=item-test']=(200,STOCK.collection([
            {'id':'old','itemId':'item-test','expiresAt':'2000-01-01T00:00:00Z'},
            {'id':'current','itemId':'item-test','expiresAt':None,'revokedAt':None}]))
        self.assertEqual(self.automatic('itau')['state'],'SUCCEEDED')
