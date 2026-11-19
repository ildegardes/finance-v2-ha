"""Allowlisted data that may be written to the local investment staging."""
from datetime import date
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


def invalid(field=None,reason='INVALID_FIELD_VALUE',*,stage='NORMALIZATION'):
    return ProviderFailure('SNAPTRADE_INVALID_DATA',stage=stage,reason=reason,field=field,remote_status=200)


def field_value(row,name,expected,*,required=False,nullable=True):
    if name not in row:
        if required:
            raise invalid(name,'MISSING_FIELD',stage='STRUCTURE')
        return None
    value=row[name]
    if value is None and nullable:
        return None
    if type(value) is not expected:
        raise invalid(name,'UNEXPECTED_FIELD_TYPE',stage='STRUCTURE')
    return value


def ident(value,field='id'):
    try:
        return str(UUID(value))
    except (ValueError,TypeError,AttributeError):
        raise invalid(field,'INVALID_IDENTIFIER') from None


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


def collection(value,fields=(),*,field=None):
    if not isinstance(value,list):
        raise invalid(field,'UNEXPECTED_COLLECTION',stage='STRUCTURE')
    if len(value)>15000:
        raise invalid(field,'COLLECTION_LIMIT',stage='STRUCTURE')
    if any(not isinstance(item,dict) for item in value):
        raise invalid(field,'UNEXPECTED_COLLECTION',stage='STRUCTURE')
    for item in value:
        for required in fields:
            if required not in item:
                raise invalid(required,'MISSING_FIELD',stage='STRUCTURE')
    return value


def connection_record(row,secrets):
    remote=ident(field_value(row,'id',str,required=True,nullable=False))
    broker=field_value(row,'brokerage',dict,required=True,nullable=False)
    disabled=field_value(row,'disabled',bool)
    name=text(field_value(broker,'display_name',str),secrets) or text(field_value(broker,'name',str),secrets) or 'Corretora'
    brokerage=text(field_value(broker,'slug',str),secrets) or name
    permission=field_value(row,'type',str)
    state='UNKNOWN' if disabled is None else 'REAUTH_REQUIRED' if disabled else 'AVAILABLE'
    return remote,(key('connection',remote),name,brokerage,permission if permission in ('read','trade') else None,state)


def account_record(row,secrets):
    remote=ident(field_value(row,'id',str,required=True,nullable=False))
    authorization=ident(field_value(row,'connection_id',str,required=True,nullable=False),'connection_id')
    kind=field_value(row,'kind',str,required=True,nullable=False)
    if not kind:
        raise invalid('kind')
    paper=field_value(row,'is_paper',bool,required=kind=='investment',nullable=kind!='investment')
    status=field_value(row,'status',str)
    if status not in (None,'open','closed','archived','unavailable'):
        raise invalid('status')
    state='AVAILABLE' if kind=='investment' and status in (None,'open') and paper is False else 'INACTIVE'
    label=text(field_value(row,'display_name',str),secrets) or 'Conta de corretora'
    account_type=text(field_value(row,'raw_type',str),secrets) or text(kind,secrets)
    masked=field_value(row,'masked_account_number',str)
    match=re.fullmatch(r'(?:[*xX•]+)?([0-9]{4})',masked) if masked and not any(secret in masked for secret in secrets) else None
    unique=field_value(row,'institution_account_id',str)
    info=field_value(row,'sync_status',dict) or {}
    updated=[]
    for name in ('positions','balances'):
        value=field_value(info,name,str)
        if value is not None:
            observed=timestamp(value)
            if not observed:
                raise invalid(name,'INVALID_TIMESTAMP')
            updated.append(observed)
    return remote,authorization,(label,account_type,match[1] if match else None,unique,state,max(updated,default=None))


def financial_amount(row,field):
    value=row.get(field)
    amount=_amount(value)
    if value is not None and amount is None:
        raise invalid(field,'INVALID_DECIMAL')
    return amount


def financial_text(row,field):
    return decimal(financial_amount(row,field))


def position(row,as_of,observed,secrets):
    instrument = row.get('instrument')
    if not isinstance(instrument,dict):
        raise invalid('instrument','UNEXPECTED_FIELD_TYPE',stage='STRUCTURE')
    kind = text(instrument.get('kind'),secrets)
    if not kind:
        raise invalid('kind')
    cash = row.get('cash_equivalent') is True or kind=='cash'
    currency = code(row.get('currency')) or (code(instrument.get('code')) if kind=='cash' else None)
    identity = instrument.get('id') or (currency if kind=='cash' else None)
    if not isinstance(identity,str) or not identity or len(identity)>200:
        raise invalid('id','INVALID_IDENTIFIER')
    units,price = financial_amount(row,'units'), financial_amount(row,'price')
    value = financial_amount(row,'market_value')
    # Contract multipliers and notional values vary. Derive only per-unit securities.
    if value is None and units is not None and price is not None and kind in SECURITIES:
        with localcontext() as ctx:
            ctx.prec=82
            value = units*price
    basis = financial_text(row,'cost_basis')
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
            format(value,'f') if value is not None and currency else None,basis,financial_text(row,'unrealized_pnl'),
            as_of,observed,int(cash),clean_lots)


def activity(row,observed,secrets):
    external = row.get('id')
    transaction_day = day(row.get('trade_date'))
    kind = text(row.get('type'),secrets)
    if not isinstance(external,str) or not external or len(external)>256:
        raise invalid('id','INVALID_IDENTIFIER')
    if not transaction_day:
        raise invalid('trade_date','INVALID_TIMESTAMP')
    if not kind:
        raise invalid('type')
    currency = row.get('currency')
    currency = code(currency.get('code')) if isinstance(currency,dict) else None
    symbol = row.get('option_symbol') or row.get('symbol') or {}
    symbol = symbol if isinstance(symbol,dict) else {}
    instrument = symbol.get('id')
    return (key('activity',external),KINDS.get(kind,'REVIEW'),kind,transaction_day,day(row.get('settlement_date')),
            text(symbol.get('symbol'),secrets),key('instrument',instrument) if isinstance(instrument,str) else None,
            text(row.get('description'),secrets),currency,financial_text(row,'amount'),financial_text(row,'units'),
            financial_text(row,'price'),financial_text(row,'fee'),observed)
