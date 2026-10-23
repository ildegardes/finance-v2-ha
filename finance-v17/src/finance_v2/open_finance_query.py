"""Owner-only, bounded, read-only OF-L2 queries. Never contacts a provider.

DC-v2 and U31-A13 are implemented here without importing F11 experiments or
transporting their frozen Unicode payload. F06 uses separately generated,
pinned Unicode13 primitives; runtime Unicode properties are not consulted.
"""
from contextlib import contextmanager
from datetime import date, datetime
from decimal import Decimal
from hashlib import sha256
import re
import sqlite3
import time

from .open_finance import SyncError
from . import unicode13_f06

CONTRACT = 'of-l2-v2'
POLICY_TEXT = '{"context_mode":"CURRENT_ACCOUNT_METADATA","contract_sha256":"DC3D8302FE338A93084FE3D62DC05C90D6569BA427D51B7A1CA6ECB3C89220FB","perspective":"DECLARED_ACCOUNT_MOVEMENT","policy_id":"PLUGGY_DECLARED_TRANSACTION_DIRECTION","policy_version":"DC-v2"}'
POLICY_HASH = sha256(POLICY_TEXT.encode()).hexdigest().upper()
SEARCH_TEXT = 'U31-A13/FIXED-1;DATA_SHA256='+unicode13_f06.DATA_SHA256+';CRLF_CR_LF;NFD;FULL_CASEFOLD;NFD;REMOVE_MN_EXCEPT_VARIATION_SELECTORS;LITERAL_SUBSTRING;256_2048_4096_32768'
SEARCH_HASH = sha256(SEARCH_TEXT.encode()).hexdigest().upper()
MAX_ROWS = 10000
READ_SECONDS = 3
TABLES = ('of_connections', 'of_accounts', 'of_categories', 'of_sync_runs',
          'of_transactions', 'of_transaction_revisions')
ALLOWED = {'contract','page','page_size','order','start','end','connection_id',
           'external_account_id','category_key','category_presence','direction',
           'search','origin_run_id','provenance_state','metrics'}
WS26 = frozenset('\t\n\v\f\r\x1c\x1d\x1e\x1f \x85\xa0\u1680\u2000\u2001\u2002\u2003\u2004\u2005\u2006\u2007\u2008\u2009\u200a\u2028\u2029\u202f\u205f\u3000')


def fail(code, status=422):
    raise SyncError(code, status)


def text(value, limit, *, identifier=False):
    return (isinstance(value, str) and 0 < len(value) <= limit
            and not any(0xD800 <= ord(c) <= 0xDFFF for c in value)
            and (not identifier or (value[0] not in WS26 and value[-1] not in WS26
                 and not any(ord(c) < 32 or ord(c) == 127 for c in value))))


def query_identifier(value, limit):
    # HTTP identifiers are literal; DC-v2 has the distinct WS26 domain.
    return (text(value,limit) and value[0]!=' ' and value[-1]!=' '
            and not any(ord(c)<32 or ord(c)==127 for c in value))


def civil(value):
    if not isinstance(value, str) or not re.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2}(?:T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]{1,6})?(?:Z|[+-][0-9]{2}:[0-9]{2}))?', value):
        return None
    try:
        if len(value) > 10:
            offset = re.search(r'[+-]([0-9]{2}):([0-9]{2})$',value)
            if offset and (int(offset[1])>23 or int(offset[2])>59):
                return None
            datetime.fromisoformat(value.replace('Z', '+00:00'))
        return date.fromisoformat(value[:10]).isoformat()
    except ValueError:
        return None


def search_ready():
    try:
        unicode13_f06.backend()
        return True
    except unicode13_f06.ProfileUnavailable:
        return False


def search_key(value, *, term=False):
    if not search_ready():
        fail('QUERY_PROFILE_UNAVAILABLE', 503)
    try:
        if term:
            unicode13_f06.verify_profile()
        return unicode13_f06.search_key(value,term=term)
    except unicode13_f06.ProfileUnavailable:
        fail('QUERY_PROFILE_UNAVAILABLE',503)
    except unicode13_f06.QueryRejected as error:
        fail(error.code,error.status)


