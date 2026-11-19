"""SnapTrade cache imports, local-only controls and durable scheduling."""
from collections import defaultdict
from contextlib import closing, contextmanager
from datetime import date, timedelta
from decimal import Decimal, localcontext
import json
import logging
import re
import sqlite3
import threading
import time
from uuid import uuid4

from .open_finance import OpenFinanceService, SyncError
from .open_finance_registry import load_keyring
from .open_finance_schedule import HOURS, _datetime, _iso
from .pluggy_credential_protection import CredentialProtectionError, ProtectedCredential
from .snaptrade_normalize import (
    account_record, activity, code, collection, connection_record, day, field_value, financial_text,
    ident, invalid, is_reit, key, position, timestamp,
)
from .snaptrade_read import ProviderFailure, SnapTradeReader

APP = 'snaptrade-personal'
PAGE_SIZE = 1000
PAGES_PER_CYCLE = 6
AUTH_FAILURES={'SNAPTRADE_AUTH','SNAPTRADE_SIGNATURE','SNAPTRADE_FORBIDDEN'}
BLOCKING = {'SNAPTRADE_RATE_LIMIT','SNAPTRADE_AUTH','SNAPTRADE_SIGNATURE'}
LOGGER=logging.getLogger(__name__)
RESULT_EVENT='ATTEMPT_RESULT'


def _attempt_detail(db,since):
    row=db.execute("SELECT action,observed_at,target FROM st_events WHERE action IN (?, 'ATTEMPT_STARTED') ORDER BY id DESC LIMIT 1",
                   (RESULT_EVENT,)).fetchone()
    if not row or row['action']!=RESULT_EVENT or row['observed_at']!=since:
        return None
    try:
        detail=json.loads(row['target'])
    except (TypeError,ValueError):
        return None
    return detail if isinstance(detail,dict) else None


@contextmanager
def _stage(stage,resource):
    try:
        yield
    except ProviderFailure as error:
        raise error.at(stage,resource) from None
    except (sqlite3.Error,SyncError):
        raise ProviderFailure('SNAPTRADE_STORAGE',stage='PERSISTENCE',resource=resource.upper()) from None


def credentials(db,settings):
    if not settings.snaptrade_enabled:
        return None
    row = db.execute('SELECT revision,key_id,nonce,ciphertext FROM st_credentials WHERE singleton=1').fetchone()
    if row:
        try:
            return load_keyring(settings.pluggy_keyring_path).open(
                APP,row['revision'],ProtectedCredential(row['key_id'],row['nonce'],row['ciphertext']))
        except CredentialProtectionError:
            raise SyncError('SNAPTRADE_CREDENTIALS_LOCKED',503) from None
    if settings.snaptrade_client_id and settings.snaptrade_consumer_key:
        return settings.snaptrade_client_id,settings.snaptrade_consumer_key
    return None


def credential_configured(db,settings):
    return bool(settings.snaptrade_enabled and (db.execute('SELECT 1 FROM st_credentials').fetchone()
        or settings.snaptrade_client_id and settings.snaptrade_consumer_key))


def _event(db,stamp,action,outcome,target=None):
    db.execute('INSERT INTO st_events(observed_at,action,target,outcome) VALUES (?,?,?,?)',
               (stamp,action,target,outcome))


def update_credentials(service,body):
    if set(body)!={'client_id','consumer_key'} or any(not isinstance(value,str) or
            not re.fullmatch(r'[!-~]{1,256}',value) for value in body.values()):
        raise SyncError('INVALID_REQUEST',422)
    if not service.settings.snaptrade_enabled:
        raise SyncError('SNAPTRADE_DISABLED',403)
    with closing(service._db()) as db, service._write(db):
        epoch,stamp=service._time()
        _check_mutation(db,epoch)
        revision=db.execute('SELECT coalesce(max(revision),0)+1 FROM st_credentials').fetchone()[0]
        try:
            sealed=load_keyring(service.settings.pluggy_keyring_path).seal(APP,revision,body['client_id'],body['consumer_key'])
        except CredentialProtectionError:
            raise SyncError('SNAPTRADE_CREDENTIALS_LOCKED',503) from None
        db.execute('''INSERT INTO st_credentials VALUES(1,?,?,?,?) ON CONFLICT(singleton) DO UPDATE SET
            revision=excluded.revision,key_id=excluded.key_id,nonce=excluded.nonce,ciphertext=excluded.ciphertext''',
            (revision,sealed.key_id,sealed.nonce,sealed.ciphertext))
        # Credentials may belong to a different Personal identity. Retain the
        # archive and wait for a new authorized discovery before showing it.
        db.execute("UPDATE st_connections SET provider_state='NOT_SEEN'")
        db.execute('UPDATE st_state SET error_code=NULL,next_attempt=0,revision=revision+1')
        _event(db,stamp,'CREDENTIALS','SAVED')
    return {'configured':True}


