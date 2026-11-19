"""Pluggy credit usage, scoped to a verified Item and its card accounts."""
from collections import defaultdict
from decimal import Decimal
import json
import re

from .open_finance import OpenFinanceService
from .open_finance_classification import normalize
from .open_finance_insights import masked_card_text
from .open_finance_query import civil
from .snaptrade_normalize import code


SCOPE_ERRORS=frozenset({'ACCOUNT_SCOPE_MISMATCH','ITEM_ID_DIFFERENT','CONNECTION_BINDING_CHANGED',
                        'CONSENT_NOT_ACTIVE','CONSENT_EXPIRED','CONSENT_ASSOCIATION_INVALID',
                        'AUTH_FAILED','ITEM_ACCESS_DENIED','ITEM_REAUTH_REQUIRED','ITEM_USER_ACTION_REQUIRED'})


def _object(value):
    return value if isinstance(value,dict) else {}


def _usage_scopes(db,settings,current,today):
    legacy={cfg.id:cfg for cfg in settings.pluggy_connections}
    scopes={}
    for cid in current:
        binding=db.execute('''SELECT c.binding_hash,r.source,i.item_id FROM of_connections c
            LEFT JOIN of_connection_registry r ON r.connection_id=c.id
            LEFT JOIN of_managed_pluggy_items i ON i.connection_id=c.id WHERE c.id=?''',(cid,)).fetchone()
        configured=legacy.get(cid)
        expected=(binding['item_id'] if binding and binding['source']=='MANAGED' else
                  configured.item_id if configured and binding and
                  binding['binding_hash']==OpenFinanceService._binding(configured) else None)
        latest=db.execute('SELECT error_code FROM of_sync_runs WHERE connection_id=? ORDER BY rowid DESC LIMIT 1',(cid,)).fetchone()
        evidence={row['resource']:row for row in db.execute('''SELECT resource,state,last_complete_run_id,error_code
            FROM of_collection_checkpoints WHERE connection_id=? AND parent_id='' AND resource IN ('accounts','consents')''',(cid,))}
        item=db.execute("""SELECT external_id,payload_json FROM of_resource_records
            WHERE connection_id=? AND resource='item' AND parent_id='' AND state='PRESENT'""",(cid,)).fetchone()
        metadata=json.loads(item['payload_json']) if item else {}
        if not expected or not item or expected!=item['external_id'] or metadata.get('id')!=expected:
            scopes[cid]=('ASSOCIATION_INCONSISTENT',None,False)
            continue
        audit=evidence.get('consents')
        if (latest and latest['error_code'] in ('ACCOUNT_SCOPE_MISMATCH','ITEM_ID_DIFFERENT','CONNECTION_BINDING_CHANGED')
                or audit and audit['error_code'] in ('ACCOUNT_SCOPE_MISMATCH','ITEM_ID_DIFFERENT','CONSENT_ASSOCIATION_INVALID')):
            scopes[cid]=('ASSOCIATION_INCONSISTENT',None,False)
            continue
        collection=evidence.get('accounts')
        closed=metadata.get('consentExpiresAt')
        active=metadata.get('status') in ('UPDATED','OUTDATED') and (closed is None or (civil(closed) or '')>today)
        regulated=_object(metadata.get('connector')).get('isOpenFinance') is True
        scopes[cid]=('CONSENT_UNVERIFIED',None,regulated)
        if (not active or latest and latest['error_code'] in SCOPE_ERRORS
                or not audit or audit['state']!='COMPLETE'):
            continue
        validated=False
        for row in db.execute("""SELECT payload_json FROM of_resource_records WHERE connection_id=? AND resource='consents'
                         AND parent_id='' AND state='PRESENT' AND last_run_id=?""",(cid,audit['last_complete_run_id'])):
            payload=json.loads(row['payload_json'])
            expiry=payload.get('expiresAt')
            if payload.get('itemId')!=expected:
                scopes[cid]=('ASSOCIATION_INCONSISTENT',None,regulated)
                validated=False
                break
            products=payload.get('products')
            grants=payload.get('openFinancePermissionsGranted')
            grants=set(grants) if isinstance(grants,list) else set()
            product_valid=isinstance(products,list) and 'CREDIT_CARDS' in products
            scope_valid=not regulated or {'CREDIT_CARDS_LIST','CREDIT_CARDS_LIMITS'}<=grants or 'CREDIT_CARDS_ALL' in grants
            if product_valid and scope_valid and payload.get('revokedAt') is None and (expiry is None or (civil(expiry) or '')>today):
                validated=True
        if validated:
            scopes[cid]=(None,(expected,collection['last_complete_run_id']) if collection and
                         collection['state'] in ('COMPLETE','PARTIAL') else None,regulated)
    return scopes


