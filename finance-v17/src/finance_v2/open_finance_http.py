"""Owner-only manual staging HTTP contracts; no official financial writes."""
from collections import deque
from contextlib import closing
import json
import re
from threading import Lock
from time import monotonic
from urllib.parse import parse_qs

from .open_finance import OpenFinanceService, SyncError, paged
from .open_finance_query import catalogs, query_transactions
from .open_finance_coverage import sync_full, sync_domain, query as query_resources, coverage_status
from .open_finance_domain import query_domain, query_relations, openapi_paths as domain_paths
from .open_finance_registry import connection_views
from .pluggy_coverage import RESOURCES, CONTRACT, output_schema


PREFIX = '/api/v2/open-finance/'


class RegistryRateLimiter:
    """The owner has a shared limit across sessions and server worker threads."""
    def __init__(self, *, now=monotonic, provider_limit=8, local_limit=32):
        self._now = now
        self._lock = Lock()
        self._provider = deque(maxlen=provider_limit)
        self._local = deque(maxlen=local_limit)

    def admit(self, operation):
        uses_provider = operation in {
            "open_finance_registry_activate", "open_finance_registry_rotate_credentials",
            "open_finance_registry_validate", "open_finance_registry_connector_catalog",
        }
        attempts = self._provider if uses_provider else self._local
        with self._lock:
            now = self._now()
            while attempts and attempts[0] <= now - 60:
                attempts.popleft()
            if len(attempts) == attempts.maxlen:
                raise SyncError("REGISTRY_RATE_LIMITED", 429)
            attempts.append(now)


OPERATIONS = (
    ('POST','registry/details','registry_details'),
    ('POST','registry/connectors','registry_connector_catalog'),
    ('POST','registry/drafts','registry_create'),
    ('POST','registry/activate','registry_activate'),
    ('POST','registry/validate','registry_validate'),
    ('POST','registry/archive/inspect','registry_archive_inspect'),
    ('POST','registry/archive','registry_archive'),
    ('POST','registry/disable','registry_disable'),
    ('POST','registry/rename','registry_rename'),
    ('POST','registry/rotate-credentials','registry_rotate_credentials'),
    ('POST','registry/delete/inspect','registry_delete_inspect'),
    ('POST','registry/delete','registry_delete'),
    ('GET','santander-binding-recovery','recovery_inspect'),
    ('POST','santander-binding-recovery/prepare','recovery_prepare'),
    ('POST','santander-binding-recovery/confirm','recovery_confirm'),
    ('GET','connections','connections'), ('POST','sync','sync'),
    ('POST','sync-all','sync_all'), ('GET','sync-runs','runs'),
    ('GET','sync-run','run'), ('GET','transactions','transactions'),
    ('GET','catalogs','catalogs'), ('GET','analytics','analytics'),
    ('GET','resources','resources'), ('GET','coverage','coverage'),
    ('POST','coverage-sync','coverage_sync'),
    ('GET','domain','domain'), ('GET','relations','relations'),
    ('POST','domain-sync','domain_sync'),
)


