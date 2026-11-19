"""One investment projection over Pluggy and SnapTrade observations."""
from collections import defaultdict
from contextlib import closing
from datetime import date, timedelta
from decimal import Decimal, localcontext
import json
import re

from .open_finance import SyncError
from .open_finance_query import read_view
from .open_finance_registry import connection_views
from .open_finance_classification import normalize
from .portfolio_fx import FX
from .snaptrade_normalize import code, day, decimal, text

MAX_ROWS=30000
PARAMS={'provider','connection_id','account_id','currency','presentation','market','kind',
        'start','end','search','sort','page','page_size','history','view','asset','group'}


def parameters(query):
    if set(query)-PARAMS or any(type(v) is not list or len(v)!=1 or not v[0] for v in query.values()):
        raise SyncError('INVALID_QUERY',422)
    result={k:v[0] for k,v in query.items()}
    allowed={'provider':('PLUGGY','SNAPTRADE'),'presentation':('original','BRL','USD'),
             'market':('BR','INTERNATIONAL','UNKNOWN'),'sort':('name','value','participation'),
             'group':('month','year'),'history':('1','0'),'view':('portfolio','activities','income','history','asset')}
    for name,valid in allowed.items():
        if name in result and result[name] not in valid:
            raise SyncError('INVALID_QUERY',422)
    if 'currency' in result and not code(result['currency']):
        raise SyncError('INVALID_QUERY',422)
    for name in ('connection_id','account_id','asset','kind','search'):
        if name in result and (len(result[name])>200 or not result[name].isprintable()):
            raise SyncError('INVALID_QUERY',422)
    for name in ('start','end'):
        if name in result and day(result[name])!=result[name]:
            raise SyncError('INVALID_PERIOD',422)
    if result.get('start','0001-01-01')>result.get('end','9999-12-31'):
        raise SyncError('INVALID_PERIOD',422)
    for name,default in (('page','1'),('page_size','50')):
        raw=result.get(name,default)
        if not re.fullmatch(r'[1-9][0-9]{0,5}',raw):
            raise SyncError('INVALID_PAGINATION',422)
        result[name]=int(raw)
    if result['page_size'] not in (25,50,100,250,500):
        raise SyncError('INVALID_PAGINATION',422)
    return result


def _execute(db,sql,args=()):
    rows=db.execute(sql+' LIMIT 30001',args).fetchall()
    if len(rows)>MAX_ROWS:
        raise SyncError('QUERY_BUDGET_EXCEEDED',503)
    return rows


def _format(value):
    return format(value,'f') if value is not None else None


def _market(country):
    return 'BR' if country=='BR' else 'INTERNATIONAL' if country else 'UNKNOWN'


def _pluggy(db,settings,include_history,*,records=None,views=None):
    if views is None:
        views=connection_views(db,settings)
    accounts={cid:{'id':cid,'account_id':cid,'label':view.institution,'connection_id':cid,'institution':view.institution,
                   'provider':'PLUGGY','state':'AVAILABLE' if view.enabled and not view.historical else 'ARCHIVED'}
              for cid,view in views.items() if include_history or view.enabled and not view.historical}
    if not accounts:
        return [],[]
    rows=[]
    source=(row for row in records if row['resource']=='investments' and row['connection_id'] in accounts) if records is not None else _execute(db,
        '''SELECT connection_id,external_id,payload_json,observed_at FROM of_resource_records
           WHERE resource='investments' AND state='PRESENT' AND connection_id IN (SELECT value FROM json_each(?))''',
        (json.dumps(list(accounts)),))
    for row in source:
        raw=row['data'] if records is not None else json.loads(row['payload_json'],parse_float=Decimal)
        cid=row['connection_id']
        # The Pluggy investment record is institution-scoped. Missing custody
        # account or trading market is represented explicitly by that context.
        market=raw.get('market')
        market=market if isinstance(market,str) else None
        country='BR' if market in ('B3','BVMF') or raw.get('type')=='TREASURY' else None
        rows.append({**accounts[cid],'account_id':cid,'instrument_id':row['external_id'],
            'account_label':accounts[cid]['label'],'ticker':text(raw.get('code') or raw.get('symbol')),'label':text(raw.get('name')) or 'Investimento',
            'kind':text(raw.get('type')) or 'UNKNOWN','subtype':text(raw.get('subtype')),'exchange':market,'country':country,
            'market':_market(country),'currency':code(raw.get('currencyCode')),'market_value':decimal(raw.get('balance')),
            'units':decimal(raw.get('quantity')),'price':decimal(raw.get('unitValue')),'cost':None,'unrealized':None,
            'reference_at':raw.get('date'),'observed_at':row['observed_at'],'lots_json':None})
    return rows,list(accounts.values())


