"""SDK-signed, read-only access to the SnapTrade Personal cache."""
from datetime import datetime, timezone
from decimal import Decimal
from email.utils import parsedate_to_datetime
import json
import logging
import re
from urllib.parse import urlsplit

from urllib3.exceptions import HTTPError

HOST = 'api.snaptrade.com'
READ_PATH = re.compile(r'/(?:api/v1/)?(?:authorizations|accounts/all|accounts/[0-9a-f-]{36}/(?:balances/v2|positions/all|activities))')
MAX_BYTES = 16_000_000


class ProviderFailure(Exception):
    def __init__(self, code, retry=0, *, stage=None, resource=None, reason=None, field=None, remote_status=None):
        super().__init__(code)
        self.code, self.retry = code, retry
        self.stage, self.resource, self.reason = stage, resource, reason
        self.field, self.remote_status = field, remote_status

    def at(self, stage, resource):
        if self.stage is None:
            self.stage = stage
        if self.resource is None:
            self.resource = resource.upper()
        return self

    def diagnostic(self):
        detail = {'error_code':self.code, 'stage':self.stage, 'resource':self.resource,
                  'reason':self.reason or self.code.removeprefix('SNAPTRADE_'),
                  'field':self.field, 'remote_status':self.remote_status}
        return {key:value for key,value in detail.items() if value is not None}


def _retry(headers):
    raw = headers.get('Retry-After','')
    if isinstance(raw,str) and raw.isdecimal() and len(raw)<=10:
        return max(60,int(raw))
    if isinstance(raw,str) and raw:
        try:
            return max(60,int((parsedate_to_datetime(raw)-datetime.now(timezone.utc)).total_seconds()))
        except (ValueError, TypeError, OverflowError):
            pass
    reset = [headers.get(prefix+'-Reset','') for prefix in ('X-RateLimit','X-RateLimit-Account')
             if headers.get(prefix+'-Remaining')=='0']
    seconds=[int(raw) for raw in reset if isinstance(raw,str) and raw.isdecimal() and len(raw)<=10]
    return max(60,*seconds) if seconds else 300


def validate_read_request(method,url):
    target = urlsplit(url)
    if method!='GET' or target.scheme!='https' or target.netloc!=HOST or not READ_PATH.fullmatch(target.path):
        raise ProviderFailure('SNAPTRADE_OPERATION_DENIED',stage='READ_GATE')


def _remote_failure(status,headers,raw):
    code=_status(status,headers)
    if status==401 and isinstance(raw,bytes) and len(raw)<=4096:
        try:
            body=json.loads(raw)
        except (ValueError,UnicodeError,RecursionError):
            body=None
        if isinstance(body,dict) and any(
            body.get(field)=='Unable to verify signature sent' for field in ('detail','default_detail')
        ):
            code='SNAPTRADE_SIGNATURE'
    return ProviderFailure(code,_retry(headers) if status==429 else 0,stage='REMOTE_HTTP',remote_status=status)


class SnapTradeReader:
    def __init__(self, client_id, consumer_key):
        from snaptrade_client import Configuration, SnapTrade, SnapTradeAuth
        auth = SnapTradeAuth.personal_api_key(client_id=client_id,consumer_key=consumer_key)
        settings = Configuration(auth=auth, host='https://'+HOST)
        settings.retries = False
        settings.debug = False
        sdk = SnapTrade(auth=auth,configuration=settings)
        api = sdk.account_information
        pool = api.api_client.rest_client.pool_manager
        request = pool.request

        def restricted(method,url,*args,**kwargs):
            validate_read_request(method,url)
            kwargs.update(redirect=False,retries=False)
            response=request(method,url,*args,**kwargs)
            # The generated client may decode or stringify an error body before
            # returning. Capture only protocol metadata and the documented signal.
            if response.status!=200:
                raise _remote_failure(response.status,response.headers,response.data if response.status==401 else None)
            raw=response.data
            if not isinstance(raw,bytes):
                raise ProviderFailure('SNAPTRADE_SDK_RESPONSE',stage='SDK_RESPONSE',reason='INVALID_RESPONSE_BYTES',remote_status=200)
            if len(raw)>MAX_BYTES:
                raise ProviderFailure('SNAPTRADE_RESPONSE_LIMIT',stage='JSON_DECODE',remote_status=200)
            return response

        pool.request = restricted
        # These loggers can include the signed URL or raw financial response at DEBUG.
        for name in ('urllib3.connectionpool','snaptrade_client.rest'):
            logging.getLogger(name).setLevel(logging.WARNING)
        self._reads = {
            'connections':sdk.connections.list_brokerage_authorizations,
            'accounts':api.list_all_user_accounts,
            'balances':api.get_account_balances_v2,
            'positions':api.get_all_account_positions,
            'activities':api.get_account_activities,
        }

    def read(self, operation, **parameters):
        if operation not in self._reads:
            raise ProviderFailure('SNAPTRADE_OPERATION_DENIED',stage='READ_GATE')
        resource=operation.upper()
        try:
            reply=self._reads[operation](timeout=(4,8),**parameters)
        except ProviderFailure as error:
            raise error.at('SDK_CALL',resource) from None
        except (json.JSONDecodeError,UnicodeError,RecursionError):
            raise ProviderFailure('SNAPTRADE_INVALID_JSON',stage='JSON_DECODE',resource=resource,remote_status=200) from None
        except (HTTPError,OSError):
            raise ProviderFailure('SNAPTRADE_TRANSPORT',stage='TRANSPORT',resource=resource) from None
        except Exception as error:
            reason='SDK_ARGUMENT_TYPE' if isinstance(error,TypeError) else (
                'SDK_ARGUMENT_VALUE' if isinstance(error,ValueError) else 'SDK_CALL_FAILED')
            raise ProviderFailure('SNAPTRADE_SDK_CALL',stage='SDK_CALL',reason=reason,resource=resource) from None
        try:
            response=reply.response
            status,headers,raw=response.status,response.headers,response.data
            if type(status) is not int or not 100<=status<=599 or not hasattr(headers,'get') or not isinstance(raw,bytes):
                raise TypeError()
        except Exception:
            raise ProviderFailure('SNAPTRADE_SDK_RESPONSE',stage='SDK_RESPONSE',resource=resource) from None
        if status!=200:
            raise _remote_failure(status,headers,raw).at('REMOTE_HTTP',resource)
        if len(raw)>MAX_BYTES:
            raise ProviderFailure('SNAPTRADE_RESPONSE_LIMIT',stage='JSON_DECODE',resource=resource,remote_status=200)
        try:
            return json.loads(raw,parse_float=Decimal,parse_constant=_invalid_constant)
        except (ValueError,UnicodeError,RecursionError):
            raise ProviderFailure('SNAPTRADE_INVALID_JSON',stage='JSON_DECODE',resource=resource,remote_status=200) from None


def _status(status,headers):
    if status==429 and headers.get('X-RateLimit-Account-Remaining')=='0' and headers.get('X-RateLimit-Remaining')!='0':
        return 'SNAPTRADE_ACCOUNT_RATE_LIMIT'
    return {401:'SNAPTRADE_AUTH',403:'SNAPTRADE_FORBIDDEN',404:'SNAPTRADE_UNAVAILABLE',
            429:'SNAPTRADE_RATE_LIMIT'}.get(status,'SNAPTRADE_REMOTE')


def _invalid_constant(_):
    raise ValueError()
