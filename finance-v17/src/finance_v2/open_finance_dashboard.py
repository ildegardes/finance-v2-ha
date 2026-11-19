"""Read model for the six Open Finance indicators and their supporting views."""
from collections import defaultdict
from datetime import date
from decimal import Decimal
import json

from .open_finance_classification import normalize
from .open_finance_insights import banking_insights, card_insights
from .open_finance_portfolio import window_start
from .open_finance_query import civil
from .open_finance_wealth import _activity_view, _execute, _format, _history, _pluggy, _snaptrade
from .portfolio_fx import FX
from .snaptrade_normalize import code, decimal


def asset_class(row):
    kind=row.get('kind')
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
    if kind in ('stock','preferred_stock','STOCK') or subtype in ('STOCK','COMMON_STOCK','PREFERRED_STOCK'):
        if row.get('country')=='BR':
            return 'BRAZIL_STOCK'
        if row.get('provider')=='SNAPTRADE' or row.get('country'):
            return 'STOCK'
    if kind in ('adr','option','future','future_option','crypto','cfd','tokenized_asset'):
        return 'OTHER'
    return 'UNKNOWN'


class DashboardValues:
    def __init__(self,db,target,today):
        self.target=target
        self.today=today
        self.fx=FX(db)
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
                continue
            presented[currency if self.target=='original' else self.target]+=value
        stale=position and any((date.fromisoformat(self.today)-date.fromisoformat(day)).days>7 for day in dates)
        mixed=position and len(dates)>1
        return {'original':{} if overlap else {k:_format(v) for k,v in sorted(native.items())},
                'amounts':{} if overlap else {k:_format(v) for k,v in sorted(presented.items())},
                'included':len(rows)-unavailable if not overlap else 0,'total':len(rows),
                'missing':unavailable,'undated':undated,'dates':sorted(dates),'stale':stale,
                'mixed_dates':mixed,'overlap':overlap,'partial':bool(partial or unavailable or undated or stale or mixed or overlap)}


def observation(row,amount='market_value',reference='reference_at'):
    return {'amount':row.get(amount),'currency':code(row.get('currency')),'reference':civil(row.get(reference))}


def current_bills(db,accounts,current,views,checkpoints,values,parse_amount):
    # Pluggy's card balance is used credit for regulated connectors. Match the
    # current billing date to an imported bill instead of using that balance.
    cards=card_insights(accounts,current,views,None,parse_amount,values.today)
    rows=_execute(db,"""SELECT connection_id,parent_id,external_id,payload_json,observed_at
                       FROM of_resource_records WHERE resource='bills' AND state='PRESENT'
                        AND connection_id IN (SELECT value FROM json_each(?))""",(json.dumps(list(current)),))
    bills=defaultdict(list)
    for row in rows:
        bills[(row['connection_id'],row['parent_id'])].append((row,json.loads(row['payload_json'],parse_float=Decimal)))
    candidates=defaultdict(list)
    evidence={}
    for card in cards['items']:
        cid,account=card['connection_id'],card['account_id']
        checkpoint=checkpoints.get((cid,'bills',account),{})
        due=card['due']
        key=(cid,account)
        if checkpoint.get('state') not in ('AVAILABLE','PARTIAL') or not due or due<values.today:
            card['consolidation_reason']='CURRENT_BILL_UNVERIFIED'
            continue
        matches=[(row,bill) for row,bill in bills[key] if civil(bill.get('dueDate'))==due]
        if len(matches)!=1:
            card['consolidation_reason']='CURRENT_BILL_UNVERIFIED'
            continue
        row,bill=matches[0]
        currency=code(bill.get('totalAmountCurrencyCode'))
        amount=parse_amount(bill.get('totalAmount'))
        if currency!=card['currency'] or amount is None or amount<0:
            card['consolidation_reason']='AMOUNT_UNAVAILABLE'
            continue
        if bill.get('status') in ('PAID','SETTLED','CANCELLED'):
            card['consolidation_reason']='CURRENT_BILL_UNVERIFIED'
            continue
        bank=normalize(views[cid].institution)
        identity=(bank,row['external_id'])
        account_data=accounts[key]['data']
        reference=civil(bill.get('billClosingDate')) or civil(account_data.get('date') or account_data.get('updatedAt'))
        if reference and reference>values.today:
            reference=None
        evidence[key]={'amount':amount,'currency':currency,'reference':reference}
        candidates[identity].append(card)
        card.update(bill_value=_format(amount),bill_currency=currency,bill_due=due,bill_reference=reference,
                    bill_observed=row['observed_at'],bill_coverage=checkpoint['state'],
                    consolidation_reason=None)
    accepted=[]
    bank_connections=defaultdict(set)
    for card in cards['items']:
        bank_connections[normalize(card['institution'])].add(card['connection_id'])
    for (bank,_),matches in candidates.items():
        if len(bank_connections[bank])>1:
            for card in matches:
                card['consolidation_reason']='OBLIGATION_OVERLAP'
            continue
        # Repeated representations of one bill count once only when they agree.
        facts=[evidence[(c['connection_id'],c['account_id'])] for c in matches]
        if any(fact!=facts[0] for fact in facts):
            for card in matches:
                card['consolidation_reason']='OBLIGATION_OVERLAP'
            continue
        accepted.append(facts[0])
        for card in matches[1:]:
            card['consolidation_reason']='OBLIGATION_OVERLAP'
    partial=(len(accepted)<cards['count'] or any(card.get('bill_coverage')=='PARTIAL' for card in cards['items']))
    total=values.total(accepted,partial=partial,position=True)
    return {**cards,'basis':'CURRENT_BILL','consolidated':None,'used':None,'included_count':total['included'],
            'bills_state':'NOT_ESTABLISHED' if not accepted else 'PARTIAL' if partial else 'COMPLETE','metric':total}


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


