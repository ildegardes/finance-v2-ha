"""Manual staging synchronization. Only migration-009 tables may be written."""
from hashlib import sha256
from .open_finance_diagnostics import annotate, emit
from contextlib import nullcontext
from datetime import datetime
from math import ceil
import json
import re
import sqlite3
import uuid

from .db import connect, immediate_transaction
from .domain.clock import SystemClock, utc_text
from .pluggy_client import PluggyClient, PluggyError, _period


class SyncError(Exception):
    def __init__(self, code, status=409):
        self.code, self.status = code, status
        super().__init__(code)


MUTABLE = ('transaction_date','amount_decimal','currency','type','status','description_original',
           'merchant_name','category_key','provider_created_at','provider_updated_at')
REVISION_FIELDS = ('amount_decimal','currency','transaction_date','type','status',
                   'description_original','merchant_name','category_key','provider_updated_at')


def validated_period(start=None, end=None):
    try:
        start,end=_period(start),_period(end)
        if start and end and start>end: raise PluggyError('INVALID_PERIOD')
        return start,end
    except PluggyError:
        raise SyncError('INVALID_PERIOD',422) from None


class OpenFinanceService:
    def __init__(self, settings, clock=None, *, client_factory=None):
        self.settings=settings
        self.clock=clock or SystemClock(settings.timezone)
        self.config={c.id:c for c in settings.pluggy_connections}
        self.client_factory=client_factory or PluggyClient
        # Default client has 10s sockets, <=3 attempts and one auth renewal.
        # Expired workers are fenced rather than assumed to have stopped.
        self.lease_seconds=300

    def _time(self):
        value=self.clock.now_utc()
        return value.timestamp(),utc_text(value)

    def _db(self):
        try:return connect(self.settings.database_path,self.settings.busy_timeout_ms)
        except (FileNotFoundError,sqlite3.Error):raise SyncError('STORAGE_UNAVAILABLE',503) from None

    @staticmethod
    def _binding(config):
        return sha256(json.dumps([config.client_id,config.item_id],separators=(',',':')).encode()).hexdigest()

    def _claim(self,c,config,actor,start,end,*,minimum_interval=0):
        epoch,stamp=self._time();token=uuid.uuid4().hex;run_id=uuid.uuid4().hex
        binding=self._binding(config)
        with immediate_transaction(c):
            row=c.execute('SELECT * FROM of_connections WHERE id=?',(config.id,)).fetchone()
            if row and row['binding_hash']!=binding:raise SyncError('CONNECTION_BINDING_CHANGED')
            if row and row['lease_token'] is not None:
                if row['lease_until']>epoch:raise SyncError('SYNC_BUSY')
                c.execute("UPDATE of_sync_runs SET state='INTERRUPTED',finished_at=?,error_code='LEASE_EXPIRED' "
                          "WHERE connection_id=? AND state='RUNNING'",(stamp,config.id))
            if minimum_interval and actor == 'AUTO:coverage':
                previous=c.execute("SELECT state,finished_at FROM of_sync_runs WHERE connection_id=? AND actor='AUTO:coverage' ORDER BY rowid DESC LIMIT 1",(config.id,)).fetchone()
                if previous and previous['finished_at'] and previous['state'] in ('SUCCEEDED','FAILED'):
                    elapsed=epoch-datetime.fromisoformat(previous['finished_at'].replace('Z','+00:00')).timestamp()
                    interval=minimum_interval if previous['state']=='SUCCEEDED' else min(300,minimum_interval)
                    if 0 <= elapsed < interval:
                        error=SyncError('AUTO_SYNC_RECENT' if previous['state']=='SUCCEEDED' else 'AUTO_SYNC_BACKOFF')
                        error.retry_after=max(1,ceil(interval-elapsed))
                        raise error
            if row:
                c.execute("UPDATE of_connections SET institution=?,enabled=1,sync_state='RUNNING',"
                          'lease_token=?,lease_until=?,updated_at=? WHERE id=?',
                          (config.institution,token,epoch+self.lease_seconds,stamp,config.id))
            else:
                c.execute("INSERT INTO of_connections(id,institution,enabled,binding_hash,sync_state,lease_token,lease_until,updated_at) "
                          "VALUES(?,?,1,?,'RUNNING',?,?,?)",
                          (config.id,config.institution,binding,token,epoch+self.lease_seconds,stamp))
            c.execute("INSERT INTO of_sync_runs(id,connection_id,actor,started_at,state,date_from,date_to) "
                      "VALUES(?,?,?,?,'RUNNING',?,?)",(run_id,config.id,actor,stamp,start,end))
        return run_id,token

    def _guard(self,c,connection_id,run_id,token):
        epoch,stamp=self._time()
        row=c.execute('SELECT lease_token,lease_until FROM of_connections WHERE id=?',(connection_id,)).fetchone()
        if not row or row['lease_token']!=token or row['lease_until']<=epoch:raise SyncError('LEASE_LOST')
        run=c.execute('SELECT state FROM of_sync_runs WHERE id=? AND connection_id=?',(run_id,connection_id)).fetchone()
        if not run or run['state']!='RUNNING':raise SyncError('LEASE_LOST')
        c.execute('UPDATE of_connections SET lease_until=?,updated_at=? WHERE id=? AND lease_token=?',
                  (epoch+self.lease_seconds,stamp,connection_id,token))
        return stamp

    def _touch(self,c,connection_id,run_id,token):
        with immediate_transaction(c):self._guard(c,connection_id,run_id,token)

    def _accounts(self,c,config,run_id,token,accounts,*,in_transaction=False):
        if in_transaction and not c.in_transaction:raise SyncError('STORAGE_TRANSACTION_REQUIRED',503)
        with nullcontext() if in_transaction else immediate_transaction(c):
            self._guard(c,config.id,run_id,token)
            for account in accounts:
                if account.connection_id!=config.id:raise annotate(SyncError('ACCOUNT_SCOPE_MISMATCH',502), resource='accounts', operation='ACCOUNTS_PERSIST', stage='STAGING_CHECK', category='LOCAL_CONNECTION_MISMATCH')
                values=account.staging_fields()
                c.execute('INSERT INTO of_accounts(connection_id,external_id,name,type,subtype,currency,provider_updated_at) '
                          'VALUES(?,?,?,?,?,?,?) ON CONFLICT(connection_id,external_id) DO UPDATE SET '
                          'name=excluded.name,type=excluded.type,subtype=excluded.subtype,currency=excluded.currency,'
                          'provider_updated_at=excluded.provider_updated_at',tuple(values[k] for k in
                          ('connection_id','external_id','name','type','subtype','currency','provider_updated_at')))

    @staticmethod
    def _category(c,config,record,stamp):
        external=record.category_id
        name=record.category_name
        if external is None and name is None:return None
        external=str(external) if external is not None else None
        # Provider IDs have precedence. Missing IDs use an explicit separate
        # namespace; no name-based association to official categories exists.
        key=('id:'+external) if external is not None and len(external)<=197 else (
            'idhash:'+sha256(external.encode()).hexdigest() if external is not None
            else 'namehash:'+sha256(name.encode()).hexdigest())
        c.execute('INSERT INTO of_categories(connection_id,category_key,external_id,original_name,updated_at) '
                  'VALUES(?,?,?,?,?) ON CONFLICT(connection_id,category_key) DO UPDATE SET '
                  'original_name=COALESCE(excluded.original_name,of_categories.original_name),updated_at=excluded.updated_at',
                  (config.id,key,external,name,stamp))
        return key

    def _page(self,c,config,run_id,token,account_id,records,*,in_transaction=False):
        if in_transaction and not c.in_transaction:raise SyncError('STORAGE_TRANSACTION_REQUIRED',503)
        with nullcontext() if in_transaction else immediate_transaction(c):
            stamp=self._guard(c,config.id,run_id,token)
            inserted=updated=0
            for record in records:
                if record.connection_id!=config.id or record.external_account_id!=account_id:
                    raise SyncError('TRANSACTION_SCOPE_MISMATCH',502)
                fields=record.staging_fields()
                fields['category_key']=self._category(c,config,record,stamp)
                old=c.execute('SELECT * FROM of_transactions WHERE connection_id=? AND external_account_id=? AND external_id=?',
                              (config.id,account_id,record.external_id)).fetchone()
                changed=old is None or any(old[k]!=fields[k] for k in MUTABLE)
                if old is None:
                    names=('connection_id','external_account_id','external_id')+MUTABLE+('first_seen_at','last_seen_at')
                    fields.update(first_seen_at=stamp,last_seen_at=stamp)
                    txid=c.execute('INSERT INTO of_transactions('+','.join(names)+') VALUES('+','.join('?' for _ in names)+')',
                                   tuple(fields[k] for k in names)).lastrowid
                    inserted+=1
                else:
                    txid=old['id']
                    c.execute('UPDATE of_transactions SET '+','.join(k+'=?' for k in MUTABLE)+',last_seen_at=? WHERE id=?',
                              tuple(fields[k] for k in MUTABLE)+(stamp,txid))
                    if changed:updated+=1
                if changed:
                    revision=c.execute('SELECT COALESCE(MAX(revision_number),0)+1 FROM of_transaction_revisions WHERE transaction_id=?',
                                       (txid,)).fetchone()[0]
                    names=('transaction_id','connection_id','revision_number','run_id','observed_at')+REVISION_FIELDS
                    values=(txid,config.id,revision,run_id,stamp)+tuple(fields[k] for k in REVISION_FIELDS)
                    c.execute('INSERT INTO of_transaction_revisions('+','.join(names)+') VALUES('+','.join('?' for _ in names)+')',values)
            c.execute('UPDATE of_sync_runs SET inserted_count=inserted_count+?,updated_count=updated_count+?,page_count=page_count+1 WHERE id=?',
                      (inserted,updated,run_id))

    def _finish(self,c,config,run_id,token,error=None,*,interrupted=False):
        if interrupted and error is None:raise ValueError('INTERRUPTION_REASON_REQUIRED')
        epoch,stamp=self._time()
        with immediate_transaction(c):
            row=c.execute('SELECT lease_token,lease_until FROM of_connections WHERE id=?',(config.id,)).fetchone()
            if row and row['lease_token']==token:
                if row['lease_until']<=epoch:error='LEASE_LOST'
                state='INTERRUPTED' if interrupted else 'FAILED' if error else 'SUCCEEDED'
                c.execute('UPDATE of_sync_runs SET state=?,finished_at=?,error_code=? WHERE id=? AND state=\'RUNNING\'',
                          (state,stamp,error,run_id))
                c.execute('UPDATE of_connections SET sync_state=?,lease_token=NULL,lease_until=NULL,updated_at=? WHERE id=? AND lease_token=?',
                          (state,stamp,config.id,token))
        return dict(c.execute('SELECT * FROM of_sync_runs WHERE id=?',(run_id,)).fetchone())

    def sync_one(self,connection_id,*,actor,start=None,end=None):
        start,end=validated_period(start,end)
        if actor!='UI:local':raise SyncError('OWNER_REQUIRED',403)
        config=self.config.get(connection_id)
        if config is None:raise SyncError('CONNECTION_NOT_FOUND',404)
        if not config.enabled:raise SyncError('CONNECTION_DISABLED')
        c=self._db()
        try:
            try:run_id,token=self._claim(c,config,actor,start,end)
            except sqlite3.Error:raise SyncError('STORAGE_BUSY',503) from None
            error=None
            try:
                client=self.client_factory(config)
                self._touch(c,config.id,run_id,token)
                accounts=client.accounts()  # Outside write transactions.
                self._accounts(c,config,run_id,token,accounts)
                for account in accounts:
                    pages=iter(client.transaction_pages(account.external_id,date_from=start,date_to=end))
                    while True:
                        self._touch(c,config.id,run_id,token)
                        try:page=next(pages)  # Outside write transactions.
                        except StopIteration:break
                        self._page(c,config,run_id,token,account.external_id,page)
            except PluggyError as exc:
                emit(config.id,run_id,exc)
                error=exc.code
            except SyncError as exc:
                emit(config.id,run_id,exc)
                error=exc.code
            except sqlite3.Error:error='STORAGE_FAILURE'
            except Exception:error='SYNC_INTERNAL_FAILURE'  # No raw provider/SQL exception logging.
            try:return self._finish(c,config,run_id,token,error)
            except sqlite3.Error:raise SyncError('FINALIZATION_FAILED',503) from None
        finally:c.close()

    def sync_all(self,*,actor,start=None,end=None):
        start,end=validated_period(start,end)
        if actor!='UI:local':raise SyncError('OWNER_REQUIRED',403)
        results=[]
        for config in self.config.values():
            if not config.enabled:continue
            try:results.append(self.sync_one(config.id,actor=actor,start=start,end=end))
            except SyncError as exc:
                results.append({'connection_id':config.id,'state':'FAILED','error_code':exc.code})
        return results

    def connections(self,c):
        result=[]
        for config in self.config.values():
            row=c.execute('SELECT sync_state,lease_until FROM of_connections WHERE id=?',(config.id,)).fetchone()
            last=c.execute('SELECT * FROM of_sync_runs WHERE connection_id=? ORDER BY started_at DESC,rowid DESC LIMIT 1',(config.id,)).fetchone()
            epoch,_=self._time()
            result.append({'id':config.id,'institution':config.institution,'enabled':config.enabled,
                           'sync_state':row['sync_state'] if row else 'IDLE',
                           'lease_expired':bool(row and row['lease_until'] is not None and row['lease_until']<=epoch),
                           'last_run':dict(last) if last else None})
        return result