def _check_mutation(db,epoch):
    state=db.execute('SELECT * FROM st_state WHERE singleton=1').fetchone()
    if state['lease_token'] and state['lease_until']>epoch:
        raise SyncError('SNAPTRADE_BUSY',409)
    return state


def configure(service,body):
    if set(body)!={'auto_enabled','interval_hours','revision'} or type(body['auto_enabled']) is not bool or (
        type(body['interval_hours']) is not int or body['interval_hours'] not in HOURS or
        type(body['revision']) is not int or body['revision']<0):
        raise SyncError('INVALID_REQUEST',422)
    with closing(service._db()) as db, service._write(db):
        epoch,stamp=service._time()
        state=db.execute('SELECT * FROM st_state WHERE singleton=1').fetchone()
        if body['revision']!=state['revision']:
            raise SyncError('SYNC_PREFERENCES_CHANGED',409)
        if body['auto_enabled'] and not credential_configured(db,service.settings):
            raise SyncError('SNAPTRADE_DISABLED',403)
        hours=body['interval_hours']
        success=_datetime(state['last_success'])
        next_attempt=state['next_attempt']
        if success and not state['error_code']:
            next_attempt=int(success.timestamp()+hours*3600)
        db.execute('UPDATE st_state SET auto_enabled=?,interval_hours=?,revision=revision+1,next_attempt=? WHERE singleton=1',
                   (body['auto_enabled'],hours,next_attempt))
        _event(db,stamp,'PREFERENCES','SAVED')
    return {'saved':True}


def connection_policy(service,body):
    flags={'archived','paused','excluded'}
    if set(body)!={'connection_id'}|flags or any(type(body[name]) is not bool for name in flags) or (
            not isinstance(body['connection_id'],str) or not re.fullmatch(r'st-[a-f0-9]{64}',body['connection_id'])):
        raise SyncError('INVALID_REQUEST',422)
    with closing(service._db()) as db, service._write(db):
        epoch,stamp=service._time()
        _check_mutation(db,epoch)
        target=body['connection_id']
        if not db.execute('UPDATE st_connections SET archived=?,paused=?,excluded=? WHERE id=?',
                (body['archived'],body['paused'],body['excluded'],target)).rowcount:
            raise SyncError('CONNECTION_NOT_FOUND',404)
        _event(db,stamp,'CONNECTION_POLICY','SAVED',target)
    return {'saved':True}


def status(db,settings,epoch):
    state=db.execute('SELECT * FROM st_state WHERE singleton=1').fetchone()
    ready=credential_configured(db,settings)
    accounts=defaultdict(list)
    for row in db.execute('''SELECT a.id,a.connection_id,a.label,a.suffix,a.kind,a.state,a.observed_at,a.provider_updated_at,
            (SELECT count(*) FROM st_positions p WHERE p.account_id=a.id) AS positions,
            (SELECT group_concat(currency,',') FROM st_balances p WHERE p.account_id=a.id) AS currencies
            FROM st_accounts a ORDER BY a.label,a.id'''):
        accounts[row['connection_id']].append(dict(row))
    coverage=defaultdict(list)
    for row in db.execute('''SELECT account_id,resource,state,observed_at,error_code,first_date,last_date,retry_after
                             FROM st_checkpoints ORDER BY account_id,resource'''):
        item=dict(row)
        item['retry_at']=_epoch_iso(item.pop('retry_after')) if row['retry_after'] else None
        coverage[row['account_id']].append(item)
    rows=[]
    for connection in db.execute('SELECT * FROM st_connections ORDER BY institution,id'):
        matched=accounts[connection['id']]
        for account in matched:
            account['coverage']=coverage.get(account['id'],[])
        rows.append({**dict(connection),'provider':'SNAPTRADE','accounts':matched})
    running=bool(state['lease_token'] and state['lease_until']>epoch)
    attempt=None if running else _attempt_detail(db,state['last_attempt'])
    return {'enabled':settings.snaptrade_enabled,'configured':ready,'auto_enabled':ready and bool(state['auto_enabled']),
            'interval_hours':state['interval_hours'],'revision':state['revision'],'options':list(HOURS),'connections':rows,
            'last_attempt':state['last_attempt'],'last_success':state['last_success'],'error_code':state['error_code'],
            'next_attempt':_epoch_iso(max(epoch,state['next_attempt'])) if ready and (
                state['auto_enabled'] or state['error_code']=='SNAPTRADE_RATE_LIMIT') else None,
            'running':running,'last_result':'RUNNING' if running else (attempt or {}).get('state'),
            'last_attempt_result':attempt}


