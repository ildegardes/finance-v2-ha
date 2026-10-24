"""Explicit cached GET contracts. Never contacts institutions or changes consent."""
from decimal import Decimal
from hashlib import sha256
import json
from pathlib import Path
import re
from urllib.parse import urlencode


RESOURCES = ('item', 'resources', 'consents', 'accounts', 'transactions', 'investments',
             'investment_transactions', 'loans', 'bills', 'statements')
CONTRACT_SHA256 = '985404C7EC53EFE9F97DC9A8591C444D974BF14CF414F8BADEE4840E798F6419'


def contracts():
    raw = Path(__file__).with_name('pluggy_coverage_contracts.json').read_bytes()
    if sha256(raw).hexdigest().upper() != CONTRACT_SHA256:
        raise RuntimeError('PLUGGY_COVERAGE_CONTRACT_INTEGRITY')
    data = json.loads(raw)
    if data.get('version') != 'PLUGGY-CACHED-COVERAGE/1' or set(data['resources']) != set(RESOURCES):
        raise RuntimeError('PLUGGY_COVERAGE_CONTRACT_VERSION')
    return data


def cached_path(path):
    # GET is not by itself a safety guarantee. Balance and SCR are deliberately absent.
    return bool(re.fullmatch(
        r'/(?:items/[A-Za-z0-9_-]{1,200}(?:/resources)?|accounts(?:/[A-Za-z0-9_-]{1,200}/statements)?|'
        r'v2/transactions|consents|investments(?:/[A-Za-z0-9_-]{1,200}/transactions)?|loans|bills)'
        r'(?:\?[^\x00-\x20#]{1,8192})?', path))


def output_schema(spec, nullable=False):
    """HTTP projection retains exact Decimal strings and explicit provider nulls."""
    result = dict(spec)
    if 'properties' in result:
        result.setdefault('type', 'object')
        result['properties'] = {k: output_schema(v, True) for k, v in result['properties'].items()}
    if 'items' in result:
        result['items'] = output_schema(result['items'], True)
    if result.get('type') == 'number' or (isinstance(result.get('type'), list) and 'number' in result['type']):
        result = {'anyOf': [result, {'type': 'string', 'pattern': r'^-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?$'}]}
    return {'anyOf': [result, {'type': 'null'}]} if nullable else result


def project(resource, row):
    """Schema allowlist, preserving null/absence/zero. Unknown/private fields counted, not logged."""
    schema = CONTRACT['resources'][resource]['schema']
    omitted = 0

    def walk(value, spec, depth=0):
        nonlocal omitted
        if depth > 16:
            raise ValueError('COVERAGE_PAYLOAD_DEPTH')
        if value is None:
            return None
        expected = spec.get('type') or ('object' if 'properties' in spec else 'array' if 'items' in spec else None)
        types = expected if isinstance(expected, list) else [expected]
        actual = 'object' if isinstance(value, dict) else 'array' if isinstance(value, list) else 'boolean' if isinstance(value, bool) else 'integer' if isinstance(value, int) else 'number' if isinstance(value, (Decimal, float)) else 'string' if isinstance(value, str) else 'unsupported'
        if expected and actual not in types and not (actual == 'integer' and 'number' in types):
            raise ValueError('COVERAGE_FIELD_TYPE')
        if isinstance(value, dict):
            result = {}
            for key, child in value.items():
                if key not in spec.get('properties', {}):
                    omitted += 1
                    continue
                result[key] = walk(child, spec['properties'][key], depth + 1)
            return result
        if isinstance(value, list):
            if len(value) > 1000:
                raise ValueError('COVERAGE_ARRAY_LIMIT')
            if 'items' not in spec:
                omitted += 1
                return None
            return [walk(child, spec['items'], depth + 1) for child in value]
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, Decimal, float)):
            if not Decimal(str(value)).is_finite():
                raise ValueError('COVERAGE_NONFINITE')
            return format(value, 'f') if isinstance(value, Decimal) else value
        if not isinstance(value, str) or len(value) > 32768:
            raise ValueError('COVERAGE_FIELD_LIMIT')
        return value

    if not isinstance(row, dict):
        raise ValueError('COVERAGE_INVALID_ROW')
    payload = walk(row, schema)
    encoded = json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(',', ':'), allow_nan=False)
    if len(encoded) > 250000:
        raise ValueError('COVERAGE_RECORD_LIMIT')
    return payload, encoded, sha256(encoded.encode()).hexdigest(), omitted


