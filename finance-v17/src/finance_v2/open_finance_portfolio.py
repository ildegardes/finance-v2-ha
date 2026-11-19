"""Prospective, complete investment observations. Never infer positions from cash flows."""
from collections import defaultdict
from calendar import monthrange
from datetime import date
from decimal import Decimal, localcontext
import json
import re

from .open_finance_query import civil


def capture_snapshot(db, connection, run, parse_amount):
    checkpoint = db.execute("""SELECT state,record_count FROM of_resource_coverage
        WHERE connection_id=? AND resource='investments' AND parent_id='' AND run_id=?""",
        (connection,run)).fetchone()
    # An empty result cannot establish zero market value.
    if not checkpoint or checkpoint['state']!='AVAILABLE' or not checkpoint['record_count']:
        return
    item = db.execute("""SELECT payload_json FROM of_resource_records
        WHERE connection_id=? AND resource='item' AND state='PRESENT' AND last_run_id=? LIMIT 1""",
        (connection,run)).fetchone()
    if item:
        data = json.loads(item['payload_json'])
        status = data.get('statusDetail') or {}
        detail = status.get('investments') or {}
        if (data.get('status')=='OUTDATED' or data.get('executionStatus') in ('PARTIAL_SUCCESS','ERROR')
                or detail.get('isUpdated') is False):
            return
    records = db.execute("""SELECT external_id,payload_json,observed_at FROM of_resource_records
        WHERE connection_id=? AND resource='investments' AND parent_id='' AND state='PRESENT' AND last_run_id=?""",
        (connection,run)).fetchall()
    if len(records)!=checkpoint['record_count']:
        return
    positions = []
    for record in records:
        data = json.loads(record['payload_json'],parse_float=Decimal)
        currency, value = data.get('currencyCode'), parse_amount(data.get('balance'))
        if not isinstance(currency,str) or not re.fullmatch('[A-Z]{3}',currency) or value is None:
            return
        positions.append((run,connection,record['external_id'],currency,format(value,'f'),
                          civil(data.get('date')),record['observed_at']))
    previous = db.execute('''SELECT p.run_id FROM of_portfolio_snapshots p
        JOIN of_sync_runs r ON r.id=p.run_id WHERE p.connection_id=? AND r.state='SUCCEEDED'
        ORDER BY r.rowid DESC LIMIT 1''',(connection,)).fetchone()
    if previous:
        already = {tuple(row) for row in db.execute('''SELECT external_id,currency,value,reference_date
            FROM of_portfolio_snapshots WHERE run_id=? AND connection_id=?''',(previous['run_id'],connection))}
        if {(external,currency,Decimal(value),reference)
            for external,currency,value,reference in already} == {
            (external,currency,Decimal(value),reference) for _,_,external,currency,value,reference,_ in positions}:
            return
    db.executemany("""INSERT INTO of_portfolio_snapshots(run_id,connection_id,external_id,currency,value,reference_date,observed_at)
        VALUES (?,?,?,?,?,?,?) ON CONFLICT(run_id,connection_id,external_id) DO NOTHING""",positions)


def window_start(today,window):
    if window=='all':
        return '0001-01-01'
    civil_today=date.fromisoformat(today)
    year,month=divmod(civil_today.year*12+civil_today.month-1-int(window),12)
    return date(year,month+1,min(civil_today.day,monthrange(year,month+1)[1])).isoformat()


def portfolio_history(db,current,currency,today,window,*,available=None,selection=None,labels=None,positions=None):
    today = str(today)
    threshold = window_start(today,window)
    result = {'state':'FORMING','first_observed_at':None,'points':[],'change':None,'percent':None,'window':window}
    if available is not None:
        candidates = set(available)
        observed = {row[0] for row in db.execute('''SELECT DISTINCT connection_id FROM of_portfolio_snapshots
            WHERE currency=? AND connection_id IN (SELECT value FROM json_each(?))''',(currency,json.dumps(list(candidates))))}
        eligible = observed | (set(positions or {}) & candidates)
        result['connections'] = [{'id':key,'label':labels[key],'eligible':key in eligible} for key in sorted(candidates)]
        connection = selection if selection in candidates else (next(iter(current)) if len(current)==1 else
                     next(iter(eligible)) if len(eligible)==1 else None)
        result['connection_id'] = connection
        if not connection:
            result['state']='SELECT_CONNECTION' if len(eligible)>1 else 'FORMING'
            return result
        result['latest_position'] = (positions or {}).get(connection)
    else:
        if len(current)!=1:
            if current:
                result['state']='SELECT_CONNECTION'
            return result
        connection = next(iter(current))
    result['first_observed_at'] = db.execute("""SELECT min(observed_at) FROM of_portfolio_snapshots
        WHERE connection_id=? AND currency=?""",(connection,currency)).fetchone()[0]
    rows = db.execute("""SELECT p.* FROM of_portfolio_snapshots p JOIN of_sync_runs r
          ON r.id=p.run_id AND r.connection_id=p.connection_id
        LEFT JOIN of_classification_import_order s ON p.run_id=s.run_id
        WHERE p.connection_id=? AND p.currency=? AND p.observed_at>=? AND r.state='SUCCEEDED'
        ORDER BY r.finished_at,s.sequence,p.observed_at,p.run_id,p.external_id LIMIT 30001""",(connection,currency,threshold)).fetchall()
    if len(rows)>30000:
        result['state']='LIMIT'
        return result
    runs = defaultdict(list)
    for row in rows:
        runs[row['run_id']].append(row)
    points = {}
    for observations in runs.values():
        references = {row['reference_date'] for row in observations}
        if len(references)!=1 or None in references:
            continue
        day = references.pop()
        if not threshold<=day<=today:
            continue
        amount = sum((Decimal(row['value']) for row in observations),Decimal(0))
        points[day] = {'date':day,'value':format(amount,'f')}
    result['points'] = [points[key] for key in sorted(points)]
    result['last_observed_at'] = db.execute('''SELECT max(observed_at) FROM of_portfolio_snapshots
        WHERE connection_id=? AND currency=?''',(connection,currency)).fetchone()[0]
    if result['points']:
        result['latest_point'] = result['points'][-1]
    if len(points)>1:
        first,last = (Decimal(point['value']) for point in (result['points'][0],result['points'][-1]))
        delta = last-first
        result.update(state='AVAILABLE',change=format(delta,'f'))
        if first>0:
            with localcontext() as context:
                context.prec = 80
                result['percent']=format((delta/first*100).quantize(Decimal('0.01')),'f')
    return result
