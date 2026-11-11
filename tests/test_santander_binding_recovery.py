"""Synthetic schema-11 recovery; no bank/network/production inputs."""
from contextlib import closing
from dataclasses import replace
from unittest.mock import patch
from pathlib import Path
import hashlib,hmac,io,json,os,secrets,sqlite3,threading,unittest
import test_full_coverage as base
from finance_v2.api import Application
from finance_v2.open_finance import OpenFinanceService,SyncError
from finance_v2.open_finance_recovery import SantanderBindingRecovery,CONFIRM,fingerprint
from finance_v2.pluggy_config import PluggyConnection

ITEM='abc00000-0000-4000-8000-000000000001'
STAMP='2026-11-10T00:00:00Z'
ACTOR=('UI','UI:local',None)

class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.fixture=base.CoverageTests();self.fixture.setUp();self.addCleanup(self.fixture.doCleanups)
        self.db=self.fixture.db
        self.cfg=PluggyConnection('santander','Santander','synthetic-current-client','synthetic-private-secret',ITEM,True,False,'meupluggy_personal')
        self.itau=replace(self.cfg,id='itau',institution='Ita\u00fa',client_id='synthetic-itau-client',item_id='def00000-0000-4000-8000-000000000002')
        self.settings=replace(self.fixture.settings,pluggy_connections=(self.itau,self.cfg),busy_timeout_ms=50,scheduler_token='synthetic-scheduler')
        self.app=Application(self.settings);self.r=self.app.santander_binding_recovery
        self.swapped=replace(self.cfg,client_id=self.cfg.item_id,item_id=self.cfg.client_id)
        with closing(base.connect(self.db)) as c:
            self.seed(c,self.swapped,26);self.seed(c,self.itau,1,'SUCCEEDED',None)
            c.execute("INSERT INTO accounts(name,active) VALUES('Synthetic manual',1)")
    def seed(self,c,config,n,state='FAILED',error='AUTH_FAILED'):
        c.execute('INSERT INTO of_connections(id,institution,enabled,binding_hash,sync_state,updated_at) VALUES(?,?,1,?,?,?)',(config.id,config.institution,OpenFinanceService._binding(config),state,STAMP))
        for i in range(n):
            run=hashlib.sha256((config.id+str(i)).encode()).hexdigest()[:32]
            c.execute('INSERT INTO of_sync_runs(id,connection_id,actor,started_at,finished_at,state,error_code) VALUES(?,?,?,?,?,?,?)',(run,config.id,'UI:local',STAMP,STAMP,state,error))
    def snapshot(self):
        with closing(base.connect(self.db)) as c:
            return {n:[tuple(r) for r in c.execute('SELECT * FROM "'+n+'" ORDER BY rowid')] for n, in c.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").fetchall()}
    def prepare(self,action='APPLY',operation=None):return self.r.prepare(ACTOR,action,True,operation)['confirmation']
    def execute(self,nonce,action='APPLY'):return self.r.execute(ACTOR,nonce,CONFIRM[action],True)
    def apply(self):return self.execute(self.prepare())
    def http(self,path='',method='GET',body=None,token='synthetic-owner-only',extra=None):
        raw=json.dumps(body).encode() if body is not None else b''
        env={'REQUEST_METHOD':method,'PATH_INFO':'/api/v2/open-finance/santander-binding-recovery'+path,'QUERY_STRING':'','CONTENT_LENGTH':str(len(raw)),'CONTENT_TYPE':'application/json','wsgi.input':io.BytesIO(raw),'wsgi.url_scheme':'http','HTTP_HOST':'127.0.0.1:8766'}
        if token:env['HTTP_AUTHORIZATION']='Bearer '+token
        if extra:env.update(extra)
        status=[];result=b''.join(self.app(env,lambda s,h:status.append(int(s.split()[0]))))
        return status[0],json.loads(result)
    def test_inverted_no_imports_apply_changes_only_one_field_and_preserves_history(self):
        before=self.snapshot();out=self.apply();after=self.snapshot()
        self.assertEqual(out['status'],'APPLIED');self.assertEqual(out['sqlite_rows_changed'],1)
        self.assertEqual(len(after['of_sync_runs']),27)
        index=next(i for i,row in enumerate(after['of_connections']) if row[0]=='santander')
        b=list(before['of_connections'][index]);a=list(after['of_connections'][index])
        columns=[r[1] for r in base.connect(self.db).execute('PRAGMA table_info(of_connections)')]
        self.assertEqual([k for k,x,y in zip(columns,a,b) if x!=y],['binding_hash'])
        after['of_connections']=before['of_connections'];self.assertEqual(after,before)
    def test_live_settings_used(self):self.assertIs(self.r.settings,self.app.settings)
    def test_current_binding_idempotent_no_receipt_or_sql_changes(self):
        with closing(base.connect(self.db)) as c:c.execute("UPDATE of_connections SET binding_hash=? WHERE id='santander'",(OpenFinanceService._binding(self.cfg),))
        before=self.snapshot();out=self.apply()
        self.assertEqual(out['status'],'ALREADY_CORRECT');self.assertEqual(self.snapshot(),before);self.assertFalse(self.r.audit_dir.exists())
    def test_unknown_binding_blocked(self):
        with closing(base.connect(self.db)) as c:c.execute("UPDATE of_connections SET binding_hash=? WHERE id='santander'",('a'*64,))
        with self.assertRaisesRegex(SyncError,'PRECHECK_BLOCKED'):self.prepare()
    def test_partial_account_blocks(self):
        with closing(base.connect(self.db)) as c:c.execute("INSERT INTO of_accounts(connection_id,external_id,name) VALUES('santander','synthetic-account','Synthetic')")
        self.assertIn('IMPORTED_RECORDS',self.r.inspect()['blockers'])
        with self.assertRaisesRegex(SyncError,'PRECHECK_BLOCKED'):self.prepare()
    def test_indirect_reference_blocks(self):
        with closing(base.connect(self.db)) as c:
            c.execute('PRAGMA foreign_keys=OFF')  # Deliberately invalid synthetic graph.
            run=c.execute("SELECT id FROM of_sync_runs WHERE connection_id='santander' LIMIT 1").fetchone()[0]
            c.execute("INSERT INTO of_resource_coverage(connection_id,resource,parent_id,run_id,state,observed_at) VALUES('itau','item','',?,'FAILED',?)",(run,STAMP))
            c.execute('PRAGMA foreign_keys=ON')
        self.assertIn('INDIRECT_OR_CROSS_REFERENCE',self.r.inspect()['blockers'])
        with self.assertRaisesRegex(SyncError,'PRECHECK_BLOCKED'):self.prepare()
    def test_running_run_blocks(self):
        with closing(base.connect(self.db)) as c:
            run=c.execute("SELECT id FROM of_sync_runs WHERE connection_id='santander' LIMIT 1").fetchone()[0]
            c.execute("UPDATE of_sync_runs SET state='RUNNING',finished_at=NULL WHERE id=?",(run,))
        with self.assertRaisesRegex(SyncError,'PRECHECK_BLOCKED'):self.prepare()
    def test_valid_and_expired_lease_both_block(self):
        for until in (1,9999999999):
            with closing(base.connect(self.db)) as c:c.execute("UPDATE of_connections SET sync_state='RUNNING',lease_token='synthetic-lease',lease_until=? WHERE id='santander'",(until,))
            with self.assertRaisesRegex(SyncError,'PRECHECK_BLOCKED'):self.prepare()
    def test_other_bank_lease_blocks_without_changing_itau(self):
        with closing(base.connect(self.db)) as c:c.execute("UPDATE of_connections SET sync_state='RUNNING',lease_token='synthetic-lease',lease_until=9999999999 WHERE id='itau'")
        before=self.snapshot()
        with self.assertRaisesRegex(SyncError,'PRECHECK_BLOCKED'):self.prepare()
        self.assertEqual(self.snapshot(),before)
    def test_auto_enabled_fails_closed(self):
        r=SantanderBindingRecovery(replace(self.settings,pluggy_connections=(replace(self.itau,auto_sync_enabled=True),self.cfg)))
        with self.assertRaisesRegex(SyncError,'AUTO_SYNC_ENABLED'):r.inspect()
    def test_state_changed_after_prepare_invalidates(self):
        nonce=self.prepare()
        with closing(base.connect(self.db)) as c:c.execute("UPDATE of_connections SET updated_at='2026-11-10T00:01:00Z' WHERE id='santander'")
        before=self.snapshot()
        with self.assertRaisesRegex(SyncError,'STATE_CHANGED'):self.execute(nonce)
        self.assertEqual(self.snapshot(),before)
    def test_confirmation_one_use_and_actor_bound(self):
        nonce=self.prepare()
        with self.assertRaisesRegex(SyncError,'CONFIRMATION_INVALID'):self.r.execute(('UI','UI:local','other-session'),nonce,CONFIRM['APPLY'],True)
        with self.assertRaisesRegex(SyncError,'CONFIRMATION_INVALID'):self.execute(nonce)
    def test_backup_and_explicit_confirmation_required(self):
        with self.assertRaisesRegex(SyncError,'BACKUP_CONFIRMATION'):self.r.prepare(ACTOR,'APPLY',False)
        nonce=self.prepare()
        with self.assertRaisesRegex(SyncError,'EXPLICIT_CONFIRMATION'):self.r.execute(ACTOR,nonce,'yes',True)
    def test_token_expiration(self):
        nonce=self.prepare();self.r.now=lambda:10**20
        with self.assertRaisesRegex(SyncError,'CONFIRMATION_INVALID'):self.execute(nonce)
    def test_audit_failure_rolls_back_entire_database(self):
        before=self.snapshot();nonce=self.prepare()
        with patch.object(self.r,'save',side_effect=OSError('SYNTHETIC_PRIVATE_MESSAGE')):
            with self.assertRaises(SyncError):self.execute(nonce)
        self.assertEqual(self.snapshot(),before)
    def test_invariant_exception_before_write_aborts(self):
        nonce=self.prepare();before=self.snapshot()
        with patch('finance_v2.open_finance_recovery.fingerprint',side_effect=RuntimeError('synthetic')):
            with self.assertRaises(RuntimeError):self.execute(nonce)
        self.assertEqual(self.snapshot(),before)
    def test_protected_data_mismatch_after_update_rolls_back(self):
        nonce=self.prepare();before=self.snapshot();original=fingerprint;calls=[]
        def mismatch(c,key,scope):
            value=original(c,key,scope)
            if scope=='protected':
                calls.append(scope)
                if len(calls)==2:return '0'*64
            return value
        with patch('finance_v2.open_finance_recovery.fingerprint',side_effect=mismatch):
            with self.assertRaisesRegex(SyncError,'PROTECTED_DATA_CHANGED'):self.execute(nonce)
        self.assertEqual(self.snapshot(),before)
    def test_restart_retains_selective_reversal(self):
        out=self.apply();self.r=Application(self.settings).santander_binding_recovery
        self.assertEqual(self.r.inspect()['revert_operation'],out['operation'])
        self.assertEqual(self.execute(self.prepare('REVERT',out['operation']),'REVERT')['status'],'REVERTED')
    def test_configuration_change_blocks_reversal(self):
        out=self.apply();self.r.settings=replace(self.settings,pluggy_connections=(self.itau,replace(self.cfg,client_id='synthetic-changed-client')))
        before=self.snapshot()
        with self.assertRaisesRegex(SyncError,'CONFIGURATION_CHANGED'):self.execute(self.prepare('REVERT',out['operation']),'REVERT')
        self.assertEqual(self.snapshot(),before)
    def test_schema_and_migration_ledger_preserved(self):
        with closing(base.connect(self.db)) as c:
            before=[tuple(r) for r in c.execute('SELECT type,name,sql FROM sqlite_master ORDER BY type,name')]
            ledger=[tuple(r) for r in c.execute('SELECT * FROM _finance_v2_schema_migrations ORDER BY rowid')]
        self.apply()
        with closing(base.connect(self.db)) as c:
            self.assertEqual([tuple(r) for r in c.execute('SELECT type,name,sql FROM sqlite_master ORDER BY type,name')],before)
            self.assertEqual([tuple(r) for r in c.execute('SELECT * FROM _finance_v2_schema_migrations ORDER BY rowid')],ledger)
            self.assertEqual(c.execute('PRAGMA user_version').fetchone()[0],11)
    def test_pending_audit_after_commit_reconciled_on_explicit_action(self):
        save=self.r.save
        def fail_final(record,phase):
            if phase=='COMMITTED':raise OSError('synthetic')
            return save(record,phase)
        with patch.object(self.r,'save',side_effect=fail_final):out=self.apply()
        self.assertEqual(out['status'],'COMMITTED_AUDIT_PENDING')
        self.r=Application(self.settings).santander_binding_recovery
        before=self.snapshot()
        self.assertTrue(self.r.inspect()['audit_pending'])
        with self.assertRaisesRegex(SyncError,'AUDIT_RECONCILIATION_REQUIRED'):self.prepare()
        result=self.execute(self.prepare('RECONCILE'),'RECONCILE')
        self.assertEqual(result['status'],'AUDIT_RECONCILED')
        self.assertEqual(result['sqlite_rows_changed'],0)
        self.assertEqual(self.snapshot(),before)
        self.assertEqual(self.r.load(out['operation'])['phase'],'COMMITTED')
    def test_prepared_before_failed_commit_reconciles_aborted_after_restart(self):
        before=self.snapshot()
        save=self.r.save
        def fail_after_receipt(record,phase):
            save(record,phase)
            if phase=='PREPARED':raise OSError('synthetic precommit failure')
        with patch.object(self.r,'save',side_effect=fail_after_receipt):
            with self.assertRaises(SyncError):self.apply()
        self.r=Application(self.settings).santander_binding_recovery
        result=self.execute(self.prepare('RECONCILE'),'RECONCILE')
        self.assertEqual(result['phase'],'ABORTED')
        self.assertEqual(self.snapshot(),before)

    def test_late_finalizer_cannot_overwrite_reverted_receipt(self):
        with patch.object(self.r,'finalize_receipt',side_effect=OSError('synthetic')):
            out=self.apply()
        pending=self.r.load(out['operation'])
        self.execute(self.prepare('RECONCILE'),'RECONCILE')
        self.execute(self.prepare('REVERT',out['operation']),'REVERT')
        before=self.r.load(out['operation'])
        with self.r.connection(write=True) as c:self.r.finalize_receipt(c,pending)
        self.assertEqual(before['phase'],'REVERTED')
        self.assertEqual(self.r.load(out['operation']),before)

    def test_interrupted_reversal_reconciliation_never_reapplies(self):
        out=self.apply()
        with patch.object(self.r,'finalize_receipt',side_effect=OSError('synthetic')):
            result=self.execute(self.prepare('REVERT',out['operation']),'REVERT')
        self.assertEqual(result['status'],'COMMITTED_AUDIT_PENDING')
        self.r=Application(self.settings).santander_binding_recovery
        path=self.r.audit_dir/(out['operation']+'.0123456789abcdef.tmp')
        path.touch(mode=0o600)
        before=self.snapshot()
        result=self.execute(self.prepare('RECONCILE'),'RECONCILE')
        self.assertEqual(result['phase'],'REVERTED')
        self.assertEqual(self.snapshot(),before)

    def test_additional_failed_history_blocks_before_preparation(self):
        with closing(base.connect(self.db)) as c:
            c.execute("INSERT INTO of_sync_runs(id,connection_id,actor,started_at,finished_at,state,error_code) VALUES(?,'santander','UI:local',?,?,'FAILED','AUTH_FAILED')",(secrets.token_hex(16),STAMP,STAMP))
        before=self.snapshot()
        self.assertIn('HISTORY_NOT_EXPECTED_26_FAILURES',self.r.inspect()['blockers'])
        with self.assertRaisesRegex(SyncError,'PRECHECK_BLOCKED'):self.prepare()
        self.assertEqual(self.snapshot(),before)

    def test_revert_preserves_later_manual_and_itau_changes(self):
        before=self.snapshot();out=self.apply()
        with closing(base.connect(self.db)) as c:
            c.execute("INSERT INTO accounts(name,active) VALUES('Synthetic later manual',1)")
            c.execute("INSERT INTO of_accounts(connection_id,external_id,name) VALUES('itau','synthetic-later','Synthetic')")
        current=self.snapshot()
        result=self.execute(self.prepare('REVERT',out['operation']),'REVERT')
        self.assertEqual(result['status'],'REVERTED')
        after=self.snapshot();after['of_connections']=current['of_connections'];self.assertEqual(after,current)
        with closing(base.connect(self.db)) as c:self.assertEqual(c.execute("SELECT binding_hash FROM of_connections WHERE id='santander'").fetchone()[0],OpenFinanceService._binding(self.swapped))
    def test_revert_blocks_new_santander_run(self):
        out=self.apply()
        with closing(base.connect(self.db)) as c:c.execute("INSERT INTO of_sync_runs(id,connection_id,actor,started_at,finished_at,state,error_code) VALUES(?,'santander','UI:local',?,?,'FAILED','SYNTHETIC')",(secrets.token_hex(16),STAMP,STAMP))
        before=self.snapshot()
        with self.assertRaisesRegex(SyncError,'SANTANDER_CHANGED'):self.execute(self.prepare('REVERT',out['operation']),'REVERT')
        self.assertEqual(self.snapshot(),before)
    def test_two_simultaneous_confirmations_only_one_updates(self):
        first=self.prepare();second=self.prepare();out=self.execute(first)
        with self.assertRaisesRegex(SyncError,'STATE_CHANGED'):self.execute(second)
        self.assertEqual(out['sqlite_rows_changed'],1)
    def test_independent_executors_race_only_one_commits(self):
        peer=Application(self.settings).santander_binding_recovery
        a=self.prepare();b=peer.prepare(ACTOR,'APPLY',True)['confirmation']
        gate=threading.Barrier(2);results=[]
        def run(recovery,nonce):
            gate.wait()
            try:results.append(recovery.execute(ACTOR,nonce,CONFIRM['APPLY'],True)['status'])
            except SyncError:results.append('BLOCKED')
        threads=[threading.Thread(target=run,args=args) for args in ((self.r,a),(peer,b))]
        for t in threads:t.start()
        for t in threads:t.join(5);self.assertFalse(t.is_alive())
        self.assertEqual(sorted(results),['APPLIED','BLOCKED'])
        self.assertEqual(len(self.r.records()),1)
        self.assertEqual(self.r.inspect()['CURRENT_BINDING_MATCH'],'MATCH')
    def test_sqlite_writer_contention_aborts_without_data_change(self):
        nonce=self.prepare();before=self.snapshot()
        with closing(base.connect(self.db)) as writer:
            writer.execute('BEGIN IMMEDIATE')
            with self.assertRaises(SyncError):self.execute(nonce)
            writer.rollback()
        self.assertEqual(self.snapshot(),before)
    def test_no_sensitive_values_in_receipts_or_http(self):
        out=self.apply()
        receipt=self.r.audit_path(out['operation']).read_text(encoding='utf-8')
        status,response=self.http()
        text=receipt+json.dumps(response)
        for value in (self.cfg.client_id,self.cfg.client_secret,self.cfg.item_id,OpenFinanceService._binding(self.cfg),OpenFinanceService._binding(self.swapped)):
            self.assertNotIn(value,text)
    def test_http_authentication_and_admin_restriction(self):
        for token,expected in ((None,401),('synthetic-external-only',403),('synthetic-scheduler',403)):
            self.assertEqual(self.http(token=token)[0],expected)
        self.assertEqual(self.http()[0],200)
    def test_http_cookie_csrf_and_origin(self):
        csrf='synthetic-csrf';sig=hmac.new(self.settings.ui_token.encode(),csrf.encode(),hashlib.sha256).hexdigest()
        cookie={'HTTP_COOKIE':'finance_v2_session='+csrf+'.'+sig}
        body={'action':'APPLY','backup_confirmed':True}
        self.assertEqual(self.http('/prepare','POST',body,token=None,extra=cookie)[0],403)
        self.assertEqual(self.http('/prepare','POST',body,token=None,extra={**cookie,'HTTP_X_CSRF_TOKEN':csrf,'HTTP_ORIGIN':'https://attacker.invalid'})[0],403)
        self.assertEqual(self.http('/prepare','POST',body,token=None,extra={**cookie,'HTTP_X_CSRF_TOKEN':csrf,'HTTP_ORIGIN':'http://127.0.0.1:8766'})[0],200)
    def test_tunnel_origin_requires_explicit_configuration(self):
        origin='https://finance.example.invalid'
        body={'action':'APPLY','backup_confirmed':True}
        headers={'HTTP_HOST':'finance.example.invalid','HTTP_ORIGIN':origin,'HTTP_X_FORWARDED_PROTO':'https','HTTP_CF_ACCESS_JWT_ASSERTION':'synthetic'}
        self.assertEqual(self.http('/prepare','POST',body,token=None,extra=headers)[0],401)
        self.assertEqual(self.http('/prepare','POST',body,extra=headers)[0],403)
        self.app=Application(replace(self.settings,cors_origins=(origin,)))
        self.assertEqual(self.http('/prepare','POST',body,extra=headers)[0],200)

    def test_http_full_explicit_flow_no_provider(self):
        status,prepared=self.http('/prepare','POST',{'action':'APPLY','backup_confirmed':True});self.assertEqual(status,200)
        body={'confirmation':prepared['confirmation'],'explicit_confirmation':CONFIRM['APPLY'],'backup_confirmed':True}
        status,out=self.http('/confirm','POST',body);self.assertEqual(status,200);self.assertEqual(out['status'],'APPLIED')
        self.assertEqual(self.http('/confirm','POST',body)[0],409)
    def test_gets_and_application_startup_never_correct(self):
        before=self.snapshot()
        self.http();self.http();Application(self.settings)
        self.assertEqual(self.snapshot(),before);self.assertFalse(self.r.audit_dir.exists())
    def test_generic_sql_fields_rejected(self):
        self.assertEqual(self.http('/prepare','POST',{'action':'APPLY','backup_confirmed':True,'sql':'UPDATE x'})[0],422)

if __name__=='__main__':unittest.main()