def collection_pages(client):
    """Configured Item only, bounded pages. Complete snapshots; no misleading createdAt-only delta."""
    from .pluggy_client import PluggyError, _identifier
    item_id = _identifier(client.connection.item_id)
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,200}', item_id):
        raise PluggyError('INVALID_IDENTIFIER')
    budget = 1000

    def get(path, optional=False):
        nonlocal budget
        budget -= 1
        if budget < 0:
            raise PluggyError('PAGE_LIMIT')
        return client.coverage_get(path, optional=optional)

    item, state = get('/items/' + item_id)
    if item.get('id') != item_id:
        raise PluggyError('ACCOUNT_SCOPE_MISMATCH')
    yield {'resource': 'item', 'parent': '', 'rows': [item], 'state': 'AVAILABLE', 'last': True}

    def pages(resource, parent, path, query, optional=True):
        spec = CONTRACT['resources'][resource]
        paged = 'page' in spec['parameters']
        cursor = resource == 'transactions'
        seen = set()
        seen_ids = set()
        request_query = query.copy()
        observed = 0
        expected_total = None
        for page in range(1, client.max_pages + 1):
            if paged:
                request_query.update(page=page, pageSize=500)
            current = path + ('?' + urlencode(request_query) if request_query else '')
            if current in seen:
                raise PluggyError('CURSOR_CYCLE')
            seen.add(current)
            data, state = get(current, optional)
            if state != 'AVAILABLE':
                if observed:
                    raise PluggyError('INVALID_RESPONSE')
                yield {'resource': resource, 'parent': parent, 'rows': [], 'state': state, 'last': True}
                return
            rows = client._rows(data)
            for row in rows:
                if resource in ('accounts','investments','loans','consents') and row.get('itemId') != item_id:
                    raise PluggyError('ACCOUNT_SCOPE_MISMATCH')
                if 'itemId' in row and row['itemId'] != item_id:
                    raise PluggyError('ACCOUNT_SCOPE_MISMATCH')
                if resource == 'transactions' and row.get('accountId') != parent:
                    raise PluggyError('TRANSACTION_SCOPE_MISMATCH')
                identity = _identifier(row.get('resourceId') if resource == 'resources' else row.get('id'))
                if identity in seen_ids:
                    raise PluggyError('INVALID_RESPONSE')
                seen_ids.add(identity)
            observed += len(rows)
            if cursor:
                if 'next' not in data:
                    raise PluggyError('INVALID_RESPONSE')
                nxt = data.get('next')
                if nxt is not None:
                    # The existing strict parser pins account and date scope, rejects hosts/traversal.
                    current_next = client._cursor(nxt, query)
                    request_query = dict(current_next)
                last = nxt is None
            else:
                total = data.get('total')
                total_pages = data.get('totalPages')
                if type(total) is not int or type(total_pages) is not int or total < 0 or total_pages < 0:
                    raise PluggyError('INVALID_RESPONSE')
                if (total_pages == 0 and total != 0) or data.get('page') != page:
                    raise PluggyError('INVALID_RESPONSE')
                if expected_total is None:
                    expected_total = total
                if total != expected_total or observed > total or (not rows and observed < total):
                    raise PluggyError('INVALID_RESPONSE')
                if not paged and total_pages > 1:
                    raise PluggyError('UNSUPPORTED_ACCOUNT_PAGINATION')
                last = page >= total_pages
                if last and observed != total:
                    raise PluggyError('INVALID_RESPONSE')
            if resource == 'resources' and not item.get('resourcesCollectedAt') and not rows:
                state = 'NOT_COLLECTED'
            yield {'resource': resource, 'parent': parent, 'rows': rows, 'state': state, 'last': last}
            if last:
                return
        raise PluggyError('PAGE_LIMIT')

    for resource in ('resources', 'consents'):
        yield from pages(resource, '', '/items/' + item_id + '/resources' if resource == 'resources' else '/consents',
                         {} if resource == 'resources' else {'itemId': item_id})
    accounts = []
    for batch in pages('accounts', '', '/accounts', {'itemId': item_id}, False):
        accounts.extend(batch['rows'])
        yield batch
    for account in accounts:
        account_id = _identifier(account['id'])
        if not re.fullmatch(r'[A-Za-z0-9_-]{1,200}', account_id):
            raise PluggyError('INVALID_IDENTIFIER')
        yield from pages('transactions', account_id, '/v2/transactions', {'accountId': account_id}, False)
        if account.get('type') == 'CREDIT':
            yield from pages('bills', account_id, '/bills', {'accountId': account_id})
        elif account.get('type') == 'BANK':
            yield from pages('statements', account_id, '/accounts/' + account_id + '/statements', {})
    investments = []
    for batch in pages('investments', '', '/investments', {'itemId': item_id}):
        investments.extend(batch['rows'])
        yield batch
    for investment in investments:
        identifier = _identifier(investment['id'])
        if not re.fullmatch(r'[A-Za-z0-9_-]{1,200}', identifier):
            raise PluggyError('INVALID_IDENTIFIER')
        yield from pages('investment_transactions', identifier, '/investments/' + identifier + '/transactions', {})
    yield from pages('loans', '', '/loans', {'itemId': item_id})


# Verified once on application import. Missing, altered or incompatible data fail closed.
CONTRACT = contracts()
