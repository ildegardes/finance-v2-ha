"""Read model for the six Open Finance indicators and their supporting views."""
from collections import defaultdict
from decimal import Decimal

from .open_finance_classification import normalize
from .open_finance_insights import banking_insights
from .open_finance_card_usage import credit_usage
from .open_finance_portfolio import window_start
from .open_finance_query import civil
from .open_finance_wealth import _activity_view, _format, _history, _pluggy, _snaptrade
from .portfolio_values import DashboardValues, asset_class, investment_projection, observation
from .snaptrade_normalize import code, decimal


def _projection_rows(rows,values):
    projected=defaultdict(list)
    for row in rows:
        currency=code(row['currency'])
        group=currency if values.target=='original' else values.target
        if not group:
            continue
        amount=values.project(row['amount'],currency,row['date'])
        projected[group].append({**row,'amount':_format(amount)})
    return projected


def movements(items,values,coverage_state):
    groups={}
    for currency,rows in _projection_rows(items,values).items():
        bank={'coverage_state':coverage_state if values.target!='original' else 'PARTIAL'}
        insights=banking_insights(rows,bank)
        incoming=defaultdict(Decimal)
        series=defaultdict(Decimal)
        ranking=defaultdict(dict)
        for row in rows:
            direction=row['direction']
            if row['product']!='BANK' or row['amount'] is None or direction not in ('incoming','outgoing'):
                continue
            amount=abs(Decimal(row['amount']))
            incoming[direction]+=amount
            series[(row['date'],direction)]+=amount
            if direction!='outgoing':
                continue
            category=row['effective_category']
            for view in ('all','economic') if row['classification_bucket']=='operating' else ('all',):
                entry=ranking[view].setdefault(category['key'],{**category,'value':Decimal(0),'count':0})
                entry['value']+=amount
                entry['count']+=1
        def ranked(view):
            return [{**row,'value':_format(row['value'])} for row in sorted(ranking[view].values(),
                      key=lambda row:(-row['value'],row['key']))[:6]]
        flow={'coverage_state':bank['coverage_state'],'reported':{k:_format(incoming.get(k)) for k in ('incoming','outgoing')},
              'observed_net':_format(incoming['incoming']-incoming['outgoing']) if len(incoming)==2 else None}
        groups[currency]={'insights':insights,'flow':{'BANK':flow},'series':[
            {'date':day,'direction':direction,'product':'BANK','value':_format(amount)}
            for (day,direction),amount in sorted(series.items())],
            'category_ranking':{'BANK':ranked('all')},'economic_category_ranking':ranked('economic'),
            'total':len(rows)}
    return groups


