"""Owner-only extended staging. Lease/fencing and legacy projections are reused."""
from contextlib import closing, nullcontext
import json
import re
import sqlite3

from .db import immediate_transaction
from .open_finance import SyncError, OpenFinanceService
from .pluggy_client import ExternalAccount, PluggyError
from .pluggy_coverage import RESOURCES, project
from .open_finance_diagnostics import emit


def _batch(service, c, config, run_id, token, batch, *, in_transaction=False):
    resource, parent = batch['resource'], batch['parent']
    if in_transaction and not c.in_transaction:
        raise SyncError('STORAGE_TRANSACTION_REQUIRED', 503)
    with nullcontext() if in_transaction else immediate_transaction(c):
        stamp = service._guard(c, config.id, run_id, token)
        c.execute('INSERT INTO of_resource_coverage(connection_id,resource,parent_id,run_id,state,observed_at) '
                  "VALUES(?,?,?,?,'RUNNING',?) ON CONFLICT(connection_id,resource,parent_id) DO UPDATE SET "
                  'run_id=excluded.run_id,state=excluded.state,page_count=0,record_count=0,omitted_field_count=0,error_code=NULL,observed_at=excluded.observed_at '
                  'WHERE of_resource_coverage.run_id<>excluded.run_id', (config.id, resource, parent, run_id, stamp))
        omitted_total = 0
        for raw in batch['rows']:
            payload, encoded, digest, omitted = project(resource, raw)
            omitted_total += omitted
            external = raw.get('resourceId') if resource == 'resources' else raw['id']
            identity = (config.id, resource, parent, external)
            old = c.execute('SELECT payload_hash,state FROM of_resource_records WHERE connection_id=? AND resource=? AND parent_id=? AND external_id=?', identity).fetchone()
            c.execute('INSERT INTO of_resource_records(connection_id,resource,parent_id,external_id,payload_json,payload_hash,state,first_run_id,last_run_id,observed_at) '
                      "VALUES(?,?,?,?,?,?,'PRESENT',?,?,?) ON CONFLICT(connection_id,resource,parent_id,external_id) DO UPDATE SET "
                      "payload_json=excluded.payload_json,payload_hash=excluded.payload_hash,state='PRESENT',last_run_id=excluded.last_run_id,observed_at=excluded.observed_at",
                      identity + (encoded, digest, run_id, run_id, stamp))
            if old is None or old['payload_hash'] != digest or old['state'] != 'PRESENT':
                c.execute('INSERT INTO of_resource_revisions(connection_id,resource,parent_id,external_id,run_id,observed_at,payload_json,payload_hash,state) '
                          "VALUES(?,?,?,?,?,?,?,?,'PRESENT')", identity + (run_id, stamp, encoded, digest))
        state = batch['state']
        c.execute('UPDATE of_resource_coverage SET page_count=page_count+1,record_count=record_count+?,omitted_field_count=omitted_field_count+?,state=?,observed_at=? '
                  'WHERE connection_id=? AND resource=? AND parent_id=? AND run_id=?',
                  (len(batch['rows']), omitted_total, state if batch['last'] else 'RUNNING', stamp, config.id, resource, parent, run_id))
        # Absence is only observed after an exhausted, successful full collection.
        # NOT_SEEN never asserts provider deletion, and never deletes historical rows.
        if batch['last'] and state == 'AVAILABLE':
            missing = c.execute("SELECT * FROM of_resource_records WHERE connection_id=? AND resource=? AND parent_id=? AND last_run_id<>? AND state='PRESENT'",
                                (config.id, resource, parent, run_id)).fetchall()
            for row in missing:
                identity = (config.id, resource, parent, row['external_id'])
                c.execute("UPDATE of_resource_records SET state='NOT_SEEN',observed_at=?,last_run_id=? WHERE connection_id=? AND resource=? AND parent_id=? AND external_id=?", (stamp,run_id) + identity)
                c.execute('INSERT INTO of_resource_revisions(connection_id,resource,parent_id,external_id,run_id,observed_at,payload_json,payload_hash,state) '
                          "VALUES(?,?,?,?,?,?,?,?,'NOT_SEEN')", identity + (run_id, stamp, row['payload_json'], row['payload_hash']))
            if not c.execute("SELECT 1 FROM of_resource_records WHERE connection_id=? AND resource=? AND parent_id=? AND state='PRESENT'", (config.id, resource, parent)).fetchone():
                c.execute("UPDATE of_resource_coverage SET state='EMPTY' WHERE connection_id=? AND resource=? AND parent_id=?", (config.id, resource, parent))