def request(e, *, limit=1_000_000):
    def unique(pairs):
        result={}
        for key,value in pairs:
            if key in result:raise ValueError()
            result[key]=value
        return result
    try:
        n=int(e.get('CONTENT_LENGTH') or 0)
        if n<0:raise ValueError()
        if n>limit:raise SyncError('PAYLOAD_TOO_LARGE',413)
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
    if operation.startswith('open_finance_registry_'):
        if identity.role != 'UI' or identity.client_id != 'UI:local' or not identity.csrf:
            raise SyncError('FORBIDDEN',403)
        from .open_finance_registry_admin import RegistryAdmin
        admin = RegistryAdmin(OpenFinanceService(app.settings, app.clock))
        if query:
            raise SyncError('INVALID_REQUEST',422)
        if operation in {'open_finance_registry_details','open_finance_registry_connector_catalog'}:
            if set(body) != {'connection_id','revision'} or not _connection_id(body['connection_id']):
                raise SyncError('INVALID_REQUEST',422)
            action = admin.connection_details if operation.endswith('_details') else admin.connector_catalog
            return action(actor=identity.client_id, **body),200
        if operation == 'open_finance_registry_create':
            required = {'label','environment','client_id','client_secret','item_id'}
            if not required <= body.keys() or body.keys() - required - {'replaces_id'}:
                raise SyncError('INVALID_REQUEST',422)
            if 'replaces_id' in body and not _connection_id(body['replaces_id']):
                raise SyncError('INVALID_CONNECTION_ID',422)
            return admin.create_draft(actor=identity.client_id, **body),201
        if operation == 'open_finance_registry_rename':
            if set(body) != {'connection_id','revision','label'} or not _connection_id(body['connection_id']):
                raise SyncError('INVALID_REQUEST',422)
            return admin.rename(body['connection_id'], actor=identity.client_id,
                                revision=body['revision'], label=body['label']),200
        if operation == 'open_finance_registry_rotate_credentials':
            if set(body) != {'connection_id','revision','confirmed','client_id','client_secret'} or not _connection_id(body['connection_id']):
                raise SyncError('INVALID_REQUEST',422)
            return admin.rotate_credentials(actor=identity.client_id, **body),200
        if operation in {'open_finance_registry_archive_inspect','open_finance_registry_delete_inspect','open_finance_registry_delete'}:
            fields = {'connection_id','revision'}
            if operation.endswith('_inspect'):
                action = (admin.inspect_archive if operation == 'open_finance_registry_archive_inspect'
                          else admin.inspect_deletion)
            else:
                fields |= {'backup_confirmed','confirmation'}
                action = admin.delete
            if set(body) != fields or not _connection_id(body['connection_id']):
                raise SyncError('INVALID_REQUEST',422)
            return action(actor=identity.client_id, **body),200
        fields = {'connection_id','revision','confirmed'}
        optional = {'connector_id'} if operation == 'open_finance_registry_activate' else set()
        if not fields <= body.keys() or body.keys() - fields - optional or not _connection_id(body['connection_id']):
            raise SyncError('INVALID_REQUEST',422)
        if 'connector_id' in body and (type(body['connector_id']) is not int or not 0 < body['connector_id'] < 2**31):
            raise SyncError('INVALID_REQUEST',422)
        args = dict(actor=identity.client_id, revision=body['revision'], confirmed=body['confirmed'])
        if operation == 'open_finance_registry_activate':
            return admin.validate_and_activate(body['connection_id'], connector_id=body.get('connector_id'), **args),200
        if operation == 'open_finance_registry_validate':
            return admin.validate_connection(body['connection_id'], **args),200
        if operation == 'open_finance_registry_archive':
            return admin.archive(body['connection_id'], **args),200
        if operation == 'open_finance_registry_disable':
            return admin.disable(body['connection_id'], **args),200
        raise SyncError('NOT_FOUND',404)
    if operation.startswith('open_finance_recovery_'):
        # The existing UI owner credential is the administrator; never expose
        # this capability to scheduled jobs, external clients or MCP.
        if identity.role!='UI' or identity.client_id!='UI:local':raise SyncError('FORBIDDEN',403)
        if query:raise SyncError('INVALID_REQUEST',422)
        recovery=app.santander_binding_recovery
        actor=(identity.role,identity.client_id,identity.csrf)
        if operation=='open_finance_recovery_inspect':
            if body:raise SyncError('INVALID_REQUEST',422)
            return recovery.inspect(),200
        if operation=='open_finance_recovery_prepare':
            if set(body)-{'action','backup_confirmed','operation'} or not {'action','backup_confirmed'}<=set(body):raise SyncError('INVALID_REQUEST',422)
            if not isinstance(body['action'],str) or body['action'] not in {'APPLY','REVERT','RECONCILE'} or body['action']!='REVERT' and 'operation' in body:raise SyncError('INVALID_REQUEST',422)
            return recovery.prepare(actor,body['action'],body['backup_confirmed'],body.get('operation')),200
        if operation=='open_finance_recovery_confirm':
            if set(body)!={'confirmation','explicit_confirmation','backup_confirmed'}:raise SyncError('INVALID_REQUEST',422)
            return recovery.execute(actor,body['confirmation'],body['explicit_confirmation'],body['backup_confirmed']),200
        raise SyncError('NOT_FOUND',404)
    payload,status=_dispatch_raw(app,operation,identity,body,query)
    from .open_finance_presentation import present_payload
    from .open_finance_output_privacy import public_payload
    with closing(app.db()) as c:
        payload=present_payload(c,app.settings,payload,operation)
        return public_payload(payload,app.settings,db=c),status