def paged(c,table,query):
    if table not in {'of_sync_runs','of_transactions'}:raise ValueError('unsupported table')
    allowed={'page','page_size','connection_id'}|({'external_account_id'} if table=='of_transactions' else set())
    if set(query)-allowed or any(len(values)!=1 for values in query.values()):raise SyncError('INVALID_QUERY',422)
    def integer(name,default):
        raw=query.get(name,[str(default)])[0]
        if not isinstance(raw,str) or not re.fullmatch(r'[0-9]{1,19}',raw) or not 0<int(raw)<=9223372036854775807:
            raise SyncError('INVALID_PAGINATION',422)
        return int(raw)
    page,size=integer('page',1),integer('page_size',50)
    if size not in {25,50,100} or (page-1)*size>9223372036854775807:raise SyncError('INVALID_PAGINATION',422)
    clauses=[];args=[]
    for key in ('connection_id','external_account_id'):
        if key in query:
            value=query[key][0]
            if not value or len(value)>200 or value!=value.strip() or any(ord(ch)<32 or ord(ch)==127 for ch in value):raise SyncError('INVALID_QUERY',422)
            clauses.append(key+'=?');args.append(value)
    rows=c.execute('SELECT * FROM '+table+(' WHERE '+' AND '.join(clauses) if clauses else '')+
                   ' ORDER BY rowid DESC LIMIT ? OFFSET ?',(*args,size+1,(page-1)*size)).fetchall()
    items=[dict(r) for r in rows[:size]]
    if table=='of_transactions':
        for item in items:
            category=c.execute('SELECT provider,external_id,original_name,display_name_pt,translation_status FROM of_categories '
                'WHERE connection_id=? AND category_key=?',(item['connection_id'],item['category_key'])).fetchone()
            item['category']=dict(category) if category else None
    return {'items':items,'page':page,'page_size':size,'has_more':len(rows)>size}
