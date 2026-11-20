"""Owner preferences and restart-safe scheduling over local run history."""
from datetime import datetime, timedelta, timezone
import json
from math import ceil

from .open_finance_registry import connection_views

HOURS = (1,2,4,6,12,24,48)
TRANSIENT_RETRY_SECONDS = 300
ACTION_REQUIRED = {'AUTH_FAILED','CONSENT_EXPIRED','CONSENT_NOT_ACTIVE',
                   'ITEM_REAUTH_REQUIRED','ITEM_USER_ACTION_REQUIRED','ITEM_ACCESS_DENIED'}


def preferences(db, settings):
    row = db.execute('SELECT enabled,interval_hours,revision FROM of_sync_preferences WHERE singleton=1').fetchone()
    return (bool(row['enabled']),row['interval_hours'],row['revision']) if row else (True,settings.open_finance_sync_interval_hours,0)


def supervisor_allows(settings, connection):
    return settings.open_finance_auto_sync_allowed is not False and connection.enabled


def allowed(settings, connection):
    return supervisor_allows(settings,connection) and connection.auto_sync_enabled


def policy_reason(settings,connection,enabled):
    if connection.historical or connection.lifecycle=='ARCHIVED':
        return 'ARCHIVED'
    if connection.lifecycle=='DRAFT':
        return 'NOT_ACTIVATED'
    if not connection.enabled:
        return 'CONNECTION_DISABLED'
    if settings.open_finance_auto_sync_allowed is False:
        return 'SUPERVISOR_DISABLED'
    if not enabled:
        return 'GLOBAL_PREFERENCE_DISABLED'
    if not connection.auto_sync_enabled:
        return 'CONNECTION_AUTO_DISABLED'
    return None


def _datetime(value):
    if not isinstance(value,str) or len(value)>50:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace('Z','+00:00'))
        return parsed.astimezone(timezone.utc) if parsed.tzinfo else None
    except ValueError:
        return None


def _iso(value):
    return value.isoformat(timespec='seconds').replace('+00:00','Z') if value else None


def run_state(db, connection, interval, now):
    latest = db.execute("""SELECT started_at, finished_at, state, error_code FROM of_sync_runs
        WHERE connection_id=? ORDER BY rowid DESC LIMIT 1""",(connection,)).fetchone()
    success = db.execute("""SELECT r.finished_at FROM of_sync_runs r WHERE r.connection_id=?
        AND r.state='SUCCEEDED' AND (r.actor='AUTO:coverage' OR EXISTS
        (SELECT 1 FROM of_domain_sync_audit a WHERE a.connection_id=r.connection_id AND a.run_id=r.id))
        ORDER BY r.rowid DESC LIMIT 1""",(connection,)).fetchone()
    success_at = _datetime(success['finished_at']) if success else None
    next_at = success_at+timedelta(hours=interval) if success_at and success_at<=now else now
    failed = latest and latest['state']=='FAILED'
    if failed:
        end = _datetime(latest['finished_at'])
        if end and end<=now:
            wait = min(86400,interval*3600) if latest['error_code'] in ACTION_REQUIRED else TRANSIENT_RETRY_SECONDS
            next_at = end+timedelta(seconds=wait)
    return latest,success_at,next_at


def claim_delay(db,connection,interval,now):
    latest,_,next_at = run_state(db,connection,interval,now)
    return ('AUTO_SYNC_BACKOFF' if latest and latest['state'] in ('FAILED','INTERRUPTED') else 'AUTO_SYNC_RECENT',
            max(0,ceil((next_at-now).total_seconds())))


def legacy_binding_mismatches(db,settings):
    from .open_finance import OpenFinanceService
    bindings={row['id']:row['binding_hash'] for row in db.execute(
        "SELECT c.id,c.binding_hash FROM of_connections c LEFT JOIN of_connection_registry r ON r.connection_id=c.id "
        "WHERE r.source IS NULL OR r.source='LEGACY'")}
    return {cfg.id for cfg in settings.pluggy_connections if cfg.id in bindings and
            bindings[cfg.id]!=OpenFinanceService._binding(cfg)}


