"""Bounded, read-only Pluggy API adapter. No SQL, persistence or financial effects."""
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, DecimalException
import json
import re
import ssl
import threading
import time
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qsl, urlencode
from urllib.request import Request, build_opener, HTTPRedirectHandler, HTTPSHandler, ProxyHandler

from .pluggy_config import PluggyConnection
from .pluggy_coverage import cached_path, collection_pages


class PluggyError(Exception):
    """Public error codes are static; provider messages/credentials never escape."""
    def __init__(self, code):
        allowed = {'INVALID_ENDPOINT','RESPONSE_TOO_LARGE','INVALID_RESPONSE','NETWORK_FAILURE',
                   'INVALID_IDENTIFIER','INVALID_PERIOD','TRANSPORT_FAILURE','TRANSIENT_EXHAUSTED',
                   'CONNECTION_DISABLED','AUTH_FAILED','INVALID_AUTH_RESPONSE',
                   'UNSUPPORTED_ACCOUNT_PAGINATION','ACCOUNT_SCOPE_MISMATCH','DUPLICATE_ACCOUNT',
                   'TRANSACTION_SCOPE_MISMATCH','INVALID_CURSOR','CURSOR_SCOPE_MISMATCH',
                   'CURSOR_CYCLE','PAGE_LIMIT','PROVIDER_HTTP_ERROR'}
        self.code = code if isinstance(code,str) and code in allowed else 'TRANSPORT_FAILURE'
        super().__init__(self.code)


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def _reject_constant(_):
    raise ValueError()


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result: raise ValueError()
        result[key] = value
    return result


def transport(method, path, headers, body, timeout):
    """Fixed TLS host, no environment proxy, redirects or provider error bodies."""
    if not ((method == 'POST' and path == '/auth') or
            (method == 'GET' and cached_path(path))):
        raise PluggyError('INVALID_ENDPOINT')
    try:
        opener = build_opener(ProxyHandler({}), _NoRedirect(), HTTPSHandler(context=ssl.create_default_context()))
        request = Request('https://api.pluggy.ai' + path, data=body, headers=headers, method=method)
        with opener.open(request, timeout=timeout) as response:
            raw = response.read(2_000_001)
            if len(raw) > 2_000_000: raise PluggyError('RESPONSE_TOO_LARGE')
            try:
                data = json.loads(raw, parse_float=Decimal, parse_constant=_reject_constant,
                                  object_pairs_hook=_unique_object)
            except (ValueError, UnicodeError, RecursionError):
                raise PluggyError('INVALID_RESPONSE') from None
            return response.status, data
    except HTTPError as error:
        status = error.code
        error.close()
        return status, None
    except (URLError, TimeoutError, OSError):
        raise PluggyError('NETWORK_FAILURE') from None


def _text(value, required=False, limit=4096):
    if value is None and not required: return None
    if not isinstance(value, str) or len(value) > limit or (required and not value.strip()):
        raise PluggyError('INVALID_RESPONSE')
    if any(ord(c) < 32 and c not in '\t\n\r' for c in value):
        raise PluggyError('INVALID_RESPONSE')
    return value


def _identifier(value):
    result = _text(value, True, 200)
    if result != result.strip() or any(ord(c) < 32 or ord(c) == 127 for c in result):
        raise PluggyError('INVALID_IDENTIFIER')
    return result


def _provider_date(value, required=False):
    result = _text(value, required, 64)
    if result is None: return None
    if not re.fullmatch(r'\d{4}-\d{2}-\d{2}(?:T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2}))?', result):
        raise PluggyError('INVALID_RESPONSE')
    try: datetime.fromisoformat(result.replace('Z', '+00:00'))
    except ValueError: raise PluggyError('INVALID_RESPONSE') from None
    return result


def _period(value):
    if value is None: return None
    try:
        if not isinstance(value, str) or date.fromisoformat(value).isoformat() != value: raise ValueError()
    except ValueError: raise PluggyError('INVALID_PERIOD') from None
    return value


@dataclass(frozen=True)
class ExternalAccount:
    connection_id: str
    external_id: str
    name: str | None
    type: str | None
    subtype: str | None
    currency: str | None
    provider_updated_at: str | None

    def staging_fields(self):
        return vars(self).copy()


@dataclass(frozen=True)
class ExternalTransaction:
    connection_id: str
    external_account_id: str
    external_id: str
    transaction_date: str
    amount_decimal: str
    currency: str
    type: str | None
    status: str | None
    description_original: str | None
    description: str | None
    merchant_name: str | None
    category_id: str | int | None
    category_name: str | None
    provider_created_at: str | None
    provider_updated_at: str | None

    def staging_fields(self):
        # Catalog association and observation timestamps belong to the future
        # synchronization service; no automatic classification is done here.
        return {key: value for key, value in vars(self).items()
                if key not in {'category_id', 'category_name', 'description'}}