def _epoch_iso(epoch):
    from datetime import datetime, timezone
    return _iso(datetime.fromtimestamp(epoch,timezone.utc))


@contextmanager
def _write(service,db,token,check):
    check()
    with service._write(db,check=check):
        stamp=service._time()[1]
        guard=db.execute('SELECT lease_token,lease_until FROM st_state WHERE singleton=1').fetchone()
        if guard['lease_token']!=token or guard['lease_until']<=service._time()[0]:
            raise ProviderFailure('SNAPTRADE_LEASE_LOST')
        yield stamp


def _claim(service,db,automatic,request_id):
    epoch,stamp=service._time()
    with service._write(db):
        state = _check_mutation(db,epoch)
        if automatic and (not state['auto_enabled'] or state['next_attempt']>epoch):
            return None
        if state['error_code']=='SNAPTRADE_RATE_LIMIT' and state['next_attempt']>epoch:
            raise SyncError('SNAPTRADE_RATE_LIMIT',429)
        if not credential_configured(db,service.settings):
            if automatic:
                return None
            raise SyncError('SNAPTRADE_DISABLED',409)
        # This isolation applies even when a manual import races the background job.
        token=uuid4().hex
        db.execute('UPDATE st_state SET lease_token=?,lease_until=?,last_attempt=? WHERE singleton=1',(token,int(epoch)+240,stamp))
        _event(db,stamp,'ATTEMPT_STARTED','STARTED',request_id)
    return token,stamp


def _discovery(service,db,token,reader,secrets,check,ignore_pause=False):
    with _stage('DISCOVERY','connections'):
        normalized={}
        for row in collection(reader.read('connections')):
            remote,record=connection_record(row,secrets)
            if remote in normalized:
                raise invalid('id','DUPLICATE_IDENTIFIER')
            normalized[remote]=record
    check()
    with _stage('DISCOVERY','accounts'):
        body=reader.read('accounts')
        if not isinstance(body,dict):
            raise invalid('results','UNEXPECTED_ENVELOPE',stage='STRUCTURE')
        accounts=[]
        seen=set()
        for row in collection(field_value(body,'results',list,required=True,nullable=False),field='results'):
            remote,authorization,record=account_record(row,secrets)
            if remote in seen:
                raise invalid('id','DUPLICATE_IDENTIFIER')
            if authorization not in normalized:
                raise ProviderFailure('SNAPTRADE_SCOPE_MISMATCH',stage='NORMALIZATION',
                                      reason='UNMATCHED_CONNECTION',field='connection_id',remote_status=200)
            seen.add(remote)
            accounts.append((remote,normalized[authorization],record))
    pending=[]
    with _stage('PERSISTENCE','discovery'), _write(service,db,token,check) as stamp:
        db.execute("UPDATE st_connections SET provider_state='NOT_SEEN'")
        db.execute("UPDATE st_accounts SET state='NOT_SEEN'")
        for local in normalized.values():
            db.execute('''INSERT INTO st_connections(id,institution,brokerage,permission,provider_state,observed_at)
                VALUES (?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET institution=excluded.institution,
                brokerage=excluded.brokerage,permission=excluded.permission,provider_state=excluded.provider_state,
                observed_at=excluded.observed_at''',(*local,stamp))
        policies={r['id']:r for r in db.execute('SELECT id,archived,paused FROM st_connections')}
        for remote,connection,account in accounts:
            cid,_,brokerage,_,provider_state=connection
            label,kind,suffix,unique,state,updated=account
            aid=key('account',cid,remote)
            fingerprint=key('institution-account',brokerage.casefold(),unique) if unique else None
            db.execute('''INSERT INTO st_accounts(id,connection_id,label,kind,suffix,fingerprint,state,provider_updated_at,observed_at)
                VALUES (?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET label=excluded.label,kind=excluded.kind,suffix=excluded.suffix,
                fingerprint=excluded.fingerprint,state=excluded.state,provider_updated_at=excluded.provider_updated_at,
                observed_at=excluded.observed_at''',(aid,cid,label,kind,suffix,fingerprint,state,updated,stamp))
            if state=='AVAILABLE' and provider_state=='AVAILABLE' and not policies[cid]['archived'] and (
                    ignore_pause or not policies[cid]['paused']):
                pending.append((aid,remote,cid))
    return pending


