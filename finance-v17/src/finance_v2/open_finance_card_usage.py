"""Pluggy credit usage, scoped to a verified Item and its card accounts."""
from collections import Counter, defaultdict
from decimal import Decimal
import json
import re

from .open_finance import OpenFinanceService
from .open_finance_classification import normalize
from .open_finance_insights import masked_card_text
from .open_finance_query import civil
from .open_finance_registry import load_keyring, managed_connection
from .pluggy_credential_protection import CredentialProtectionError
from .snaptrade_normalize import code


SCOPE_ERRORS=frozenset({'ACCOUNT_SCOPE_MISMATCH','ITEM_ID_DIFFERENT','CONNECTION_BINDING_CHANGED',
                        'CONSENT_NOT_ACTIVE','CONSENT_EXPIRED','CONSENT_ASSOCIATION_INVALID',
                        'AUTH_FAILED','ITEM_ACCESS_DENIED','ITEM_REAUTH_REQUIRED','ITEM_USER_ACTION_REQUIRED'})


def _object(value):
    return value if isinstance(value,dict) else {}


def _local_binding(db,settings,legacy,cid,row):
    if not row:
        return None,'LOCAL_ITEM_UNIDENTIFIED'
    if row['source']=='MANAGED':
        if not row['item_id']:
            return None,'LOCAL_ITEM_UNIDENTIFIED'
        try:
            config=managed_connection(db,cid,row['revision'],load_keyring(settings.pluggy_keyring_path))
        except (CredentialProtectionError,OSError):
            return None,'MANAGED_BINDING_UNVERIFIED'
    else:
        config=legacy.get(cid)
    if not config:
        return None,'LOCAL_ITEM_UNIDENTIFIED'
    if row['binding_hash']!=OpenFinanceService._binding(config):
        return None,'LOCAL_BINDING_MISMATCH'
    return config.item_id,None


def _previous_error(db,cid,checkpoints,item_run):
    latest=db.execute('SELECT id,error_code FROM of_sync_runs WHERE connection_id=? ORDER BY rowid DESC LIMIT 1',(cid,)).fetchone()
    if not latest or latest['error_code'] not in SCOPE_ERRORS:
        return None
    error=latest['error_code']
    if error in ('CONSENT_EXPIRED','CONSENT_NOT_ACTIVE'):
        return error
    if error=='CONNECTION_BINDING_CHANGED':
        return 'LOCAL_BINDING_MISMATCH'
    if error=='CONSENT_ASSOCIATION_INVALID':
        return 'CONSENT_ASSOCIATION_UNVERIFIED'
    if error in ('ACCOUNT_SCOPE_MISMATCH','ITEM_ID_DIFFERENT'):
        failed=[row['resource'] for row in db.execute("""SELECT resource FROM of_collection_checkpoints WHERE connection_id=?
            AND run_id=? AND state='FAILED'""",(cid,latest['id']))]
        # A later resource can fail after all three card prerequisites have
        # already completed successfully in that same, fenced import.
        verified=all(resource in checkpoints and checkpoints[resource]['state']=='COMPLETE'
                     and checkpoints[resource]['last_complete_run_id']==latest['id']
                     for resource in ('item','consents','accounts'))
        if verified and item_run==latest['id'] and failed and set(failed)<={'investments','investment_transactions','loans'}:
            return None
        return 'PRIOR_SCOPE_FAILURE'
    return 'ITEM_ACCESS_UNVERIFIED'


