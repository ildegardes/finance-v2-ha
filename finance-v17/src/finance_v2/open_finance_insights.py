"""Financial projections over classified, already-scoped Open Finance observations."""
from collections import Counter, defaultdict
from decimal import Decimal
import re

from .open_finance_classification import AUTOMATIC, normalize
from .open_finance_query import civil

INCOME = {'INCOME','SALARY','INVESTMENT_INCOME'}
EXPENSE = {'EXPENSE','CHARGE','TAX'}
INTERNAL = {'OWN_TRANSFER','INTERNAL'}
CAPITAL = {'APPLICATION','CAPITAL_RETURN','BORROWING','DEBT_PRINCIPAL'}
SETTLEMENT = {'CARD_PAYMENT','SETTLEMENT'}


def classified_bucket(item):
    decision = item['classification']
    nature, direction = decision['nature'], item['direction']
    if decision['review']!='CONFIRMED':
        return 'pending'
    if nature in INCOME and direction=='incoming' or nature in EXPENSE and direction=='outgoing':
        return 'operating'
    if nature in CAPITAL and (direction=='outgoing' if nature in ('APPLICATION','DEBT_PRINCIPAL') else direction=='incoming'):
        return 'capital'
    if nature=='REDEMPTION' and decision.get('principal_only') is True and direction=='incoming':
        return 'capital'
    if nature in INTERNAL and direction in ('incoming','outgoing'):
        return 'internal'
    if nature in SETTLEMENT and direction=='outgoing':
        return 'settlement'
    return 'pending'


def _amount_text(value):
    return format(value,'f') if value is not None else None


def _totals(values):
    return {key:_amount_text(value) for key,value in values.items()}


def _percent(used,limit):
    if used is not None and limit is not None and limit>0 and used>=0:
        return _amount_text((100*used/limit).quantize(Decimal('0.01')))
    return None


def classification_center(items, group_by='pattern', order='count'):
    groups = {}
    counters = Counter(total=len(items))
    for row in items:
        tx = row['classification']
        counters[tx['origin'].lower()]+=1
        counters[tx['review'].lower()]+=1
        if tx['review']=='CONFIRMED' and tx['nature']!='UNKNOWN':
            counters['classified']+=1
            continue
        description = row.get('description_original') or row['description']
        label = {'pattern':lambda:normalize(description),
                 'recurring':lambda:re.sub(r'\b[0-9]{4,}\b','…',normalize(description)), 'institution':lambda:row['institution'],
                 'account':lambda:row['account_name'], 'direction':lambda:row['direction'],
                 'category':lambda:row['effective_category'].get('name')}[group_by]() or 'Sem informação'
        key = (row['connection_id'],row['account_id'] if group_by in ('pattern','recurring','account') else None,row['direction'],label)
        group = groups.setdefault(key,{'label':label,'count':0,'start':row['date'],'end':row['date'],
                                       'institution':row['institution'],'direction':row['direction'],
                                       'suggestion':tx['category'],'review':tx['review'],'sample':row,'_magnitude':Decimal(0)})
        group['count']+=1
        if row['amount'] is not None:
            group['_magnitude']+=abs(Decimal(row['amount']))
        group['start']=min(group['start'],row['date'])
        group['end']=max(group['end'],row['date'])
    ranking = {'count':lambda row:-row['count'], 'date':lambda row:-int(row['end'].replace('-','')),
               'magnitude':lambda row:-row['_magnitude']}[order]
    ordered = sorted(groups.values(),key=lambda row:(ranking(row),row['label'],row['institution']))
    return {'counts':dict(counters),'groups':[{k:v for k,v in row.items() if k!='_magnitude'}
                                              for row in ordered[:50]],'group_count':len(groups)}


