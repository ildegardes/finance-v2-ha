"""Owner-only manual staging HTTP contracts; no official financial writes."""
from contextlib import closing
import json
import re
from urllib.parse import parse_qs

from .open_finance import OpenFinanceService, SyncError, paged
from .open_finance_query import catalogs, query_transactions
from .open_finance_coverage import sync_full, query as query_resources, coverage_status
from .pluggy_coverage import RESOURCES, CONTRACT, output_schema


PREFIX = '/api/v2/open-finance/'
OPERATIONS = (
    ('GET','connections','connections'), ('POST','sync','sync'),
    ('POST','sync-all','sync_all'), ('GET','sync-runs','runs'),
    ('GET','sync-run','run'), ('GET','transactions','transactions'),
    ('GET','catalogs','catalogs'),
    ('GET','resources','resources'), ('GET','coverage','coverage'),
    ('POST','coverage-sync','coverage_sync'),
)


def request(e):
    def unique(pairs):
        result={}
        for key,value in pairs:
            if key in result:raise ValueError()
            result[key]=value
        return result
    try:
        n=int(e.get('CONTENT_LENGTH') or 0)
        if n<0:raise ValueError()
        if n>1_000_000:raise SyncError('PAYLOAD_TOO_LARGE',413)
        raw=e['wsgi.input'].read(n)
        if raw and e.get('CONTENT_TYPE','').split(';',1)[0].strip().lower()!='application/json':
            raise SyncError('JSON_CONTENT_TYPE_REQUIRED',415)
        body=json.loads(raw,object_pairs_hook=unique,parse_constant=lambda _: (_ for _ in ()).throw(ValueError())) if raw else {}
        if not isinstance(body,dict):raise ValueError()
        raw_query=e.get('QUERY_STRING','')
        query=parse_qs(raw_query,keep_blank_values=True,strict_parsing=True,max_num_fields=20) if raw_query else {}
        if 'contract' in query:
            if len(raw_query.encode('utf-8'))>8192 or re.search(r'%(?![0-9a-fA-F]{2})',raw_query):raise ValueError()
            query=parse_qs(raw_query,keep_blank_values=True,strict_parsing=True,max_num_fields=20,errors='strict')
            if any(len(v)!=1 for v in query.values()):raise ValueError()
            if raw:raise SyncError('GET_BODY_NOT_ALLOWED',422)
        elif any(len(v)!=1 or not v[0] for v in query.values()):raise ValueError()
        return body,query
    except (ValueError,UnicodeError,RecursionError):raise SyncError('INVALID_REQUEST',422) from None


def dispatch(app,operation,identity,body,query):
    if identity.role!='UI' or identity.client_id!='UI:local':raise SyncError('FORBIDDEN',403)
    service=OpenFinanceService(app.settings,app.clock)
    op=operation.removeprefix('open_finance_')
    if op=='coverage_sync':
        if query or set(body)!={'connection_id'} or not isinstance(body.get('connection_id'),str) or not re.fullmatch(r'[a-z][a-z0-9-]{1,63}',body['connection_id']):
            raise SyncError('INVALID_REQUEST',422)
        run=sync_full(service,body['connection_id'],actor=identity.client_id)
        return {'run':run},200 if run['state']=='SUCCEEDED' else 502
    if op in {'resources','coverage'}:
        if body or (op=='coverage' and query):raise SyncError('INVALID_REQUEST',422)
        with closing(app.db()) as c:
            return (query_resources(c,app.settings,query) if op=='resources' else coverage_status(c,app.settings)),200
    if op in {'sync','sync_all'}:
        allowed={'date_from','date_to'} | ({'connection_id'} if op=='sync' else set())
        if query or set(body)-allowed:raise SyncError('INVALID_REQUEST',422)
        # Explicit null is not a civil-date filter; omission alone means unbounded.
        if any(k in body and not isinstance(body[k],str) for k in ('date_from','date_to')):
            raise SyncError('INVALID_PERIOD',422)
        args=dict(actor=identity.client_id,start=body.get('date_from'),end=body.get('date_to'))
        if op=='sync':
            cid=body.get('connection_id')
            if not isinstance(cid,str) or not re.fullmatch(r'[a-z][a-z0-9-]{1,63}',cid):raise SyncError('INVALID_CONNECTION_ID',422)
            run=service.sync_one(cid,**args)
            return {'run':run},200 if run['state']=='SUCCEEDED' else 502
        runs=service.sync_all(**args)
        failures=sum(r['state']!='SUCCEEDED' for r in runs)
        return {'runs':runs},(200 if not failures else 502 if failures==len(runs) else 207)
    if body:raise SyncError('GET_BODY_NOT_ALLOWED',422)
    with closing(app.db()) as c:
        if op=='catalogs':
            if query:raise SyncError('INVALID_QUERY',422)
            return catalogs(c,app.settings.pluggy_connections),200
        if op=='transactions' and 'contract' in query:
            return query_transactions(c,query,app.settings.pluggy_connections,
                origin_evidence=app.settings.open_finance_origin_evidence),200
        if op=='connections':
            if query:raise SyncError('INVALID_QUERY',422)
            return {'connections':service.connections(c)},200
        if op=='run':
            if set(query)!={'run_id'} or not re.fullmatch('[0-9a-f]{32}',query['run_id'][0]):raise SyncError('INVALID_RUN_ID',422)
            row=c.execute('SELECT * FROM of_sync_runs WHERE id=?',(query['run_id'][0],)).fetchone()
            if row is None:raise SyncError('RUN_NOT_FOUND',404)
            return {'run':dict(row)},200
        if op in {'runs','transactions'}:
            if 'connection_id' in query and query['connection_id'][0] not in service.config:
                raise SyncError('CONNECTION_NOT_FOUND',404)
            return paged(c,'of_sync_runs' if op=='runs' else 'of_transactions',query),200
    raise SyncError('NOT_FOUND',404)


