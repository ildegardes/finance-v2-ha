"""Allowlisted data that may be written to the local investment staging."""
from datetime import date, datetime
from decimal import Decimal, localcontext
from hashlib import sha256
import re
from uuid import UUID

from .open_finance_analytics import _amount
from .open_finance_schedule import _datetime, _iso
from .snaptrade_read import ProviderFailure

KINDS = {
    'BUY':'CAPITAL', 'SELL':'CAPITAL', 'CONTRIBUTION':'TRANSFER', 'DEPOSIT':'TRANSFER',
    'WITHDRAWAL':'TRANSFER', 'TRANSFER':'TRANSFER', 'DIVIDEND':'DIVIDEND',
    'SUBSTITUTE_DIVIDEND':'DIVIDEND', 'INTEREST':'INTEREST', 'REI':'REINVESTMENT',
    'REINVESTMENT':'REINVESTMENT', 'FEE':'FEE', 'TAX':'TAX', 'WITHHOLDING':'TAX',
    'SPLIT':'CORPORATE_ACTION', 'REVERSE_SPLIT':'CORPORATE_ACTION', 'STOCK_DIVIDEND':'CORPORATE_ACTION',
    'MERGER':'CORPORATE_ACTION', 'SPINOFF':'CORPORATE_ACTION', 'OPTIONEXPIRATION':'CORPORATE_ACTION',
    'OPTIONEXERCISE':'CORPORATE_ACTION','OPTIONASSIGNMENT':'CORPORATE_ACTION',
}
SECURITIES = {'stock','preferred_stock','adr','etf','mutualfund','cef','bond','other'}


def key(*parts):
    return 'st-'+sha256('\0'.join(('SNAPTRADE',*parts)).encode()).hexdigest()


def ident(value):
    try:
        return str(UUID(value))
    except (ValueError,TypeError,AttributeError):
        raise ProviderFailure('SNAPTRADE_INVALID_DATA') from None


def code(value):
    return value if isinstance(value,str) and re.fullmatch(r'[A-Z]{3}',value) else None


def text(value, secrets=()):
    if not isinstance(value,str) or not value.isprintable() or any(secret in value for secret in secrets if secret):
        return None
    # Owner descriptions and institution labels sometimes contain an account number.
    return re.sub(r'(?<!\d)(?:\d[ -]?){7,}\d(?!\d)','••••',value).strip()[:180] or None


def decimal(value):
    amount = _amount(value)
    return format(amount,'f') if amount is not None else None


def day(value):
    if not isinstance(value,str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}(?:T.*)?',value):
        return None
    try:
        return date.fromisoformat(value[:10]).isoformat()
    except ValueError:
        return None


def timestamp(value):
    return _iso(_datetime(value))


def collection(value,fields=None):
    if not isinstance(value,list) or len(value)>15000 or any(not isinstance(item,dict) for item in value):
        raise ProviderFailure('SNAPTRADE_INVALID_DATA')
    if fields and any(any(field not in item for field in fields) for item in value):
        raise ProviderFailure('SNAPTRADE_INVALID_DATA')
    return value


def position(row,as_of,observed,secrets):
    instrument = row.get('instrument')
    if not isinstance(instrument,dict):
        raise ProviderFailure('SNAPTRADE_INVALID_DATA')
    kind = text(instrument.get('kind'),secrets)
    if not kind:
        raise ProviderFailure('SNAPTRADE_INVALID_DATA')
    cash = row.get('cash_equivalent') is True or kind=='cash'
    currency = code(row.get('currency')) or (code(instrument.get('code')) if kind=='cash' else None)
    identity = instrument.get('id') or (currency if kind=='cash' else None)
    if not isinstance(identity,str) or not identity or len(identity)>200:
        raise ProviderFailure('SNAPTRADE_INVALID_DATA')
    units,price = _amount(row.get('units')), _amount(row.get('price'))
    value = _amount(row.get('market_value'))
    # Contract multipliers and notional values vary. Derive only per-unit securities.
    if value is None and units is not None and price is not None and kind in SECURITIES:
        with localcontext() as ctx:
            ctx.prec=82
            value = units*price
    basis = decimal(row.get('cost_basis'))
    exchange = text(instrument.get('exchange'),secrets)
    country = instrument.get('country')
    country = country if isinstance(country,str) and re.fullmatch('[A-Z]{2}',country) else None
    if country is None:
        country = 'US' if exchange in ('XNYS','XNAS','ARCX','BATS','IEXG','XASE') else 'BR' if exchange=='BVMF' else None
    lots = row.get('tax_lots')
    clean_lots = None
    if isinstance(lots,list):
        clean_lots = [{'date':day(lot.get('original_purchase_date') or lot.get('acquisition_date') or lot.get('date')),
                       'units':decimal(lot.get('units') if 'units' in lot else lot.get('quantity')),
                       'cost':decimal(lot.get('cost_basis'))} for lot in lots[:500] if isinstance(lot,dict)]
    return (key('instrument',identity),text(instrument.get('symbol'),secrets),
            text(instrument.get('description'),secrets),kind,exchange,country,currency,decimal(units),decimal(price),
            format(value,'f') if value is not None and currency else None,basis,decimal(row.get('unrealized_pnl')),
            as_of,observed,int(cash),clean_lots)


def activity(row,observed,secrets):
    external = row.get('id')
    transaction_day = day(row.get('trade_date'))
    kind = text(row.get('type'),secrets)
    if not isinstance(external,str) or not external or len(external)>256 or not transaction_day or not kind:
        raise ProviderFailure('SNAPTRADE_INVALID_DATA')
    currency = row.get('currency')
    currency = code(currency.get('code')) if isinstance(currency,dict) else None
    symbol = row.get('option_symbol') or row.get('symbol') or {}
    symbol = symbol if isinstance(symbol,dict) else {}
    instrument = symbol.get('id')
    return (key('activity',external),KINDS.get(kind,'REVIEW'),kind,transaction_day,day(row.get('settlement_date')),
            text(symbol.get('symbol'),secrets),key('instrument',instrument) if isinstance(instrument,str) else None,
            text(row.get('description'),secrets),currency,decimal(row.get('amount')),decimal(row.get('units')),
            decimal(row.get('price')),decimal(row.get('fee')),observed)
