"""Read-only Open Finance analytics over current provider observations."""
import json
from hashlib import sha256
import re
import time
from decimal import Decimal, InvalidOperation, localcontext

from .open_finance import SyncError
from .open_finance_query import civil, read_view, search_key
from .open_finance_registry import connection_views

PARAMS = {'start', 'end', 'connection_id', 'account_id', 'category', 'product',
          'status', 'direction', 'currency', 'search', 'page', 'page_size', 'history'}


def _parameters(query):
    if set(query) - PARAMS or any(not isinstance(v, list) or len(v) != 1 or not v[0] for v in query.values()):
        raise SyncError('INVALID_QUERY', 422)
    q = {k: v[0] for k, v in query.items()}
    for key in ('start', 'end'):
        if key in q and (len(q[key]) != 10 or civil(q[key]) is None):
            raise SyncError('INVALID_PERIOD', 422)
    if q.get('start', '') > q.get('end', '9999-12-31'):
        raise SyncError('INVALID_PERIOD', 422)
    for key, default, allowed in (('product', 'BANK', {'BANK', 'CREDIT', 'ALL'}),
                                  ('status', 'POSTED', {'POSTED', 'PENDING', 'ALL'}),
                                  ('direction', 'all', {'all', 'incoming', 'outgoing', 'unknown'}),
                                  ('history', '0', {'0', '1'})):
        q.setdefault(key, default)
        if q[key] not in allowed:
            raise SyncError('INVALID_QUERY', 422)
    q.setdefault('currency', 'BRL')
    if not re.fullmatch(r'[A-Z]{3}', q['currency']):
        raise SyncError('INVALID_QUERY', 422)
    for key, default in (('page', '1'), ('page_size', '25')):
        value = q.get(key, default)
        if not re.fullmatch(r'[1-9][0-9]{0,8}', value):
            raise SyncError('INVALID_PAGINATION', 422)
        q[key] = int(value)
    if q['page_size'] not in (25, 50, 100):
        raise SyncError('INVALID_PAGINATION', 422)
    for key in ('connection_id', 'account_id', 'category', 'search'):
        if key in q and (len(q[key]) > 256 or any(ord(ch) < 32 for ch in q[key])):
            raise SyncError('INVALID_QUERY', 422)
    if q.get('account_id') and not q.get('connection_id'):
        raise SyncError('INVALID_FILTER_COMBINATION', 422)
    if 'search' in q:
        q['_search'] = search_key(q['search'], term=True)
    return q


def _amount(value):
    if value is None or isinstance(value, bool) or not isinstance(value, (str, int, Decimal)):
        return None
    try:
        number = Decimal(value)
        if not number.is_finite() or len(number.as_tuple().digits) > 40 or abs(number.as_tuple().exponent) > 20:
            return None
        return number
    except (InvalidOperation, ValueError):
        return None


def _category(data, connection):
    ident = data.get('categoryId')
    name = data.get('category')
    if isinstance(ident, str) and ident:
        return {'key': 'pluggy:' + ident, 'name': name or ident}
    if isinstance(name, str) and name:
        return {'key': 'local:' + connection + ':namehash:' + sha256(name.encode('utf-8')).hexdigest(), 'name': name}
    return {'key': 'missing', 'name': 'Sem categoria'}