class PluggyClient:
    def coverage_get(self, path, *, optional=False):
        if not cached_path(path):
            raise PluggyError('INVALID_ENDPOINT')
        for attempt in range(2):
            status, data = self._bounded_send('GET', path,
                {'X-API-KEY': self._api_key(), 'Accept': 'application/json'}, None)
            if status == 401:
                self._key, self._expires = None, 0
                if attempt == 0:
                    continue
                raise PluggyError('AUTH_FAILED')
            if optional and status in (403, 404):
                return {}, 'NOT_AUTHORIZED' if status == 403 else 'NOT_AVAILABLE'
            if status != 200 or not isinstance(data, dict):
                raise PluggyError('AUTH_FAILED' if status == 403 else 'PROVIDER_HTTP_ERROR')
            return data, 'AVAILABLE'

    def coverage_pages(self):
        return collection_pages(self)

    def __init__(self, connection, *, send=transport, now=time.monotonic, sleep=time.sleep,
                 timeout=10, max_attempts=3, max_pages=200):
        if not isinstance(connection, PluggyConnection): raise ValueError('invalid connection type')
        if isinstance(timeout, bool) or not isinstance(timeout, (int,float)) or not 0 < timeout <= 60:
            raise ValueError('invalid timeout')
        if type(max_attempts) is not int or not 1 <= max_attempts <= 3:
            raise ValueError('invalid attempts limit')
        if type(max_pages) is not int or not 1 <= max_pages <= 1000:
            raise ValueError('invalid pages limit')
        self.connection = connection
        self._send, self._now, self._sleep = send, now, sleep
        self.timeout, self.max_attempts, self.max_pages = timeout, max_attempts, max_pages
        self._key, self._expires = None, 0
        self._account_ids = None
        self._lock = threading.RLock()

    def _bounded_send(self, method, path, headers, body):
        for attempt in range(self.max_attempts):
            try:
                status, data = self._send(method, path, headers, body, self.timeout)
            except (TimeoutError, OSError, URLError):
                status, data = 0, None
            except PluggyError as error:
                if error.code != 'NETWORK_FAILURE': raise
                status, data = 0, None
            except Exception:
                raise PluggyError('TRANSPORT_FAILURE') from None
            if type(status) is not int: raise PluggyError('INVALID_RESPONSE')
            if status == 0 or status in (408,429) or 500 <= status <= 599:
                if attempt + 1 < self.max_attempts:
                    self._sleep(attempt + 1)
                    continue
                raise PluggyError('NETWORK_FAILURE' if status == 0 else 'TRANSIENT_EXHAUSTED')
            return status, data

    def _api_key(self):
        if not self.connection.enabled: raise PluggyError('CONNECTION_DISABLED')
        with self._lock:
            if self._key is not None and self._now() < self._expires: return self._key
            body = json.dumps({'clientId':self.connection.client_id,
                               'clientSecret':self.connection.client_secret}).encode()
            status, data = self._bounded_send('POST','/auth',{'Content-Type':'application/json'},body)
            if status != 200: raise PluggyError('AUTH_FAILED')
            key = data.get('apiKey') if isinstance(data,dict) else None
            if not isinstance(key,str) or not 1 <= len(key) <= 4096 or not all(33 <= ord(c) <= 126 for c in key):
                raise PluggyError('INVALID_AUTH_RESPONSE')
            self._key, self._expires = key, self._now() + 6900
            return self._key

    def _get(self, path):
        for renewal in range(2):
            key = self._api_key()
            status, data = self._bounded_send('GET',path,{'X-API-KEY':key,'Accept':'application/json'},None)
            if status == 401:
                with self._lock:
                    if self._key == key: self._key, self._expires = None, 0
                if renewal == 0: continue
                raise PluggyError('AUTH_FAILED')
            if status != 200:
                raise PluggyError('AUTH_FAILED' if status == 403 else 'PROVIDER_HTTP_ERROR')
            if not isinstance(data,dict): raise PluggyError('INVALID_RESPONSE')
            return data

    @staticmethod
    def _rows(data):
        rows = data.get('results')
        if not isinstance(rows,list) or len(rows)>1000 or not all(isinstance(row,dict) for row in rows):
            raise PluggyError('INVALID_RESPONSE')
        return rows

    def accounts(self):
        data = self._get('/accounts?' + urlencode({'itemId':self.connection.item_id}))
        rows = self._rows(data)
        pages = data.get('totalPages',1)
        if isinstance(pages,bool) or not isinstance(pages,(int,float,Decimal)) or pages not in (0,1) or (pages==0 and rows):
            raise PluggyError('UNSUPPORTED_ACCOUNT_PAGINATION')
        total = data.get('total',len(rows))
        if isinstance(total,bool) or not isinstance(total,(int,float,Decimal)) or total != len(rows):
            raise PluggyError('INVALID_RESPONSE')
        result=[]; ids=set()
        for row in rows:
            identifier = _identifier(row.get('id'))
            if row.get('itemId') != self.connection.item_id: raise PluggyError('ACCOUNT_SCOPE_MISMATCH')
            if identifier in ids: raise PluggyError('DUPLICATE_ACCOUNT')
            ids.add(identifier)
            result.append(ExternalAccount(self.connection.id,identifier,_text(row.get('name')),
                _text(row.get('type')), _text(row.get('subtype')), _text(row.get('currencyCode')),
                _provider_date(row.get('updatedAt'))))
        with self._lock: self._account_ids=frozenset(ids)
        return tuple(result)

    def _transaction(self, row, account_id):
        if row.get('accountId') != account_id: raise PluggyError('TRANSACTION_SCOPE_MISMATCH')
        amount=row.get('amount')
        if isinstance(amount,bool) or not isinstance(amount,(str,int,float,Decimal)):
            raise PluggyError('INVALID_RESPONSE')
        try:
            if isinstance(amount,str) and len(amount)>128: raise ValueError()
            amount=Decimal(str(amount))
            if not amount.is_finite() or not -12 <= amount.as_tuple().exponent <= 18 or amount.copy_abs()>Decimal('1e18'): raise ValueError()
        except (DecimalException,ValueError): raise PluggyError('INVALID_RESPONSE') from None
        category=row.get('categoryId')
        if category is not None and (type(category) not in (str,int) or len(str(category))>200 or (isinstance(category,str) and not category.strip())):
            raise PluggyError('INVALID_RESPONSE')
        merchant=row.get('merchant')
        if merchant is not None and not isinstance(merchant,dict): raise PluggyError('INVALID_RESPONSE')
        description=_text(row.get('description'))
        raw_description=_text(row.get('descriptionRaw'))
        return ExternalTransaction(self.connection.id,account_id,_identifier(row.get('id')),
            _provider_date(row.get('date'),True),format(amount,'f'),_text(row.get('currencyCode'),True,16),
            _text(row.get('type')), _text(row.get('status')),raw_description if raw_description is not None else description,
            description,_text(merchant.get('name')) if merchant else None,category,_text(row.get('category')),
            _provider_date(row.get('createdAt')), _provider_date(row.get('updatedAt')))

    @staticmethod
    def _cursor(query_string, scope):
        if not isinstance(query_string,str) or not query_string.startswith('?') or len(query_string)>8192:
            raise PluggyError('INVALID_CURSOR')
        if '#' in query_string or any(ord(c)<32 or ord(c)==127 for c in query_string):
            raise PluggyError('INVALID_CURSOR')
        try:
            pairs=parse_qsl(query_string[1:],keep_blank_values=True,strict_parsing=True,max_num_fields=8)
        except ValueError: raise PluggyError('INVALID_CURSOR') from None
        fields=dict(pairs)
        if len(fields)!=len(pairs) or set(fields)-{'accountId','dateFrom','dateTo','after'} or not fields.get('after'):
            raise PluggyError('INVALID_CURSOR')
        if {k:v for k,v in fields.items() if k!='after'} != scope: raise PluggyError('CURSOR_SCOPE_MISMATCH')
        # Compare semantic query identities for cycle detection; send next as-is.
        return tuple(sorted(fields.items()))

    def transaction_pages(self, account_id, *, date_from=None, date_to=None):
        account_id=_identifier(account_id)
        start,end=_period(date_from),_period(date_to)
        if start and end and start>end: raise PluggyError('INVALID_PERIOD')
        if self._account_ids is None: self.accounts()
        if account_id not in self._account_ids: raise PluggyError('ACCOUNT_SCOPE_MISMATCH')
        scope={'accountId':account_id}
        if start: scope['dateFrom']=start
        if end: scope['dateTo']=end
        path='/v2/transactions?'+urlencode(scope); seen=set()
        for page in range(self.max_pages):
            data=self._get(path)
            rows=tuple(self._transaction(row,account_id) for row in self._rows(data))
            if 'next' not in data: raise PluggyError('INVALID_RESPONSE')
            next_query=data['next']
            if next_query is not None:
                marker=self._cursor(next_query,scope)
                if marker in seen: raise PluggyError('CURSOR_CYCLE')
                seen.add(marker)
                if page+1 == self.max_pages: raise PluggyError('PAGE_LIMIT')
            yield rows
            if next_query is None: return
            path='/v2/transactions'+next_query

    def transactions(self, account_id, **period):
        for page in self.transaction_pages(account_id,**period): yield from page


def clients_for_connections(connections, **options):
    if len({connection.id for connection in connections}) != len(connections):
        raise ValueError('duplicate connection IDs')
    return {connection.id:PluggyClient(connection,**options) for connection in connections}
