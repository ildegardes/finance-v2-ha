"""Owner-only Santander inverted-binding maintenance. No provider or migrations.

Only one SQLite field may be written. Audit receipts contain keyed integrity
checks, never bank identifiers, credentials, payloads or binding digests.
"""
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
import base64,hashlib,hmac,json,os,re,secrets,sqlite3,stat,threading,time

from .open_finance import OpenFinanceService,SyncError
from .open_finance_write import staging_transaction
from .open_finance_recovery_checks import TABLES,Blocked,schema_check,dependencies

EXPECTED=json.loads(Path(__file__).with_name('open_finance_recovery_schema.json').read_text(encoding='utf-8'))
CONFIRM={'APPLY':'CORRIGIR_BINDING_SANTANDER','REVERT':'REVERTER_BINDING_SANTANDER'}
MAX_SECONDS=30

def fail(code,status=409):raise SyncError('SANTANDER_RECOVERY_'+code,status)

def encoded(value):
    return json.dumps(value,ensure_ascii=True,separators=(',',':'),sort_keys=True,
        allow_nan=False,default=lambda v:{'blob':v.hex()} if isinstance(v,bytes) else (_ for _ in ()).throw(ValueError())).encode()

def fingerprint(c,key,scope):
    """Streaming, keyed, private equality check; never returned over HTTP."""
    out=hmac.new(key,digestmod=hashlib.sha256)
    def add(value):
        raw=encoded(value);out.update(len(raw).to_bytes(8,'big'));out.update(raw)
    add([tuple(r) for r in c.execute('SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name')])
    add(c.execute('PRAGMA user_version').fetchone()[0])
    for name, in c.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").fetchall():
        if scope=='santander' and name not in TABLES:continue
        quoted='"'+name.replace('"','""')+'"'
        where=(' WHERE '+('id' if name=='of_connections' else 'connection_id')+"='santander'") if scope=='santander' else ''
        add(name)
        for row in c.execute('SELECT * FROM '+quoted+where+' ORDER BY rowid'):
            values=dict(row)
            if scope=='protected' and name=='of_connections' and values.get('id')=='santander':
                values['binding_hash']='AUTHORIZED_FIELD_MASK'
            add(values)
    return out.hexdigest()

def sql_guard(action,a,b,db,origin):
    if action in (sqlite3.SQLITE_SELECT,sqlite3.SQLITE_READ):return sqlite3.SQLITE_OK
    if action==sqlite3.SQLITE_FUNCTION:return sqlite3.SQLITE_DENY if (b or '').lower()=='load_extension' else sqlite3.SQLITE_OK
    if action==sqlite3.SQLITE_UPDATE:return sqlite3.SQLITE_OK if a=='of_connections' and b=='binding_hash' else sqlite3.SQLITE_DENY
    if action==sqlite3.SQLITE_TRANSACTION:return sqlite3.SQLITE_OK
    if action==sqlite3.SQLITE_PRAGMA and (a or '').lower()=='busy_timeout':return sqlite3.SQLITE_OK
    if action==sqlite3.SQLITE_PRAGMA and (a or '').lower() in ('user_version','table_xinfo','foreign_key_list','foreign_key_check','integrity_check','index_list','index_xinfo') and b is None:return sqlite3.SQLITE_OK
    # Table-argument schema pragmas are read-only; user_version assignments aren't.
    if action==sqlite3.SQLITE_PRAGMA and (a or '').lower() in ('table_xinfo','foreign_key_list','index_list','index_xinfo'):return sqlite3.SQLITE_OK
    return sqlite3.SQLITE_DENY