def _checkpoint(db,account,resource,state,stamp,error=None,retry_after=None):
    db.execute('''INSERT INTO st_checkpoints(account_id,resource,state,observed_at,error_code,retry_after)
      VALUES(?,?,?,?,?,?) ON CONFLICT(account_id,resource) DO UPDATE SET state=excluded.state,
      observed_at=excluded.observed_at,error_code=excluded.error_code,retry_after=excluded.retry_after''',
      (account,resource,state,stamp,error,retry_after))


def _as_of(body):
    data=body.get('data_freshness') or {}
    return timestamp(data.get('as_of')) if isinstance(data,dict) else None


def _balances(db,aid,remote,body,stamp):
    if ident(field_value(body,'account_id',str,required=True,nullable=False),'account_id')!=remote:
        raise ProviderFailure('SNAPTRADE_SCOPE_MISMATCH',stage='NORMALIZATION',field='account_id',remote_status=200)
    margin=field_value(body,'margin',dict) or {}
    values=defaultdict(dict)
    for field,items in (('cash',field_value(body,'cash',list,required=True,nullable=False)),('power',body.get('buying_power')),('margin',margin.get('loan_balances'))):
        if items is None:
            continue
        for row in collection(items,('currency','amount')):
            currency=code(row['currency'])
            if not currency or field in values[currency]:
                raise invalid('currency','INVALID_OR_DUPLICATE_CURRENCY')
            values[currency][field]=financial_text(row,'amount')
    db.execute('DELETE FROM st_balances WHERE account_id=?',(aid,))
    db.executemany('INSERT INTO st_balances VALUES(?,?,?,?,?,?,?)',
        [(aid,currency,row.get('cash'),row.get('power'),row.get('margin'),_as_of(body),stamp) for currency,row in values.items()])
    net=field_value(body,'net_value',dict) or {}
    db.execute('UPDATE st_accounts SET net_value=?,net_currency=? WHERE id=?',
               (financial_text(net,'amount'),code(net.get('currency')),aid))
    _checkpoint(db,aid,'balances','AVAILABLE' if values else 'UNAVAILABLE',stamp)


def _positions(db,aid,body,stamp,secrets):
    rows=[position(row,_as_of(body),stamp,secrets) for row in collection(field_value(body,'results',list,required=True,nullable=False),('instrument',),field='results')]
    if len({row[0] for row in rows})!=len(rows):
        raise invalid('id','DUPLICATE_IDENTIFIER')
    complete=all((row[6] is not None and row[9] is not None) or row[14] for row in rows)
    empty_cache=not db.execute('SELECT 1 FROM st_positions WHERE account_id=? LIMIT 1',(aid,)).fetchone()
    if not complete and not empty_cache:
        _checkpoint(db,aid,'positions','PARTIAL',stamp)
        return False,None
    identified={row[0] for row in db.execute("SELECT instrument_id FROM st_positions WHERE account_id=? AND kind='reit'",(aid,))}
    rows=[(*row[:3],'reit',*row[4:]) if row[0] in identified and row[3] in ('stock','other','preferred_stock') else row for row in rows]
    db.execute('DELETE FROM st_positions WHERE account_id=?',(aid,))
    db.executemany('INSERT INTO st_positions VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',[
        (aid,*row[:-1],json.dumps(row[-1]) if row[-1] is not None else None) for row in rows])
    _checkpoint(db,aid,'positions','AVAILABLE' if complete else 'PARTIAL',stamp)
    return complete,_as_of(body)


