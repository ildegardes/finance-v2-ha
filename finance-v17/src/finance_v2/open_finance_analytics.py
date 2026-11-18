"""Read-only Open Finance analytics over current provider observations."""
import json
from hashlib import sha256
from datetime import date, timedelta
import re
import time
import unicodedata
from decimal import Decimal, InvalidOperation, localcontext

from .open_finance import SyncError
from .open_finance_query import civil, read_view, search_key
from .open_finance_registry import connection_views
from .domain.clock import SystemClock
from .open_finance_portfolio import portfolio_history
from .open_finance_classification import AUTOMATIC, Classifier, Facts, NATURES, ORIGINS, normalize
from .open_finance_insights import banking_insights, card_insights, classification_center, classified_bucket, masked_card_text
from .open_finance_domain import _origin, _context_at_origin, _freshness

PARAMS = {'start', 'end', 'connection_id', 'account_id', 'category', 'product',
          'status', 'direction', 'currency', 'search', 'page', 'page_size', 'history', 'bill_id', 'nature', 'effective_category', 'origin', 'review', 'rule', 'bucket', 'group_by', 'group_order', 'center', 'effective_key', 'portfolio_window', 'investment', 'provent'}


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
    for key in ('connection_id', 'account_id', 'category', 'search', 'bill_id'):
        if key in q and (len(q[key]) > 256 or any(ord(ch) < 32 for ch in q[key])):
            raise SyncError('INVALID_QUERY', 422)
    choices = {'nature':NATURES,'origin':ORIGINS,'review':{'CONFIRMED','SUGGESTED','CONFLICT','UNCLASSIFIED'},
               'bucket':{'operating','capital','internal','settlement','pending'},
               'group_by':{'pattern','recurring','institution','account','direction','category'},
               'group_order':{'count','date','magnitude'},'center':{'1'},'portfolio_window':{'3','6','12','all'}}
    if any(key in q and q[key] not in allowed for key,allowed in choices.items()):
        raise SyncError('INVALID_QUERY',422)
    for key in ('effective_category','rule','effective_key','investment','provent'):
        if key in q and (len(q[key])>256 or not q[key].isprintable()):
            raise SyncError('INVALID_QUERY',422)
    if q.get('account_id') and not q.get('connection_id'):
        raise SyncError('INVALID_FILTER_COMBINATION', 422)
    if q.get('bill_id') and (not q.get('connection_id') or not q.get('account_id') or q['product'] != 'CREDIT'):
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
        return {'key': 'pluggy:' + ident, 'name': name or ident, 'has_name': bool(name)}
    if isinstance(name, str) and name:
        return {'key': 'local:' + connection + ':namehash:' + sha256(name.encode('utf-8')).hexdigest(), 'name': name}
    return {'key': 'missing', 'name': 'Sem categoria'}


def effective_category(decision, provider):
    label = decision.get('category')
    if not isinstance(label,str) or not label.strip():
        return dict(provider)
    normalized = unicodedata.normalize('NFC',' '.join(label.split()).casefold())
    return {'key':'finance:'+sha256(normalized.encode()).hexdigest(),'name':label,
            'has_name':True,'translated':True}


def _available(checkpoint):
    return bool(checkpoint and checkpoint['state'] in ('AVAILABLE', 'EMPTY') and not checkpoint['omitted_field_count'])


def _covers(checkpoint, start, end):
    return (_available(checkpoint) and bool(checkpoint['date_from'] and checkpoint['date_to'])
            and checkpoint['date_from'] <= start <= end <= checkpoint['date_to'])


def _coverage_state(checkpoint, known, missing):
    if _available(checkpoint) and not missing:
        return 'COMPLETE'
    if known or missing:
        return 'PARTIAL'
    return checkpoint['state'] if checkpoint else 'NOT_ESTABLISHED'


def _unfiltered(q):
    return (not any(q.get(key) for key in ('search', 'bill_id', 'category', 'account_id', 'nature', 'effective_category', 'origin', 'review', 'rule', 'bucket', 'effective_key', 'investment', 'provent')) and q['direction'] == 'all')


