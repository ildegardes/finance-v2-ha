"""Typed, owner-only views over the existing external staging, never official ledgers."""
from datetime import datetime, timezone
from decimal import Decimal, DecimalException
import json
import re

from .open_finance import SyncError
from .pluggy_coverage import CONTRACT, RESOURCES

LABELS={
 'name':'Nome','marketingName':'Produto','type':'Tipo','subtype':'Subtipo','status':'Estado informado',
 'balance':'Saldo informado','currencyCode':'Moeda','creditData':'Dados do cartão','bankData':'Dados bancários',
 'creditLimit':'Limite contratado','availableCreditLimit':'Limite disponível','minimumPayment':'Pagamento mínimo',
 'balanceCloseDate':'Fechamento','balanceDueDate':'Vencimento','brand':'Bandeira','level':'Nível',
 'closingBalance':'Saldo de fechamento','automaticallyInvestedBalance':'Aplicado automaticamente',
 'overdraftContractedLimit':'Cheque especial contratado','overdraftUsedLimit':'Cheque especial utilizado',
 'disaggregatedCreditLimits':'Limites por modalidade','usedAmount':'Valor utilizado','limitAmount':'Limite',
 'availableAmount':'Disponível','customizedLimitAmount':'Limite personalizado','isLimitFlexible':'Limite flexível',
 'amount':'Valor','amountInAccountCurrency':'Valor na moeda da conta','date':'Data de origem',
 'description':'Descrição','descriptionRaw':'Descrição original','category':'Categoria bancária',
 'creditCardMetadata':'Dados da compra','installmentNumber':'Parcela','totalInstallments':'Total de parcelas',
 'totalAmount':'Valor total','dueDate':'Vencimento','billClosingDate':'Fechamento',
 'totalAmountCurrencyCode':'Moeda da fatura','minimumPaymentAmount':'Pagamento mínimo',
 'allowsInstallments':'Permite parcelamento','financeCharges':'Encargos','payments':'Pagamentos informados',
 'paymentDate':'Data do pagamento','paymentMode':'Meio de pagamento','paymentType':'Forma de cobrança',
 'billForecastDate':'Previsão de fatura','billPostDate':'Data civil de inclusão na fatura',
 'transactionDateTime':'Instante original da transação','purchaseDate':'Data de aquisição',
 'merchant':'Estabelecimento','paymentData':'Dados da movimentação','operationType':'Operação bancária',
 'value':'Preço informado','quantity':'Quantidade','netAmount':'Valor líquido','movementType':'Direção na posição',
 'tradeDate':'Confirmação','expenses':'Despesas e tributos informados','taxes':'Tributos','taxes2':'Outros tributos',
 'lastMonthRate':'Rentabilidade mensal informada','lastTwelveMonthsRate':'Rentabilidade anual informada',
 'annualRate':'Taxa anual informada','rate':'Taxa informada','CET':'Custo efetivo total',
 'amountProfit':'Resultado informado','amountOriginal':'Valor original','amountWithdrawal':'Resgate informado',
 'productName':'Produto de crédito','contractAmount':'Valor contratado','contractDate':'Data do contrato',
 'settlementDate':'Liquidação','firstInstallmentDueDate':'Primeiro vencimento',
 'installments':'Parcelas','totalNumberOfInstallments':'Total de parcelas','contractRemainingNumber':'Parcelas restantes',
 'paidInstallments':'Parcelas pagas','dueInstallments':'Parcelas a vencer','pastDueInstallments':'Parcelas vencidas',
 'balloonPayments':'Pagamentos intermediários','interestRates':'Taxas de juros','contractedFees':'Tarifas contratadas',
 'contractedFinanceCharges':'Encargos contratados','warranties':'Garantias','releases':'Liberações e pagamentos',
 'contractOutstandingBalance':'Saldo devedor informado','paidAmount':'Valor pago','paidDate':'Data do pagamento',
 'monthYear':'Competência do extrato','expiresAt':'Expiração','revokedAt':'Revogação',
 'products':'Produtos','openFinancePermissionsGranted':'Permissões declaradas','connector':'Instituição',
 'createdAt':'Criado no provedor','updatedAt':'Atualizado no provedor','lastUpdatedAt':'Última atualização',
 'statusDetail':'Qualidade por produto','resourcesCollectedAt':'Declaração de recursos obtida em',
 'hasResourcesPendingAuthorization':'Recursos pendentes de autorização','consentExpiresAt':'Consentimento vence em',
 'code':'Código do ativo','isin':'ISIN','institution':'Instituição da posição','issuer':'Emissor',
 'issueDate':'Data de emissão','gracePeriodDate':'Fim da carência','fixedAnnualRate':'Taxa fixa anual informada',
 'rateType':'Tipo de taxa','taxExempt':'Isento de tributos','ratePeriodicity':'Periodicidade da taxa',
 'indexerAdditionalInfo':'Informação do indexador','priceFactor':'Fator de preço','couponPayment':'Pagamento de cupom',
 'metadata':'Características da posição','balanceForeignCurrency':'Saldo em moeda estrangeira',
 'disbursementDates':'Datas de liberação','kind':'Modalidade','installmentPeriodicity':'Periodicidade das parcelas',
 'amortizationScheduled':'Sistema de amortização','valueType':'Tipo de pagamento','revokedAt':'Revogação',
}
KINDS={'item':'CONNECTION','resources':'DECLARED_RESOURCE','consents':'CONSENT','accounts':'BANK_ACCOUNT',
 'transactions':'BANK_TRANSACTION','investments':'INVESTMENT_POSITION','investment_transactions':'INVESTMENT_MOVEMENT',
 'loans':'CREDIT_CONTRACT','bills':'CREDIT_BILL','statements':'STATEMENT_REFERENCE'}
