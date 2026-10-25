"""Full SQLite, lease, API and ingestion tests against synthetic databases only."""
from contextlib import closing
from dataclasses import replace
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from unittest.mock import patch
from wsgiref.simple_server import make_server, WSGIRequestHandler

from support import ROOT, FIXTURES, CANDIDATE, CLOCK, STOCK, settings, seed_official, fingerprint, Providers
from finance_v2.api import Application
from finance_v2.db import connect
from finance_v2.domain.clock import FixedClock
from finance_v2.ha_pluggy_options import registry_from_options
from finance_v2.pluggy_config import connections_from_json
from finance_v2.migrations import migrate, require_current_schema, migration_status
from finance_v2.open_finance import OpenFinanceService, SyncError
from finance_v2.open_finance_coverage import sync_full, sync_full_automatic
from finance_v2.open_finance_auto import CoverageWorkers
from finance_v2.http_runtime import ConcurrentWSGIServer
from finance_v2.pluggy_client import PluggyError

EVIDENCE = []
def wait_for(predicate, seconds=5):
    deadline = time.monotonic()+seconds
    while time.monotonic() < deadline:
        if predicate(): return
        time.sleep(.02)
    raise AssertionError('SYNTHETIC_WAIT_LIMIT')

class DatabaseCase(unittest.TestCase):
    def setUp(self):
        self.directory = Path(tempfile.mkdtemp(prefix='new-synthetic-',dir=FIXTURES))
        self.path = self.directory / 'fixture.sqlite3'
        self.assertFalse(self.path.exists())
        self.assertEqual(migrate(self.path), list(range(1,11)))
        self.config = settings(self.path)
        self.entities = seed_official(self.config)
        self.before = fingerprint(self.path)
        self.providers = Providers(self.config)
        self.service = OpenFinanceService(self.config, client_factory=self.providers.factory)
    def tearDown(self):
        after = fingerprint(self.path)
        self.assertEqual(after, self.before, 'OFFICIAL_ROWS_OR_SCHEMA_CHANGED')
        with closing(connect(self.path)) as c:
            self.assertEqual(c.execute('PRAGMA integrity_check').fetchall()[0][0], 'ok')
            self.assertEqual(c.execute('PRAGMA foreign_key_check').fetchall(), [])
            self.assertEqual(c.execute('PRAGMA user_version').fetchone()[0], 10)
            self.assertTrue(migration_status(c)['up_to_date'])
            active = c.execute("SELECT count(*) FROM of_connections WHERE lease_token IS NOT NULL").fetchone()[0]
            counts = {name:c.execute('SELECT count(*) FROM '+name).fetchone()[0] for name in
                ('of_accounts','of_transactions','of_transaction_revisions','of_resource_records','of_resource_revisions','of_sync_runs')}
        EVIDENCE.append({'test':self.id(),'database':self.path.relative_to(FIXTURES).as_posix(),
            'integrity':'ok','fk_violations':0,'schema':10,'official_fingerprints':after,
            'official_preserved':True,'active_leases_after_test':active,'staging_counts':counts})
    def automatic(self, bank):
        return sync_full_automatic(self.service, bank, check=lambda:None)
    def counts(self):
        with closing(connect(self.path)) as c:
            return [c.execute('SELECT count(*) FROM '+table).fetchone()[0] for table in
                ('of_accounts','of_transactions','of_transaction_revisions','of_resource_records','of_resource_revisions')]