def _consent_state(db,cid,expected,audit,regulated,today):
    if not audit:
        return 'CONSENT_CHECKPOINT_MISSING'
    if audit['error_code'] in ('ITEM_ID_DIFFERENT','ACCOUNT_SCOPE_MISMATCH'):
        return 'CONSENT_ITEM_MISMATCH'
    if audit['error_code'] in ('CONSENT_NOT_ACTIVE','CONSENT_EXPIRED'):
        return audit['error_code']
    if audit['state']!='COMPLETE':
        return 'CONSENT_SCAN_UNVERIFIED'
    failures=set()
    validated=False
    for row in db.execute("""SELECT payload_json FROM of_resource_records WHERE connection_id=? AND resource='consents'
                         AND parent_id='' AND state='PRESENT' AND last_run_id=?""",(cid,audit['last_complete_run_id'])):
        payload=_object(json.loads(row['payload_json']))
        item=payload.get('itemId')
        if not item:
            failures.add('CONSENT_ASSOCIATION_UNVERIFIED')
            continue
        if item!=expected:
            return 'CONSENT_ITEM_MISMATCH'
        expiry=payload.get('expiresAt')
        expiry_date=civil(expiry)
        products=payload.get('products')
        grants=payload.get('openFinancePermissionsGranted')
        if payload.get('revokedAt') is not None:
            failures.add('CONSENT_REVOKED')
        elif expiry is not None and not expiry_date:
            failures.add('CONSENT_METADATA_INCOMPLETE')
        elif expiry_date and expiry_date<=today:
            failures.add('CONSENT_EXPIRED')
        elif not isinstance(products,list):
            failures.add('CONSENT_METADATA_INCOMPLETE')
        elif 'CREDIT_CARDS' not in products:
            failures.add('CONSENT_NO_CARD_SCOPE')
        elif regulated and not isinstance(grants,list):
            failures.add('CONSENT_GRANTS_UNREPORTED')
        elif regulated and 'CREDIT_CARDS_ALL' not in grants and not all(
                code in grants for code in ('CREDIT_CARDS_LIST','CREDIT_CARDS_LIMITS')):
            failures.add('CONSENT_NO_CARD_SCOPE')
        else:
            validated=True
    if 'CONSENT_ASSOCIATION_UNVERIFIED' in failures:
        return 'CONSENT_ASSOCIATION_UNVERIFIED'
    if validated:
        return None
    if len(failures)==1:
        return next(iter(failures))
    return 'CONSENT_SCAN_UNVERIFIED'


