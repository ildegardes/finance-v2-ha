"""Allowlisted error context only. No I/O except one best-effort diagnostic log."""
from hashlib import sha256
import json
import logging
import re


LOGGER = logging.getLogger('finance_v2.open_finance.diagnostics')
ERRORS = frozenset({'ACCOUNT_SCOPE_MISMATCH', 'AUTH_FAILED'})
RESOURCES = frozenset({'item', 'resources', 'consents', 'accounts', 'transactions',
    'investments', 'investment_transactions', 'loans', 'bills', 'statements', 'other'})
OPERATIONS = {
    'item': 'ITEM_GET', 'resources': 'ITEM_RESOURCES_LIST', 'consents': 'CONSENTS_LIST',
    'accounts': 'ACCOUNTS_LIST', 'transactions': 'TRANSACTIONS_LIST',
    'investments': 'INVESTMENTS_LIST', 'investment_transactions': 'INVESTMENT_TRANSACTIONS_LIST',
    'loans': 'LOANS_LIST', 'bills': 'BILLS_LIST', 'statements': 'STATEMENTS_LIST',
}
OPERATION_NAMES = frozenset(OPERATIONS.values()) | {'AUTH_CREATE', 'ACCOUNTS_PERSIST',
    'TRANSACTION_ACCOUNT_SCOPE', 'OTHER_OPERATION'}
STAGES = frozenset({'TOKEN_ACQUISITION', 'RESOURCE_QUERY', 'SCOPE_CHECK', 'STAGING_CHECK', 'UNKNOWN'})
CATEGORIES = frozenset({'AUTH_REQUEST_REJECTED', 'REPEATED_401', 'REQUIRED_RESOURCE_403',
    'ITEM_ID_MISSING', 'ITEM_ID_NULL', 'ITEM_ID_DIFFERENT',
    'RESPONSE_ID_MISSING', 'RESPONSE_ID_NULL', 'RESPONSE_ID_DIFFERENT',
    'ACCOUNT_MEMBERSHIP_MISS', 'LOCAL_CONNECTION_MISMATCH', 'OTHER_CONDITION'})


def _choice(value, choices, fallback):
    return value if type(value) is str and value in choices else fallback


def _context(values):
    values = values if type(values) is dict else {}
    status = values.get('http_status')
    return {
        'resource': _choice(values.get('resource'), RESOURCES, 'other'),
        'operation': _choice(values.get('operation'), OPERATION_NAMES, 'OTHER_OPERATION'),
        'stage': _choice(values.get('stage'), STAGES, 'UNKNOWN'),
        'category': _choice(values.get('category'), CATEGORIES, 'OTHER_CONDITION'),
        'http_status': status if type(status) is int and 100 <= status <= 599 else None,
    }


def annotate(error, *, resource='other', operation='OTHER_OPERATION', stage='UNKNOWN',
             category='OTHER_CONDITION', http_status=None):
    code = getattr(error, 'code', None)
    if type(code) is not str or code not in ERRORS:
        return error
    # Never retain a provider row, URL, identifier, header, body or message.
    error._of_diagnostic = _context({'resource': resource, 'operation': operation,
        'stage': stage, 'category': category, 'http_status': http_status})
    return error


def scope_category(row, field='itemId'):
    prefix = {'itemId': 'ITEM_ID_', 'id': 'RESPONSE_ID_'}.get(field)
    if prefix is None or not isinstance(row, dict):
        return 'OTHER_CONDITION'
    return prefix + ('MISSING' if field not in row else 'NULL' if row[field] is None else 'DIFFERENT')


def describe_resource(resource):
    resource = _choice(resource, RESOURCES, 'other')
    return {'resource': resource, 'operation': OPERATIONS.get(resource, 'OTHER_OPERATION')}


def describe_path(path):
    # Classification only, called after the existing error predicate. Captures
    # are never returned and query strings are never stored or logged.
    if type(path) is not str or len(path) > 16384:
        return describe_resource('other')
    base = path.split('?', 1)[0]
    if base in ('/accounts', '/consents', '/investments', '/loans', '/bills'):
        return describe_resource(base[1:])
    if base == '/v2/transactions':
        return describe_resource('transactions')
    for pattern, resource in (
        (r'/items/[^/?]+', 'item'), (r'/items/[^/?]+/resources', 'resources'),
        (r'/accounts/[^/?]+/statements', 'statements'),
        (r'/investments/[^/?]+/transactions', 'investment_transactions')):
        if re.fullmatch(pattern, base):
            return describe_resource(resource)
    return describe_resource('other')


def emit(institution, run_id, error):
    code = getattr(error, 'code', None)
    if type(code) is not str or code not in ERRORS:
        return False
    logical = {'itau': 'ITAU', 'santander': 'SANTANDER'}.get(institution, 'OTHER') if type(institution) is str else 'OTHER'
    correlation = ('ofdiag-' + sha256(run_id.encode('ascii')).hexdigest()[:24]
        if type(run_id) is str and re.fullmatch(r'[0-9a-f]{32}', run_id) else 'UNAVAILABLE')
    event = {'event': 'OPEN_FINANCE_DIAGNOSTIC', 'version': 'D02/1',
        'institution': logical, 'correlation_id': correlation, 'error_code': code,
        **_context(getattr(error, '_of_diagnostic', None))}
    try:
        LOGGER.warning('OPEN_FINANCE_DIAGNOSTIC %s', json.dumps(event, sort_keys=True, separators=(',', ':')))
    except Exception:
        # A broken diagnostic sink must not replace the original error or prevent
        # its existing finalization/lease cleanup. No error is marked successful.
        return False
    return True