def _connection_id(value):
    return isinstance(value,str) and re.fullmatch(r'[a-z][a-z0-9-]{1,63}',value) is not None


def _dispatch_raw(app,operation,identity,body,query):
    if identity.role!='UI' or identity.client_id!='UI:local':raise SyncError('FORBIDDEN',403)
    service=OpenFinanceService(app.settings,app.clock)
    op=operation.removeprefix('open_finance_')
    if op=='domain_sync':
        if query or set(body)!={'connection_id','mode'} or not isinstance(body.get('connection_id'),str) or not re.fullmatch(r'[a-z][a-z0-9-]{1,63}',body['connection_id']) or not isinstance(body.get('mode'),str) or body['mode'] not in {'FULL','INCREMENTAL','RESUME'}:
            raise SyncError('INVALID_REQUEST',422)
        run=sync_domain(service,body['connection_id'],actor=identity.client_id,mode=body['mode'])
        return {'run':run},200 if run['state']=='SUCCEEDED' else 502
    if op in {'domain','relations'}:
        if body:raise SyncError('GET_BODY_NOT_ALLOWED',422)
        with closing(app.db()) as c:
            return (query_domain(c,app.settings,query) if op=='domain' else query_relations(c,app.settings,query)),200
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
        if op=='analytics':
            from .open_finance_analytics import analytics
            return analytics(c,app.settings,query),200
        if op=='catalogs':
            if query:raise SyncError('INVALID_QUERY',422)
            return catalogs(c,connection_views(c,app.settings).values()),200
        if op=='transactions' and 'contract' in query:
            return query_transactions(c,query,connection_views(c,app.settings).values(),
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
            if 'connection_id' in query:
                connection_id = query['connection_id'][0]
                if connection_id not in service.config and not c.execute(
                    "SELECT 1 FROM of_connection_registry WHERE connection_id=? AND lifecycle<>'REMOVED'",
                    (connection_id,),
                ).fetchone():
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
    from .open_finance_presentation import presentation_schema
    run['properties']['operational_presentation']=presentation_schema()
    bank_connection['properties']['presentation_profile']={'type':'string','enum':['meupluggy_personal']}
    bank_account=obj({'connection_id':text,'external_id':text,**{k:nullable for k in ('name','type','subtype','currency','provider_updated_at')}})
    bank_category=obj({'connection_id':text,'category_key':text,'provider':enum('PLUGGY'),
        **{k:nullable for k in ('external_id','original_name','display_name_pt')},
        'translation_status':enum('UNVERIFIED','VERIFIED','OWNER_OVERRIDE'),'updated_at':text})
    result={}
    for method,path,op in OPERATIONS:
        if op.startswith('registry_'):
            if op=='registry_create':
                fields={name:{'type':'string','minLength':1,'maxLength':maximum}
                        for name,maximum in (('label',200),('client_id',512),('client_secret',512),('item_id',200))}
                for name in ('client_id','client_secret','item_id'):
                    fields[name]['writeOnly']=True
                fields['environment']=enum('PERSONAL','SANDBOX','STRICT')
                required=list(fields)
                fields['replaces_id']=text
            else:
                fields={'connection_id':text,'revision':{'type':'integer','minimum':0}}
                if op=='registry_rename':
                    fields['label']={'type':'string','minLength':1,'maxLength':200}
                elif op=='registry_delete':
                    fields['backup_confirmed']={'type':'boolean','const':True}
                    fields['confirmation']=enum('EXCLUIR DEFINITIVAMENTE')
                elif op not in {'registry_archive_inspect','registry_delete_inspect','registry_details','registry_connector_catalog'}:
                    fields['confirmed']={'type':'boolean','const':True}
                if op=='registry_rotate_credentials':
                    fields.update({name:{'type':'string','minLength':1,'maxLength':512,'writeOnly':True}
                                   for name in ('client_id','client_secret')})
                required=list(fields)
                if op=='registry_activate':
                    fields['connector_id']={'type':'integer','minimum':1,'maximum':2**31-1}
            spec={'operationId':'open_finance_'+op,'x-owner-only':True,'x-owner-admin-only':True,
                  'x-external-capability':'not-available',
                  'description':'Private owner browser session only. Exact configured origin and CSRF required.',
                  'parameters':[{'name':'X-CSRF-Token','in':'header','required':True,'schema':text}],
                  'requestBody':{'required':True,'content':{'application/json':{'schema':{
                      'type':'object','additionalProperties':False,'properties':fields,'required':required}}}},
                  'responses':{str(status):{'description':'Sanitized registry result' if status in (200,201)
                                            else 'Sanitized error'}
                               for status in (200,201,401,403,404,409,413,415,422,429,502,503)}}
            result[PREFIX+path]={method.lower():spec};continue
        if op.startswith('recovery_'):
            properties={'action':enum('APPLY','REVERT','RECONCILE'),'backup_confirmed':{'type':'boolean','const':True},'operation':{'type':'string','pattern':'^[0-9a-f]{32}$'}} if op=='recovery_prepare' else {'confirmation':{'type':'string','pattern':'^[0-9a-f]{64}$'},'explicit_confirmation':enum('CORRIGIR_BINDING_SANTANDER','REVERTER_BINDING_SANTANDER','RECONCILIAR_AUDITORIA_SANTANDER'),'backup_confirmed':{'type':'boolean','const':True}}
            spec={'operationId':'open_finance_'+op,'security':[{'bearerAuth':[]}],'x-owner-only':True,'x-owner-admin-only':True,'x-external-capability':'not-available','description':'Explicit Santander-only maintenance. Uses live application Settings. No provider calls. Cookie POST requires CSRF. Backup is owner-attested; no generic SQL.'}
            if method=='POST':spec['requestBody']={'required':True,'content':{'application/json':{'schema':{'type':'object','additionalProperties':False,'properties':properties,'required':['action','backup_confirmed'] if op=='recovery_prepare' else list(properties)}}}}
            spec['responses']={str(s):{'description':'Sanitized recovery result' if s==200 else 'Sanitized error'} for s in (200,401,403,409,413,415,422,429,503)}
            result[PREFIX+path]={method.lower():spec};continue
        if op in {'resources','coverage','coverage_sync','domain','relations','domain_sync'}:continue
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
        elif op=='analytics':
            from .open_finance_analytics import PARAMS
            parameters=[{'name':name,'in':'query','required':False,'schema':text} for name in sorted(PARAMS)]
            schema={'type':'object','required':['contract','filters','positions','flow','series','categories','items','total','page','has_more','coverage'],
                    'properties':{'contract':{'type':'string','enum':['OF-ANALYTICS/1']},
                    **{name:{'type':'object'} for name in ('filters','positions','flow')},
                    **{name:{'type':'array','items':{'type':'object'}} for name in ('series','categories','items','coverage')},
                    'total':integer,'page':integer,'has_more':{'type':'boolean'}}}
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
                'staged_account_count':{'type':'integer','minimum':0},
                'observed_resources':{'type':'array','items':text},
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
    coverage_response['properties']['runs']['items']['properties']['operational_presentation']=presentation_schema()
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
    result.update(domain_paths())
    return result