def _usage_scopes(db,settings,current,today):
    legacy={cfg.id:cfg for cfg in settings.pluggy_connections}
    scopes={}
    for cid in current:
        binding=db.execute("""SELECT c.binding_hash,r.source,r.revision,i.item_id FROM of_connections c
            LEFT JOIN of_connection_registry r ON r.connection_id=c.id
            LEFT JOIN of_managed_pluggy_items i ON i.connection_id=c.id WHERE c.id=?""",(cid,)).fetchone()
        expected,reason=_local_binding(db,settings,legacy,cid,binding)
        if reason:
            scopes[cid]=(reason,None,None)
            continue
        evidence={row['resource']:row for row in db.execute("""SELECT resource,state,last_complete_run_id,error_code
            FROM of_collection_checkpoints WHERE connection_id=? AND parent_id=''
            AND resource IN ('item','accounts','consents')""",(cid,))}
        items=db.execute("""SELECT external_id,payload_json,last_run_id FROM of_resource_records
            WHERE connection_id=? AND resource='item' AND parent_id='' AND state='PRESENT' LIMIT 2""",(cid,)).fetchall()
        if not items:
            scopes[cid]=('ITEM_RECORD_MISSING',None,None)
            continue
        item=items[0]
        metadata=_object(json.loads(item['payload_json']))
        if len(items)!=1 or item['external_id']!=expected or metadata.get('id') not in (None,'',expected):
            scopes[cid]=('ITEM_ASSOCIATION_MISMATCH',None,None)
            continue
        expiry=metadata.get('consentExpiresAt')
        expiry_date=civil(expiry)
        connector=_object(metadata.get('connector'))
        regulated=connector.get('isOpenFinance')
        audit=evidence.get('consents')
        if not metadata.get('id') or not metadata.get('status') or expiry is not None and not expiry_date:
            reason='ITEM_METADATA_INCOMPLETE'
        elif expiry_date and expiry_date<=today:
            reason='CONSENT_EXPIRED'
        elif metadata['status'] not in ('UPDATED','OUTDATED'):
            reason='ITEM_ACCESS_UNVERIFIED'
        elif audit and audit['error_code'] in ('ITEM_ID_DIFFERENT','ACCOUNT_SCOPE_MISMATCH'):
            reason='CONSENT_ITEM_MISMATCH'
        else:
            reason=_previous_error(db,cid,evidence,item['last_run_id']) or _consent_state(db,cid,expected,audit,regulated,today)
        collection=evidence.get('accounts')
        last_complete=collection['last_complete_run_id'] if collection else None
        if last_complete and not db.execute('SELECT 1 FROM of_sync_runs WHERE id=? AND connection_id=?',
                                            (last_complete,cid)).fetchone():
            last_complete=None
        if not reason and (not last_complete or collection['state']!='COMPLETE'):
            reason='ACCOUNT_COLLECTION_UNVERIFIED'
        binding=(expected,last_complete) if metadata.get('id')==expected and last_complete and reason not in (
            'PRIOR_SCOPE_FAILURE','LOCAL_BINDING_MISMATCH') else None
        scopes[cid]=(reason,binding,regulated)
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
    credit_connections={cid for (cid,_),row in accounts.items() if cid in current and row['data'].get('type')=='CREDIT'}
    scopes=_usage_scopes(db,settings,credit_connections,values.today)
    cards=[]
    open_rows=defaultdict(list)
    grouped=defaultdict(list)
    preserved=defaultdict(list)
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
        reason,binding,regulated=scopes.get(cid,('HISTORICAL_CONNECTION',None,None))
        local_error=None
        if not data.get('id') or not data.get('itemId'):
            local_error='ACCOUNT_METADATA_INCOMPLETE'
        elif data['id']!=account:
            local_error='ACCOUNT_ID_MISMATCH'
        elif binding and data['itemId']!=binding[0]:
            local_error='ACCOUNT_ITEM_MISMATCH'
        elif binding and row['last_run_id']!=binding[1]:
            local_error='ACCOUNT_PRESERVED'
        elif state not in ('ACTIVE',None):
            local_error='CARD_STATUS_UNVERIFIED'
        identity=line.get('identificationNumber')
        line_type=line.get('consolidationType')
        used_field=parse_amount(line.get('usedAmount')) if currency and line.get('usedAmountCurrencyCode')==currency else None
        used=(used_field if line_type=='CONSOLIDATED' or not regulated else
              parse_amount(data.get('balance')) if holder!='ADDITIONAL' else used_field)
        basis='PROVIDER_USED_AMOUNT' if line_type=='CONSOLIDATED' or not regulated or holder=='ADDITIONAL' else 'REGULATED_BALANCE'
        limit=(parse_amount(line.get('limitAmount')) if currency and line.get('limitAmountCurrencyCode')==currency else None)
        if not line and not ambiguous and credit.get('isLimitFlexible') is not True:
            limit=parse_amount(credit.get('creditLimit'))
        if not local_error and not currency:
            local_error='CURRENCY_UNAVAILABLE'
        if not local_error and reference and reference>values.today:
            local_error='FUTURE_REFERENCE'
        if local_error in ('ACCOUNT_ID_MISMATCH','ACCOUNT_ITEM_MISMATCH'):
            reason=local_error
        readable=bool(binding and not local_error)
        amount_reason=('AMOUNT_UNAVAILABLE' if used is None else 'NEGATIVE_REPORTED' if used<0 else None)
        current_reason=reason or local_error or amount_reason
        open_balance=parse_amount(data.get('balance')) if readable and regulated is False else None
        if open_balance is not None:
            open_rows[(binding[0],account)].append({'amount':open_balance,'currency':currency,'reference':reference})
        blocked=current_reason in ('LOCAL_BINDING_MISMATCH','ITEM_ASSOCIATION_MISMATCH',
                                   'ACCOUNT_ID_MISMATCH','ACCOUNT_ITEM_MISMATCH')
        card={'connection_id':cid,'account_id':account,'institution':views[cid].institution,
              'name':masked_card_text(data.get('marketingName') or data.get('name')) or 'Cartão sem nome',
              'brand':masked_card_text(credit.get('brand')),
              'tail':_number(data.get('cardLastFour')) or _number(data.get('number')),'currency':currency,
              'status':state,'holder':holder,'reference_date':reference,'observed_at':row['observed_at'],
              'used':_format(used) if not current_reason else None,
              'used_basis':basis if readable and not amount_reason else None,'included':False,
              'consolidation_reason':current_reason,'limit_reason':None,'limit':None,
              'provenance_verified':readable,'position_state':'CURRENT' if readable and not reason else
              'PRESERVED' if readable else 'UNAVAILABLE',
              'reported_balance':_format(open_balance),'open_balance_applicable':regulated is False}
        if readable and line_type!='CONSOLIDATED' and limit is not None and limit>=0:
            card['reported_limit']=_format(limit)
        if blocked:
            card.update(name='Cartão com origem não confirmada',brand=None,tail=None)
        cards.append(card)
        if cid not in current:
            continue
        bank=normalize(views[cid].institution)
        banks[bank].add(cid)
        key=(bank,cid,currency)
        line_data=(limit,line_type,identity,ambiguous,line.get('isLimitFlexible',credit.get('isLimitFlexible')))
        grouped[key].append((card,used if not current_reason else None,*line_data))
        if reason and readable:
            copy={**card,'consolidation_reason':amount_reason,'used':_format(used) if not amount_reason else None}
            preserved[key].append((copy,used if not amount_reason else None,*line_data))
    actual=_totals(grouped,banks,cards,values)
    # A connection shares one authorization state. Leave other cards from that
    # Item in the cohort so an unverified line cannot turn into an independent limit.
    for key,group in preserved.items():
        ids={entry[0]['account_id'] for entry in group}
        group.extend(({**card,'consolidation_reason':'OBLIGATION_UNVERIFIED'},used,*extras)
                     for card,used,*extras in grouped[key] if card['account_id'] not in ids)
    last=[entry[0] for group in preserved.values() for entry in group]
    preserved_totals=_totals(preserved,banks,last,values,preserved=True)
    preserved_by_id={(card['connection_id'],card['account_id']):card for card in last}
    for card in cards:
        if card['position_state']=='PRESERVED':
            previous=preserved_by_id[(card['connection_id'],card['account_id'])]
            card.update(preserved_used=previous['used'],limit=previous['limit'])
    # A native balance is attributable to one Item and account. An overlapping
    # observation is never added twice and conflicting copies are excluded.
    balances=[rows[0] for rows in open_rows.values() if all(row==rows[0] for row in rows)]
    open_balance=values.total(balances,partial=len(cards)!=len(balances),position=True)
    open_balance.update(applicable=any(card['open_balance_applicable'] for card in cards),
                        preserved=any(card['position_state']=='PRESERVED' and card['reported_balance'] is not None
                                      for card in cards))
    diagnostics=Counter((card['consolidation_reason'] or 'INCLUDED',card['limit_reason']) for card in cards)
    return {'diagnostics':[{'usage':usage,'limit':limit,'count':count}
                           for (usage,limit),count in sorted(diagnostics.items(),key=lambda entry:(entry[0][0],entry[0][1] or ''))],
            'items':cards,'active_count':sum(card['status']=='ACTIVE' for card in cards),'count':len(cards),
            'basis':'CREDIT_USED',**actual,'preserved':preserved_totals,'open_balance':open_balance}


def _totals(grouped,banks,cards,values,*,preserved=False):
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
                    card['shared_line']=True
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
                card['limit']=_format(limit)
                limit_rows.append({'amount':limit,'currency':currency,'reference':card['reference_date']})
    used=values.total(used_rows,partial=used_partial,position=True)
    limits=values.total(limit_rows,partial=limit_partial,position=True)
    same_references=used['dates']==limits['dates'] and len(used['dates'])==1
    complete=not (used_partial or limit_partial or used['missing'] or limits['missing'] or
                  used['undated'] or limits['undated'])
    comparable=(complete and same_references and used['amounts'].keys()==limits['amounts'].keys()
                and (preserved or not (used['stale'] or limits['stale'])))
    if preserved:
        for metric,partial in ((used,used_partial),(limits,limit_partial)):
            metric['partial']=bool(partial or metric['missing'] or metric['undated'] or metric['mixed_dates'])
    utilization={currency:_format(Decimal(amount)/Decimal(limits['amounts'][currency]))
                 for currency,amount in used['amounts'].items() if comparable and Decimal(limits['amounts'][currency])>0}
    return {'included_count':used['included'],'metric':used,'limit_metric':limits,
            'utilization_by_currency':utilization}