def report(db,settings,now):
    enabled,interval,revision = preferences(db,settings)
    views = connection_views(db,settings)
    mismatched=legacy_binding_mismatches(db,settings)
    revisions={row['connection_id']:row['revision'] for row in db.execute(
        'SELECT connection_id,revision FROM of_connection_registry')}
    permission = any(supervisor_allows(settings,view) and view.id not in mismatched for view in views.values())
    rows = []
    for view in views.values():
        reason=policy_reason(settings,view,enabled)
        if not reason and view.id in mismatched:
            reason='CONNECTION_BINDING_CHANGED'
        effective=reason is None
        latest,success,next_at = run_state(db,view.id,interval,now)
        item = db.execute("""SELECT payload_json, observed_at FROM of_resource_records
            WHERE resource='item' AND connection_id=? AND state='PRESENT' LIMIT 1""",(view.id,)).fetchone()
        data = json.loads(item['payload_json']) if item else {}
        provider_next = _datetime(data.get('nextAutoSyncAt'))
        rows.append({'connection_id':view.id,'institution':view.institution,'effective':effective,'reason':reason,
            'lifecycle':view.lifecycle,'requested_enabled':view.auto_sync_enabled,'revision':revisions.get(view.id,0),
            'policy_editable':view.enabled and not view.historical and view.id not in mismatched
                and (supervisor_allows(settings,view) or view.auto_sync_enabled),
            'action_required':latest['error_code'] if latest and latest['error_code'] in ACTION_REQUIRED else None,
            'last_pluggy_update':_iso(_datetime(data.get('lastUpdatedAt'))),
            'metadata_observed_at':item['observed_at'] if item else None,
            'next_pluggy_update':_iso(provider_next) if provider_next and provider_next>now else None,
            'last_success':_iso(success),'last_attempt':latest['started_at'] if latest else None,
            'next_attempt':_iso(max(now,next_at)) if effective and (not latest or latest['state']!='RUNNING') else None,
            'state':latest['state'] if latest else 'NOT_RUN',
            'last_error':latest['error_code'] if latest else None})
    return {'requested_enabled':enabled,'effective_enabled':any(row['effective'] for row in rows),'available':permission,
            'interval_hours':interval,'revision':revision,'interval_options':list(HOURS),'connections':rows}


def save(service,body):
    from .open_finance import SyncError
    from contextlib import closing
    if (set(body)!={'enabled','interval_hours','revision'} or type(body['enabled']) is not bool or
            type(body['interval_hours']) is not int or body['interval_hours'] not in HOURS or
            type(body['revision']) is not int or body['revision']<0):
        raise SyncError('INVALID_REQUEST',422)
    _,stamp=service._time()
    with closing(service._db()) as db, service._write(db):
        before,old_interval,revision = preferences(db,service.settings)
        if revision!=body['revision']:
            raise SyncError('SYNC_PREFERENCES_CHANGED',409)
        mismatched=legacy_binding_mismatches(db,service.settings)
        if body['enabled'] and not any(supervisor_allows(service.settings,view) and view.id not in mismatched
                                      for view in connection_views(db,service.settings).values()):
            raise SyncError('AUTO_SYNC_DISABLED',403)
        interval = body['interval_hours']
        enabled = body['enabled']
        if (before,old_interval)!=(enabled,interval) or not revision:
            db.execute("""INSERT INTO of_sync_preferences VALUES (1,?,?,?)
                ON CONFLICT(singleton) DO UPDATE SET enabled=excluded.enabled,interval_hours=excluded.interval_hours,
                revision=excluded.revision""",(enabled,interval,revision+1))
            db.execute("INSERT INTO of_sync_preference_events VALUES (?,?,'UI:local',?,?)",
                       (revision+1,stamp,enabled,interval))
        return report(db,service.settings,_datetime(stamp))