def _comparison(records, accounts, q, product, start, end, observed=None):
    totals = {'incoming': Decimal(0), 'outgoing': Decimal(0)}
    for row in records:
        if row['resource'] != 'transactions':
            continue
        data = row['data']
        account = accounts.get((row['connection_id'], row['parent_id']))
        day = civil(data.get('date'))
        if not account or account['data'].get('type') != product:
            continue
        currency, status = data.get('currencyCode'), data.get('status')
        if currency and currency != q['currency'] or day and not start <= day <= end:
            continue
        if q['status'] != 'ALL' and status in ('POSTED', 'PENDING') and status != q['status']:
            continue
        if not currency or day is None or (q['status'] != 'ALL' and status not in ('POSTED', 'PENDING')):
            return None
        direction = {'CREDIT': 'incoming', 'DEBIT': 'outgoing'}.get(data.get('type'))
        amount = _amount(data.get('amount'))
        if direction is None or amount is None:
            return None
        totals[direction] += abs(amount)
        if observed is not None:
            observed.append((row,day,direction,amount))
    return totals


def analytics(c, settings, query, today=None):
    q = _parameters(query)
    with read_view(c) as deadline, localcontext() as ctx:
        ctx.prec = 80
        views = connection_views(c, settings)
        if q.get('connection_id') and q['connection_id'] not in views:
            raise SyncError('CONNECTION_NOT_FOUND', 404)
        eligible = {k: v for k, v in views.items() if v.enabled and not v.historical}
        selected = {k: v for k, v in (views if q['history'] == '1' else eligible).items()
                    if not q.get('connection_id') or q['connection_id'] == k}
        current = eligible.keys() & selected.keys()
        # Apply scope before the row budget and before decoding provider observations.
        scope = json.dumps(list(selected))
        rows = c.execute("""SELECT r.connection_id,r.resource,r.parent_id,r.external_id,r.payload_json,r.observed_at,r.last_run_id,
                   coalesce(s.sequence,0) AS first_sequence
            FROM of_resource_records r LEFT JOIN of_classification_import_order s ON s.run_id=r.first_run_id
            WHERE r.connection_id IN (SELECT value FROM json_each(?))
            AND r.state='PRESENT' AND r.resource IN ('accounts','transactions','investments') LIMIT 30001""",
            (scope,)).fetchall()
        if len(rows) > 30000 or time.monotonic() > deadline:
            raise SyncError('QUERY_BUDGET_EXCEEDED', 503)
        records = [{**dict(row), 'data': json.loads(row['payload_json'], parse_float=Decimal)} for row in rows]
        accounts = {(r['connection_id'], r['external_id']): r for r in records if r['resource'] == 'accounts'}
        if q.get('account_id') and (q['connection_id'], q['account_id']) not in accounts:
            raise SyncError('RESOURCE_NOT_FOUND', 404)
        if q.get('bill_id') and not c.execute("SELECT 1 FROM of_resource_records WHERE connection_id=? AND resource='bills' AND parent_id=? AND external_id=? AND state='PRESENT'", (q['connection_id'], q['account_id'], q['bill_id'])).fetchone():
            raise SyncError('RESOURCE_NOT_FOUND', 404)
        translations = {}
        for cat in c.execute("SELECT connection_id,external_id,display_name_pt,translation_status FROM of_categories WHERE external_id IS NOT NULL"):
            if cat['translation_status'] in ('VERIFIED', 'OWNER_OVERRIDE') and cat['display_name_pt']:
                translations[(cat['connection_id'], cat['external_id'])] = cat['display_name_pt']

        positions = {'accounts': [], 'investments': []}
        unknown_currency = {kind: {} for kind in positions}
        for r in records:
            kind = r['resource']
            if kind not in positions or r['connection_id'] not in current:
                continue
            data = r['data']
            if kind == 'accounts' and (data.get('type') != 'BANK' or data.get('status') == 'CLOSED'):
                continue
            if not data.get('currencyCode'):
                missing = unknown_currency[kind]
                missing[r['connection_id']] = missing.get(r['connection_id'], 0) + 1
                continue
            if data.get('currencyCode') != q['currency']:
                continue
            value = _amount(data.get('balance'))
            origin_run, _ = _origin(c, {**r, '_resource': kind, 'data': json.loads(r['payload_json'])}, False)
            origin_item = _context_at_origin(c, r['connection_id'], 'item', None, origin_run) if origin_run else {}
            freshness = _freshness(origin_item, kind, 'BANK_ACCOUNT' if kind == 'accounts' else 'INVESTMENT_POSITION')
            positions[kind].append({'connection_id': r['connection_id'], 'external_id': r['external_id'],
                'institution': views[r['connection_id']].institution, 'name': data.get('name'), 'type': data.get('type'),
                'value': format(value, 'f') if value is not None else None, 'observed_at': r['observed_at'],
                'reference_date': data.get('date'), 'reference_date_state': 'KNOWN' if civil(data.get('date')) else 'NOT_ESTABLISHED', 'provider_updated_at': data.get('updatedAt') or data.get('lastUpdatedAt'), 'freshness': freshness})
        for kind, items in list(positions.items()):
            values = [Decimal(x['value']) for x in items if x['value'] is not None]
            positions[kind] = {'value': format(sum(values, Decimal(0)), 'f') if values else None,
                               'known': len(values), 'unavailable': len(items) - len(values), 'unknown_currency': sum(unknown_currency[kind].values()), 'items': items}
            if kind == 'investments':
                classes = {}
                for item in items:
                    label = item.get('type') or 'Não informada'
                    group = classes.setdefault(label, {'type': label, 'known': 0, 'unavailable': 0, '_total': Decimal(0)})
                    if item['value'] is None:
                        group['unavailable'] += 1
                    else:
                        group['known'] += 1
                        value = Decimal(item['value'])
                        group['_total'] += value
                positions[kind]['by_class'] = [{**{k:v for k,v in group.items() if k != '_total'},
                    'value': format(group['_total'], 'f') if group['known'] else None} for group in classes.values()]
        bill_links = {(row['connection_id'], row['source_parent_id'], row['source_external_id']): dict(row)
                      for row in c.execute("SELECT connection_id,source_parent_id,source_external_id,state,target_parent_id,target_external_id FROM of_resource_links WHERE source_resource='transactions' AND kind='TRANSACTION_BILL'")}
        items = []
        classifier = Classifier(c,set(selected))
        unresolved_scope = {'BANK': 0, 'CREDIT': 0}
        for r in records:
            if r['resource'] != 'transactions':
                continue
            data = r['data']; account = accounts.get((r['connection_id'], r['parent_id']))
            product = account['data'].get('type') if account else None
            day = civil(data.get('date'))
            if product not in ('BANK', 'CREDIT') or (q['product'] != 'ALL' and product != q['product']): continue
            if q.get('account_id') and q['account_id'] != r['parent_id']: continue
            currency = data.get('currencyCode')
            status = data.get('status')
            if currency and currency != q['currency']: continue
            if day is not None and (day < q.get('start', '0001-01-01') or day > q.get('end', '9999-12-31')): continue
            if q['status'] != 'ALL' and status in ('POSTED', 'PENDING') and status != q['status']: continue
            if not currency or day is None or (q['status'] != 'ALL' and status not in ('POSTED', 'PENDING')):
                unresolved_scope[product] += 1
                continue
            original_category = _category(data, r['connection_id'])
            category = dict(original_category)
            translation = translations.get((r['connection_id'], data.get('categoryId')))
            if translation:
                category.update(name=translation, has_name=True, translated=True)
            if q.get('category') and q['category'] != category['key']: continue
            classification = {'CREDIT': 'incoming', 'DEBIT': 'outgoing'}.get(data.get('type'), 'unknown')
            if q['direction'] != 'all' and q['direction'] != classification: continue
            description = data.get('description') or ''
            merchant = data.get('merchant') or {}
            merchant = merchant.get('name', '') if isinstance(merchant, dict) else ''
            if q.get('_search') and not any(q['_search'] in (search_key(str(x)) or '') for x in (description, merchant)): continue
            amount = _amount(data.get('amount'))
            link = bill_links.get((r['connection_id'], r['parent_id'], r['external_id'])) if product == 'CREDIT' else None
            relation = {'state': link['state'], 'target_parent_id': link['target_parent_id'], 'target_external_id': link['target_external_id']} if link else {'state': 'NOT_ESTABLISHED'}
            if q.get('bill_id') and (not link or link['state'] != 'MATCHED' or link['target_external_id'] != q['bill_id'] or link['target_parent_id'] != r['parent_id']):
                continue
            decision = classifier.classify(Facts.from_row(r,views[r['connection_id']].institution,product,original_category['key']),original_category['key'])
            bucket = classified_bucket({'classification':decision,'direction':classification}) if amount is not None else 'pending'
            effective = effective_category(decision,category)
            if q.get('effective_key') and amount is None:
                continue
            selectors = {'nature':decision['nature'],'effective_category':effective['name'],
                         'effective_key':effective['key'],'investment':decision.get('investment'),
                         'provent':decision.get('provent','other') if decision['nature']=='INVESTMENT_INCOME' else None,
                         'origin':decision['origin'],'review':decision['review'],'rule':decision.get('rule_id'),'bucket':bucket}
            if any(key in q and q[key]!=value for key,value in selectors.items()):
                continue
            items.append({'connection_id': r['connection_id'], 'account_id': r['parent_id'], 'external_id': r['external_id'],
                'institution': views[r['connection_id']].institution, 'account_name': masked_card_text(account['data'].get('name')) if product=='CREDIT' else account['data'].get('name'),
                'date': day, 'description': description, 'description_original':data.get('descriptionRaw') or description, 'merchant': merchant, 'amount': format(amount, 'f') if amount is not None else None,
                'currency': q['currency'], 'category': category, 'direction': classification, 'status': data.get('status'), 'product': product,
                'classification':decision,'classification_bucket':bucket,'original_category':original_category,
                'effective_category':effective,
                'economic_classification': 'NOT_ESTABLISHED', 'reconciliation': 'UNRECONCILED', 'bill_relation': relation})
        items.sort(key=lambda x: (x['date'], x['connection_id'], x['account_id'], x['external_id']), reverse=True)
        flow = {p: {'incoming': Decimal(0), 'outgoing': Decimal(0), 'unavailable': 0} for p in ('BANK', 'CREDIT')}
        series = {}; categories = {}; economic_categories = {}; observed = {p: set() for p in flow}
        for item in items:
            amount = _amount(item['amount']); direction = item['direction']; product = item['product']
            if amount is None or direction == 'unknown':
                flow[product]['unavailable'] += 1; continue
            amount = abs(amount); flow[product][direction] += amount
            observed[product].add(direction)
            key = (item['date'], product, direction); series[key] = series.get(key, Decimal(0)) + amount
            if direction == 'outgoing':
                category = item['effective_category']
                for totals in (categories,economic_categories) if item['classification_bucket']=='operating' else (categories,):
                    key = (product,category['key'])
                    group = totals.setdefault(key,[category,Decimal(0),set()])
                    group[1] += amount
                    group[2].add(item['classification']['review'])
        for total in flow.values():
            for name in ('incoming', 'outgoing'): total[name] = format(total[name], 'f')
        category_rows = [{**category, 'product': p, 'value': format(v, 'f'), 'review': sorted(review)}
                         for (p, _), (category, v, review) in categories.items()]
        economic_ranking = sorted(({**category,'product':p,'value':format(v,'f'),'review':sorted(review)}
                                  for (p,_),(category,v,review) in economic_categories.items() if p=='BANK'),
                                 key=lambda row:(-Decimal(row['value']),row['key']))
        ranking = {}
        for product in ('BANK', 'CREDIT'):
            rows_for_product = sorted((row for row in category_rows if row['product'] == product and row['key'] != 'missing'),
                                      key=lambda row: (-Decimal(row['value']), row['key']))
            chosen, rest = rows_for_product[:5], rows_for_product[5:]
            groups = list(chosen)
            if rest:
                groups.append({'product': product, 'key': 'other', 'name': 'Outras',
                               'value': format(sum((Decimal(row['value']) for row in rest), Decimal(0)), 'f')})
            groups.extend(row for row in category_rows if row['product'] == product and row['key'] == 'missing')
            ranking[product] = groups
        coverage = [dict(r) for r in c.execute("""SELECT cv.connection_id,cv.resource,cv.parent_id,
                cv.state,cv.observed_at,cv.omitted_field_count,r.date_from,r.date_to
            FROM of_resource_coverage cv JOIN of_sync_runs r ON r.id=cv.run_id AND r.connection_id=cv.connection_id
            WHERE cv.connection_id IN (SELECT value FROM json_each(?))""", (scope,))]
        checkpoints = {(x['connection_id'], x['resource'], x['parent_id']): x for x in coverage}

        institutions = {cid: {'connection_id': cid, 'institution': selected[cid].institution,
                              'current': cid in current} for cid in selected}
        for row in c.execute("""SELECT connection_id,max(finished_at) AS finished FROM of_sync_runs
            WHERE state='SUCCEEDED' AND connection_id IN (SELECT value FROM json_each(?)) GROUP BY connection_id""",(scope,)):
            institutions[row['connection_id']]['last_sync']=row['finished']
        for kind in positions:
            by_connection = {}
            for item in positions[kind]['items']:
                by_connection.setdefault(item['connection_id'], []).append(item)
            for cid in current:
                subset = by_connection.get(cid, [])
                values = [Decimal(x['value']) for x in subset if x['value'] is not None]
                unknown = unknown_currency[kind].get(cid, 0)
                checkpoint = checkpoints.get((cid, kind, ''))
                institutions[cid][kind] = {
                    'value': format(sum(values, Decimal(0)), 'f') if values else None,
                    'coverage_state': _coverage_state(checkpoint, bool(values), unknown or len(values) != len(subset)),
                    'known': len(values),
                    'unavailable': len(subset) - len(values),
                    'unknown_currency': unknown,
                    'items': subset,
                }
            states = {institutions[cid][kind]['coverage_state'] for cid in current}
            positions[kind]['coverage_state'] = (states.pop() if len(states) == 1
                                                 else 'PARTIAL' if states else 'NOT_ESTABLISHED')

        prior_bank = None
        for product, total in flow.items():
            total['unresolved_scope'] = unresolved_scope[product]
            parents = [(cid, external) for (cid, external), account in accounts.items()
                       if account['data'].get('type') == product
                       and (not q.get('account_id') or q['account_id'] == external)]
            expected = ([checkpoints.get((cid, 'transactions', external)) for cid, external in parents]
                        if q['product'] in ('ALL', product) else [])
            account_lists = [checkpoints.get((cid, 'accounts', '')) for cid in selected]
            # A complete provider cache is not proof of a complete calendar period.
            # Only dated evidence for every in-scope account supports a definitive total.
            start_day, end_day = q.get('start'), q.get('end')
            complete_accounts = bool(account_lists) and all(_available(x) for x in account_lists)
            complete = (complete_accounts and bool(expected) and bool(start_day and end_day)
                        and all(_covers(x, start_day, end_day) for x in expected)
                        and not (total['unavailable'] or unresolved_scope[product]))
            cache_known = any(_available(x) for x in expected)
            total['coverage_state'] = 'COMPLETE' if complete else 'PARTIAL' if observed[product] or cache_known else 'NOT_ESTABLISHED'
            total['reported'] = {direction: total[direction] if direction in observed[product] or complete else None
                                 for direction in ('incoming', 'outgoing')}
            total['observed_net'] = format(Decimal(total['incoming']) - Decimal(total['outgoing']), 'f') if len(observed[product]) == 2 and _unfiltered(q) else None
            total['net'] = format(Decimal(total['incoming']) - Decimal(total['outgoing']), 'f') if complete and _unfiltered(q) else None
            total['comparison'] = None
            if total['net'] is not None:
                length = (date.fromisoformat(end_day) - date.fromisoformat(start_day)).days + 1
                first = date.fromisoformat(start_day)
                if first.toordinal() > length:
                    prior_start = (first - timedelta(days=length)).isoformat()
                    prior_end = (first - timedelta(days=1)).isoformat()
                    observations = [] if product=='BANK' else None
                    prior = _comparison(records, accounts, q, product, prior_start, prior_end,observations) if all(
                        _covers(x, prior_start, prior_end) for x in expected
                    ) else None
                    if prior is not None:
                        if observations is not None:
                            prior_bank = (prior_start,prior_end,observations)
                        total['comparison'] = {'start': prior_start, 'end': prior_end,
                            **{direction: format(Decimal(total[direction]) - prior[direction], 'f')
                               for direction in ('incoming', 'outgoing')},
                            'net': format(Decimal(total['net']) - (prior['incoming'] - prior['outgoing']), 'f')}
        for product in flow:
            flow[product]['economic_totals'] = {'state': 'NOT_ESTABLISHED', 'incoming': None, 'outgoing': None}
            flow[product]['basis'] = 'DECLARED_GROSS_MOVEMENTS'
            flow[product]['classification_completeness'] = 'NOT_ESTABLISHED' if any(item['product'] == product for item in items) else 'NO_DATA'

        start = (q['page'] - 1) * q['page_size']
        if time.monotonic()>deadline:
            raise SyncError('QUERY_BUDGET_EXCEEDED',503)
        insights = banking_insights(items,flow['BANK'])
        automatic_positions = [item for item in positions['investments']['items']
                               if normalize(item['name']) == normalize(AUTOMATIC)]
        if len(automatic_positions)==1:
            insights['automatic']['position'] = automatic_positions[0]['value']
        if prior_bank and insights['coverage']=='COMPLETE_BANK_SCOPE':
            prior_start,prior_end,observations=prior_bank
            historical=[]
            for row,day,direction,amount in observations:
                cid=row['connection_id']
                category=_category(row['data'],cid)
                decision=classifier.classify(Facts.from_row(row,views[cid].institution,'BANK',category['key']),category['key'])
                historical.append({'product':'BANK','date':day,'direction':direction,'amount':format(amount,'f'),
                    'classification':decision,'classification_bucket':classified_bucket({'classification':decision,'direction':direction}),
                    'connection_id':cid,'institution':views[cid].institution})
            before=banking_insights(historical,{'coverage_state':'COMPLETE'})
            if before['coverage']=='COMPLETE_BANK_SCOPE':
                insights['comparison']={'start':prior_start,'end':prior_end,**{
                    key:format(Decimal(insights['known'][key])-Decimal(value),'f') for key,value in before['known'].items()
                }}
                insights['income']['comparison']=format(Decimal(insights['income']['value'] or 0)-Decimal(before['income']['value'] or 0),'f')
        if time.monotonic()>deadline:
            raise SyncError('QUERY_BUDGET_EXCEEDED',503)
        cards = card_insights(accounts,current,views,q['currency'],_amount,today or str(SystemClock(settings.timezone).today()))
        history = portfolio_history(c,current,q['currency'],today or SystemClock(settings.timezone).today(),q.get('portfolio_window','6')) if 'portfolio_window' in q else None
        center = classification_center(items,q.get('group_by','pattern'),q.get('group_order','count')) if q.get('center') else None
        return {'contract': 'OF-ANALYTICS/1', 'filters': {k: v for k, v in q.items() if not k.startswith('_')},
            'positions': positions, 'flow': flow, 'institutions': list(institutions.values()),
            'insights': insights, 'cards': cards, 'classification_center': center,
            'economic_category_ranking':economic_ranking,'portfolio_history':history,
            'series': [{'date': d, 'product': p, 'direction': dr, 'value': format(v, 'f')} for (d, p, dr), v in sorted(series.items())],
            'categories': sorted(category_rows, key=lambda r: Decimal(r['value']), reverse=True), 'category_ranking': ranking,
            'items': items[start:start + q['page_size']], 'total': len(items), 'page': q['page'],
            'has_more': start + q['page_size'] < len(items), 'coverage': coverage}