def parse(query):
    if any(not isinstance(v, list) or len(v) != 1 for v in query.values()):
        fail('INVALID_QUERY')
    q = {k:v[0] for k,v in query.items()}
    if q.get('contract') != CONTRACT:
        fail('UNSUPPORTED_CONTRACT')
    if set(q) - ALLOWED:
        fail('INVALID_QUERY')
    for key, default in (('page','1'), ('page_size','50')):
        value = q.get(key,default)
        if not isinstance(value,str) or not re.fullmatch('[1-9][0-9]{0,18}', value) or int(value)>9223372036854775807:
            fail('INVALID_PAGINATION')
        q[key] = int(value)
    if q['page_size'] not in {25,50,100} or (q['page']-1)*q['page_size']>9223372036854775807:
        fail('INVALID_PAGINATION')
    if q.get('order','id_desc') != 'id_desc':
        fail('INVALID_QUERY')
    for key in ('start','end'):
        if key in q and (not isinstance(q[key],str) or len(q[key])!=10 or civil(q[key]) is None):
            fail('INVALID_PERIOD')
    if q.get('start','') > q.get('end','9999-12-31'):
        fail('INVALID_PERIOD')
    for key, limit in (('connection_id',64),('external_account_id',200),('category_key',200),('origin_run_id',32)):
        if key in q and not query_identifier(q[key],limit):
            fail('INVALID_IDENTIFIER')
    if 'origin_run_id' in q and not re.fullmatch('[0-9a-f]{32}',q['origin_run_id']):
        fail('INVALID_IDENTIFIER')
    for key, default, values in (('direction','all',{'all','incoming','outgoing','unknown','conflict'}),
            ('category_presence','any',{'any','present','missing'}),('provenance_state','any',{'any','known','unknown'}),
            ('metrics','none',{'none','exact'})):
        q.setdefault(key, default)
        if q[key] not in values:
            fail('INVALID_DIRECTION_FILTER' if key=='direction' else 'INVALID_FILTER_COMBINATION')
    if (any(k in q for k in ('external_account_id','category_key','origin_run_id')) and 'connection_id' not in q
            or q['category_presence']=='missing' and 'category_key' in q
            or q['provenance_state']=='unknown' and 'origin_run_id' in q):
        fail('INVALID_FILTER_COMBINATION')
    if 'search' in q:
        q['_search'] = search_key(q['search'], term=True)
    return q


@contextmanager
def read_view(c):
    if c.in_transaction:
        fail('READ_VIEW_UNAVAILABLE',503)
    deadline = time.monotonic() + READ_SECONDS
    c.execute('PRAGMA query_only=ON')
    c.set_progress_handler(lambda: int(time.monotonic()>deadline),1000)
    try:
        c.execute('BEGIN')
        yield deadline
    except sqlite3.Error:
        fail('QUERY_BUDGET_EXCEEDED' if time.monotonic()>deadline else 'STAGING_INTEGRITY_UNAVAILABLE',503)
    finally:
        c.set_progress_handler(None,0)
        c.rollback()


def capture(c, deadline):
    data = {}
    for name in TABLES:
        rows = c.execute('SELECT * FROM '+name+' LIMIT ?', (MAX_ROWS+1,)).fetchall()
        if len(rows)>MAX_ROWS or time.monotonic()>deadline:
            fail('QUERY_BUDGET_EXCEEDED',503)
        data[name] = [dict(r) for r in rows]
    return data


