"""Public BCB PTAX close, persisted in civil-date order for offline reads."""
from contextlib import closing
from datetime import date, timedelta
from decimal import Decimal, localcontext
import json
from urllib.parse import urlencode
from urllib.request import HTTPRedirectHandler, Request, build_opener

from .open_finance import SyncError
from .snaptrade_normalize import day, decimal

SOURCE='BCB_PTAX_SELL'
URL='https://olinda.bcb.gov.br/olinda/servico/PTAX/versao/v1/odata/CotacaoDolarPeriodo(dataInicial=@dataInicial,dataFinalCotacao=@dataFinalCotacao)'


class FixedOrigin(HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):
        return None


def fetch(start,end):
    query=urlencode({'@dataInicial':start.strftime("'%m-%d-%Y'"),
        '@dataFinalCotacao':end.strftime("'%m-%d-%Y'"),'$format':'json','$top':500,
        '$select':'cotacaoVenda,dataHoraCotacao'})
    with build_opener(FixedOrigin).open(Request(URL+'?'+query,headers={'Accept':'application/json'}),timeout=8) as response:
        raw=response.read(300_001)
    if len(raw)>300_000:
        raise ValueError()
    body=json.loads(raw,parse_float=Decimal)
    if not isinstance(body.get('value'),list) or body.get('@odata.nextLink'):
        raise ValueError()
    return body['value']


def refresh(service,start,end,*,transport=fetch):
    if not isinstance(start,date) or not isinstance(end,date) or not start<=end<=service.clock.today() or (
        end-start).days>366:
        raise SyncError('INVALID_PERIOD',422)
    try:
        rows=transport(start,end)
        if not isinstance(rows,list) or len(rows)>500:
            raise ValueError()
        dates={}
        for row in rows:
            quote=day(row['dataHoraCotacao'].replace(' ','T',1))
            value=decimal(row['cotacaoVenda'])
            if not quote or not start.isoformat()<=quote<=end.isoformat() or value is None or Decimal(value)<=0:
                raise ValueError()
            if quote in dates and dates[quote]!=value:
                raise ValueError()
            dates[quote]=value
    except Exception:
        raise SyncError('PTAX_UNAVAILABLE',502) from None
    _,stamp=service._time()
    with closing(service._db()) as db,service._write(db):
        db.executemany('''INSERT INTO portfolio_fx_rates VALUES(?,?,?,?)
          ON CONFLICT(quote_date) DO UPDATE SET rate=excluded.rate,observed_at=excluded.observed_at''',
          [(day,value,stamp,SOURCE) for day,value in dates.items()])
    return {'source':SOURCE,'quotes':len(dates),'start':start.isoformat(),'end':end.isoformat()}


class FX:
    def __init__(self,db):
        self.rates={row['quote_date']:row['rate'] for row in db.execute('SELECT quote_date,rate FROM portfolio_fx_rates')}
        self.cache={}

    def at(self,reference):
        if reference not in self.cache:
            when=date.fromisoformat(reference)
            days=[(when-timedelta(days=i)).isoformat() for i in range(8)] if when.year>1 else [reference]
            self.cache[reference]=next(({'date':d,'rate':self.rates[d],'source':SOURCE,
                'method':'SELL_USD_BRL','lag_days':(when-date.fromisoformat(d)).days}
                for d in days if d in self.rates),None)
        return self.cache[reference]

    def convert(self,amount,origin,presentation,reference):
        if amount is None or not origin:
            return None,None
        if origin==presentation:
            return Decimal(amount),None
        if {origin,presentation}!={'USD','BRL'} or not reference:
            return None,None
        quote=self.at(reference)
        if not quote:
            return None,None
        rate=Decimal(quote['rate'])
        with localcontext() as ctx:
            ctx.prec=82
            return (Decimal(amount)*rate if presentation=='BRL' else Decimal(amount)/rate),quote