def sync_full(service, connection_id, *, actor):
    if actor != 'UI:local':
        raise SyncError('OWNER_REQUIRED', 403)
    return _sync_full(service, connection_id, actor=actor)


def sync_full_automatic(service, connection_id, *, check, minimum_interval=0):
    """Internal worker entry; never exposed through HTTP or MCP authorization."""
    config = service.config.get(connection_id)
    if config is None or not config.auto_sync_enabled:
        raise SyncError('AUTO_SYNC_DISABLED', 403)
    return _sync_full(service, connection_id, actor='AUTO:coverage', check=check, minimum_interval=minimum_interval)


def _sync_full(service, connection_id, *, actor, check=lambda: None, minimum_interval=0):
    check()
    config = service.config.get(connection_id)
    if config is None:
        raise SyncError('CONNECTION_NOT_FOUND', 404)
    if not config.enabled:
        raise SyncError('CONNECTION_DISABLED')
    with closing(service._db()) as c:
        try:
            run_id, token = service._claim(c, config, actor, None, None, minimum_interval=minimum_interval)
        except sqlite3.Error:
            raise SyncError('STORAGE_BUSY', 503) from None
        error = None
        try:
            client = service.client_factory(config)
            for batch in client.coverage_pages():
                check()
                service._touch(c, config.id, run_id, token)
                # Persist complete safe projections alongside existing OF-L2 rows.
                with immediate_transaction(c):
                    if batch['resource'] == 'accounts':
                        accounts = [ExternalAccount(config.id, row['id'], row.get('name'), row.get('type'),
                            row.get('subtype'), row.get('currencyCode'), row.get('updatedAt')) for row in batch['rows']]
                        service._accounts(c, config, run_id, token, accounts, in_transaction=True)
                    elif batch['resource'] == 'transactions':
                        records = [client._transaction(row, batch['parent']) for row in batch['rows']]
                        service._page(c, config, run_id, token, batch['parent'], records, in_transaction=True)
                    _batch(service, c, config, run_id, token, batch, in_transaction=True)
                    check()  # Cancellation before commit rolls back this complete page.
        except PluggyError as exc:
            emit(config.id, run_id, exc)
            error = exc.code
        except SyncError as exc:
            emit(config.id, run_id, exc)
            error = exc.code
        except (sqlite3.Error, ValueError, RuntimeError):
            error = 'COVERAGE_INVALID_OR_STORAGE_FAILURE'
        except Exception:
            error = 'COVERAGE_INTERNAL_FAILURE'
        interrupted = error == 'AUTO_SYNC_CANCELLED' and actor == 'AUTO:coverage'
        try:
            if error:
                with immediate_transaction(c):
                    # An expired worker may not write over a newer worker's diagnostics.
                    stamp = service._guard(c, config.id, run_id, token)
                    c.execute("UPDATE of_resource_coverage SET state='FAILED',error_code=?,observed_at=? WHERE run_id=? AND state='RUNNING'", (error, stamp, run_id))
            return service._finish(c, config, run_id, token, error, interrupted=interrupted)
        except sqlite3.Error:
            if interrupted:
                # Do not pretend the lease was released when storage refuses cleanup.
                # The existing finite expiry and fencing remain authoritative.
                raise SyncError('CANCELLATION_FINALIZATION_DEFERRED', 503) from None
            raise