HIDDEN={'id','itemId','accountId','resourceId','providerId','providerCode','order','categoryId','billId',
 'transactions','identificationNumber','installmentId','proposalNumber','processNumber','credentials','url'}
MONEY=re.compile(r'balance|amount|value|limit|payment|profit|taxes|fee$',re.I)
RATE=re.compile(r'rate|percentage|^CET$',re.I)


def decimal_text(value):
    if isinstance(value,bool) or not isinstance(value,(str,int,float,Decimal)):raise ValueError()
    if isinstance(value,str) and len(value)>32768:raise ValueError()
    number=Decimal(str(value))
    # Preserve the staging contract's precision, bounded by its existing text limit.
    if not number.is_finite() or abs(number.as_tuple().exponent)>32766 or number.adjusted()>32766:raise ValueError()
    text=format(number,'f')
    if len(text)>32768:raise ValueError()
    return text


def _currency(data,default=None):
    for key in ('currencyCode','totalAmountCurrencyCode'):
        if key in data:return data[key] if isinstance(data[key],str) and data[key] else None
    return default


def field(key,spec,value,present,currency,depth=0):
    if key=='balanceForeignCurrency':currency=None
    label=LABELS.get(key,re.sub(r'([a-z])([A-Z])',r'\1 \2',key))
    node={'key':key,'label':label,'state':'ABSENT' if not present else 'NULL' if value is None else 'VALUE','kind':'TEXT'}
    if not present or value is None:return node
    if depth>12:return {**node,'state':'UNSUPPORTED'}
    if isinstance(value,dict):
        local=_currency(value,currency)
        children=[field(k,s,value.get(k),k in value,value.get(k+'CurrencyCode') if k+'CurrencyCode' in value else local,depth+1) for k,s in spec.get('properties',{}).items() if k not in HIDDEN]
        return {**node,'kind':'SECTION','children':children}
    if isinstance(value,list):
        items=[]
        # Foreign balances declare their own currency; never inherit the card's BRL.
        child_currency=None if key=='balanceForeignCurrency' else currency
        for entry in value:
            if isinstance(entry,dict):items.append(field(key,spec.get('items',{}),entry,True,child_currency,depth+1))
            elif type(entry) in (str,int,float,bool):items.append(field(key,spec.get('items',{}),entry,True,child_currency,depth+1))
            else:items.append({'key':key,'label':label,'state':'NULL' if entry is None else 'UNSUPPORTED','kind':'TEXT'})
        return {**node,'kind':'COLLECTION','items':items}
    if isinstance(value,bool):return {**node,'kind':'BOOLEAN','value':value}
    if spec.get('format') in ('date','date-time'):
        try:
            if not isinstance(value,str) or len(value)>40:raise ValueError()
            dt=datetime.fromisoformat(value.replace('Z','+00:00'))
            result={**node,'kind':'CIVIL_DATE' if len(value)==10 else 'INSTANT','value':value}
            if dt.tzinfo is not None:result['utc']=dt.astimezone(timezone.utc).isoformat()
            return result
        except (ValueError,TypeError):return {**node,'kind':'DATE','state':'UNSUPPORTED'}
    numeric=spec.get('type')=='number' or (isinstance(spec.get('type'),list) and 'number' in spec['type']) or type(value) in (int,float,Decimal)
    if numeric:
        try:text=decimal_text(value)
        except (ValueError,DecimalException):return {**node,'state':'UNSUPPORTED','kind':'NUMBER'}
        kind='QUANTITY' if key=='quantity' else 'RATE' if RATE.search(key) else 'MONEY' if MONEY.search(key) else 'NUMBER'
        return {**node,'kind':kind,'value':text,'currency':currency if kind=='MONEY' else None}
    return {**node,'value':str(value)}