def _line(credit,currency):
    lines=credit.get('disaggregatedCreditLimits')
    if not isinstance(lines,list):
        return {},False
    totals=[row for row in lines if isinstance(row,dict) and row.get('creditLineLimitType')=='LIMITE_CREDITO_TOTAL']
    if len(totals)!=1:
        return {},bool(totals)
    line=totals[0]
    if line.get('consolidationType') not in ('INDIVIDUAL','CONSOLIDATED'):
        return {},True
    if line.get('usedAmountCurrencyCode') not in (None,currency) or line.get('limitAmountCurrencyCode') not in (None,currency):
        return {},True
    return line,False


def _number(value):
    match=re.fullmatch(r'[xX*• -]*([0-9]{4})',value.strip()) if isinstance(value,str) else None
    return match[1] if match else None


def _format(amount):
    return format(amount,'f') if amount is not None else None


def credit_usage(db,settings,accounts,current,views,values,parse_amount):
    scopes=_usage_scopes(db,settings,current,values.today)
    cards=[]
    grouped=defaultdict(list)
    banks=defaultdict(set)
    for (cid,account),row in accounts.items():
        data=row['data']
        if data.get('type')!='CREDIT':
            continue
        credit=_object(data.get('creditData'))
        state=credit.get('status')
        if state in ('BLOCKED','CANCELLED') or data.get('status') in ('CLOSED','INACTIVE'):
            continue
        currency=code(data.get('currencyCode'))
        reference=civil(data.get('date') or data.get('updatedAt'))
        holder=credit.get('holderType')
        line,ambiguous=_line(credit,currency)
        reason,binding,regulated=scopes.get(cid,('HISTORICAL_CONNECTION',None,False))
        if not reason and (data.get('id')!=account or not binding or data.get('itemId')!=binding[0]):
            reason='ASSOCIATION_INCONSISTENT' if binding else 'ACCOUNT_COLLECTION_UNVERIFIED'
        if not reason and row['last_run_id']!=binding[1]:
            reason='ACCOUNT_COLLECTION_UNVERIFIED'
        if not reason and state not in ('ACTIVE',None):
            reason='CARD_STATUS_UNVERIFIED'
        identity=line.get('identificationNumber')
        line_type=line.get('consolidationType')
        used_field=parse_amount(line.get('usedAmount')) if currency and line.get('usedAmountCurrencyCode')==currency else None
        used=(used_field if line_type=='CONSOLIDATED' or not regulated else
              parse_amount(data.get('balance')) if holder!='ADDITIONAL' else used_field)
        basis='PROVIDER_USED_AMOUNT' if line_type=='CONSOLIDATED' or not regulated or holder=='ADDITIONAL' else 'REGULATED_BALANCE'
        limit=(parse_amount(line.get('limitAmount')) if currency and line.get('limitAmountCurrencyCode')==currency else None)
        if not line and not ambiguous and credit.get('isLimitFlexible') is not True:
            limit=parse_amount(credit.get('creditLimit'))
        if not reason and not currency:
            reason='CURRENCY_UNAVAILABLE'
        if not reason and reference and reference>values.today:
            reason='FUTURE_REFERENCE'
        if not reason and used is not None and used<0:
            reason='NEGATIVE_REPORTED'
        if not reason and used is None:
            reason='AMOUNT_UNAVAILABLE'
        if reason and reason!='AMOUNT_UNAVAILABLE':
            used=None
        card={'connection_id':cid,'account_id':account,'institution':views[cid].institution,
              'name':masked_card_text(data.get('marketingName') or data.get('name')) or 'Cartão sem nome',
              'brand':masked_card_text(credit.get('brand')),'tail':_number(data.get('cardLastFour')),'currency':currency,
              'status':state,'holder':holder,'reference_date':reference,'observed_at':row['observed_at'],
              'used':_format(used),'used_basis':basis if used is not None else None,'included':False,
              'consolidation_reason':reason,'limit_reason':None}
        cards.append(card)
        if cid not in current:
            continue
        bank=normalize(views[cid].institution)
        banks[bank].add(cid)
        grouped[(bank,cid,currency)].append((card,used,limit,line_type,identity,ambiguous,
                                             line.get('isLimitFlexible',credit.get('isLimitFlexible'))))
    used_rows=[]
    limit_rows=[]
    used_partial=any(card['consolidation_reason'] for card in cards)
    limit_partial=any(card['consolidation_reason']=='HISTORICAL_CONNECTION' for card in cards)
    for (bank,_,currency),group in grouped.items():
        aggregate=[entry for entry in group if entry[3]=='CONSOLIDATED']
        main_entries=[entry for entry in group if entry[0]['holder']=='MAIN']
        distinct_lines=defaultdict(int)
        for _,_,_,typ,identity,_,_ in group:
            if typ=='INDIVIDUAL' and isinstance(identity,str):
                distinct_lines[identity]+=1
        # A consolidated line is scoped to its Item and currency. Accept a
        # single authoritative main and verified repeated representations only.
        shared_main=None
        if aggregate and len(main_entries)==1 and main_entries[0] in aggregate:
            candidate=main_entries[0]
            if (candidate[0]['consolidation_reason'] is None and isinstance(candidate[4],str) and candidate[4]
                    and all(e[4]==candidate[4] and e[0]['reference_date']==candidate[0]['reference_date'] and
                            (e[1],e[2])==(candidate[1],candidate[2]) and not e[0]['consolidation_reason'] for e in aggregate)):
                shared_main=candidate[0]['account_id']
        for card,used,limit,typ,identity,ambiguous,flexible in group:
            reason=card['consolidation_reason']
            limit_reason=None
            if len(banks[bank])>1 or isinstance(identity,str) and distinct_lines[identity]>1:
                reason=reason or 'OBLIGATION_OVERLAP'
            elif aggregate and (typ=='CONSOLIDATED' or card['holder']!='MAIN'):
                if shared_main and card['account_id']!=shared_main and typ=='CONSOLIDATED':
                    card['consolidation_reason']='ALREADY_IN_SHARED_LINE'
                    card['used']=None  # This value is the line total, not this card's amount.
                    continue
                if not shared_main or typ!='CONSOLIDATED':
                    reason=reason or 'SHARED_SCOPE_UNVERIFIED'
            elif len(group)>1 and (card['holder']!='MAIN' and typ!='INDIVIDUAL' or ambiguous):
                reason=reason or 'OBLIGATION_UNVERIFIED'
            card['consolidation_reason']=reason
            if reason:
                used_partial=True
                if reason in ('OBLIGATION_OVERLAP','SHARED_SCOPE_UNVERIFIED'):
                    card['used']=None
            else:
                card['included']=values.project(used,currency,card['reference_date']) is not None
                used_rows.append({'amount':used,'currency':currency,'reference':card['reference_date']})
                if not card['included']:
                    card['consolidation_reason']='CONVERSION_UNAVAILABLE'
            shared_evidence_missing=aggregate and card['account_id']!=shared_main and typ=='CONSOLIDATED'
            if (reason and reason not in ('AMOUNT_UNAVAILABLE','NEGATIVE_REPORTED')) or ambiguous or flexible is True or shared_evidence_missing:
                limit_reason=reason or 'LIMIT_UNVERIFIED'
            elif limit is None or limit<0:
                limit_reason='LIMIT_UNAVAILABLE'
            elif typ!='INDIVIDUAL' and card['account_id']!=shared_main and len(group)!=1:
                limit_reason='LIMIT_SCOPE_UNVERIFIED'
            if limit_reason:
                card['limit_reason']=limit_reason
                limit_partial=True
            else:
                limit_rows.append({'amount':limit,'currency':currency,'reference':card['reference_date']})
    used=values.total(used_rows,partial=used_partial,position=True)
    limits=values.total(limit_rows,partial=limit_partial,position=True)
    same_references=used['dates']==limits['dates'] and len(used['dates'])==1
    comparable=not used['partial'] and not limits['partial'] and same_references and used['amounts'].keys()==limits['amounts'].keys()
    utilization={currency:_format(Decimal(amount)/Decimal(limits['amounts'][currency]))
                 for currency,amount in used['amounts'].items() if comparable and Decimal(limits['amounts'][currency])>0}
    return {'items':cards,'active_count':sum(card['status']=='ACTIVE' for card in cards),'count':len(cards),
            'basis':'CREDIT_USED','included_count':used['included'],'metric':used,'limit_metric':limits,'utilization_by_currency':utilization}