class SQLiteTests(DatabaseCase):
    def test_schema10_migration_history_and_reapplication(self):
        require_current_schema(self.path)
        self.assertEqual(migrate(self.path), [])
        with closing(connect(self.path)) as c:
            self.assertEqual([r[0] for r in c.execute('SELECT version FROM _finance_v2_schema_migrations ORDER BY version')], list(range(1,11)))
            self.assertGreater(sum(v['rows'] for v in self.before.values() if 'rows' in v), 10)

    def test_repeated_automatic_ingestion_no_duplicates_or_promotion(self):
        for bank in ('itau','santander'):
            self.assertEqual(self.automatic(bank)['state'],'SUCCEEDED')
        before = self.counts()
        for _ in range(2):
            for bank in ('itau','santander'):
                self.assertEqual(self.automatic(bank)['state'],'SUCCEEDED')
        self.assertEqual(self.counts(), before)
        with closing(connect(self.path)) as c:
            self.assertEqual(c.execute('SELECT count(*) FROM of_transactions').fetchone()[0], 4)
            self.assertEqual(c.execute('SELECT count(DISTINCT connection_id) FROM of_accounts').fetchone()[0], 2)
            self.assertEqual({r[0] for r in c.execute('SELECT actor FROM of_sync_runs')}, {'AUTO:coverage'})
            self.assertEqual(c.execute('SELECT count(*) FROM of_sync_runs').fetchone()[0], 6)

    def test_same_external_ids_are_scoped_by_institution(self):
        self.automatic('itau'); self.automatic('santander')
        with closing(connect(self.path)) as c:
            self.assertEqual([tuple(r) for r in c.execute('SELECT connection_id,count(*) FROM of_transactions GROUP BY connection_id ORDER BY connection_id')], [('itau',2),('santander',2)])
            self.assertEqual(c.execute("SELECT count(*) FROM of_resource_records WHERE resource='investments' AND external_id='investment-test'").fetchone()[0], 2)

    def test_each_bank_auth_failure_leaves_peer_successful(self):
        for failed, peer in (('itau','santander'),('santander','itau')):
            self.providers.banks[failed].mode = 'auth-failed'
            self.providers.banks[peer].mode = 'ok'
            run = self.automatic(failed)
            self.assertEqual((run['state'],run['error_code']), ('FAILED','AUTH_FAILED'))
            self.assertEqual(self.automatic(peer)['state'],'SUCCEEDED')

    def test_timeout_is_recorded_and_retry_is_idempotent(self):
        self.providers.banks['itau'].mode = 'timeout'
        run = self.automatic('itau')
        self.assertEqual((run['state'],run['error_code']),('FAILED','NETWORK_FAILURE'))
        self.assertEqual(self.automatic('santander')['state'],'SUCCEEDED')
        self.providers.banks['itau'].mode = 'ok'
        self.assertEqual(self.automatic('itau')['state'],'SUCCEEDED')
        previous = self.counts()
        self.assertEqual(self.automatic('itau')['state'],'SUCCEEDED')
        self.assertEqual(self.counts(),previous)

    def test_partial_collection_fails_without_false_absence_or_peer_loss(self):
        self.automatic('itau'); self.automatic('santander')
        provider = self.providers.banks['itau']
        row = {'id':'investment-test','itemId':'item-test'}
        provider.overrides['/investments?itemId=item-test&page=1&pageSize=500'] = (200,{'results':[row],'page':1,'total':2,'totalPages':2})
        provider.overrides['/investments?itemId=item-test&page=2&pageSize=500'] = (200,{'results':[],'page':2,'total':2,'totalPages':2})
        run = self.automatic('itau')
        self.assertEqual(run['state'],'FAILED')
        with closing(connect(self.path)) as c:
            self.assertEqual(c.execute("SELECT state FROM of_resource_coverage WHERE connection_id='itau' AND resource='investments'").fetchone()[0], 'FAILED')
            self.assertEqual(c.execute("SELECT state FROM of_resource_records WHERE connection_id='itau' AND resource='investments'").fetchone()[0], 'PRESENT')
            self.assertEqual(c.execute("SELECT sync_state FROM of_connections WHERE id='santander'").fetchone()[0], 'SUCCEEDED')

    def test_malformed_page_rolls_back_both_staging_projections(self):
        self.providers.banks['itau'].overrides['/accounts?itemId=item-test'] = (200, STOCK.collection([
            {'id':'valid','itemId':'item-test','type':'BANK','balance':10},
            {'id':'bad','itemId':'item-test','type':'BANK','balance':'INVALID'}]))
        self.assertEqual(self.automatic('itau')['state'],'FAILED')
        with closing(connect(self.path)) as c:
            self.assertEqual(c.execute('SELECT count(*) FROM of_accounts').fetchone()[0],0)
            self.assertEqual(c.execute("SELECT count(*) FROM of_resource_records WHERE resource='accounts'").fetchone()[0],0)
        self.assertEqual(self.automatic('santander')['state'],'SUCCEEDED')

    def test_cancellation_inside_page_rolls_back_and_releases_lease(self):
        calls = 0
        def check():
            nonlocal calls
            calls += 1
            if calls == 3:
                raise PluggyError('AUTO_SYNC_CANCELLED')
        run = sync_full_automatic(self.service,'itau',check=check)
        self.assertEqual((run['state'],run['error_code']),('INTERRUPTED','AUTO_SYNC_CANCELLED'))
        with closing(connect(self.path)) as c:
            self.assertEqual(c.execute('SELECT count(*) FROM of_resource_records').fetchone()[0],0)
            self.assertIsNone(c.execute("SELECT lease_token FROM of_connections WHERE id='itau'").fetchone()[0])
        self.assertEqual(self.automatic('itau')['state'],'SUCCEEDED')

    def test_concurrent_manual_auto_same_bank_rejected_peer_continues(self):
        provider = self.providers.banks['itau']; provider.mode = 'hold'
        outcomes = []
        worker = threading.Thread(target=lambda:outcomes.append(self.automatic('itau')))
        worker.start()
        try:
            self.assertTrue(provider.entered.wait(5))
            with self.assertRaisesRegex(SyncError,'SYNC_BUSY'):
                sync_full(self.service,'itau',actor='UI:local')
            self.assertEqual(self.automatic('santander')['state'],'SUCCEEDED')
        finally:
            provider.release.set(); worker.join(5)
        self.assertFalse(worker.is_alive())
        self.assertEqual(len(outcomes),1)
        self.assertEqual(outcomes[0]['state'],'SUCCEEDED')
        self.assertEqual(self.counts()[1],4)

    def test_binding_change_rejected_without_replacing_existing_connection(self):
        self.automatic('itau')
        altered = replace(self.config,pluggy_connections=(replace(self.config.pluggy_connections[0],item_id='synthetic-different-item'),))
        with self.assertRaisesRegex(SyncError,'CONNECTION_BINDING_CHANGED'):
            sync_full_automatic(OpenFinanceService(altered),'itau',check=lambda:None)
        self.assertEqual(self.automatic('santander')['state'],'SUCCEEDED')

    def test_existing_live_lease_not_stolen(self):
        with closing(connect(self.path)) as c:
            run_id, token = self.service._claim(c,self.config.pluggy_connections[0],'AUTO:coverage',None,None)
            with self.assertRaisesRegex(SyncError,'SYNC_BUSY'):
                self.automatic('itau')
            self.service._finish(c,self.config.pluggy_connections[0],run_id,token,'AUTO_SYNC_CANCELLED')

    def _recover_after_process_crash(self, kind):
        env = {key:os.environ[key] for key in ('SystemRoot','WINDIR','PATH','VALIDATION_FIXTURE_ROOT') if key in os.environ}
        env['PYTHONDONTWRITEBYTECODE']='1'
        child = subprocess.run([sys.executable,'-B',str(ROOT/'crash_child.py'),str(self.path),kind],
            env=env,capture_output=True,text=True,timeout=45)
        self.assertEqual(child.returncode,71,child.stderr)
        marker = json.loads(child.stdout.strip())
        self.assertEqual(marker['active_write_confirmed'],kind=='uncommitted-page')
        with closing(connect(self.path)) as c:
            old = dict(c.execute("SELECT * FROM of_connections WHERE id='itau'").fetchone())
            old_run = dict(c.execute("SELECT * FROM of_sync_runs WHERE connection_id='itau'").fetchone())
            self.assertEqual(old_run['state'],'RUNNING')
            count = c.execute('SELECT count(*) FROM of_resource_records').fetchone()[0]
            self.assertEqual(count == 0,kind=='uncommitted-page')
            with self.assertRaisesRegex(SyncError,'SYNC_BUSY'): self.automatic('itau')
        clock = FixedClock(datetime.fromtimestamp(old['lease_until']+1,timezone.utc),'UTC')
        recovered = OpenFinanceService(self.config,clock=clock,client_factory=self.providers.factory)
        result = sync_full_automatic(recovered,'itau',check=lambda:None)
        self.assertEqual(result['state'],'SUCCEEDED')
        counts = self.counts()
        self.assertEqual(sync_full_automatic(recovered,'itau',check=lambda:None)['state'],'SUCCEEDED')
        self.assertEqual(self.counts(),counts)
        with closing(connect(self.path)) as c:
            row = c.execute('SELECT state,error_code FROM of_sync_runs WHERE id=?',(old_run['id'],)).fetchone()
            self.assertEqual(tuple(row),('INTERRUPTED','LEASE_EXPIRED'))
            with self.assertRaisesRegex(SyncError,'LEASE_LOST'):
                recovered._touch(c,'itau',old_run['id'],old['lease_token'])
        EVIDENCE.append({'test':self.id(),'interrupted_process_exit':71,'phase':kind,
            'active_write_confirmed':marker['active_write_confirmed'],
            'live_lease_rejected':True,'expired_lease_recovered':True,'stale_worker_fenced':True})

    def test_restart_after_abrupt_interruption_of_uncommitted_page(self):
        self._recover_after_process_crash('uncommitted-page')

    def test_restart_after_abrupt_interruption_with_committed_pages(self):
        self._recover_after_process_crash('committed-pages')

    def test_actual_workers_failure_isolated_and_all_threads_stop(self):
        providers = Providers(self.config,{'itau':'unavailable'})
        workers = CoverageWorkers(self.config,send=providers.send)
        try:
            workers.start()
            def completed():
                with closing(connect(self.path)) as c:
                    return c.execute("SELECT count(*) FROM of_sync_runs WHERE state IN ('FAILED','SUCCEEDED')").fetchone()[0] == 2
            wait_for(completed)
        finally:
            self.assertTrue(workers.stop())
        self.assertFalse(any(t.is_alive() for t in workers.threads))
        with closing(connect(self.path)) as c:
            self.assertEqual({r[0]:r[1] for r in c.execute('SELECT connection_id,state FROM of_sync_runs')}, {'itau':'FAILED','santander':'SUCCEEDED'})

    def test_auto_disabled_no_ingestion(self):
        config = settings(self.path,False)
        workers = CoverageWorkers(config,send=lambda *args:self.fail('UNAUTHORIZED_PROVIDER_CALL'))
        workers.start()
        self.assertTrue(workers.stop())
        self.assertEqual(workers.threads,[])
        self.assertEqual(self.counts(),[0,0,0,0,0])

    def test_missing_bank_credentials_do_not_prevent_valid_peer(self):
        options = {'open_finance_enabled':True,'open_finance_auto_sync_enabled':True}
        for connection in self.config.pluggy_connections:
            prefix = 'pluggy_'+connection.id+'_'
            options.update({prefix+'enabled':True,prefix+'client_id':connection.client_id,
                prefix+'client_secret':connection.client_secret,prefix+'item_id':connection.item_id})
        options['pluggy_itau_client_secret']=''
        registry = registry_from_options(options)
        config = replace(self.config,pluggy_connections=connections_from_json(registry))
        self.assertEqual([c.id for c in config.pluggy_connections],['santander'])
        service = OpenFinanceService(config,client_factory=self.providers.factory)
        self.assertEqual(sync_full_automatic(service,'santander',check=lambda:None)['state'],'SUCCEEDED')