def openapi_paths():
    """Explicit new contracts; existing API schemas/semantics are untouched."""
    text={'type':'string'}; nullable={'type':['string','null']}
    run={'type':'object','required':['id','connection_id','state','started_at','inserted_count','updated_count','page_count'],
         'properties':{**{k:text for k in ('id','connection_id','actor','started_at')},
                       **{k:nullable for k in ('finished_at','date_from','date_to','error_code')},
                       'state':{'type':'string','enum':['RUNNING','SUCCEEDED','FAILED','INTERRUPTED']},
                       **{k:{'type':'integer','minimum':0} for k in ('inserted_count','updated_count','page_count')}}}
    transaction={'type':'object','properties':{'id':{'type':'integer'},
        **{k:text for k in ('connection_id','external_account_id','external_id','transaction_date','amount_decimal','currency','first_seen_at','last_seen_at')},
        **{k:nullable for k in ('type','status','description_original','merchant_name','category_key','provider_created_at','provider_updated_at')},
        'category':{'anyOf':[{'type':'null'},{'type':'object','properties':{'provider':{'type':'string','enum':['PLUGGY']},
            **{k:nullable for k in ('external_id','original_name','display_name_pt')},
            'translation_status':{'type':'string','enum':['UNVERIFIED','VERIFIED','OWNER_OVERRIDE']}}}]}}}
    def obj(properties):
        return {'type':'object','required':list(properties),'additionalProperties':False,'properties':properties}
    def enum(*values):return {'type':'string','enum':list(values)}
    integer={'type':'integer','minimum':0}
    hash_schema={'type':'string','pattern':'^[0-9A-F]{64}$'}
    projection=obj({**{k:text for k in ('policy_id','policy_version','context_mode','reason_code','type_observation','type_presence')},
        'policy_hash':hash_schema,'result':enum('CREDIT','DEBIT','UNKNOWN','CONFLICT'),'rule_id':nullable,
        'settlement_evidence':enum('POSTED','PENDING','NOT_ESTABLISHED'),'warnings':{'type':'array','items':text}})
    provenance=obj({'basis':enum('FIRST_IMPORT_RUN'),'status':enum('known','unknown'),'origin_run_id':nullable,
        'origin_revision':{'type':['integer','null'],'enum':[1,None]},'reason_code':nullable,'origin_run_state':nullable})
    metric=obj({'state':enum('EXACT','NOT_REQUESTED','UNAVAILABLE'),'value':{'type':['integer','null'],'minimum':0},'reason':nullable})
    counts=obj({'global_authorized':metric,'non_directional':obj({k:metric for k in ('matched','not_matched','indeterminate')}),
        'classification':obj({k:metric for k in ('credit','debit','unknown','conflict','not_evaluable_policy')}),
        'after_f04':metric,'page_returned':metric})
    ratio={'anyOf':[{'type':'null'},obj({'numerator':integer,'denominator':{'type':'integer','minimum':1}})]}
    coverage_block=obj({'state':enum('COMPLETE','PARTIAL','NO_DATA','NOT_ESTABLISHED','UNAVAILABLE'),
        'basis':enum('EXACT_COUNTS','SEMANTIC_IDENTITY','QUALIFIED_GLOBAL_CHECK','NOT_AVAILABLE'),'ratio':ratio})
    query_meta=obj({'contract':enum('of-l2-v2'),'live':{'type':'boolean'},'order':enum('id_desc'),
        'date_basis':enum('provider_representation_day'),'provenance_basis':enum('FIRST_IMPORT_RUN'),
        'selection':obj({'direction':enum('all','incoming','outgoing','unknown','conflict'),'metrics':enum('none','exact'),
            'active_filters':{'type':'array','items':enum('F01','F02','F03','F04','F05','F06','F07'),'uniqueItems':True}}),
        'policy':obj({'status':enum('ACTIVE'),'id':enum('PLUGGY_DECLARED_TRANSACTION_DIRECTION'),'version':enum('DC-v2'),
            'hash':hash_schema,'context_mode':enum('CURRENT_ACCOUNT_METADATA'),'perspective':enum('DECLARED_ACCOUNT_MOVEMENT')}),
        'search_policy':{'anyOf':[{'type':'null'},obj({'id':text,'version':text,'hash':hash_schema})]},
        'read_consistency':enum('same_read_view'),'catalog_context':enum('CURRENT_PERSISTED_METADATA'),
        'counts':counts,'coverage':obj({'membership':coverage_block,'direction':coverage_block}),
        'query_completeness':enum('COMPLETE','QUALIFIED_PARTIAL','NOT_ESTABLISHED'),'warnings':{'type':'array','items':text}})
    bank_connection=obj({'id':text,'institution':text,'enabled':{'type':'boolean'},'historical':{'type':'boolean'}})
    bank_account=obj({'connection_id':text,'external_id':text,**{k:nullable for k in ('name','type','subtype','currency','provider_updated_at')}})
    bank_category=obj({'connection_id':text,'category_key':text,'provider':enum('PLUGGY'),
        **{k:nullable for k in ('external_id','original_name','display_name_pt')},
        'translation_status':enum('UNVERIFIED','VERIFIED','OWNER_OVERRIDE'),'updated_at':text})
    result={}
    for method,path,op in OPERATIONS:
        if op in {'resources','coverage','coverage_sync'}:continue
        statuses=[200,401,403,422,503,500,405]
        parameters=[]
        spec={'operationId':'open_finance_'+op,'security':[{'bearerAuth':[]}],
              'x-owner-only':True,'x-external-capability':'not-available',
              'description':'UI owner bearer or existing UI session only. Cookie writes require X-CSRF-Token. No external/OAuth/scheduler access.'}
        if method=='POST':
            properties={k:{'type':'string','format':'date'} for k in ('date_from','date_to')}
            if op=='sync':properties['connection_id']={'type':'string','pattern':'^[a-z][a-z0-9-]{1,63}$'}
            spec['requestBody']={'required':op=='sync','content':{'application/json':{'schema':{'type':'object','additionalProperties':False,
                'properties':properties,'required':['connection_id'] if op=='sync' else []}}}}
            parameters.append({'name':'X-CSRF-Token','in':'header','required':False,'description':'Required for UI cookie authentication; not for owner bearer.','schema':text})
            statuses += [409,413,415,502,207] if op=='sync_all' else [404,409,413,415,502]
            schema={'type':'object','properties':{'run':run}} if op=='sync' else {'type':'object','properties':{'runs':{'type':'array','items':run}}}
        elif op in {'runs','transactions'}:
            parameters=[{'name':k,'in':'query','schema':s,'required':False} for k,s in (
                ('page',{'type':'integer','minimum':1,'maximum':9223372036854775807}),('page_size',{'type':'integer','enum':[25,50,100]}),('connection_id',text))]
            if op=='transactions':
                parameters.append({'name':'external_account_id','in':'query','schema':{'type':'string','minLength':1,'maxLength':200}})
                parameters += [{'name':k,'in':'query','required':False,'description':'Only with contract=of-l2-v2; legacy behavior is unchanged.','schema':s} for k,s in (
                    ('contract',{'type':'string','enum':['of-l2-v2']}),('order',{'type':'string','enum':['id_desc']}),
                    ('start',{'type':'string','format':'date'}),('end',{'type':'string','format':'date'}),
                    ('category_key',text),('category_presence',{'type':'string','enum':['any','present','missing']}),
                    ('direction',{'type':'string','enum':['all','incoming','outgoing','unknown','conflict']}),
                    ('search',{'type':'string','maxLength':256}),('origin_run_id',{'type':'string','pattern':'^[0-9a-f]{32}$'}),
                    ('provenance_state',{'type':'string','enum':['any','known','unknown']}),('metrics',{'type':'string','enum':['none','exact']}))]
                spec['description'] += ' Opt-in of-l2-v2 filters the entire bounded read view before pagination; direction DC-v2, U31-A13 search, first-import-run provenance. Unproven legacy origin remains unknown.'
                transaction['properties'].update(direction=projection,provenance=provenance,institution=text,account_name=nullable)
            schema={'type':'object','required':['items','page','page_size','has_more'],'properties':{'items':{'type':'array','items':run if op=='runs' else transaction},
                'page':{'type':'integer'},'page_size':{'type':'integer'},'has_more':{'type':'boolean'}}}
            if op=='transactions':schema['properties']['query_meta']=query_meta
            statuses.append(404)
        elif op=='catalogs':
            schema=obj({k:{'type':'array','items':item} for k,item in
                (('connections',bank_connection),('accounts',bank_account),('categories',bank_category),('runs',run))})
        elif op=='run':
            parameters=[{'name':'run_id','in':'query','required':True,'schema':{'type':'string','pattern':'^[0-9a-f]{32}$'}}]
            schema={'type':'object','properties':{'run':run}};statuses.append(404)
        else:
            schema={'type':'object','properties':{'connections':{'type':'array','items':{'type':'object','properties':{'id':text,'institution':text,
                'enabled':{'type':'boolean'},'sync_state':{'type':'string','enum':['IDLE','RUNNING','SUCCEEDED','FAILED','INTERRUPTED']},
                'lease_expired':{'type':'boolean'},'last_run':{'anyOf':[run,{'type':'null'}]}}}}}}
        spec['parameters']=parameters
        spec['responses']={str(s):{'description':'Completed sync / diagnostic outcome' if s in {200,207,502} else 'Sanitized error',
            'content':{'application/json':{'schema':schema if s in {200,207,502} else {'$ref':'#/components/schemas/Error'}}}} for s in statuses}
        result[PREFIX+path]={method.lower():spec}
    text_schema={'type':'string'}
    coverage_schema=obj({**{k:text for k in ('connection_id','resource','parent_id','run_id','state','observed_at')},
        **{k:integer for k in ('page_count','record_count','omitted_field_count')},'error_code':nullable})
    resource_row={'type':'object','required':['connection_id','parent_id','external_id','state','observed_at','data'],
        'properties':{**{k:text for k in ('connection_id','parent_id','external_id','state','observed_at','first_run_id','last_run_id','run_id')},
            'data':{'anyOf':[output_schema(v['schema']) for v in CONTRACT['resources'].values()]}}}
    resource_response=obj({'resource':enum(*RESOURCES),'items':{'type':'array','items':resource_row},'total':integer,
        'page':integer,'page_size':integer,'history':{'type':'boolean'},'has_more':{'type':'boolean'},
        'coverage':{'type':'array','items':coverage_schema},'source':enum('CACHED_STAGING'),
        'net_worth':obj({'state':enum('NOT_ESTABLISHED'),'reason':enum('CURRENCY_AND_OVERLAP_NOT_PROVEN')})})
    coverage_response=obj({'coverage':{'type':'array','items':coverage_schema},
        'runs':{'type':'array','items':obj({k:nullable if k=='error_code' else text for k in ('id','connection_id','state','error_code')})},
        'automatic_sync':{'type':'boolean'},'remote_updates':{'type':'boolean','const':False}})
    for method,path,op in OPERATIONS:
        if op not in {'resources','coverage','coverage_sync'}:continue
        response_schema=resource_response if op=='resources' else coverage_response if op=='coverage' else obj({'run':run})
        spec={'operationId':'open_finance_'+op,'security':[{'bearerAuth':[]}],
              'x-owner-only':True,'x-external-capability':'not-available',
              'description':'Owner-only cached staging. No real-time balance, SCR or remote update. Cookie POST requires CSRF.',
              'parameters':[],'responses':{str(code):{'description':'Staging result' if code==200 else 'Sanitized error',
                'content':{'application/json':{'schema':response_schema if code==200 or (op=='coverage_sync' and code==502) else {'$ref':'#/components/schemas/Error'}}}} for code in (200,401,403,404,409,422,502,503)}}
        if op=='coverage_sync':
            spec['requestBody']={'required':True,'content':{'application/json':{'schema':{'type':'object','additionalProperties':False,
                'required':['connection_id'],'properties':{'connection_id':{'type':'string','pattern':'^[a-z][a-z0-9-]{1,63}$'}}}}}}
            spec['parameters']=[{'name':'X-CSRF-Token','in':'header','schema':text_schema,'description':'Required for cookie authentication.'}]
        if op=='resources':
            spec['parameters']=[{'name':name,'in':'query','schema':schema} for name,schema in (
                ('resource',{'type':'string','enum':list(RESOURCES)}),('connection_id',text_schema),('parent_id',text_schema),
                ('state',{'type':'string','enum':['PRESENT','NOT_SEEN']}),('page',{'type':'integer','minimum':1}),
                ('history',{'type':'string','enum':['0','1']}),('type',text_schema),('currency',text_schema),
                ('page_size',{'type':'integer','enum':[25,50,100]}))]
        result[PREFIX+path]={method.lower():spec}
    return result
