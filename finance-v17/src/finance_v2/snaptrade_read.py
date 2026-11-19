"""The complete SnapTrade SDK surface used by Finance V17."""
from datetime import datetime, timezone
from decimal import Decimal
from email.utils import parsedate_to_datetime
import json
import logging
import re
from urllib.parse import urlsplit

HOST = 'api.snaptrade.com'
READ_PATH = re.compile(r'/(?:api/v1/)?(?:authorizations|accounts/all|accounts/[0-9a-f-]{36}/(?:balances/v2|positions/all|activities))')
MAX_BYTES = 16_000_000


class ProviderFailure(Exception):
    def __init__(self, code, retry=0):
        super().__init__(code)
        self.code, self.retry = code, retry


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
        raise ProviderFailure('SNAPTRADE_OPERATION_DENIED')


class SnapTradeReader:
    def __init__(self, client_id, consumer_key):
        from snaptrade_client import Configuration, SnapTrade, SnapTradeAuth
        auth = SnapTradeAuth.personal_api_key(client_id=client_id,consumer_key=consumer_key)
        settings = Configuration(auth=auth, host='https://'+HOST)
        settings.retries = False
        settings.debug = False
        sdk = SnapTrade(auth=auth,configuration=settings)
        api = sdk.account_information
        # The generated client signs the request. Its synchronous pool is also
        # restricted so accidentally wired SDK operations fail before transport.
        pool = api.api_client.rest_client.pool_manager
        request = pool.request
        def restricted(method,url,*args,**kwargs):
            validate_read_request(method,url)
            kwargs.update(redirect=False,retries=False)
            return request(method,url,*args,**kwargs)
        pool.request = restricted
        # urllib3 DEBUG includes the signed query string.
        logging.getLogger('urllib3.connectionpool').setLevel(logging.WARNING)
        self._reads = {
            'connections':sdk.connections.list_brokerage_authorizations,
            'accounts':api.list_all_user_accounts,
            'balances':api.get_account_balances_v2,
            'positions':api.get_all_account_positions,
            'activities':api.get_account_activities,
        }

    def read(self, operation, **parameters):
        if operation not in self._reads:
            raise ProviderFailure('SNAPTRADE_OPERATION_DENIED')
        try:
            response = self._reads[operation](timeout=(4,8),**parameters).response
            status, headers = response.status,response.headers
            if status != 200:
                raise ProviderFailure(_status(status,headers),_retry(headers) if status==429 else 0)
            raw = response.data
            if not isinstance(raw,bytes) or len(raw)>MAX_BYTES:
                raise ProviderFailure('SNAPTRADE_RESPONSE_LIMIT')
            return json.loads(raw,parse_float=Decimal,parse_constant=_invalid_constant)
        except ProviderFailure:
            raise
        except Exception as error:
            status = getattr(error,'status',None)
            headers = getattr(error,'headers',None) or {}
            if status:
                code, delay = _status(status,headers),_retry(headers) if status==429 else 0
            elif isinstance(error,(ValueError,TypeError)):
                code, delay = 'SNAPTRADE_INVALID_DATA',0
            else:
                code, delay = 'SNAPTRADE_TRANSPORT',0
            raise ProviderFailure(code,delay) from None


def _status(status,headers):
    if status==429 and headers.get('X-RateLimit-Account-Remaining')=='0' and headers.get('X-RateLimit-Remaining')!='0':
        return 'SNAPTRADE_ACCOUNT_RATE_LIMIT'
    return {401:'SNAPTRADE_AUTH',403:'SNAPTRADE_FORBIDDEN',404:'SNAPTRADE_UNAVAILABLE',
            429:'SNAPTRADE_RATE_LIMIT'}.get(status,'SNAPTRADE_REMOTE')


def _invalid_constant(_):
    raise ValueError()