class HttpTests(DatabaseCase):
    def test_real_api_available_while_bank_waits_and_peer_finishes(self):
        providers = Providers(self.config,{'itau':'hold'})
        workers = CoverageWorkers(self.config,send=providers.send)
        class Quiet(WSGIRequestHandler):
            def log_message(self,*args): pass
        server = make_server('127.0.0.1',0,Application(self.config,CLOCK),server_class=ConcurrentWSGIServer,handler_class=Quiet)
        thread = threading.Thread(target=server.serve_forever,kwargs={'poll_interval':.02})
        def get(path):
            request = Request('http://127.0.0.1:'+str(server.server_port)+path,
                headers={'Authorization':'Bearer synthetic-owner-only-token'})
            with urlopen(request,timeout=2) as response:
                self.assertEqual(response.status,200)
                return json.loads(response.read())
        try:
            thread.start(); workers.start()
            self.assertTrue(providers.banks['itau'].entered.wait(5))
            health = get('/api/v2/health')
            self.assertTrue(health)
            for path in ('/api/v2/expenses','/api/v2/revenues','/api/v2/cards','/api/v2/open-finance/coverage'):
                get(path)
            def peer_done():
                with closing(connect(self.path)) as c:
                    row = c.execute("SELECT sync_state FROM of_connections WHERE id='santander'").fetchone()
                    return row and row[0] == 'SUCCEEDED'
            wait_for(peer_done)
        finally:
            providers.banks['itau'].release.set()
            self.assertTrue(workers.stop())
            server.shutdown(); thread.join(3); server.server_close()
        self.assertFalse(thread.is_alive())

    def test_real_api_available_with_both_providers_unavailable(self):
        providers = Providers(self.config,{'itau':'unavailable','santander':'timeout'})
        workers = CoverageWorkers(self.config,send=providers.send)
        try:
            workers.start()
            def done():
                with closing(connect(self.path)) as c:
                    return c.execute("SELECT count(*) FROM of_sync_runs WHERE state='FAILED'").fetchone()[0] == 2
            wait_for(done)
            app = Application(self.config,CLOCK)
            from support import request
            for path in ('health','expenses','revenues','cards','open-finance/connections','open-finance/coverage'):
                status, _ = request(app,'/api/v2/'+path)
                self.assertEqual(status,200)
        finally:
            self.assertTrue(workers.stop())