def analytics(c, settings, query):
    q = _parameters(query)
    with read_view(c) as deadline, localcontext() as ctx:
        ctx.prec = 80
        views = connection_views(c, settings)
        if q.get('connection_id') and q['connection_id'] not in views:
            raise SyncError('CONNECTION_NOT_FOUND', 404)
        selected = {k: v for k, v in views.items() if (q['history'] == '1' or (v.enabled and not v.historical))
                    and (not q.get('connection_id') or q['connection_id'] == k)}
        rows = c.execute("SELECT connection_id,resource,parent_id,external_id,payload_json,observed_at FROM of_resource_records WHERE state='PRESENT' AND resource IN ('accounts','transactions','investments') LIMIT 30001").fetchall()
        if len(rows) > 30000 or time.monotonic() > deadline:
            raise SyncError('QUERY_BUDGET_EXCEEDED', 503)
        records = []
        for row in rows:
            if row['connection_id'] in selected:
                records.append({**dict(row), 'data': json.loads(row['payload_json'], parse_float=Decimal)})
        accounts = {(r['connection_id'], r['external_id']): r for r in records if r['resource'] == 'accounts'}
        if q.get('account_id') and (q['connection_id'], q['account_id']) not in accounts:
            raise SyncError('RESOURCE_NOT_FOUND', 404)
        translations = {}
        for cat in c.execute("SELECT connection_id,external_id,display_name_pt,translation_status FROM of_categories WHERE external_id IS NOT NULL"):
            if cat['translation_status'] in ('VERIFIED', 'OWNER_OVERRIDE') and cat['display_name_pt']:
                translations[(cat['connection_id'], cat['external_id'])] = cat['display_name_pt']

        positions = {'accounts': [], 'investments': []}
        for r in records:
            kind = r['resource']
            if kind not in positions or not views[r['connection_id']].enabled or views[r['connection_id']].historical:
                continue
            data = r['data']
            if kind == 'accounts' and data.get('type') != 'BANK':
                continue
            if data.get('currencyCode') != q['currency']:
                continue
            value = _amount(data.get('balance'))
            positions[kind].append({'connection_id': r['connection_id'], 'external_id': r['external_id'],
                'institution': views[r['connection_id']].institution, 'name': data.get('name'), 'type': data.get('type'),
                'value': str(value) if value is not None else None, 'observed_at': r['observed_at'],
                'reference_date': data.get('date') or data.get('updatedAt')})
        for kind, items in list(positions.items()):
            values = [Decimal(x['value']) for x in items if x['value'] is not None]
            positions[kind] = {'value': str(sum(values, Decimal(0))) if values else None,
                               'known': len(values), 'unavailable': len(items) - len(values), 'items': items}
        items = []
        for r in records:
            if r['resource'] != 'transactions':
                continue
            data = r['data']; account = accounts.get((r['connection_id'], r['parent_id']))
            product = account['data'].get('type') if account else None
            day = civil(data.get('date'))
            if product not in ('BANK', 'CREDIT') or (q['product'] != 'ALL' and product != q['product']): continue
            if q.get('account_id') and q['account_id'] != r['parent_id']: continue
            if q['status'] != 'ALL' and data.get('status') != q['status']: continue
            if day is None or day < q.get('start', '0001-01-01') or day > q.get('end', '9999-12-31'): continue
            if data.get('currencyCode') != q['currency']: continue
            category = _category(data, r['connection_id'])
            translation = translations.get((r['connection_id'], data.get('categoryId')))
            if translation:
                category['name'] = translation
            if q.get('category') and q['category'] != category['key']: continue
            classification = {'CREDIT': 'incoming', 'DEBIT': 'outgoing'}.get(data.get('type'), 'unknown')
            if q['direction'] != 'all' and q['direction'] != classification: continue
            description = data.get('description') or ''
            merchant = data.get('merchant') or {}
            merchant = merchant.get('name', '') if isinstance(merchant, dict) else ''
            if q.get('_search') and not any(q['_search'] in (search_key(str(x)) or '') for x in (description, merchant)): continue
            amount = _amount(data.get('amount'))
            items.append({'connection_id': r['connection_id'], 'account_id': r['parent_id'], 'external_id': r['external_id'],
                'institution': views[r['connection_id']].institution, 'account_name': account['data'].get('name') if account else None,
                'date': day, 'description': description, 'merchant': merchant, 'amount': str(amount) if amount is not None else None,
                'currency': q['currency'], 'category': category, 'direction': classification, 'status': data.get('status'), 'product': product,
                'economic_classification': 'NOT_ESTABLISHED', 'reconciliation': 'UNRECONCILED'})
        items.sort(key=lambda x: (x['date'], x['connection_id'], x['account_id'], x['external_id']), reverse=True)
        flow = {p: {'incoming': Decimal(0), 'outgoing': Decimal(0), 'unavailable': 0} for p in ('BANK', 'CREDIT')}
        series = {}; categories = {}
        for item in items:
            amount = _amount(item['amount']); direction = item['direction']; product = item['product']
            if amount is None or direction == 'unknown':
                flow[product]['unavailable'] += 1; continue
            amount = abs(amount); flow[product][direction] += amount
            key = (item['date'], product, direction); series[key] = series.get(key, Decimal(0)) + amount
            if direction == 'outgoing':
                key = (product, item['category']['key'])
                if key not in categories: categories[key] = [item['category']['name'], Decimal(0)]
                categories[key][1] += amount
        for total in flow.values():
            for name in ('incoming', 'outgoing'): total[name] = str(total[name])
        category_rows = [{'product': p, 'key': k, 'name': n, 'value': str(v)} for (p, k), (n, v) in categories.items()]
        coverage = [dict(r) for r in c.execute('SELECT connection_id,resource,parent_id,state,observed_at,omitted_field_count FROM of_resource_coverage') if r['connection_id'] in selected]
        for kind in positions:
            checkpoints = [x for x in coverage if x['resource'] == kind]
            missing_connections = set(selected) - {x['connection_id'] for x in checkpoints}
            state = 'PARTIAL' if missing_connections or any(x['state'] not in ('AVAILABLE', 'EMPTY') or x['omitted_field_count'] for x in checkpoints) or positions[kind]['unavailable'] else ('COMPLETE' if selected else 'NOT_ESTABLISHED')
            positions[kind]['coverage_state'] = state
        for product in flow:
            flow[product]['economic_totals'] = {'state': 'NOT_ESTABLISHED', 'incoming': None, 'outgoing': None}
            flow[product]['basis'] = 'DECLARED_GROSS_MOVEMENTS'

        start = (q['page'] - 1) * q['page_size']
        return {'contract': 'OF-ANALYTICS/1', 'filters': {k: v for k, v in q.items() if not k.startswith('_')},
            'positions': positions, 'flow': flow,
            'series': [{'date': d, 'product': p, 'direction': dr, 'value': str(v)} for (d, p, dr), v in sorted(series.items())],
            'categories': sorted(category_rows, key=lambda r: Decimal(r['value']), reverse=True),
            'items': items[start:start + q['page_size']], 'total': len(items), 'page': q['page'],
            'has_more': start + q['page_size'] < len(items), 'coverage': coverage}