def _capture(db,aid,reference,stamp):
    if not reference or day(reference)>day(stamp):
        return
    totals=defaultdict(Decimal)
    with localcontext() as ctx:
        ctx.prec=82
        for row in db.execute('SELECT instrument_id,currency,market_value FROM st_positions WHERE account_id=? AND cash_equivalent=0',(aid,)):
            totals[row['currency']]+=Decimal(row['market_value'])
            db.execute('''INSERT INTO st_position_snapshots VALUES(?,?,?,?,?,?,?)
              ON CONFLICT(account_id,instrument_id,currency,reference_date) DO UPDATE SET
              reference_at=excluded.reference_at,observed_at=excluded.observed_at,market_value=excluded.market_value
              WHERE excluded.reference_at>=st_position_snapshots.reference_at
                AND excluded.market_value<>st_position_snapshots.market_value''',
              (aid,row['instrument_id'],row['currency'],day(reference),reference,stamp,row['market_value']))
    cash={item['currency']:item['cash'] for item in db.execute('SELECT * FROM st_balances WHERE account_id=?',(aid,))
          if item['cash'] is not None and day(item['reference_at'])==day(reference)}
    for currency in totals.keys() | cash.keys():
        db.execute('''INSERT INTO st_snapshots VALUES(?,?,?,?,?,?,?)
           ON CONFLICT(account_id,currency,reference_date) DO UPDATE SET reference_at=excluded.reference_at,
           observed_at=excluded.observed_at,market_value=excluded.market_value,cash=excluded.cash
           WHERE excluded.reference_at>=st_snapshots.reference_at
           AND (excluded.market_value<>st_snapshots.market_value OR excluded.cash IS NOT st_snapshots.cash)''',
           (aid,currency,day(reference),reference,stamp,format(totals[currency],'f'),cash.get(currency)))


def _read_page(reader,remote,start,end,offset,limit):
    data=reader.read('activities',account_id=remote,start_date=date.fromisoformat(start) if start else None,
                     end_date=date.fromisoformat(end),offset=offset,limit=limit)
    if not isinstance(data,dict):
        raise invalid('data','UNEXPECTED_ENVELOPE',stage='STRUCTURE')
    pagination=field_value(data,'pagination',dict,required=True,nullable=False)
    rows=collection(field_value(data,'data',list,required=True,nullable=False),('id','type','trade_date'),field='data')
    for row in rows:
        external=field_value(row,'id',str,required=True,nullable=False)
        if not external or len(external)>256:
            raise invalid('id','INVALID_IDENTIFIER')
        account=field_value(row,'account',dict)
        if account is not None and ident(field_value(account,'id',str,required=True,nullable=False))!=remote:
            raise ProviderFailure('SNAPTRADE_SCOPE_MISMATCH',stage='NORMALIZATION',field='account',remote_status=200)
    count=field_value(pagination,'total',int,required=True,nullable=False)
    if type(count) is not int or count<0 or count>10_000_000 or len(rows)>limit or (
        count>offset and not rows) or (rows and offset+len(rows)>count):
        raise ProviderFailure('SNAPTRADE_INVALID_PAGINATION',stage='STRUCTURE',field='pagination',remote_status=200)
    return rows,count