def direction(tx, connection, account):
    kind, status = tx['type'], tx['status']
    obs = ('TYPE_PRESENCE_UNRECOVERABLE' if kind is None else 'TYPE_VALID_'+kind
           if kind in ('CREDIT','DEBIT') else 'TYPE_UNKNOWN_VALUE')
    settlement = status if status in ('POSTED','PENDING') else 'NOT_ESTABLISHED'
    product = (account['type'],account['subtype']) if account else (None,None)
    warnings = []
    if product == ('CREDIT','CREDIT_CARD'):
        warnings.append('CARD_SIGN_DOCUMENTATION_UNRESOLVED')
    if settlement == 'NOT_ESTABLISHED':
        warnings.append('SETTLEMENT_NOT_ESTABLISHED')
    result, reason, rule = 'UNKNOWN', None, None
    if account is None or any(not text(tx[k],64 if k=='connection_id' else 200,identifier=True)
            for k in ('connection_id','external_account_id','external_id')):
        reason = 'ACCOUNT_IDENTITY_UNESTABLISHED'
    elif product[0] is None or product[1] is None:
        reason = 'PRODUCT_CONTEXT_MISSING'
    elif product in {('BANK','CREDIT_CARD'),('CREDIT','CHECKING_ACCOUNT'),('CREDIT','SAVINGS_ACCOUNT')}:
        result, reason = 'CONFLICT','ACCOUNT_PRODUCT_CONFLICT'
    elif product not in {('BANK','CHECKING_ACCOUNT'),('BANK','SAVINGS_ACCOUNT'),('CREDIT','CREDIT_CARD')}:
        reason = 'PRODUCT_NOT_COVERED'
    elif not isinstance(tx['amount_decimal'],str) or not re.fullmatch(r'-?(?:0|[1-9][0-9]*)(?:\.[0-9]{1,12})?',tx['amount_decimal']) or len(tx['amount_decimal'])>33 or Decimal(tx['amount_decimal']).copy_abs()>Decimal('1e18'):
        reason = 'VALUE_UNSUPPORTED'
    elif Decimal(tx['amount_decimal']) == 0:
        reason = 'ZERO_UNCLASSIFIED'
    elif not text(tx['currency'],16) or not tx['currency'].strip(''.join(WS26)) or any(ord(x)<32 and x not in '\t\n\r' for x in tx['currency']):
        reason = 'MONETARY_CONTEXT_MISSING'
    elif kind is None:
        reason = 'TYPE_PRESENCE_UNRECOVERABLE'
    elif kind not in ('CREDIT','DEBIT'):
        reason = 'TYPE_UNKNOWN_VALUE'
    else:
        result, reason = kind,'DECLARED_PROVIDER_TYPE'
        rule = 'R_CARD_TYPE' if product[0]=='CREDIT' else 'R_BANK_TYPE'
    return dict(policy_id='PLUGGY_DECLARED_TRANSACTION_DIRECTION',policy_version='DC-v2',policy_hash=POLICY_HASH,
                context_mode='CURRENT_ACCOUNT_METADATA',result=result,reason_code=reason,rule_id=rule,
                type_observation=obs,type_presence='UNRECOVERABLE' if kind is None else 'PRESENT',
                settlement_evidence=settlement,warnings=sorted(warnings))


def origin(tx, revisions, runs, evidence):
    row = revisions.get(tx['id'])
    reason = 'REVISION_ONE_MISSING'
    if row:
        run = runs.get(row['run_id'])
        reason = 'LINK_INCONSISTENT' if not run else 'LEGACY_ORIGIN_UNPROVEN'
        if run and evidence and run['connection_id']==tx['connection_id']:
            return dict(basis='FIRST_IMPORT_RUN',status='known',origin_run_id=run['id'],origin_revision=1,
                        reason_code=None,origin_run_state=run['state'])
    return dict(basis='FIRST_IMPORT_RUN',status='unknown',origin_run_id=None,origin_revision=None,
                reason_code=reason,origin_run_state=None)


def indices(data):
    connections = {r['id']:r for r in data['of_connections']}
    accounts = {(r['connection_id'],r['external_id']):r for r in data['of_accounts']}
    categories = {(r['connection_id'],r['category_key']):r for r in data['of_categories']}
    runs = {r['id']:r for r in data['of_sync_runs']}
    transactions = {r['id']:r for r in data['of_transactions']}
    first = {}
    seen = set()
    for row in list(accounts.values())+list(categories.values())+list(runs.values()):
        if row['connection_id'] not in connections:
            fail('STAGING_INTEGRITY_UNAVAILABLE',503)
    for run in runs.values():
        if not re.fullmatch('[0-9a-f]{32}',run['id']) or run['state'] not in {'RUNNING','SUCCEEDED','FAILED','INTERRUPTED'}:
            fail('STAGING_INTEGRITY_UNAVAILABLE',503)
    for tx in transactions.values():
        key = (tx['connection_id'],tx['external_account_id'],tx['external_id'])
        if (type(tx['id']) is not int or key in seen or tx['connection_id'] not in connections
                or connections[tx['connection_id']]['provider']!='PLUGGY'
                or any(not query_identifier(x,64 if i==0 else 200) for i,x in enumerate(key))):
            fail('STAGING_INTEGRITY_UNAVAILABLE',503)
        seen.add(key)
    for row in data['of_transaction_revisions']:
        tx, run = transactions.get(row['transaction_id']), runs.get(row['run_id'])
        if tx and (row['connection_id']!=tx['connection_id'] or run and run['connection_id']!=tx['connection_id']):
            fail('STAGING_INTEGRITY_UNAVAILABLE',503)
        if row['revision_number']==1:
            if row['transaction_id'] in first:
                fail('STAGING_INTEGRITY_UNAVAILABLE',503)
            first[row['transaction_id']] = row
    return connections, accounts, categories, runs, first