def investment_income(items,foreign,values,overlap,q):
    events=[]
    for row in items:
        classification=row['classification']
        if row['product']=='BANK' and row['direction']=='incoming' and row['classification_bucket']=='operating' \
                and classification['nature']=='INVESTMENT_INCOME':
            events.append({'provider':'PLUGGY','institution':row['institution'],'connection_id':row['connection_id'],
                'account_id':row['account_id'],'asset':classification.get('asset'),'date':row['date'],
                'description':row['description'],
                'currency':code(row['currency']),'amount':abs(Decimal(row['amount'])) if row['amount'] is not None else None,
                'kind':classification.get('provent','other'),'tax':False})
    seen=set()
    for row in foreign:
        tax=row['kind']=='TAX'
        if row['kind'] not in ('DIVIDEND','INTEREST','TAX'):
            continue
        amount=Decimal(row['amount']) if row['amount'] is not None else None
        if amount is not None and (amount>0 if tax else amount<0):
            continue
        tax_kind='foreign_withholding' if row['provider_kind'] in ('WITHHOLDING','TAX_WITHHOLDING') else 'foreign_tax'
        kind=(tax_kind if tax else 'foreign_interest' if row['kind']=='INTEREST' else
              {'REIT':'reit_distribution','ETF':'etf_distribution','STOCK':'stock_dividend'}.get(row['asset_class'],'foreign_dividend'))
        identity=(row['date'],row['currency'],amount,(row['ticker'] or '').upper())
        if not tax and row['ticker'] and amount is not None:
            seen.add(identity)
        events.append({'provider':'SNAPTRADE','institution':row['institution'],'connection_id':row['connection_id'],
                       'account_id':row['account_id'],'asset':row['ticker'],'date':row['date'],'currency':row['currency'],
                       'amount':abs(amount) if amount is not None else None,'kind':kind,'tax':tax,'description':row['description']})
    summary=defaultdict(Decimal)
    months=defaultdict(Decimal)
    for row in events:
        identity=(row['date'],row['currency'],row['amount'],(row['asset'] or '').upper())
        row['overlap']=(row['provider']=='SNAPTRADE' and overlap) or (row['provider']=='PLUGGY' and identity in seen)
        row['reference']=row['date']
        presented=values.project(row['amount'],row['currency'],row['date']) if not row['overlap'] else None
        currency=row['currency'] if values.target=='original' else values.target
        if presented is not None:
            summary[(currency,row['kind'])]+=presented
            if not row['tax']:
                months[(row['date'][:7],currency)]+=presented
        row.update(amount=_format(row['amount']),presented=_format(presented),presentation_currency=currency)
    usable=[row for row in events if not row['overlap']]
    detail={}
    if q.get('income_kind'):
        ordered=sorted((row for row in usable if not row['tax'] and row['kind']==q['income_kind']
                        and row['presentation_currency']==q['income_currency'] and row['presented'] is not None),
                       key=lambda row:row['date'],reverse=True)
        size,number=q['page_size'],q['page']
        offset=(number-1)*size
        detail={'kind':q['income_kind'],'currency':q['income_currency'],'page':number,
                'total':len(ordered),'has_more':offset+size<len(ordered),'items':ordered[offset:offset+size]}
    return {'credits':values.total([r for r in usable if not r['tax']],partial=len(usable)!=len(events)),
            'tax':values.total([r for r in usable if r['tax']],partial=any(r['tax'] and r['overlap'] for r in events)),
            'net':None,'by_kind':[{'currency':c,'kind':k,'value':_format(v)} for (c,k),v in sorted(summary.items())],
            'months':[{'month':month,'currency':currency,'value':_format(value)} for (month,currency),value in sorted(months.items(),reverse=True)],
            'events':sorted(events,key=lambda r:r['date'],reverse=True)[:300],'event_count':len(events),
            **({'detail':detail} if detail else {})}