def _origin(c,row,history):
    """First observation of this content, never replay/absence/reappearance context."""
    cutoff=' AND s.rowid<=(SELECT rowid FROM of_sync_runs WHERE id=?)' if history else ''
    args=(row['connection_id'],row['_resource'],row['parent_id'],row['external_id'],
        json.dumps(row['data'],ensure_ascii=True,separators=(',',':'),sort_keys=True))+((row['run_id'],) if history else ())
    found=c.execute('SELECT r.run_id,r.observed_at FROM of_resource_revisions r JOIN of_sync_runs s ON s.id=r.run_id WHERE r.connection_id=? AND r.resource=? AND r.parent_id=? AND r.external_id=? AND r.payload_json=? AND r.state=\'PRESENT\''+cutoff+' ORDER BY r.id LIMIT 1',args).fetchone()
    return (found['run_id'],found['observed_at']) if found else (None,None)


def _context_at_origin(c,connection,resource,external,run_id):
    """Only an earlier/same-run revision is evidence. Never consult today's parent."""
    identity=' AND r.external_id=?' if external is not None else ''
    args=(connection,resource)+((external,) if external is not None else ())+(run_id,)
    row=c.execute('SELECT r.payload_json,r.state FROM of_resource_revisions r JOIN of_sync_runs s ON s.id=r.run_id WHERE r.connection_id=? AND r.resource=? AND r.parent_id=\'\''+identity+' AND s.rowid<=(SELECT rowid FROM of_sync_runs WHERE id=?) ORDER BY s.rowid DESC,r.id DESC LIMIT 1',args).fetchone()
    if row is None or row['state']!='PRESENT':return {}
    return json.loads(row['payload_json'])