def _activities(service,db,token,reader,aid,remote,secrets,check):
    checkpoint=db.execute("SELECT * FROM st_checkpoints WHERE account_id=? AND resource='activities'",(aid,)).fetchone()
    end=str(service.clock.today())
    start=None
    offset=0
    if checkpoint and checkpoint['next_offset'] and checkpoint['window_end']:
        start,end,offset=checkpoint['window_start'],checkpoint['window_end'],checkpoint['next_offset']
        check()
        anchor,_=_read_page(reader,remote,start,end,offset-1,1)
        if not anchor or key('activity',anchor[0]['id'])!=checkpoint['page_anchor']:
            offset=0
    elif checkpoint and checkpoint['last_date']:
        start=(date.fromisoformat(checkpoint['last_date'])-timedelta(days=30)).isoformat()
    for _ in range(PAGES_PER_CYCLE):
        check()
        rows,total=_read_page(reader,remote,start,end,offset,PAGE_SIZE)
        today=str(service.clock.today())
        if any(not day(row['trade_date']) or day(row['trade_date'])>today for row in rows):
            raise invalid('trade_date','INVALID_TIMESTAMP')
        with _write(service,db,token,check) as stamp:
            records=[activity(row,stamp,secrets) for row in rows]
            if len({record[0] for record in records})!=len(records):
                raise ProviderFailure('SNAPTRADE_INVALID_PAGINATION',stage='STRUCTURE',field='pagination',remote_status=200)
            db.executemany('''INSERT INTO st_activities VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(account_id,activity_id) DO UPDATE SET kind=excluded.kind,provider_kind=excluded.provider_kind,
               date=excluded.date,settled=excluded.settled,ticker=excluded.ticker,instrument_id=excluded.instrument_id,
               description=excluded.description,currency=excluded.currency,amount=excluded.amount,units=excluded.units,
               price=excluded.price,fee=excluded.fee,observed_at=excluded.observed_at''',[(aid,*row) for row in records])
            reits={record[6] for row,record in zip(rows,records)
                   if not row.get('option_symbol') and record[6] and is_reit(row.get('symbol'))}
            if reits:
                db.executemany("UPDATE st_positions SET kind='reit' WHERE account_id=? AND instrument_id=? AND kind IN ('stock','other','preferred_stock')",
                               [(aid,instrument_id) for instrument_id in reits])
            offset+=len(records)
            complete=offset>=total
            _checkpoint(db,aid,'activities','AVAILABLE' if complete else 'PARTIAL',stamp)
            first,last=db.execute('SELECT min(date),max(date) FROM st_activities WHERE account_id=?',(aid,)).fetchone()
            db.execute('''UPDATE st_checkpoints SET window_start=?,window_end=?,next_offset=?,page_anchor=?,
                       first_date=?,last_date=? WHERE account_id=? AND resource='activities' ''',
                       (start,end,0 if complete else offset,records[-1][0] if records and not complete else None,first,last,aid))
            if complete:
                return True
    return False


def _import_resource(service,db,token,reader,aid,remote,resource,secrets,check,balances_ok):
    with _stage('NORMALIZATION',resource):
        if resource=='activities':
            return _activities(service,db,token,reader,aid,remote,secrets,check)
        body=reader.read(resource,account_id=remote)
        if not isinstance(body,dict):
            raise invalid(reason='UNEXPECTED_ENVELOPE',stage='STRUCTURE')
        with _write(service,db,token,check) as stamp:
            if resource=='balances':
                _balances(db,aid,remote,body,stamp)
                return True
            complete,reference=_positions(db,aid,body,stamp,secrets)
            if complete and reference and balances_ok:
                _capture(db,aid,reference,stamp)
            return complete