def banking_insights(items, bank):
    buckets = defaultdict(lambda: defaultdict(lambda: None))
    series = defaultdict(lambda: Decimal(0))
    automatic = defaultdict(dict)
    automatic_counts = Counter()
    income = defaultdict(lambda: Decimal(0))
    by_asset = {}
    income_rows = []
    pending = 0
    automatic_pending = defaultdict(lambda:None)
    for row in items:
        if row['product']!='BANK':
            continue
        tag = row['classification']
        direction = row['direction']
        amount = abs(Decimal(row['amount'])) if row['amount'] is not None and direction!='unknown' else None
        bucket = row['classification_bucket']
        if amount is None:
            pending+=1
            continue
        if bucket=='pending':
            pending+=1
        buckets[bucket][direction]=(buckets[bucket][direction] or Decimal(0))+amount
        series[(row['date'],bucket,direction)]+=amount
        if (tag.get('investment')==AUTOMATIC and tag['nature']=='REDEMPTION'
                and tag['review']=='CONFIRMED' and direction=='incoming' and bucket=='pending'):
            automatic_pending[direction]=(automatic_pending[direction] or Decimal(0))+amount
        if tag.get('investment')==AUTOMATIC and tag['review']=='CONFIRMED':
            key = {'APPLICATION':'applied','REDEMPTION':'redeemed','INVESTMENT_INCOME':'credited','TAX':'tax',
                   'CHARGE':'charge'}.get(tag['nature'])
            if key and (direction=='incoming')==(key in ('redeemed','credited')):
                period = row['date'][:7]
                automatic[period][key] = automatic[period].get(key,Decimal(0))+amount
                automatic_counts[key]+=1
        if bucket=='operating' and tag['nature']=='INVESTMENT_INCOME':
            kind = tag.get('provent','other')
            income[kind]+=amount
            code = tag.get('asset')
            resolution = 'USER_IDENTIFIED' if code and tag['origin']=='MANUAL' else 'SUGGESTED' if code else 'UNKNOWN'
            identity = (code,resolution,kind,row['connection_id'])
            group = by_asset.setdefault(identity,{'asset':code,'resolution':resolution,'provent':kind,'institution':row['institution'],
                                                 'count':0,'value':Decimal(0),'last_date':row['date']})
            group['count']+=1
            group['value']+=amount
            group['last_date']=max(group['last_date'],row['date'])
            income_rows.append({'asset':code,'resolution':resolution,'provent':kind,'date':row['date'],
                                'institution':row['institution'],'value':_amount_text(amount)})
    complete = bank['coverage_state']=='COMPLETE' and pending==0 and not (
        buckets['settlement']['incoming'] is not None or buckets['settlement']['outgoing'] is not None
    )
    known = buckets['operating']
    incoming = known['incoming'] if known['incoming'] is not None else Decimal(0) if complete else None
    outgoing = known['outgoing'] if known['outgoing'] is not None else Decimal(0) if complete else None
    result = incoming-outgoing if incoming is not None and outgoing is not None else None
    totals = {}
    for month in automatic.values():
        for key,value in month.items():
            totals[key]=totals.get(key,Decimal(0))+value
    volumes = totals.get('applied'),totals.get('redeemed')
    totals['capital_flow'] = volumes[1]-volumes[0] if all(value is not None for value in volumes) else None
    return {
        'coverage':'COMPLETE_BANK_SCOPE' if complete else 'PARTIAL',
        'pending':pending, 'unresolved_scope':bank.get('unresolved_scope',0), 'known':_totals({'incoming':incoming,'outgoing':outgoing,'net':result}),
        'bridge':{name:_totals({direction:buckets[name][direction] for direction in ('incoming','outgoing')})
                  for name in ('operating','capital','internal','settlement','pending')},
        'series':[{'date':day,'bucket':bucket,'direction':direction,'value':_amount_text(value)}
                  for (day,bucket,direction),value in sorted(series.items())],
        'automatic':{'value':_totals(totals),'counts':dict(automatic_counts),
                     'months':[{'month':month,**_totals(values)} for month,values in sorted(automatic.items())],
                     'pending':_totals(automatic_pending),'position':None,'return_state':'NOT_ESTABLISHED'},
        'income':{'value':_amount_text(sum(income.values(),Decimal(0))) if income else None,'by_kind':_totals(income),
                  'assets':[{**group,'value':_amount_text(group['value'])} for group in by_asset.values()],
                  'events':income_rows[:300], 'event_count':len(income_rows),
                  'months':_income_months(income_rows), 'scope':'IDENTIFIED_BANK_CREDITS'},
    }