def catalogs(c, configs):
    with read_view(c) as deadline:
        data = capture(c,deadline)
        connections, accounts, categories, runs, _ = indices(data)
        configured = {cfg.id:cfg for cfg in configs}
        choices = {cid:dict(id=cid,institution=row['institution'],enabled=bool(row['enabled']),historical=cid not in configured)
                   for cid,row in connections.items()}
        for cid,cfg in configured.items():
            choices.setdefault(cid,dict(id=cid,institution=cfg.institution,enabled=cfg.enabled,historical=False))
        return dict(connections=sorted(choices.values(),key=lambda r:(r['institution'],r['id'])),
                    accounts=sorted(accounts.values(),key=lambda r:(r['connection_id'],r['external_id'])),
                    categories=sorted(categories.values(),key=lambda r:(r['connection_id'],r['category_key'])),
                    runs=sorted(runs.values(),key=lambda r:(r['started_at'],r['id']),reverse=True))


def query_transactions(c, query, configs, *, origin_evidence=False):
    q = parse(query)
    with read_view(c) as deadline:
        data = capture(c,deadline)
        connections, accounts, categories, runs, first = indices(data)
        known = set(connections) | {cfg.id for cfg in configs}
        cid = q.get('connection_id')
        if cid is not None and cid not in known:
            fail('RESOURCE_NOT_FOUND',404)
        for param, index in (('external_account_id',accounts),('category_key',categories)):
            if param in q and (cid,q[param]) not in index:
                fail('RESOURCE_NOT_FOUND',404)
        if 'origin_run_id' in q and (q['origin_run_id'] not in runs or runs[q['origin_run_id']]['connection_id']!=cid):
            fail('RESOURCE_NOT_FOUND',404)
        selected, states = [], dict(CREDIT=0,DEBIT=0,UNKNOWN=0,CONFLICT=0)
        excluded = indeterminate = eligible = 0
        configured = {cfg.id:cfg for cfg in configs}
        historical = unknown_origin = False
        for tx in data['of_transactions']:
            if time.monotonic()>deadline:
                fail('QUERY_BUDGET_EXCEEDED',503)
            tx = dict(tx)
            provenance = origin(tx,first,runs,origin_evidence)
            predicates = []
            day = civil(tx['transaction_date'])
            if 'start' in q or 'end' in q:
                predicates.append(None if day is None else q.get('start','0001-01-01')<=day<=q.get('end','9999-12-31'))
            for param, field in (('connection_id','connection_id'),('external_account_id','external_account_id'),('category_key','category_key')):
                if param in q:
                    predicates.append(tx[field]==q[param])
            if q['category_presence']!='any':
                predicates.append((tx['category_key'] is not None)==(q['category_presence']=='present'))
            if 'search' in q:
                keys = [search_key(tx[k]) if tx[k] is not None else '' for k in ('description_original','merchant_name')]
                predicates.append(True if any(k is not None and q['_search'] in k for k in keys) else None if None in keys else False)
            if q['provenance_state']!='any':
                predicates.append(provenance['status']==q['provenance_state'])
            if 'origin_run_id' in q:
                predicates.append(provenance['origin_run_id']==q['origin_run_id'] if provenance['status']=='known' else None)
            if False in predicates:
                excluded += 1
                continue
            if None in predicates:
                indeterminate += 1
                continue
            eligible += 1
            conn = connections[tx['connection_id']]
            account = accounts.get((tx['connection_id'],tx['external_account_id']))
            classification = direction(tx,conn,account)
            states[classification['result']] += 1
            if q['direction']!='all' and classification['result']!={'incoming':'CREDIT','outgoing':'DEBIT','unknown':'UNKNOWN','conflict':'CONFLICT'}[q['direction']]:
                continue
            category = categories.get((tx['connection_id'],tx['category_key']))
            tx.update(institution=conn['institution'],account_name=account['name'] if account else None,
                      category={k:category[k] for k in ('provider','external_id','original_name','display_name_pt','translation_status')} if category else None,
                      direction=classification,provenance=provenance)
            selected.append(tx)
        selected.sort(key=lambda r:r['id'], reverse=True)
        offset = (q['page']-1)*q['page_size']
        items = selected[offset:offset+q['page_size']]
        historical = any(r['connection_id'] not in configured or not configured[r['connection_id']].enabled for r in items)
        unknown_origin = any(r['provenance']['status']=='unknown' for r in items)
        def metric(n, required=False):
            return dict(state='EXACT',value=n,reason=None) if q['metrics']=='exact' or required else dict(state='NOT_REQUESTED',value=None,reason='NOT_REQUESTED')
        total = len(data['of_transactions'])
        counts = dict(global_authorized=metric(total),non_directional=dict(matched=metric(eligible),not_matched=metric(excluded),indeterminate=metric(indeterminate)),
                      classification={**{k.lower():metric(v) for k,v in states.items()},'not_evaluable_policy':metric(0,True)},
                      after_f04=metric(len(selected)),page_returned=metric(len(items),True))
        exact = q['metrics']=='exact'
        membership = dict(state='PARTIAL' if indeterminate else 'COMPLETE',basis='EXACT_COUNTS' if exact else 'QUALIFIED_GLOBAL_CHECK',
                          ratio=dict(numerator=total-indeterminate,denominator=total) if exact and total else None)
        coverage = dict(membership=membership,direction=dict(state='NO_DATA' if not eligible else 'PARTIAL' if states['UNKNOWN']+states['CONFLICT'] else 'COMPLETE',
            basis='EXACT_COUNTS' if exact else 'QUALIFIED_GLOBAL_CHECK',ratio=dict(numerator=states['CREDIT']+states['DEBIT'],denominator=eligible) if exact and eligible else None))
        active = [name for name,yes in [('F01','start' in q or 'end' in q),('F02',cid is not None),('F03','external_account_id' in q),
            ('F04',q['direction']!='all'),('F05','category_key' in q or q['category_presence']!='any'),('F06','search' in q),
            ('F07','origin_run_id' in q or q['provenance_state']!='any')] if yes]
        if not exact and not any(x!='F04' for x in active):
            membership['basis']='SEMANTIC_IDENTITY'
        warnings = []
        for flag,warning in ((indeterminate,'MEMBERSHIP_PARTIAL'),(states['UNKNOWN']+states['CONFLICT'],'DIRECTION_COVERAGE_PARTIAL'),
                (historical,'HISTORICAL_CONNECTION_INCLUDED'),(unknown_origin,'PROVENANCE_UNKNOWN_PRESENT')):
            if flag:
                warnings.append(warning)
        meta = dict(contract=CONTRACT,live=True,order='id_desc',date_basis='provider_representation_day',provenance_basis='FIRST_IMPORT_RUN',
            selection=dict(direction=q['direction'],metrics=q['metrics'],active_filters=active),
            policy=dict(status='ACTIVE',id='PLUGGY_DECLARED_TRANSACTION_DIRECTION',version='DC-v2',hash=POLICY_HASH,
                        context_mode='CURRENT_ACCOUNT_METADATA',perspective='DECLARED_ACCOUNT_MOVEMENT'),
            search_policy=dict(id='U31-A',version='13.0.0/FIXED-1',hash=SEARCH_HASH) if 'search' in q else None,
            read_consistency='same_read_view',catalog_context='CURRENT_PERSISTED_METADATA',counts=counts,coverage=coverage,
            query_completeness='QUALIFIED_PARTIAL' if indeterminate else 'COMPLETE',warnings=sorted(warnings))
        if time.monotonic()>deadline:
            fail('QUERY_BUDGET_EXCEEDED',503)
        return dict(items=items,page=q['page'],page_size=q['page_size'],has_more=len(selected)>offset+q['page_size'],query_meta=meta)
