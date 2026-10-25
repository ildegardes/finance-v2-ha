"""H06-R: cancellation boundaries, finite I/O slots and fenced persistence."""
from contextlib import closing
from dataclasses import replace
from datetime import datetime,timezone
import json
import threading
import time
import unittest
from unittest.mock import patch

from support import CLOCK, Providers
from test_sqlite_validation import DatabaseCase, wait_for
from finance_v2.db import connect
from finance_v2.domain.clock import FixedClock
from finance_v2.open_finance import OpenFinanceService, SyncError
from finance_v2.open_finance_auto import CoverageWorkers
from finance_v2.open_finance_coverage import sync_full_automatic, _batch

class CancellationTests(DatabaseCase):
    def coordinator(self,bank):
        config=replace(self.config,pluggy_connections=tuple(c for c in self.config.pluggy_connections if c.id==bank))
        return CoverageWorkers(config,send=self.providers.send)

    def run_row(self,bank):
        with closing(connect(self.path)) as c:
            return dict(c.execute('SELECT * FROM of_sync_runs WHERE connection_id=? ORDER BY rowid DESC LIMIT 1',(bank,)).fetchone())

    def lease(self,bank):
        with closing(connect(self.path)) as c:
            return dict(c.execute('SELECT * FROM of_connections WHERE id=?',(bank,)).fetchone())

    def staging(self):
        with closing(connect(self.path)) as c:
            names=[r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'of_%' ORDER BY name")]
            return {name:sorted(json.dumps(tuple(r),separators=(',',':')) for r in c.execute('SELECT * FROM '+name)) for name in names}

    def blocked(self,bank,*,page=False,cooperative=False):
        worker=self.coordinator(bank)
        provider=self.providers.banks[bank]
        original=provider.send
        entered,release=threading.Event(),threading.Event()
        if page:
            row={'id':'transaction-test','accountId':'account-BANK','date':'2026-10-22','amount':10,
                'currencyCode':'BRL','type':'DEBIT','status':'POSTED','description':'Compra sintética','categoryId':'1','category':'Food'}
            provider.overrides['/v2/transactions?accountId=account-BANK']=(200,{'results':[row],'next':'?accountId=account-BANK&after=next'})
            provider.overrides['/v2/transactions?accountId=account-BANK&after=next']=(200,{'results':[{**row,'id':'late-never-persist'}],'next':None})
        def send(method,path,headers,body,timeout):
            if (page and 'after=next' in path) or (not page and path.startswith('/loans')):
                entered.set()
                if cooperative:
                    assert worker.stop_event.wait(10),'COOPERATIVE_CONTROL_LIMIT'
                else:
                    assert release.wait(10),'NONCOOPERATIVE_CONTROL_LIMIT'
            return original(method,path,headers,body,timeout)
        provider.send=send
        def cleanup():
            release.set();worker.stop()
            wait_for(lambda:not worker._inflight,seconds=3)
        self.addCleanup(cleanup)
        worker.start()
        self.assertTrue(entered.wait(5))
        return worker,release,provider,original

    def assert_interrupted(self,bank):
        run=self.run_row(bank)
        self.assertEqual((run['state'],run['error_code']),('INTERRUPTED','AUTO_SYNC_CANCELLED'))
        self.assertIsNone(self.lease(bank)['lease_token'])
        self.assertIsNotNone(run['finished_at'])
        return run

    def test_cooperative_transport_cancellation(self):
        worker,release,_,_=self.blocked('itau',cooperative=True)
        self.assertTrue(worker.stop())
        self.assert_interrupted('itau')
        self.assertFalse(any(t.is_alive() for t in worker.threads))
        wait_for(lambda:not worker._inflight)

    def test_noncooperative_io_detached_not_reported_as_provider_cancelled(self):
        worker,release,_,_=self.blocked('itau')
        started=time.monotonic()
        with self.assertLogs('finance_v2.open_finance_auto',level='WARNING') as logs:
            self.assertTrue(worker.stop())
        self.assertLess(time.monotonic()-started,1.5)
        self.assertIn('IO_DETACHED',' '.join(logs.output))
        self.assertTrue(worker._inflight)
        self.assert_interrupted('itau')
        self.assertFalse(any(t.is_alive() for t in worker.threads))
        before=self.staging()
        release.set();wait_for(lambda:not worker._inflight)
        self.assertEqual(self.staging(),before)

    def _bank_isolation(self,bank,peer):
        worker,release,_,_=self.blocked(bank)
        self.assertEqual(self.automatic(peer)['state'],'SUCCEEDED')
        self.assertTrue(worker.stop())
        self.assert_interrupted(bank)
        self.assertEqual(self.automatic(peer)['state'],'SUCCEEDED')
        before=self.staging()
        release.set();wait_for(lambda:not worker._inflight)
        self.assertEqual(self.staging(),before)

    def test_itau_interrupted_santander_operational(self):self._bank_isolation('itau','santander')
    def test_santander_interrupted_itau_operational(self):self._bank_isolation('santander','itau')

    def _pagination(self,bank):
        worker,release,provider,original=self.blocked(bank,page=True)
        with closing(connect(self.path)) as c:
            self.assertEqual(c.execute('SELECT count(*) FROM of_transactions WHERE connection_id=?',(bank,)).fetchone()[0],1)
        self.assertTrue(worker.stop());self.assert_interrupted(bank)
        release.set();wait_for(lambda:not worker._inflight)
        provider.send=original;provider.overrides.clear()
        self.assertEqual(self.automatic(bank)['state'],'SUCCEEDED')
        before=self.counts()
        self.assertEqual(self.automatic(bank)['state'],'SUCCEEDED')
        self.assertEqual(self.counts(),before)
        with closing(connect(self.path)) as c:
            self.assertEqual(c.execute("SELECT count(*) FROM of_transactions WHERE external_id='late-never-persist'").fetchone()[0],0)

    def test_cancellation_during_pagination_itau(self):self._pagination('itau')
    def test_cancellation_during_pagination_santander(self):self._pagination('santander')

    def test_cancellation_inside_persistence_rolls_back_entire_page(self):
        worker=self.coordinator('itau')
        entered,release=threading.Event(),threading.Event()
        def persist(*args,**kwargs):
            _batch(*args,**kwargs)
            if args[-1]['resource']=='accounts':
                entered.set();self.assertTrue(release.wait(5))
        result=[]
        with patch('finance_v2.open_finance_coverage._batch',side_effect=persist):
            worker.start()
            try:
                self.assertTrue(entered.wait(5))
                stopper=threading.Thread(target=lambda:result.append(worker.stop()))
                stopper.start()
                self.assertTrue(worker.stop_event.wait(2))
                release.set();stopper.join(2)
                self.assertFalse(stopper.is_alive())
                self.assertEqual(result,[True])
            finally:
                release.set();worker.stop()
        self.assert_interrupted('itau')
        with closing(connect(self.path)) as c:
            self.assertEqual(c.execute("SELECT count(*) FROM of_accounts WHERE connection_id='itau'").fetchone()[0],0)
            self.assertEqual(c.execute("SELECT count(*) FROM of_resource_records WHERE connection_id='itau' AND resource='accounts'").fetchone()[0],0)

    def test_timeout_error_releases_slot_and_peer_can_collect(self):
        worker=self.coordinator('itau');self.providers.banks['itau'].mode='timeout'
        result=worker._run_one(worker.settings.pluggy_connections[0])
        self.assertEqual((result['state'],result['error_code']),('FAILED','NETWORK_FAILURE'))
        self.assertFalse(worker._inflight)
        self.assertEqual(self.automatic('santander')['state'],'SUCCEEDED')

    def test_deadline_bounds_wait_and_prevents_unbounded_retry_threads(self):
        worker=self.coordinator('itau')
        worker.RUN_BUDGET_SECONDS=.75
        entered,release=threading.Event(),threading.Event()
        count=[]
        original=self.providers.send
        def blocked(method,path,headers,body,timeout):
            count.append(path);entered.set()
            assert release.wait(10),'TRANSPORT_CONTROL_LIMIT'
            return original(method,path,headers,body,timeout)
        worker.send=blocked
        try:
            result=worker._run_one(worker.settings.pluggy_connections[0])
            self.assertEqual((result['state'],result['error_code']),('FAILED','AUTO_SYNC_DEADLINE'))
            for _ in range(3):
                result=worker._run_one(worker.settings.pluggy_connections[0])
                self.assertEqual((result['state'],result['error_code']),('FAILED','AUTO_SYNC_IO_BUSY'))
            self.assertEqual(len(count),1)
            self.assertEqual(len(worker._inflight),1)
        finally:
            release.set();wait_for(lambda:not worker._inflight)
            worker.stop()

    def test_old_worker_and_late_transport_cannot_write_over_new_owner(self):
        worker,release,_,_=self.blocked('itau')
        old=self.lease('itau');old_run=self.run_row('itau')
        self.assertTrue(worker.stop());self.assert_interrupted('itau')
        config=self.config.pluggy_connections[0]
        with closing(connect(self.path)) as c:
            new_run,new_token=self.service._claim(c,config,'AUTO:coverage',None,None)
            with self.assertRaisesRegex(SyncError,'LEASE_LOST'):
                self.service._touch(c,'itau',old_run['id'],old['lease_token'])
            with self.assertRaisesRegex(SyncError,'LEASE_LOST'):
                self.service._page(c,config,old_run['id'],old['lease_token'],'account-BANK',[])
            before=self.staging()
            release.set();wait_for(lambda:not worker._inflight)
            self.assertEqual(self.staging(),before)
            self.service._finish(c,config,old_run['id'],old['lease_token'],'AUTO_SYNC_CANCELLED',interrupted=True)
            self.assertEqual(self.lease('itau')['lease_token'],new_token)
            self.assertEqual(c.execute('SELECT state FROM of_sync_runs WHERE id=?',(new_run,)).fetchone()[0],'RUNNING')
            self.service._finish(c,config,new_run,new_token,'AUTO_SYNC_CANCELLED',interrupted=True)
        self.assertEqual(self.automatic('itau')['state'],'SUCCEEDED')
        before=self.counts();self.automatic('itau');self.assertEqual(self.counts(),before)

    def test_storage_refuses_cleanup_deferred_lease_is_expiring_and_recoverable(self):
        worker,release,_,_=self.blocked('itau')
        worker.settings=replace(worker.settings,busy_timeout_ms=100)
        # Service already owns the original fixture setting (300ms); both are
        # below the unchanged 1s worker shutdown budget in this test.
        blocker=connect(self.path)
        blocker.execute('BEGIN IMMEDIATE')
        try:
            with self.assertLogs('finance_v2.open_finance_auto',level='WARNING') as logs:
                self.assertTrue(worker.stop())
            self.assertIn('CANCELLATION_FINALIZATION_DEFERRED',' '.join(logs.output))
        finally:
            blocker.rollback();blocker.close()
        old=self.lease('itau');old_run=self.run_row('itau')
        self.assertEqual(old_run['state'],'RUNNING')
        self.assertGreater(old['lease_until'],0)
        with self.assertRaisesRegex(SyncError,'SYNC_BUSY'):self.automatic('itau')
        clock=FixedClock(datetime.fromtimestamp(old['lease_until']+1,timezone.utc),'UTC')
        successor=OpenFinanceService(self.config,clock=clock,client_factory=self.providers.factory)
        with closing(connect(self.path)) as c:
            new_run,new_token=successor._claim(c,self.config.pluggy_connections[0],'AUTO:coverage',None,None)
            self.assertEqual(tuple(c.execute('SELECT state,error_code FROM of_sync_runs WHERE id=?',(old_run['id'],)).fetchone()),('INTERRUPTED','LEASE_EXPIRED'))
            with self.assertRaisesRegex(SyncError,'LEASE_LOST'):successor._touch(c,'itau',old_run['id'],old['lease_token'])
            before=self.staging()
            release.set();wait_for(lambda:not worker._inflight)
            self.assertEqual(self.staging(),before)
            successor._finish(c,self.config.pluggy_connections[0],new_run,new_token,'AUTO_SYNC_CANCELLED',interrupted=True)

    def test_interrupt_cannot_be_recorded_without_reason(self):
        with closing(connect(self.path)) as c:
            run,token=self.service._claim(c,self.config.pluggy_connections[0],'AUTO:coverage',None,None)
            with self.assertRaisesRegex(ValueError,'INTERRUPTION_REASON_REQUIRED'):
                self.service._finish(c,self.config.pluggy_connections[0],run,token,interrupted=True)
            self.service._finish(c,self.config.pluggy_connections[0],run,token,'AUTO_SYNC_CANCELLED',interrupted=True)
