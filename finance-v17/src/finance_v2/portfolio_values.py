"""Shared investment and currency presentation for Open Finance read models."""
from collections import defaultdict
from datetime import date
from decimal import Decimal

from .portfolio_fx import FX
from .open_finance_query import civil
from .snaptrade_normalize import code


def _format(value):
    return format(value,'f') if value is not None else None


def asset_class(row):
    kind=row.get('kind')
    if row.get('provider')=='PLUGGY':
        # The bank view has always grouped by the provider's top-level type.
        # Keep FIIs, BDRs, and shares in EQUITY when that is the supplied type.
        return 'PLUGGY:'+kind if kind and kind!='UNKNOWN' else 'PLUGGY:'
    subtype=row.get('subtype')
    if subtype in ('REAL_ESTATE_FUND','FII'):
        return 'FII'
    if kind in ('reit','REIT') or subtype=='REIT':
        return 'REIT'
    if kind in ('ETF','etf') or subtype in ('ETF','ETF_FUND'):
        return 'ETF'
    if kind in ('bond','FIXED_INCOME','TREASURY'):
        return 'FIXED_INCOME'
    if kind in ('mutualfund','cef','FUND','MUTUAL_FUND'):
        return 'FUND'
    if kind in ('stock','preferred_stock','STOCK'):
        return 'STOCK'
    if kind in ('adr','option','future','future_option','crypto','cfd','tokenized_asset'):
        return 'OTHER'
    return 'UNKNOWN'


class DashboardValues:
    def __init__(self,db,target,today,*,fx=None):
        self.target=target
        self.today=today
        self.fx=fx if fx is not None else FX(db)
        self.quotes={}

    def record_quote(self,quote):
        if quote and (quote['date'] not in self.quotes or self.quotes[quote['date']]['lag_days']<quote['lag_days']):
            self.quotes[quote['date']]=quote

    def project(self,amount,currency,reference):
        if amount is None or not currency or reference and reference>self.today:
            return None
        if self.target=='original':
            return Decimal(amount)
        value,quote=self.fx.convert(amount,currency,self.target,reference)
        self.record_quote(quote)
        return value

    def total(self,rows,*,overlap=False,partial=False,position=False):
        native=defaultdict(Decimal)
        presented=defaultdict(Decimal)
        dates=set()
        unavailable=undated=0
        excluded=defaultdict(Decimal)
        reasons=defaultdict(int)
        for row in rows:
            amount,currency,reference=row['amount'],row['currency'],row['reference']
            if amount is not None and currency and (not reference or reference<=self.today):
                native[currency]+=Decimal(amount)
                if reference:
                    dates.add(reference)
                else:
                    undated+=1
            value=self.project(amount,currency,reference)
            if value is None:
                unavailable+=1
                if amount is None:
                    reasons['VALUE_UNAVAILABLE']+=1
                elif not currency:
                    reasons['CURRENCY_UNAVAILABLE']+=1
                elif reference and reference>self.today:
                    reasons['FUTURE_REFERENCE']+=1
                else:
                    excluded[currency]+=Decimal(amount)
                    if {currency,self.target}!={'BRL','USD'}:
                        reasons['CURRENCY_UNSUPPORTED']+=1
                    elif not reference:
                        reasons['REFERENCE_UNAVAILABLE']+=1
                    else:
                        reasons['RATE_UNAVAILABLE']+=1
                continue
            presented[currency if self.target=='original' else self.target]+=value
        stale=position and any((date.fromisoformat(self.today)-date.fromisoformat(day)).days>7 for day in dates)
        mixed=position and len(dates)>1
        return {'original':{} if overlap else {k:_format(v) for k,v in sorted(native.items())},
                'amounts':{} if overlap else {k:_format(v) for k,v in sorted(presented.items())},
                'included':len(rows)-unavailable if not overlap else 0,'total':len(rows),
                'missing':unavailable,'undated':undated,'dates':sorted(dates),'stale':stale,
                'conversion_excluded':{k:_format(v) for k,v in sorted(excluded.items())},
                'missing_reasons':dict(reasons),
                'mixed_dates':mixed,'overlap':overlap,'partial':bool(partial or unavailable or undated or stale or mixed or overlap)}


def observation(row,amount='market_value',reference='reference_at'):
    return {'amount':row.get(amount),'currency':code(row.get('currency')),'reference':civil(row.get(reference))}


def investment_projection(rows,values,*,overlap=False,partial=False,classes=False):
    observations=[observation(row) for row in rows]
    result=values.total(observations,overlap=overlap,partial=partial,position=True)
    if not classes or overlap:
        return result,[]
    groups=defaultdict(list)
    for row,obs in zip(rows,observations):
        groups[asset_class(row)].append(obs)
    return result,[{'class':kind,'metric':values.total(group),
        'negative':any(row['amount'] is not None and Decimal(row['amount'])<0 for row in group)}
        for kind,group in sorted(groups.items())]