def _freshness(item,resource,kind):
    if not item:return {'state':'UNKNOWN','source':'PROVIDER_CACHE'}
    group={'transactions':'transactions','investments':'investments','investment_transactions':'investmentsTransactions',
           'loans':'loans','bills':'creditCards','statements':'accountStatements','accounts':'creditCards' if kind=='CREDIT_CARD' else 'accounts'}.get(resource)
    detail=(item.get('statusDetail') or {}).get(group) if group else None
    updated=detail.get('isUpdated') if isinstance(detail,dict) else None
    warnings=detail.get('warnings') if isinstance(detail,dict) else None
    # A provider's "isUpdated" reports its execution, not the age of a balance/position.
    return {'state':'STALE' if updated is False else 'UNKNOWN',
        'source':'PROVIDER_CACHE','provider_execution_partial':item.get('executionStatus') in ('PARTIAL_SUCCESS','PARTIAL SUCCESS'),
        'warning_count':len(warnings) if isinstance(warnings,list) else 0}


def query_domain(c,settings,values):
    from .open_finance_coverage import query
    c.execute('BEGIN')
    try:
        result=query(c,settings,values,manage_transaction=False)
        resource=result['resource'];items=[]
        for row in result['items']:
            data=row['data'];kind='CREDIT_CARD' if resource=='accounts' and data.get('type')=='CREDIT' else KINDS[resource]
            origin_run,origin_collected_at=_origin(c,{**row,'_resource':resource},result['history'])
            currency=_currency(data)
            parent_currency=None
            if resource in ('investment_transactions','bills','transactions'):
                parent='investments' if resource=='investment_transactions' else 'accounts'
                parent_currency=_context_at_origin(c,row['connection_id'],parent,row['parent_id'],origin_run).get('currencyCode')
                currency=_currency(data,parent_currency)
            fields=[field(k,s,data.get(k),k in data,parent_currency if k=='amountInAccountCurrency' else data.get(k+'CurrencyCode') if k+'CurrencyCode' in data else currency) for k,s in CONTRACT['resources'][resource]['schema']['properties'].items() if k not in HIDDEN]
            identity={k:row[k] for k in ('connection_id','parent_id','external_id')}
            checkpoint=c.execute('SELECT state,page_count,record_count,last_complete_run_id,error_code FROM of_collection_checkpoints WHERE connection_id=? AND resource=? AND parent_id=?',
                (row['connection_id'],resource,row['parent_id'])).fetchone()
            relation={'state':'NOT_APPLICABLE'}
            if resource=='transactions':
                if result['history']:
                    link=c.execute('SELECT state FROM of_resource_link_revisions WHERE connection_id=? AND source_resource=? AND source_parent_id=? AND source_external_id=? AND run_id=? ORDER BY id DESC LIMIT 1',
                        (row['connection_id'],resource,row['parent_id'],row['external_id'],row['run_id'])).fetchone()
                    relation={'state':link[0] if link else 'HISTORICAL_NOT_ESTABLISHED'}
                else:
                    link=c.execute('SELECT state FROM of_resource_links WHERE connection_id=? AND source_resource=? AND source_parent_id=? AND source_external_id=?',
                        (row['connection_id'],resource,row['parent_id'],row['external_id'])).fetchone()
                    relation={'state':link[0] if link else 'NOT_APPLICABLE'}
            children=[]
            if resource=='accounts':children=['transactions','bills' if kind=='CREDIT_CARD' else 'statements']
            elif resource=='investments':children=['investment_transactions']
            # Historical context is distinct from the mutable current sync/checkpoint.
            origin_item=_context_at_origin(c,row['connection_id'],'item',None,origin_run)
            quality=_freshness(origin_item,resource,kind)
            current_run=c.execute('SELECT state,error_code,started_at,finished_at FROM of_sync_runs WHERE connection_id=? ORDER BY rowid DESC LIMIT 1',(row['connection_id'],)).fetchone()
            financial_dates={k:data[k] for k in ('date','transactionDateTime','tradeDate','billPostDate','paymentDate') if isinstance(data.get(k),str)}
            temporal={'financial_observation':financial_dates or None,'collected_at':row['observed_at'],
                'content_first_collected_at':origin_collected_at,'last_seen_at':row['observed_at'] if row['state']=='PRESENT' else None,
                'absence_observed_at':row['observed_at'] if row['state']=='NOT_SEEN' else None,
                'provider_updated_at':data.get('updatedAt') or data.get('lastUpdatedAt'),
                'provider_execution_at_collection':{'context':'CONTENT_FIRST_COLLECTION','status':origin_item.get('executionStatus'),'updated_at':origin_item.get('lastUpdatedAt') or origin_item.get('updatedAt'),
                    'quality':quality},'current_sync':dict(current_run) if current_run else None,
                'effective_freshness':'STALE' if quality['state']=='STALE' else 'NOT_ESTABLISHED',
                'historical_revision':result['history']}
            items.append({'identity':identity,'kind':kind,'name':data.get('name') or data.get('productName') or data.get('description') or LABELS.get(resource,kind),
                'record_state':row['state'],'observed_at':row['observed_at'],'fields':fields,'children':children,'relation':relation,
                'collection':dict(checkpoint) if checkpoint else {'state':'NOT_QUERIED'},
                'freshness':quality,'temporal':temporal,
                'currency_context':{'currency':currency,'source':'PROVIDER_RECORD' if _currency(data) else 'NOT_PROVIDED' if 'currencyCode' in data or 'totalAmountCurrencyCode' in data else 'PARENT_AT_ORIGIN' if parent_currency else 'NOT_PROVIDED',
                    'account_currency':parent_currency},'source':'EXTERNAL_STAGING'})
        # Empty scopes still return checkpoints; they must not look "not queried".
        clauses=['resource=?'];args=[resource]
        for k in ('connection_id','parent_id'):
            if k in values:clauses.append(k+'=?');args.append(values[k][0])
        checkpoints=[dict(row) for row in c.execute('SELECT connection_id,resource,parent_id,state,page_count,record_count,last_complete_run_id,error_code,observed_at FROM of_collection_checkpoints WHERE '+' AND '.join(clauses)+' ORDER BY connection_id,parent_id',args)]
        return {'contract':'OF-DOMAIN/1','resource':resource,'items':items,'total':result['total'],'page':result['page'],'page_size':result['page_size'],
            'has_more':result['has_more'],'history':result['history'],'coverage':result['coverage'],'checkpoints':checkpoints,
            'source':'EXTERNAL_STAGING','net_worth':result['net_worth'],'document_download':'NOT_ENABLED',
            'consent_diagnostics':consent_diagnostics(c,settings)}
    finally:c.rollback()