def query(c, settings, values):
    allowed = {'resource', 'connection_id', 'parent_id', 'state', 'page', 'page_size', 'type', 'currency', 'history'}
    if set(values) - allowed or any(len(v) != 1 for v in values.values()):
        raise SyncError('INVALID_QUERY', 422)
    resource = values.get('resource', ['accounts'])[0]
    if resource not in RESOURCES:
        raise SyncError('INVALID_RESOURCE', 422)
    def integer(name, default):
        raw = values.get(name, [str(default)])[0]
        if not re.fullmatch('[1-9][0-9]{0,7}', raw):
            raise SyncError('INVALID_PAGINATION', 422)
        return int(raw)
    page, size = integer('page', 1), integer('page_size', 25)
    if size not in (25, 50, 100):
        raise SyncError('INVALID_PAGINATION', 422)
    clauses, args = ['resource=?'], [resource]
    for name in ('connection_id', 'parent_id', 'state'):
        if name in values:
            value = values[name][0]
            if not value or len(value) > 200 or any(ord(ch) < 32 for ch in value):
                raise SyncError('INVALID_QUERY', 422)
            if name == 'state' and value not in ('PRESENT', 'NOT_SEEN'):
                raise SyncError('INVALID_QUERY', 422)
            if name == 'connection_id' and value not in {x.id for x in settings.pluggy_connections}:
                raise SyncError('CONNECTION_NOT_FOUND', 404)
            clauses.append(name + '=?')
            args.append(value)
    coverage_clauses = [clause for clause in clauses if clause != 'state=?']
    coverage_args = [value for clause, value in zip(clauses, args) if clause != 'state=?']
    for name, expression in (('type', "json_extract(payload_json,'$.type')"), ('currency', "COALESCE(json_extract(payload_json,'$.currencyCode'),json_extract(payload_json,'$.totalAmountCurrencyCode'))")):
        if name in values:
            if not re.fullmatch('[A-Za-z0-9_-]{1,64}', values[name][0]):
                raise SyncError('INVALID_QUERY', 422)
            clauses.append(expression + '=?')
            args.append(values[name][0])
    history = values.get('history', ['0'])[0]
    if history not in ('0', '1'):
        raise SyncError('INVALID_QUERY', 422)
    where = ' AND '.join(clauses)
    # Counts, rows and coverage share one read view.
    c.execute('BEGIN')
    try:
        table = 'of_resource_revisions' if history == '1' else 'of_resource_records'
        order = 'id DESC' if history == '1' else 'connection_id,parent_id,external_id'
        total = c.execute('SELECT COUNT(*) FROM ' + table + ' WHERE ' + where, args).fetchone()[0]
        rows = c.execute('SELECT * FROM ' + table + ' WHERE ' + where +
                         ' ORDER BY ' + order + ' LIMIT ? OFFSET ?', args + [size, (page - 1) * size]).fetchall()
        keys = ('connection_id', 'parent_id', 'external_id', 'state', 'run_id', 'observed_at') if history == '1' else ('connection_id', 'parent_id', 'external_id', 'state', 'first_run_id', 'last_run_id', 'observed_at')
        items = [{**{k: row[k] for k in keys},
                  'data': json.loads(row['payload_json'])} for row in rows]
        coverage = [dict(row) for row in c.execute('SELECT * FROM of_resource_coverage WHERE ' +
                    ' AND '.join(coverage_clauses), coverage_args)]
        return {'resource': resource, 'items': items, 'total': total, 'page': page, 'page_size': size,
                'has_more': page * size < total, 'history': history == '1', 'coverage': coverage, 'source': 'CACHED_STAGING',
                'net_worth': {'state': 'NOT_ESTABLISHED', 'reason': 'CURRENCY_AND_OVERLAP_NOT_PROVEN'}}
    finally:
        c.rollback()


def coverage_status(c, settings=None):
    return {'coverage': [dict(row) for row in c.execute('SELECT * FROM of_resource_coverage ORDER BY connection_id,resource,parent_id')],
            'runs': [dict(row) for row in c.execute('SELECT id,connection_id,state,error_code FROM of_sync_runs ORDER BY rowid DESC LIMIT 25')],
            'automatic_sync': bool(settings and any(x.enabled and x.auto_sync_enabled for x in settings.pluggy_connections)), 'remote_updates': False}