def _snaptrade(db,include_history,settings,activities=False):
    accounts={}
    for row in _execute(db,'''SELECT a.id,a.label,a.connection_id,a.state,a.suffix,c.institution,c.provider_state,
            c.archived,c.excluded,c.paused,a.net_value,a.net_currency FROM st_accounts a
            JOIN st_connections c ON a.connection_id=c.id ORDER BY c.institution,a.id'''):
        current=bool(settings.snaptrade_enabled and not row['archived'] and not row['excluded']
                     and row['provider_state']=='AVAILABLE' and row['state']=='AVAILABLE')
        if current or include_history:
            accounts[row['id']]={**dict(row),'account_id':row['id'],'provider':'SNAPTRADE','state':'AVAILABLE' if current else 'ARCHIVED'}
    if not accounts:
        return [],[],[],False
    # Fail closed for overlapping broker authorization sets. An owner may
    # select one connection, even when the underlying account fingerprint is absent.
    brokers=defaultdict(set)
    for row in db.execute("SELECT id,brokerage FROM st_connections WHERE archived=0 AND excluded=0 AND provider_state='AVAILABLE'"):
        brokers[row['brokerage'].casefold()].add(row['id'])
    overlap=any(len(scope)>1 for scope in brokers.values())
    scope=json.dumps(list(accounts))
    projection='account_id,instrument_id,country,ticker' if activities else '*'
    positions=[({**dict(row),'market':_market(row['country'])} if activities else
      {**accounts[row['account_id']],**dict(row),'account_label':accounts[row['account_id']]['label'],'market':_market(row['country'])})
      for row in _execute(db,'SELECT '+projection+''' FROM st_positions WHERE cash_equivalent=0
      AND account_id IN (SELECT value FROM json_each(?))''',(scope,))]
    if activities:
        return positions,[],list(accounts.values()),overlap
    balances=[{**accounts[row['account_id']],**dict(row),'market':'UNKNOWN','kind':'CASH'}
      for row in _execute(db,'''SELECT * FROM st_balances WHERE account_id IN (SELECT value FROM json_each(?))''',(scope,))]
    return positions,balances,list(accounts.values()),overlap


def _scope(row,q):
    if any(q.get(k) is not None and row.get(k)!=q[k] for k in ('provider','connection_id','account_id','currency','kind','market')):
        return False
    term=normalize(q.get('search',''))
    return not term or term in normalize(' '.join(str(row.get(f) or '') for f in
                                                   ('label','ticker','institution','description','provider_kind')))


def _summary(rows,balances,accounts,target,fx,today,overlap,scope,quality):
    totals=defaultdict(lambda: {'positions':None,'cash':None,'count':0})
    composition={key:defaultdict(lambda: defaultdict(Decimal)) for key in ('country','kind','provider','institution')}
    references=set()
    missing=0
    converted={'positions':Decimal(0),'cash':Decimal(0)}
    converted_count={'positions':0,'cash':0}
    fx_refs={}
    for name,source,field in (('positions',rows,'market_value'),('cash',balances,'cash')):
        for row in source:
            currency=row.get('currency')
            original=row.get(field)
            reference=day(row.get('reference_at'))
            if original is None or not currency or (reference and reference>today):
                missing+=1
                continue
            position=Decimal(original)
            group=totals[currency]
            group[name]=(group[name] or Decimal(0))+position
            group['count']+= name=='positions'
            if name=='positions':
                for key,groups in composition.items():
                    groups[row.get(key) or 'UNKNOWN'][currency]+=position
            references.add(reference)
            if reference is None and target=='original':
                missing+=1
            if target!='original':
                value,quote=fx.convert(original,currency,target,reference)
                if value is None or reference is None:
                    missing+=1
                else:
                    converted[name]+=value
                    converted_count[name]+=1
                    if quote:
                        fx_refs[quote['date']]=quote
    warning=overlap and not scope.get('connection_id') and not scope.get('account_id')
    date_comparable=len(references)<=1 and None not in references
    stale=any(reference and (date.fromisoformat(today)-date.fromisoformat(reference)).days>7 for reference in references)
    incomplete=warning or missing or not date_comparable or stale or quality
    parts={key:{name:{currency:_format(value) for currency,value in sorted(group.items())}
                for name,group in sorted(values.items())} for key,values in composition.items()}
    return {'original':{k:{**v,'positions':_format(v['positions']),'cash':_format(v['cash'])} for k,v in sorted(totals.items())},
            'regions':parts.pop('country'),'composition':parts,
            'presentation':target,'converted':{k:_format(v) if converted_count[k] and not incomplete else None for k,v in converted.items()},
            'converted_subtotal':{k:_format(v) if converted_count[k] and not warning else None for k,v in converted.items()},
            'quote_dates':list(fx_refs.values()),'overlap':bool(warning),'missing':missing,'stale':stale,
            'date_comparable':date_comparable,'partial_resources':bool(quality),'account_count':len(accounts)}