def investment_income(items,foreign,values,overlap):
    events=[]
    for row in items:
        classification=row['classification']
        if row['product']=='BANK' and row['direction']=='incoming' and row['classification_bucket']=='operating' \
                and classification['nature']=='INVESTMENT_INCOME':
            events.append({'provider':'PLUGGY','institution':row['institution'],'connection_id':row['connection_id'],
                'account_id':row['account_id'],'asset':classification.get('asset'),'date':row['date'],
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
                       'amount':abs(amount) if amount is not None else None,'kind':kind,'tax':tax})
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
    return {'credits':values.total([r for r in usable if not r['tax']],partial=len(usable)!=len(events)),
            'tax':values.total([r for r in usable if r['tax']],partial=any(r['tax'] and r['overlap'] for r in events)),
            'net':None,'by_kind':[{'currency':c,'kind':k,'value':_format(v)} for (c,k),v in sorted(summary.items())],
            'months':[{'month':month,'currency':currency,'value':_format(value)} for (month,currency),value in sorted(months.items(),reverse=True)],
            'events':sorted(events,key=lambda r:r['date'],reverse=True)[:300],'event_count':len(events)}


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
    by_class=defaultdict(list)
    for row,obs in zip(positions,portfolio_obs):
        by_class[asset_class(row)].append(obs)
    composition=[] if blocked else [{'class':kind,'metric':values.total(rows),
                                     'negative':any(row['amount'] is not None and Decimal(row['amount'])<0 for row in rows)}
                                    for kind,rows in sorted(by_class.items())]
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
        values.record_quote(point.get('fx'))
    history.update(window=window,connection_id=pref,consolidated=True,
                   connections=[{'id':cid,'label':label,'eligible':cid in invested}
                                for cid,label in history_options.items()])
    snap_index={row['id']:row for row in broker_members if applicable(row)}
    activity_q={key:q[key] for key in ('start','end') if key in q}
    activity=_activity_view(db,{**activity_q,'view':'income','page':1,'page_size':25},snap_index,foreign,values.fx,
                            all_income=True,asset_classifier=asset_class)
    income=investment_income(items,activity['items'],values,blocked)
    adjusted=[r for r in items if r['product']=='BANK' and r['classification_bucket']=='operating']
    bank_groups=movements(items,values,bank_coverage)
    automatic=values.total([obs for row,obs in zip(positions,portfolio_obs) if row['provider']=='PLUGGY' and
                            normalize(row['label'])=='aplic aut mais'])
    for currency,view in bank_groups.items():
        view['insights']['automatic']['position']=automatic['amounts'].get(currency)
    out={
      'currency':target,'institutions':inst,'composition':composition,'income':income,'movements':bank_groups,'history':history,
      'accounts':values.total(bank_rows,partial=incomplete([r for r in members if r['provider']=='PLUGGY'],'accounts','balances'),position=True),
      'investments':values.total(portfolio_obs,overlap=blocked,partial=incomplete(members,'investments','positions'),position=True),
      'cash':values.total(cash_obs,overlap=blocked,position=True,partial=incomplete([r for r in members if r['provider']=='SNAPTRADE'],'accounts','balances')),
      'cards':current_bills(db,accounts,current,views,checkpoints,values,parse_amount)}
    for direction in ('incoming','outgoing'):
        out[direction]=values.total([dict(observation(row,'amount','date'),amount=_format(abs(Decimal(row['amount']))) if row['amount'] is not None else None)
                                     for row in adjusted if row['direction']==direction],partial=bank_coverage!='COMPLETE')
        out['gross_'+direction]=values.total([dict(observation(row,'amount','date'),amount=_format(abs(Decimal(row['amount']))) if row['amount'] is not None else None)
                                     for row in items if row['product']=='BANK' and row['direction']==direction],partial=bank_coverage!='COMPLETE')
    dates={day for key in ('accounts','investments','cash') for day in out[key]['dates']}
    out['quality']={'rates':[values.quotes[day] for day in sorted(values.quotes,reverse=True)],'mixed_dates':len(dates)>1,'dates':sorted(dates),
                    'first':min(dates,default=None),'last':max(dates,default=None),'overlap':blocked}
    return out