class SantanderBindingRecovery:
    def __init__(self,settings,*,now=time.monotonic):
        self.settings=settings;self.now=now
        self.lock=threading.Lock();self.pending={};self.session_key=secrets.token_bytes(32)
        self.audit_dir=settings.database_path.resolve().parent/(settings.database_path.name+'.santander-recovery')

    def config(self):
        configs=[c for c in self.settings.pluggy_connections if c.id=='santander']
        if len(configs)!=1:fail('CONNECTION_NOT_UNIQUE')
        cfg=configs[0]
        if not cfg.enabled or cfg.access_mode!='meupluggy_personal':fail('CONFIGURATION_NOT_ELIGIBLE')
        if any(c.enabled and c.auto_sync_enabled for c in self.settings.pluggy_connections):fail('AUTO_SYNC_ENABLED')
        if cfg.client_id==cfg.item_id:fail('AMBIGUOUS_IDENTIFIERS')
        return cfg

    def config_mac(self,key):
        c=self.config()
        return hmac.new(key,encoded([c.id,c.client_id,c.item_id,c.enabled,c.auto_sync_enabled,c.access_mode]),hashlib.sha256).hexdigest()

    @contextmanager
    def connection(self,write=False):
        path=self.settings.database_path.resolve()
        if not path.is_file() or self.settings.database_path.is_symlink():fail('DATABASE_UNAVAILABLE',503)
        c=None;deadline=self.now()+MAX_SECONDS
        try:
            c=sqlite3.connect(path.as_uri()+('?mode=rw&cache=private' if write else '?mode=ro&cache=private'),uri=True,timeout=min(self.settings.busy_timeout_ms,2000)/1000,isolation_level=None)
            c.row_factory=sqlite3.Row;c.execute('PRAGMA foreign_keys=ON')
            if not write:c.execute('PRAGMA query_only=ON')
            c.set_authorizer(sql_guard)
            c.set_progress_handler(lambda:1 if self.now()>=deadline else 0,1000)
            yield c
        except Blocked:fail('SCHEMA_OR_INTEGRITY_UNAVAILABLE',503)
        except (sqlite3.Error,OSError,ValueError,TypeError):fail('STORAGE_OR_AUDIT_UNAVAILABLE',503)
        finally:
            if c is not None:
                if c.in_transaction:c.rollback()
                c.close()

    def bindings(self,c):
        cfg=self.config()
        row=c.execute("SELECT binding_hash FROM of_connections WHERE id='santander'").fetchone()
        if row is None:fail('NO_RECORD')
        stored=row[0]
        if not isinstance(stored,str) or not re.fullmatch('[0-9a-f]{64}',stored):fail('INVALID_BINDING')
        current=OpenFinanceService._binding(cfg)
        swapped=OpenFinanceService._binding(replace(cfg,client_id=cfg.item_id,item_id=cfg.client_id))
        return stored,current,swapped

    def inspect_db(self,c):
        schema_check(c,EXPECTED)
        stored,current,swapped=self.bindings(c)
        audit=dependencies(c,'santander')
        blockers=[]
        if not audit['SQLITE_INTEGRITY_OK'] or audit['FOREIGN_KEY_VIOLATIONS']:blockers.append('INTEGRITY')
        if any(audit['CROSS_CONNECTION_RUN_REFERENCES'].values()) or audit['CROSS_CONNECTION_TRANSACTION_REFERENCES']:blockers.append('INDIRECT_OR_CROSS_REFERENCE')
        imported=('of_accounts','of_categories','of_transactions','of_transaction_revisions','of_resource_records','of_resource_revisions','of_resource_links','of_resource_link_revisions')
        if any(audit['COUNTS'][t] for t in imported):blockers.append('IMPORTED_RECORDS')
        if audit['COUNTS']['of_sync_runs']!=26 or audit['AUTH_FAILED_RUNS']!=26 or audit['RUN_COUNTS']['FAILED']!=26:blockers.append('HISTORY_NOT_EXPECTED_26_FAILURES')
        if c.execute("SELECT count(*) FROM of_sync_runs WHERE state='RUNNING'").fetchone()[0]:blockers.append('ACTIVE_RUN')
        if c.execute('SELECT count(*) FROM of_connections WHERE lease_token IS NOT NULL OR lease_until IS NOT NULL').fetchone()[0]:blockers.append('LEASE_PRESENT')
        if c.execute("SELECT count(*) FROM of_collection_checkpoints WHERE connection_id='santander' AND (resource<>'item' OR parent_id<>'' OR state<>'FAILED' OR page_count<>0 OR record_count<>0 OR last_complete_run_id IS NOT NULL OR last_complete_page_count<>0 OR last_complete_record_count<>0)").fetchone()[0]:blockers.append('CHECKPOINT_DEPENDENCY')
        if c.execute("SELECT count(*) FROM of_resource_coverage WHERE connection_id='santander' AND (resource<>'item' OR parent_id<>'' OR state<>'FAILED' OR page_count<>0 OR record_count<>0)").fetchone()[0]:blockers.append('COVERAGE_DEPENDENCY')
        if c.execute("SELECT count(*) FROM of_domain_sync_audit WHERE connection_id='santander' AND (mode='RESUME' OR resumed_from_run_id IS NOT NULL)").fetchone()[0]:blockers.append('RESUME_DEPENDENCY')
        if stored!=current and stored!=swapped:blockers.append('UNRECOGNIZED_BINDING')
        status='ALREADY_CORRECT' if stored==current else 'ELIGIBLE' if not blockers and stored==swapped else 'BLOCKED'
        return {'status':status,'CURRENT_BINDING_MATCH':'MATCH' if stored==current else 'MISMATCH',
            'SWAPPED_BINDING_MATCH':'MATCH' if stored==swapped else 'MISMATCH','blockers':blockers,
            'counts':audit['COUNTS'],'running_runs':audit['RUN_COUNTS']['RUNNING'],
            'integrity':audit['SQLITE_INTEGRITY_OK'] and audit['FOREIGN_KEY_VIOLATIONS']==0,
            'config_source':'LIVE_APPLICATION_SETTINGS'},(stored,current,swapped)

    def audit_path(self,operation_id):
        if not isinstance(operation_id,str) or re.fullmatch('[0-9a-f]{32}',operation_id) is None:fail('INVALID_OPERATION',422)
        return self.audit_dir/(operation_id+'.json')

    def check_private(self,path,directory=False):
        if path.is_symlink():fail('UNSAFE_AUDIT_PATH',503)
        if os.name=='posix':
            s=path.stat()
            if s.st_uid!=os.geteuid() or stat.S_IMODE(s.st_mode)&0o077:fail('AUDIT_PERMISSIONS',503)
        if directory and not path.is_dir():fail('UNSAFE_AUDIT_PATH',503)

    def load(self,operation_id):
        path=self.audit_path(operation_id)
        self.check_private(self.audit_dir,True);self.check_private(path)
        with path.open('rb') as f:raw=f.read(65537)
        if len(raw)>65536:fail('AUDIT_INVALID',503)
        record=json.loads(raw)
        if set(record)!={'version','operation','key','config','before','after','phase','events'} or record['version']!=1 or record['operation']!=operation_id:fail('AUDIT_INVALID',503)
        if record['phase'] not in ('PREPARED','COMMITTED','ABORTED','REVERT_PREPARED','REVERTED'):fail('AUDIT_INVALID',503)
        if len(base64.b64decode(record['key'],validate=True))!=32:fail('AUDIT_INVALID',503)
        if not all(isinstance(record[k],str) and re.fullmatch('[0-9a-f]{64}',record[k]) for k in ('config','before','after')):fail('AUDIT_INVALID',503)
        return record

    def save(self,record,phase):
        """Durable PREPARED before SQLite commit; reconcile crash ambiguity later."""
        self.audit_dir.mkdir(mode=0o700,exist_ok=True)
        self.check_private(self.audit_dir,True)
        record=dict(record);record['phase']=phase
        record['events']=[*record['events'],{'phase':phase,'time_ns':time.time_ns()}]
        path=self.audit_path(record['operation']);temp=self.audit_dir/(record['operation']+'.'+secrets.token_hex(8)+'.tmp')
        fd=os.open(temp,os.O_WRONLY|os.O_CREAT|os.O_EXCL|getattr(os,'O_NOFOLLOW',0),0o600)
        try:
            with os.fdopen(fd,'wb') as f:f.write(encoded(record));f.flush();os.fsync(f.fileno())
            if path.exists():self.check_private(path)
            os.replace(temp,path)
            if os.name=='posix':
                directory=os.open(self.audit_dir,os.O_RDONLY|getattr(os,'O_DIRECTORY',0))
                try:os.fsync(directory)
                finally:os.close(directory)
        finally:
            if temp.exists():temp.unlink()
        return record

    def records(self):
        if not self.audit_dir.exists():return []
        self.check_private(self.audit_dir,True)
        paths=list(self.audit_dir.iterdir())
        if len(paths)>256 or any(p.suffix!='.json' for p in paths):fail('AUDIT_REVIEW_REQUIRED',503)
        return [self.load(p.stem) for p in paths]

    def reconcile(self,c,record):
        key=base64.b64decode(record['key'],validate=True)
        if not hmac.compare_digest(record['config'],self.config_mac(key)):fail('CONFIGURATION_CHANGED')
        observed=fingerprint(c,key,'santander')
        if record['phase']=='PREPARED':
            phase='COMMITTED' if observed==record['after'] else 'ABORTED' if observed==record['before'] else None
        elif record['phase']=='REVERT_PREPARED':
            phase='REVERTED' if observed==record['before'] else 'COMMITTED' if observed==record['after'] else None
        else:return record
        if phase is None:fail('AUDIT_OUTCOME_UNKNOWN')
        return self.save(record,phase)

    def inspect(self):
        with self.connection() as c:
            c.execute('BEGIN');report,_=self.inspect_db(c)
            receipts=self.records();active=[r for r in receipts if r['phase'] in ('COMMITTED','PREPARED','REVERT_PREPARED')]
            report['revert_operation']=None;report['audit_pending']=any(r['phase'] in ('PREPARED','REVERT_PREPARED') for r in active)
            if len(active)==1 and active[0]['phase']=='COMMITTED':
                r=active[0];key=base64.b64decode(r['key'],validate=True)
                if r['config']==self.config_mac(key) and r['after']==fingerprint(c,key,'santander') and not any(x in report['blockers'] for x in ('ACTIVE_RUN','LEASE_PRESENT','INTEGRITY','INDIRECT_OR_CROSS_REFERENCE')):
                    report['revert_operation']=r['operation']
            return report

    def prepare(self,actor,action,backup_confirmed,operation_id=None):
        if action not in CONFIRM or backup_confirmed is not True:fail('BACKUP_CONFIRMATION_REQUIRED',422)
        with self.lock:
            self.pending={k:v for k,v in self.pending.items() if v['until']>self.now()}
            if len(self.pending)>=16:fail('TOO_MANY_CONFIRMATIONS',429)
            with self.connection() as c:
                c.execute('BEGIN');report,_=self.inspect_db(c)
                if action=='APPLY' and report['status'] not in ('ELIGIBLE','ALREADY_CORRECT'):fail('PRECHECK_BLOCKED')
                if action=='REVERT':self.load(operation_id)
                nonce=secrets.token_hex(32)
                self.pending[nonce]={'actor':actor,'action':action,'operation':operation_id,'until':self.now()+300,
                    'config':self.config_mac(self.session_key),'snapshot':fingerprint(c,self.session_key,'santander')}
                return {'confirmation':nonce,'expires_in_seconds':300,'action':action,'precheck':report}

    def execute(self,actor,nonce,confirmation,backup_confirmed):
        with self.lock:
            pending=self.pending.pop(nonce,None) if isinstance(nonce,str) else None
            if pending is None or pending['actor']!=actor or pending['until']<=self.now():fail('CONFIRMATION_INVALID')
            action=pending['action']
            if backup_confirmed is not True or confirmation!=CONFIRM[action]:fail('EXPLICIT_CONFIRMATION_REQUIRED',422)
            with self.connection(write=True) as c:
                record=None;committed=False
                try:
                    with staging_transaction(c,self.settings.database_path,timeout_ms=min(self.settings.busy_timeout_ms,2000),check=lambda:None):
                        report,bindings=self.inspect_db(c)
                        if pending['config']!=self.config_mac(self.session_key) or pending['snapshot']!=fingerprint(c,self.session_key,'santander'):fail('STATE_CHANGED_RECHECK_REQUIRED')
                        receipts=[self.reconcile(c,r) for r in self.records()]
                        if sum(r['phase']=='COMMITTED' for r in receipts)>1:fail('AUDIT_REVIEW_REQUIRED')
                        if action=='APPLY' and report['status']=='ALREADY_CORRECT':return {'status':'ALREADY_CORRECT','sqlite_rows_changed':0}
                        if action=='APPLY' and report['status']!='ELIGIBLE':fail('PRECHECK_BLOCKED')
                        if action=='REVERT' and any(x in report['blockers'] for x in ('ACTIVE_RUN','LEASE_PRESENT','INTEGRITY','INDIRECT_OR_CROSS_REFERENCE')):fail('PRECHECK_BLOCKED')
                        if action=='APPLY':
                            if any(r['phase']=='COMMITTED' for r in receipts):fail('PREVIOUS_OPERATION_REQUIRES_REVIEW')
                            key=secrets.token_bytes(32)
                            record={'version':1,'operation':secrets.token_hex(16),'key':base64.b64encode(key).decode(),'config':self.config_mac(key),'before':fingerprint(c,key,'santander'),'after':'0'*64,'phase':'PREPARED','events':[]}
                            old,new=bindings[0],bindings[1]
                        else:
                            record=self.reconcile(c,self.load(pending['operation']))
                            key=base64.b64decode(record['key'],validate=True)
                            if record['phase']=='REVERTED' and fingerprint(c,key,'santander')==record['before']:return {'status':'ALREADY_REVERTED','sqlite_rows_changed':0,'operation':record['operation']}
                            if record['phase']!='COMMITTED' or fingerprint(c,key,'santander')!=record['after']:fail('SANTANDER_CHANGED_SINCE_OPERATION')
                            old,new=bindings[1],bindings[2]
                            if bindings[0]!=old:fail('UNEXPECTED_CURRENT_BINDING')
                        protected=fingerprint(c,key,'protected')
                        # Predict the exact post-image without writing SQLite.
                        before_row=c.execute("SELECT * FROM of_connections WHERE id='santander'").fetchone()
                        if action=='REVERT':record=self.save(record,'REVERT_PREPARED')
                        # For APPLY the actual post-MAC is captured before a durable receipt
                        # and before commit; any audit failure rolls back this single update.
                        c.execute('UPDATE of_connections SET binding_hash=? WHERE id=? AND binding_hash=? AND lease_token IS NULL AND lease_until IS NULL',(new,'santander',old))
                        if c.execute('SELECT changes()').fetchone()[0]!=1:fail('COMPARE_AND_SWAP_FAILED')
                        after_row=c.execute("SELECT * FROM of_connections WHERE id='santander'").fetchone()
                        if any(before_row[k]!=after_row[k] for k in before_row.keys() if k!='binding_hash'):fail('UNEXPECTED_ROW_CHANGE')
                        if protected!=fingerprint(c,key,'protected'):fail('PROTECTED_DATA_CHANGED')
                        if c.execute('PRAGMA foreign_key_check').fetchall() or [tuple(r) for r in c.execute('PRAGMA integrity_check')]!=[('ok',)]:fail('INTEGRITY_FAILED')
                        after=fingerprint(c,key,'santander')
                        if action=='APPLY':record['after']=after;record=self.save(record,'PREPARED')
                        elif after!=record['before']:fail('REVERSAL_INVARIANT_FAILED')
                    committed=True
                except BaseException:
                    if record is not None and not committed:
                        try:self.reconcile(c,record)
                        except Exception:pass  # Durable PREPARED is reconciled; never discarded.
                    raise
                phase='COMMITTED' if action=='APPLY' else 'REVERTED'
                try:self.save(record,phase);status='APPLIED' if action=='APPLY' else 'REVERTED'
                except Exception:status='COMMITTED_AUDIT_PENDING'
                return {'status':status,'operation':record['operation'],'sqlite_rows_changed':1,'historical_runs_preserved':True,'protected_data_preserved':True,'backup_confirmed_by_owner':True,'provider_calls':0}