def consent_diagnostics(c,settings):
    result=[]
    for config in settings.pluggy_connections:
        row=c.execute("SELECT state,error_code,last_complete_run_id FROM of_collection_checkpoints WHERE connection_id=? AND resource='consents' AND parent_id=''",(config.id,)).fetchone()
        if row is None:state='NOT_QUERIED'
        elif row['state']=='FAILED':state='ASSOCIATION_INCONSISTENT' if row['error_code'] in ('ACCOUNT_SCOPE_MISMATCH','ITEM_ID_DIFFERENT') else 'QUERY_FAILED'
        elif row['state']=='EMPTY':state='NO_CONSENT_OBSERVED'
        elif row['state']=='COMPLETE':state='ASSOCIATION_VALIDATED_IN_LAST_SCAN'
        else:state='NOT_CURRENTLY_ESTABLISHED'
        result.append({'connection_id':config.id,'state':state,'new_import_requires_valid_scope':True,'access_mode':config.access_mode})
    return result


def query_relations(c,settings,values):
    allowed={'connection_id','parent_id','page','page_size'}
    if set(values)-allowed or any(len(v)!=1 for v in values.values()):raise SyncError('INVALID_QUERY',422)
    def integer(name,default):
        value=values.get(name,[str(default)])[0]
        if not re.fullmatch('[1-9][0-9]{0,7}',value):raise SyncError('INVALID_PAGINATION',422)
        return int(value)
    page,size=integer('page',1),integer('page_size',25)
    if size not in (25,50,100):raise SyncError('INVALID_PAGINATION',422)
    clauses=[];args=[]
    for name in ('connection_id','parent_id'):
        if name in values:
            value=values[name][0]
            if not isinstance(value,str) or not value or len(value)>200 or any(ord(ch)<32 for ch in value):raise SyncError('INVALID_QUERY',422)
            if name=='connection_id' and value not in {x.id for x in settings.pluggy_connections}:raise SyncError('CONNECTION_NOT_FOUND',404)
            clauses.append(('source_parent_id' if name=='parent_id' else name)+'=?');args.append(value)
    where=' WHERE '+' AND '.join(clauses) if clauses else ''
    c.execute('BEGIN')
    try:
        total=c.execute('SELECT COUNT(*) FROM of_resource_links'+where,args).fetchone()[0]
        rows=[dict(row) for row in c.execute('SELECT connection_id,source_parent_id,source_external_id,state,target_parent_id,target_external_id,run_id,observed_at FROM of_resource_links'+where+
            ' ORDER BY connection_id,source_parent_id,source_external_id LIMIT ? OFFSET ?',args+[size,(page-1)*size])]
        return {'contract':'OF-RELATIONS/1','items':rows,'total':total,'page':page,'page_size':size,'has_more':page*size<total,'source':'EXTERNAL_STAGING'}
    finally:c.rollback()