def dashboard(db,settings,q,today,views,current,records,accounts,checkpoints,items,parse_amount,bank_coverage):
    target=q['presentation']
    values=DashboardValues(db,target,today)
    local,bank_members=_pluggy(db,settings,False,records=records,views=views)
    foreign,balances,broker_members,overlap=_snaptrade(db,False,settings)
    all_positions=local+foreign
    bank_names={normalize(row['institution']) for row in bank_members}
    overlap|=any(normalize(row['institution']) in bank_names for row in broker_members)
    scope=q.get('connection_id')
    applicable=lambda row:not scope or row['connection_id']==scope
    members=[row for row in bank_members+broker_members if applicable(row)]
    positions=[row for row in all_positions if applicable(row)]
    cash=[row for row in balances if applicable(row)]
    bank_rows=[]
    for (cid,external),record in accounts.items():
        if cid not in current or not applicable(record):
            continue
        data=record['data']
        if data.get('type')!='BANK' or data.get('status') in ('CLOSED','INACTIVE'):
            continue
        bank_rows.append({'connection_id':cid,'account_id':external,'label':data.get('name'),'provider':'PLUGGY',
            'currency':code(data.get('currencyCode')),'amount':decimal(data.get('balance')),
            'reference':civil(data.get('date') or data.get('updatedAt')),'observed_at':record['observed_at']})
    portfolio_obs=[observation(row) for row in positions]
    cash_obs=[observation(row,'cash') for row in cash]
    blocked=overlap and not scope
    snap_states={tuple(row) for row in db.execute("SELECT account_id,resource,state FROM st_checkpoints")}
    checkpoints_snap={(account,resource):state for account,resource,state in snap_states}
    def incomplete(rows,bank_resource,broker_resource):
        return any((checkpoints.get((row['id'],bank_resource,''),{}).get('state') not in ('AVAILABLE','EMPTY'))
                   if row['provider']=='PLUGGY' else checkpoints_snap.get((row['id'],broker_resource)) not in ('AVAILABLE','EMPTY')
                   for row in rows)
    groups={}
    for member in members:
        cid=member['connection_id']
        groups.setdefault(cid,{'connection_id':cid,'institution':member['institution'],'provider':member['provider'],
                               'connection_state':'PAUSED' if member.get('paused') else 'AVAILABLE','members':[]})['members'].append(member)
    details=defaultdict(list)
    investments_by_connection=defaultdict(list)
    liquid_by_connection=defaultdict(list)
    for record,obs in zip(positions,portfolio_obs):
        cid=record['connection_id']
        investments_by_connection[cid].append(obs)
        details[cid].append({**obs,'label':record['label'],'account':record.get('account_label'),
                             'observed_at':record['observed_at']})
    for record,obs in zip(cash,cash_obs):
        cid=record['connection_id']
        liquid_by_connection[cid].append(obs)
        details[cid].append(dict(obs,label=record['label'],observed_at=record['observed_at']))
    for row in bank_rows:
        cid=row['connection_id']
        liquid_by_connection[cid].append(row)
        details[cid].append(row)
    inst=[{**{key:value for key,value in row.items() if key!='members'},
           'investments':values.total(investments_by_connection[cid],position=True,
                                     partial=incomplete(row['members'],'investments','positions')),
           'liquid':values.total(liquid_by_connection[cid],position=True,
                                 partial=incomplete(row['members'],'accounts','balances')),
           'details':details[cid][:100]} for cid,row in groups.items()]
    investments,composition=investment_projection(positions,values,overlap=blocked,classes=True,
                                                  partial=incomplete(members,'investments','positions'))
    history_options={r['connection_id']:r['institution'] for r in bank_members+broker_members}
    invested={row['connection_id'] for row in all_positions}
    pref=q.get('portfolio_connection')
    window=q.get('portfolio_window','6')
    series_rows=[row for row in all_positions if not pref or pref==row['connection_id']]
    series_ids={row['account_id'] for row in series_rows}
    history=_history(db,{'presentation':target,'start':window_start(today,window),'end':today,'positions_only':True,
                         **({'connection_id':pref} if pref else {})},
                     [row for row in bank_members+broker_members if row['id'] in series_ids],series_rows,values.fx,today,overlap)
    if target!='original' and len(history['points'])>1:
        first,last=history['points'][0],history['points'][-1]
        history['change']=_format(Decimal(last['value'])-Decimal(first['value']))
    for point in history['points']:
        for quote in point.get('fx_rates') or [point.get('fx')]:
            values.record_quote(quote)
    history.update(window=window,connection_id=pref,consolidated=True,
                   connections=[{'id':cid,'label':label,'eligible':cid in invested}
                                for cid,label in history_options.items()])
    snap_index={row['id']:row for row in broker_members if applicable(row)}
    activity_q={key:q[key] for key in ('start','end') if key in q}
    activity=_activity_view(db,{**activity_q,'view':'income','page':1,'page_size':25},snap_index,foreign,values.fx,
                            all_income=True,asset_classifier=asset_class)
    income=investment_income(items,activity['items'],values,blocked,q)
    adjusted=[r for r in items if r['product']=='BANK' and r['classification_bucket']=='operating']
    bank_groups=movements(items,values,bank_coverage)
    automatic=values.total([obs for row,obs in zip(positions,portfolio_obs) if row['provider']=='PLUGGY' and
                            normalize(row['label'])=='aplic aut mais'])
    for currency,view in bank_groups.items():
        view['insights']['automatic']['position']=automatic['amounts'].get(currency)
    out={
      'currency':target,'institutions':inst,'composition':composition,'income':income,'movements':bank_groups,'history':history,
      'accounts':values.total(bank_rows,partial=incomplete([r for r in members if r['provider']=='PLUGGY'],'accounts','balances'),position=True),
      'investments':investments,
      'cash':values.total(cash_obs,overlap=blocked,position=True,partial=incomplete([r for r in members if r['provider']=='SNAPTRADE'],'accounts','balances')),
      'cards':credit_usage(db,settings,accounts,current,views,values,parse_amount)}
    for direction in ('incoming','outgoing'):
        out[direction]=values.total([dict(observation(row,'amount','date'),amount=_format(abs(Decimal(row['amount']))) if row['amount'] is not None else None)
                                     for row in adjusted if row['direction']==direction],partial=bank_coverage!='COMPLETE')
        out['gross_'+direction]=values.total([dict(observation(row,'amount','date'),amount=_format(abs(Decimal(row['amount']))) if row['amount'] is not None else None)
                                     for row in items if row['product']=='BANK' and row['direction']==direction],partial=bank_coverage!='COMPLETE')
    dates={day for key in ('accounts','investments','cash') for day in out[key]['dates']}
    out['quality']={'rates':[values.quotes[day] for day in sorted(values.quotes,reverse=True)],'mixed_dates':len(dates)>1,'dates':sorted(dates),
                    'first':min(dates,default=None),'last':max(dates,default=None),'overlap':blocked}
    return out