def _income_months(events):
    months = defaultdict(lambda: defaultdict(lambda: Decimal(0)))
    for event in events:
        months[event['date'][:7]][event['provent']]+=Decimal(event['value'])
    return [{'month':month,'by_kind':_totals(kinds),'value':_amount_text(sum(kinds.values(),Decimal(0)))}
            for month,kinds in sorted(months.items())]


def masked_card_text(value):
    # Stored names may incorporate an account/card identifier; present at most a last-four hint.
    return re.sub(r'(?<!\d)(?:\d[ .-]?){8,}\d(?!\d)',lambda found:'•••• '+re.sub(r'\D','',found[0])[-4:],value or '')


def card_insights(accounts,current,views,currency,parse_amount,today):
    cards = []
    obligation_keys = []
    for (cid,external),row in accounts.items():
        data = row['data']
        if cid not in current or data.get('type')!='CREDIT' or data.get('currencyCode')!=currency:
            continue
        credit = data.get('creditData') or {}
        status = credit.get('status')
        if status in ('BLOCKED','CANCELLED') or data.get('status') in ('CLOSED','INACTIVE'):
            continue
        lines = credit.get('disaggregatedCreditLimits') or []
        total_lines = [line for line in lines if line.get('creditLineLimitType')=='LIMITE_CREDITO_TOTAL']
        individual = [line for line in total_lines if line.get('consolidationType')=='INDIVIDUAL'
                      and line.get('usedAmountCurrencyCode')==line.get('limitAmountCurrencyCode')==currency
                      and line.get('isLimitFlexible') is False]
        usable = individual[0] if len(individual)==1 and len(total_lines)==1 else {}
        used = parse_amount(usable.get('usedAmount'))
        limit = parse_amount(usable.get('limitAmount')) if usable else parse_amount(credit.get('creditLimit'))
        available = parse_amount(usable.get('availableAmount')) if usable and usable.get('availableAmountCurrencyCode')==currency else parse_amount(credit.get('availableCreditLimit'))
        due = civil(credit.get('balanceDueDate'))
        collection = row.get('last_run_id')
        identity = usable.get('identificationNumber')
        explicit = usable and isinstance(identity,str) and bool(identity.strip()) and credit.get('holderType')=='MAIN'
        obligation_keys.append((cid,identity,collection) if explicit and collection else None)
        cards.append({'connection_id':cid,'account_id':external,'institution':views[cid].institution,
                      'name':masked_card_text(data.get('marketingName') or data.get('name')) or 'Cartão sem nome',
                      'brand':masked_card_text(credit.get('brand')), 'status':status,'holder':credit.get('holderType'),
                      'balance':_amount_text(parse_amount(data.get('balance'))),'used':_amount_text(used),
                      'limit':_amount_text(limit),'available':_amount_text(available),'utilization':_percent(used,limit),
                      'shared_or_unknown':not bool(usable), 'due':due, 'observed_at':row['observed_at']})
    used = cards[0]['used'] if len(cards)==1 else None
    # Unique reported individual obligations in one collection scope support
    # used-balance aggregation. Credit limits have a separate shared-line policy.
    if len(cards)>1 and all(obligation_keys) and all(card['used'] is not None for card in cards):
        contexts = {(cid,run) for cid,_,run in obligation_keys}
        if len(contexts)==1 and len({identity for _,identity,_ in obligation_keys})==len(cards):
            used = format(sum((Decimal(card['used']) for card in cards),Decimal(0)),'f')
    next_due = min((card['due'] for card in cards if card['due'] and card['due']>=today),default=None)
    return {'items':cards,'active_count':sum(card['status']=='ACTIVE' for card in cards),
            'count':len(cards),'used':used,'limit':None,'utilization':None,'next_reported_due':next_due,
            'limit_state':'NOT_ESTABLISHED','bills_state':'NOT_ESTABLISHED'}