def sync(service,*,automatic=False,discover=False,connection=None,reader_factory=SnapTradeReader,stop=None,request_id=None):
    if not isinstance(request_id,str) or not re.fullmatch('[a-f0-9]{32}',request_id):
        request_id=uuid4().hex
    phase='DISCOVERY' if discover else 'SYNC'
    deadline=time.monotonic()+200
    def check():
        if (stop and stop.is_set()) or time.monotonic()>deadline:
            raise ProviderFailure('SNAPTRADE_INTERRUPTED',stage='CONTROL')
    with closing(service._db()) as db:
        claimed=_claim(service,db,automatic,request_id)
        if not claimed:
            return {'state':'NOT_DUE'}
        token,started=claimed
        failure=None
        result='AVAILABLE'
        try:
            try:
                secrets=credentials(db,service.settings)
            except SyncError as error:
                raise ProviderFailure(error.code,stage='CONFIGURATION',resource='CLIENT') from None
            try:
                reader=reader_factory(*secrets)
            except ProviderFailure:
                raise
            except Exception:
                raise ProviderFailure('SNAPTRADE_SDK_CALL',stage='SDK_INIT',resource='CLIENT') from None
            pending=_discovery(service,db,token,reader,secrets,check,ignore_pause=connection is not None and not automatic)
            if connection and not db.execute('SELECT 1 FROM st_connections WHERE id=?',(connection,)).fetchone():
                raise ProviderFailure('SNAPTRADE_UNAVAILABLE',stage='CONTROL',resource='CONNECTIONS')
            for aid,remote,cid in ([] if discover else pending):
                if connection and cid!=connection:
                    continue
                retry_at=db.execute('SELECT max(retry_after) FROM st_checkpoints WHERE account_id=?',(aid,)).fetchone()[0]
                if retry_at and retry_at>service._time()[0]:
                    result='PARTIAL'
                    failure=ProviderFailure('SNAPTRADE_ACCOUNT_RATE_LIMIT',stage='CONTROL',resource='ACCOUNTS')
                    continue
                balances_ok=False
                for resource in ('balances','positions','activities'):
                    try:
                        check()
                        complete=_import_resource(service,db,token,reader,aid,remote,resource,secrets,check,balances_ok)
                        if resource=='balances':
                            balances_ok=complete
                        if not complete:
                            result='PARTIAL'
                    except ProviderFailure as error:
                        failure=error.at('COLLECTION',resource)
                        if error.code in BLOCKING or error.code in ('SNAPTRADE_INTERRUPTED','SNAPTRADE_LEASE_LOST'):
                            raise
                        result='PARTIAL'
                        account_rate=error.code=='SNAPTRADE_ACCOUNT_RATE_LIMIT'
                        with _stage('PERSISTENCE',resource), _write(service,db,token,check) as stamp:
                            retry_after=int(service._time()[0])+error.retry if account_rate else None
                            state='UNAVAILABLE' if error.code in ('SNAPTRADE_UNAVAILABLE','SNAPTRADE_FORBIDDEN') else 'FAILED'
                            _checkpoint(db,aid,resource,state,stamp,error.code,retry_after)
                        if account_rate:
                            break
        except ProviderFailure as error:
            failure=error.at('CONTROL','client')
            result='PARTIAL' if result=='PARTIAL' else 'FAILED'
        except (sqlite3.Error,SyncError):
            failure=ProviderFailure('SNAPTRADE_STORAGE',stage='PERSISTENCE',resource='STATUS')
            result='FAILED'
        except Exception:
            failure=ProviderFailure('SNAPTRADE_IMPORT_FAILED',stage='INTERNAL',resource='CLIENT')
            result='FAILED'
        epoch,stamp=service._time()
        attempt={'state':result,'phase':phase,'request_id':request_id,'attempted_at':started}
        if failure:
            attempt.update(failure.diagnostic())
        try:
            with service._write(db):
                current=db.execute('SELECT * FROM st_state WHERE singleton=1').fetchone()
                if current['lease_token']!=token:
                    raise SyncError('SNAPTRADE_LEASE_LOST',409)
                retry=failure.retry if failure and failure.code!='SNAPTRADE_ACCOUNT_RATE_LIMIT' else 0
                delay=max(retry,86400 if failure and failure.code in AUTH_FAILURES else
                          300 if result!='AVAILABLE' else current['interval_hours']*3600)
                successful=result=='AVAILABLE' and not discover
                next_attempt=current['next_attempt'] if discover and not failure else int(epoch)+delay
                db.execute('''UPDATE st_state SET lease_token=NULL,lease_until=NULL,next_attempt=?,last_success=?,
                           error_code=? WHERE singleton=1''',
                           (next_attempt,stamp if successful else current['last_success'],failure.code if failure else None))
                _event(db,started,RESULT_EVENT,result,json.dumps(attempt,separators=(',',':')))
        except (sqlite3.Error,SyncError):
            failure=ProviderFailure('SNAPTRADE_STORAGE',stage='PERSISTENCE',resource='STATUS')
            result='FAILED'
            attempt={'state':result,'phase':phase,'request_id':request_id,'attempted_at':started,**failure.diagnostic()}
        if failure or result=='PARTIAL':
            LOGGER.warning('SNAPTRADE_ATTEMPT %s',json.dumps(attempt,separators=(',',':')))
        return {'state':result,'error_code':failure.code if failure else None,'diagnostic':attempt}


class SnapTradeWorker:
    def __init__(self,settings):
        self.service=OpenFinanceService(settings)
        self.event=threading.Event()
        self.thread=None

    def start(self):
        if self.service.settings.snaptrade_enabled:
            self.thread=threading.Thread(target=self._loop,name='snaptrade-cache',daemon=True)
            self.thread.start()

    def _loop(self):
        while not self.event.is_set():
            try:
                sync(self.service,automatic=True,stop=self.event)
            except Exception:
                # The separate worker must neither log provider exceptions nor stop Pluggy.
                pass
            self.event.wait(15)

    def stop(self):
        self.event.set()
        if self.thread:
            self.thread.join(timeout=1)