def _page(rows,q):
    size,number=q['page_size'],q['page']
    offset=(number-1)*size
    return {'items':rows[offset:offset+size],'total':len(rows),'page':number,
            'total_pages':max(1,(len(rows)+size-1)//size)}


ACTIVITY_DECISIONS=('CAPITAL','TRANSFER','CORPORATE_ACTION','DIVIDEND','INTEREST','TAX','FEE','REINVESTMENT')


def classify_activity(service,body):
    if not service.settings.snaptrade_enabled or set(body)!={'account_id','activity_id','kind'} or (
        not all(isinstance(body[field],str) for field in body) or body['kind'] not in (*ACTIVITY_DECISIONS,'REVIEW')):
        raise SyncError('INVALID_REQUEST',422)
    with closing(service._db()) as db,service._write(db):
        sample=db.execute('SELECT * FROM st_activities WHERE account_id=? AND activity_id=?',
                          (body['account_id'],body['activity_id'])).fetchone()
        description=normalize(sample['description'] or '') if sample else ''
        if not sample or sample['kind']!='REVIEW' or not description:
            raise SyncError('INVALID_REQUEST',422)
        match=(sample['account_id'],sample['provider_kind'],description)
        stamp=service._time()[1]
        if body['kind']=='REVIEW':
            db.execute('DELETE FROM st_activity_rules WHERE account_id=? AND provider_kind=? AND description_key=?',match)
        else:
            db.execute('''INSERT INTO st_activity_rules(account_id,provider_kind,description_key,kind,observed_at)
                VALUES (?,?,?,?,?) ON CONFLICT(account_id,provider_kind,description_key)
                DO UPDATE SET kind=excluded.kind,observed_at=excluded.observed_at''',(*match,body['kind'],stamp))
        db.execute("INSERT INTO st_events(observed_at,action,target,outcome) VALUES (?,'ACTIVITY_RULE',?,?)",
                   (stamp,sample['activity_id'],body['kind']))
    return {'state':'AVAILABLE'}


def _activity_view(db,q,account_index,positions,fx,*,all_income=False,asset_classifier=None):
    instruments={(row['account_id'],row['instrument_id']):row for row in positions}
    reviewing=q.get('kind')=='OWNER_REVIEW'
    scope={key:value for key,value in q.items() if key!='kind'} if reviewing else q
    items=[]
    total=0
    income=defaultdict(lambda: defaultdict(Decimal))
    precision=4 if q.get('group')=='year' else 7
    page_size,number=q['page_size'],q['page']
    offset=(number-1)*page_size
    target=q.get('presentation','original')
    income_kinds=('DIVIDEND','INTEREST','TAX','FEE')
    if account_index:
        encoded=json.dumps(list(account_index))
        rules={(row['account_id'],row['provider_kind'],row['description_key']):row['kind'] for row in _execute(db,
            'SELECT * FROM st_activity_rules WHERE account_id IN (SELECT value FROM json_each(?))',(encoded,))}
        terms=['account_id IN (SELECT value FROM json_each(?))','date BETWEEN ? AND ?']
        args=[encoded,q.get('start','0001-01-01'),q.get('end','9999-12-31')]
        if q.get('currency'):
            terms.append('currency=?')
            args.append(q['currency'])
        if q.get('asset'):
            terms.append('instrument_id=?')
            args.append(q['asset'])
        if reviewing:
            terms.append("kind='REVIEW' AND description IS NOT NULL")
        if all_income:
            terms.append("kind IN ('DIVIDEND','INTEREST','TAX','REVIEW')")
        cursor=db.execute('SELECT * FROM st_activities WHERE '+' AND '.join(terms)+
                          ' ORDER BY date DESC,account_id,activity_id LIMIT ?',(*args,MAX_ROWS+1))
        for index,row in enumerate(cursor):
            if index==MAX_ROWS:
                raise SyncError('QUERY_BUDGET_EXCEEDED',503)
            account=account_index[row['account_id']]
            instrument=instruments.get((row['account_id'],row['instrument_id'])) or {}
            combined={**account,**dict(row),'market':instrument.get('market','UNKNOWN'),'country':instrument.get('country')}
            if row['kind']=='REVIEW' and row['description']:
                effective=rules.get((row['account_id'],row['provider_kind'],normalize(row['description'])))
                combined.update(rule_eligible=True,classification_source='OWNER_RULE' if effective else 'REVIEW',
                                kind=effective or row['kind'])
            if not _scope(combined,scope):
                continue
            label,currency,amount=combined['kind'],combined['currency'],combined['amount']
            if label in income_kinds and currency and amount is not None:
                income[(row['date'][:precision],currency)][label]+=Decimal(amount)
            if q.get('view')=='income' and label not in (*income_kinds,'REINVESTMENT'):
                continue
            if all_income or offset<=total<offset+page_size:
                if asset_classifier:
                    combined['asset_class']=asset_classifier(instrument)
                value,quote=fx.convert(amount,currency,target,row['date']) if target!='original' else (None,None)
                combined.update(presented_amount=_format(value),fx=quote)
                items.append(combined)
            total+=1
    totals=[{'month':period,'currency':currency,'components':{k:_format(v) for k,v in values.items()}}
            for (period,currency),values in sorted(income.items(),reverse=True)]
    return {'items':items,'total':total,'page':number,'total_pages':max(1,(total+page_size-1)//page_size),
            'income':totals,'accounts':list(account_index.values())}


def _history(db,q,accounts,current,fx,today,has_overlap):
    target=q.get('presentation','original')
    members={row['id']:row for row in accounts if row['state']=='AVAILABLE' or
             q.get('history')=='1' and (q.get('connection_id') or q.get('account_id'))}
    if not members or has_overlap and not q.get('connection_id') and not q.get('account_id'):
        return {'state':'FORMING' if not members else 'OVERLAP','points':[]}
    scope=json.dumps(list(members))
    start=q.get('start',(date.fromisoformat(today)-timedelta(days=365)).isoformat())
    end=q.get('end',today)
    sources=defaultdict(lambda: defaultdict(lambda: defaultdict(Decimal)))
    asset=q.get('asset')
    sql = ('SELECT account_id,currency,reference_date,market_value FROM st_position_snapshots WHERE instrument_id=?'
           if asset else 'SELECT account_id,currency,reference_date,market_value FROM st_snapshots WHERE 1=1')
    if q.get('positions_only') and not asset:
        sql+=''' AND EXISTS(SELECT 1 FROM st_position_snapshots p WHERE p.account_id=st_snapshots.account_id
                        AND p.currency=st_snapshots.currency AND p.reference_date=st_snapshots.reference_date)'''
    for row in _execute(db,sql+''' AND account_id IN (SELECT value FROM json_each(?))
           AND reference_date BETWEEN ? AND ?''',((asset,) if asset else ())+(scope,start,end)):
        sources[row['reference_date']][row['account_id']][row['currency']]=Decimal(row['market_value'])
    runs={}
    for row in _execute(db,'''SELECT p.connection_id,p.currency,p.reference_date,p.value,p.external_id,p.run_id,
           r.finished_at FROM of_portfolio_snapshots p JOIN of_sync_runs r ON p.run_id=r.id
           WHERE p.connection_id IN (SELECT value FROM json_each(?)) AND r.state='SUCCEEDED'
             AND (? IS NULL OR p.external_id=?) AND (? IS NULL OR p.currency=?)
             AND EXISTS(SELECT 1 FROM of_portfolio_snapshots candidate WHERE candidate.run_id=p.run_id
                        AND candidate.connection_id=p.connection_id AND candidate.reference_date BETWEEN ? AND ?)
           ORDER BY r.finished_at,p.run_id''',(scope,asset,asset,q.get('currency'),q.get('currency'),start,end)):
        runs.setdefault((row['connection_id'],row['run_id']),[]).append(row)
    for (account,_),rows in runs.items():
        dates={row['reference_date'] for row in rows}
        if len(dates)!=1 or None in dates:
            continue
        reference=dates.pop()
        if not start<=reference<=end:
            continue
        values=defaultdict(Decimal)
        for row in rows:
            values[row['currency']]+=Decimal(row['value'])
        sources[reference][account]=values
    points=[]
    selected_currency=q.get('currency')
    expected=defaultdict(set)
    for row in current:
        if row['account_id'] in members and row.get('currency'):
            expected[row['account_id']].add(row['currency'])
    for reference,snapshots in sorted(sources.items()):
        scoped={account:{key:value for key,value in values.items() if not selected_currency or selected_currency==key}
                for account,values in snapshots.items()}
        scoped={account:values for account,values in scoped.items() if values}
        if {account:set(values) for account,values in scoped.items()}!=dict(expected):
            continue
        amounts=defaultdict(Decimal)
        for values in scoped.values():
            for currency,value in values.items():
                amounts[currency]+=value
        if q.get('currency'):
            if q['currency'] not in amounts:
                continue
            amounts={q['currency']:amounts[q['currency']]}
        if target=='original':
            points.append({'date':reference,'original':{k:_format(v) for k,v in amounts.items()}})
            continue
        values=[fx.convert(value,origin,target,reference) for origin,value in amounts.items()]
        if any(value is None for value,_ in values):
            continue
        points.append({'date':reference,'value':_format(sum((value for value,_ in values),Decimal(0))),
                      'fx':next((rate for _,rate in values if rate),None)})
    return {'state':'AVAILABLE' if len(points)>1 else 'FORMING','points':points}


def report(db,settings,query,today):
    q=parameters(query)
    include_history=q.get('history')=='1'
    with read_view(db),localcontext() as ctx:
        ctx.prec=82
        page=q.get('view','portfolio')
        activities=page in ('activities','income')
        brazil,local=_pluggy(db,settings,include_history) if not activities and q.get('provider')!='SNAPTRADE' else ([],[])
        foreign,balances,international,overlap=_snaptrade(db,include_history,settings,activities) if q.get('provider')!='PLUGGY' else ([],[],[],False)
        options=local+international
        institutions={normalize(row['institution']) for row in local if row['state']=='AVAILABLE'}
        overlap|=any(normalize(row['institution']) in institutions for row in international if row['state']=='AVAILABLE')
        accounts=[row for row in options if _scope(row,{k:q[k] for k in ('provider','connection_id','account_id') if k in q})]
        fx=FX(db)
        if activities:
            return _activity_view(db,q,{row['id']:row for row in accounts if row['provider']=='SNAPTRADE'},foreign,fx)
        if page=='history':
            if q.get('kind') or q.get('market') or q.get('search'):
                raise SyncError('INVALID_FILTER_COMBINATION',422)
            # A bank connection enters the series only if it has a position
            # in the current investment scope, rather than by name alone.
            current=[row for row in brazil+foreign+balances if _scope(row,q)
                     and (not q.get('asset') or row.get('instrument_id')==q['asset'])]
            investment_ids={row['account_id'] for row in current}
            return _history(db,q,[row for row in accounts if row['id'] in investment_ids],current,fx,today,overlap)
        rows=[row for row in brazil+foreign if _scope(row,q) and (not q.get('asset') or row['instrument_id']==q['asset'])]
        matched_balances=[row for row in balances if _scope(row,q)] if not q.get('asset') else []
        missing_resources=db.execute('''SELECT count(*) FROM st_checkpoints
            WHERE state IN ('FAILED','UNAVAILABLE','PARTIAL') AND resource IN ('balances','positions')
              AND account_id IN (SELECT value FROM json_each(?))''',
            (json.dumps([row['id'] for row in accounts if row['provider']=='SNAPTRADE']),)).fetchone()[0]
        summary=_summary(rows,matched_balances,accounts,q.get('presentation','original'),fx,today,overlap,q,missing_resources)
        target=q.get('presentation','original')
        for row in rows:
            value,quote=fx.convert(row['market_value'],row['currency'],target,day(row['reference_at'])) if target!='original' else (None,None)
            row['presented_value'],row['fx']=_format(value),quote
            row['lots']=json.loads(row.pop('lots_json')) if row.get('lots_json') else None
            row.pop('lots_json',None)
        rows.sort(key=lambda row:(normalize(row.get('ticker') or row['label'] or ''),row['account_id'],row['instrument_id']))
        if q.get('sort') in ('value','participation'):
            field='market_value' if target=='original' else 'presented_value'
            rows.sort(key=lambda row:((row.get('currency') or '') if target=='original' else '',
               row[field] is None,-Decimal(row[field]) if row[field] is not None else Decimal(0)))
        for row in rows:
            original=summary['original'].get(row.get('currency'),{}).get('positions')
            if original is not None and Decimal(original)>0 and row['market_value'] is not None:
                row['participation']=_format((Decimal(row['market_value'])/Decimal(original)*100).quantize(Decimal('.01')))
        return {**_page(rows,q),'summary':summary,'accounts':options,'cash':matched_balances[:500]}