def openapi_paths():
    node={'type':'object','required':['key','label','state','kind'],'properties':{
        'key':{'type':'string'},'label':{'type':'string'},'state':{'type':'string','enum':['VALUE','NULL','ABSENT','UNSUPPORTED']},
        'kind':{'type':'string'},'value':{},'currency':{'type':['string','null']},'children':{'type':'array','items':{'type':'object'}},'items':{'type':'array','items':{'type':'object'}}}}
    response={'type':'object','required':['resource','items','total','page','page_size','has_more','source','checkpoints'],
        'properties':{'resource':{'enum':list(RESOURCES)},'items':{'type':'array','items':{'type':'object','properties':{'fields':{'type':'array','items':node}}}},
                      'source':{'const':'EXTERNAL_STAGING'},'total':{'type':'integer'},'page':{'type':'integer'},'page_size':{'enum':[25,50,100]},
                      'has_more':{'type':'boolean'},'checkpoints':{'type':'array','items':{'type':'object'}}}}
    paths={}
    for path,op in (('domain','domain'),('relations','relations'),('domain-sync','domain_sync')):
        method='post' if path=='domain-sync' else 'get'
        spec={'operationId':'open_finance_'+op,'security':[{'bearerAuth':[]}],'x-owner-only':True,
            'x-external-capability':'not-available','description':'External staging only; no document download or implicit provider call on GET.',
            'parameters':[],'responses':{'200':{'description':'Typed staging result','content':{'application/json':{'schema':response if path=='domain' else {'type':'object'}}}}}}
        if method=='post':
            spec['requestBody']={'required':True,'content':{'application/json':{'schema':{'type':'object','additionalProperties':False,'required':['connection_id','mode'],
                'properties':{'connection_id':{'type':'string'},'mode':{'enum':['FULL','INCREMENTAL','RESUME']}}}}}}
            spec['parameters']=[{'name':'X-CSRF-Token','in':'header','schema':{'type':'string'}}]
        else:
            names=['connection_id','parent_id','page','page_size']+(['resource','state','type','currency','history'] if path=='domain' else [])
            spec['parameters']=[{'name':name,'in':'query','schema':{'type':'string'}} for name in names]
        for status in (401,403,404,409,413,415,422,502,503,500):
            spec['responses'][str(status)]={'description':'Sanitized error or failed collection',
                'content':{'application/json':{'schema':{'type':'object'} if method=='post' and status==502 else {'$ref':'#/components/schemas/Error'}}}}
        paths['/api/v2/open-finance/'+path]={method:spec}
    return paths
