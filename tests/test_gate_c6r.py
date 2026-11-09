"""C6-R: real synthetic staging transactions, FIFO admission and parallel services."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from dataclasses import replace
from pathlib import Path
import sqlite3
import sys
import threading
import time
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parent/'auto_sync'))
from test_sqlite_validation import DatabaseCase
from support import settings,Providers
from finance_v2.db import connect,immediate_transaction
from finance_v2.migrations import migrate
from finance_v2.open_finance import OpenFinanceService,SyncError
from finance_v2.open_finance_coverage import sync_domain
from finance_v2.pluggy_client import PluggyError


class ConcurrencyTests(DatabaseCase):
    def parallel(self, config):
        providers=Providers(config);barrier=threading.Barrier(len(config.pluggy_connections))
        def collect(bank):
            service=OpenFinanceService(config,client_factory=providers.factory)
            barrier.wait(3)
            return sync_domain(service,bank,actor='UI:local')
        with ThreadPoolExecutor(max_workers=len(config.pluggy_connections)) as pool:
            tasks=[pool.submit(collect,c.id) for c in config.pluggy_connections]
            deadline=time.monotonic()+8
            result=[f.result(max(.001,deadline-time.monotonic())) for f in tasks]
        self.assertTrue(all(r['state']=='SUCCEEDED' for r in result),[r['error_code'] for r in result])
        return providers

    def test_two_independent_service_instances_collect_distinct_items(self):
        self.parallel(self.config)
        with closing(connect(self.path)) as c:
            self.assertEqual(c.execute("SELECT count(*) FROM of_connections WHERE sync_state='SUCCEEDED' AND lease_token IS NULL").fetchone()[0],2)

    def test_four_concurrent_items_and_idempotent_reimport(self):
        extra=tuple(replace(self.config.pluggy_connections[0],id=n,institution='Synthetic '+n,client_id='synthetic-client-'+n,client_secret='synthetic-secret-'+n,item_id='synthetic-item-'+n) for n in ('bank3','bank4'))
        config=replace(self.config,pluggy_connections=self.config.pluggy_connections+extra)
        self.parallel(config)
        def rows():
            with closing(connect(self.path)) as c:
                return {n:[tuple(r) for r in c.execute('SELECT connection_id,resource,parent_id,external_id,payload_hash,state FROM '+n+' ORDER BY connection_id,resource,parent_id,external_id')] for n in ('of_resource_records','of_resource_revisions')}
        before=rows();self.parallel(config);self.assertEqual(rows(),before)

    def test_same_item_duplicate_is_rejected_while_owner_is_collecting(self):
        providers=Providers(self.config,{'itau':'hold'})
        service=OpenFinanceService(self.config,client_factory=providers.factory)
        with ThreadPoolExecutor(max_workers=1) as pool:
            task=pool.submit(sync_domain,service,'itau',actor='UI:local')
            try:
                self.assertTrue(providers.banks['itau'].entered.wait(5))
                with self.assertRaises(SyncError) as exc:
                    sync_domain(OpenFinanceService(self.config,client_factory=providers.factory),'itau',actor='UI:local')
                self.assertEqual(exc.exception.code,'SYNC_BUSY')
            finally:providers.banks['itau'].release.set()
            self.assertEqual(task.result(5)['state'],'SUCCEEDED')

    def test_queued_peer_is_not_overtaken_by_reacquiring_writer(self):
        waiting=threading.Event();order=[]
        def peer():
            with closing(self.service._db()) as c:
                with self.service._write(c,check=waiting.set):
                    c.execute('SELECT 1');order.append('peer')
        with ThreadPoolExecutor(max_workers=1) as pool,closing(self.service._db()) as c:
            with self.service._write(c):
                task=pool.submit(peer);self.assertTrue(waiting.wait(1))
            with self.service._write(c):order.append('reacquire')
            task.result(1)
        self.assertEqual(order,['peer','reacquire'])

    def test_queued_cancellation_removes_waiter_and_preserves_busy_budget(self):
        waiting=threading.Event();cancel=threading.Event()
        def check():
            waiting.set()
            if cancel.is_set():raise PluggyError('AUTO_SYNC_CANCELLED')
        def peer():
            with closing(self.service._db()) as c:
                try:
                    with self.service._write(c,check=check):self.fail('CANCELLED_WRITER_ADMITTED')
                finally:self.assertEqual(c.execute('PRAGMA busy_timeout').fetchone()[0],self.config.busy_timeout_ms)
        with ThreadPoolExecutor(max_workers=1) as pool,closing(self.service._db()) as c:
            with self.service._write(c):
                task=pool.submit(peer);self.assertTrue(waiting.wait(1));cancel.set()
                with self.assertRaises(PluggyError) as exc:task.result(.5)
                self.assertEqual(exc.exception.code,'AUTO_SYNC_CANCELLED')
            with self.service._write(c):c.execute('SELECT 1')

    def test_rollback_releases_writer_without_committing_intermediate_state(self):
        config=self.config.pluggy_connections[0]
        with closing(self.service._db()) as c:
            run,token=self.service._claim(c,config,'UI:local',None,None)
            with self.assertRaises(RuntimeError):
                with self.service._write(c):
                    c.execute("UPDATE of_connections SET enabled=0 WHERE id='itau'")
                    raise RuntimeError('synthetic interrupted persistence')
            self.assertEqual(c.execute("SELECT enabled FROM of_connections WHERE id='itau'").fetchone()[0],1)
            self.service._finish(c,config,run,token,'SYNTHETIC_FAILURE')
        self.parallel(self.config)

    def test_external_sqlite_writer_still_fails_within_existing_budget(self):
        def attempt():
            with closing(self.service._db()) as c:
                before=c.execute('PRAGMA busy_timeout').fetchone()[0]
                start=time.monotonic()
                with self.assertRaises(sqlite3.OperationalError):
                    with self.service._write(c):self.fail('EXTERNAL_WRITE_LOCK_BYPASSED')
                self.assertLess(time.monotonic()-start,1)
                self.assertEqual(c.execute('PRAGMA busy_timeout').fetchone()[0],before)
        with closing(connect(self.path)) as c,ThreadPoolExecutor(max_workers=1) as pool:
            with immediate_transaction(c):pool.submit(attempt).result(2)

    def test_other_database_does_not_share_the_write_gate(self):
        path=self.directory/'independent.sqlite3';migrate(path)
        service=OpenFinanceService(settings(path))
        def independent():
            with closing(service._db()) as c:
                with service._write(c):c.execute('SELECT 1')
        with closing(self.service._db()) as c,ThreadPoolExecutor(max_workers=1) as pool:
            with self.service._write(c):pool.submit(independent).result(1)


if __name__=='__main__':unittest.main(verbosity=2)
