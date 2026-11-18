"""Owner-authorized rule management and reversible classification operations."""
from collections import Counter
from contextlib import closing
from hashlib import sha256
import json
import sqlite3
from uuid import uuid4

from .open_finance import OpenFinanceService, SyncError
from .open_finance_classification import (
    Classifier, Facts, NATURES, PROVENTS, custom_decision, encode, invalid, matches,
    native_catalog, normalize, result_definition, rule_definition, string,
)
from .open_finance_query import civil, read_view
from .open_finance_registry import connection_views

MAX_RULES = 120
MAX_REVISIONS = 2500
MAX_MATCHES = 30000
NATIVES = {rule['id']:rule for rule in native_catalog()}


def _scope(raw):
    if not isinstance(raw, dict) or set(raw) != {'start','end','currency','history'} or type(raw['history']) is not bool:
        invalid()
    start, end, currency = (string(raw[key], maximum) for key,maximum in (('start',10),('end',10),('currency',3)))
    if len(start)!=10 or len(end)!=10 or not civil(start) or not civil(end) or start>end:
        invalid('INVALID_PERIOD')
    if len(currency)!=3 or not all('A' <= char <= 'Z' for char in currency):
        invalid()
    return raw


def _required(body, fields, optional=()):
    if not set(fields) <= body.keys() or body.keys() - set(fields) - set(optional):
        invalid()


def _identity(raw):
    if not isinstance(raw, dict):
        invalid()
    keys = ('connection_id','account_id','transaction_id')
    _required(raw, keys)
    return tuple(string(raw[key], 200 if key != 'connection_id' else 64) for key in keys)


def _revision(value, *, new=False):
    if type(value) is not int or not (0 if new else 1) <= value < 2**31:
        invalid()
    return value


def _current_rule(db,id):
    row = db.execute("""SELECT v.* FROM of_classification_rules r
        JOIN of_classification_rule_revisions v ON v.rule_id=r.id AND v.revision=r.revision
        WHERE r.id=?""",(id,)).fetchone()
    return ({**json.loads(row['definition_json']),'id':id,'revision':row['revision'],
             'updated_at':row['recorded_at']} if row else None)


def _scope_rule(db,settings,rule,history=False):
    cond = rule['conditions']
    cid = cond['connection_id']
    view = connection_views(db,settings).get(cid)
    if not view or (not history and (view.historical or not view.enabled)):
        raise SyncError('CLASSIFICATION_SCOPE_UNAVAILABLE',409)
    if cond.get('account_id') and not db.execute("""SELECT 1 FROM of_resource_records
        WHERE connection_id=? AND resource='accounts' AND parent_id='' AND external_id=?""",
        (cid,cond['account_id'])).fetchone():
        raise SyncError('RESOURCE_NOT_FOUND',404)
    return view


def _append(db,key,action,stamp,actor,decision,previous,previous_json,*,effective=None,batch=None,reverses=None):
    return db.execute("""INSERT INTO of_classification_events
        (connection_id,account_id,transaction_id,action,recorded_at,actor,decision_json,previous_event,previous_json,previous_effective_json,batch_id,reverses_event)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
        (*key,action,stamp,actor,decision,previous,previous_json,effective,batch,reverses)).lastrowid


def _last(db,key):
    row = db.execute("""SELECT id,decision_json FROM of_classification_events
        WHERE connection_id=? AND account_id=? AND transaction_id=? ORDER BY id DESC LIMIT 1""",key).fetchone()
    return (row['id'],row['decision_json']) if row else (None,None)


def _category_key(data,cid):
    from .open_finance_analytics import _category
    return _category(data,cid)['key']


class ClassificationAdmin:
    def __init__(self, service):
        self.service = service

    def dispatch(self, action, body, query, actor):
        if query and (action not in ('audit',) or set(query) != {'before'}):
            invalid()
        if action in ('catalog','audit','preview'):
            with closing(self.service._db()) as db, read_view(db):
                if action=='catalog':
                    _required(body,())
                    return self.catalog(db)
                if action=='audit':
                    _required(body,())
                    raw = query.get('before',['9223372036854775807'])[0]
                    if not raw.isascii() or not raw.isdecimal() or len(raw)>19 or int(raw)>2**63-1:
                        invalid()
                    return self.audit(db,int(raw))
                return self.preview(db,body)
        with closing(self.service._db()) as db, self.service._write(db):
            _, stamp = self.service._time()
            if action=='rule':
                return self.save_rule(db,body,actor,stamp)
            if action=='manual':
                return self.manual(db,body,actor,stamp)
            if action=='apply':
                return self.apply(db,body,actor,stamp)
            if action=='undo':
                return self.undo(db,body,actor,stamp)
        raise SyncError('NOT_FOUND',404)

    def catalog(self,db):
        rules = [_current_rule(db,row['id']) for row in db.execute("SELECT id FROM of_classification_rules ORDER BY id")]
        switches = {rule['native_id']:rule for rule in rules if 'native_id' in rule}
        native = [{**rule,'enabled':switches.get(id,{}).get('enabled',True),
                   'switch_revision':switches.get(id,{}).get('revision',0)} for id,rule in NATIVES.items()]
        return {'natures':NATURES,'provents':PROVENTS,'native':native,
                'rules':[rule for rule in rules if 'native_id' not in rule],
                'finance_categories':[row[0] for row in db.execute('SELECT name FROM categories WHERE active=1 ORDER BY name LIMIT 200')]}

    def save_rule(self,db,body,actor,stamp):
        _required(body,('revision','rule'),('id','history'))
        expected = _revision(body['revision'],new=True)
        id = string(body['id'],80) if 'id' in body else uuid4().hex
        if id.startswith('native:'):
            native_id = id.split(':',1)[1]
            if native_id not in NATIVES or not isinstance(body['rule'],dict) or set(body['rule']) != {'enabled'} or type(body['rule']['enabled']) is not bool:
                invalid()
            definition = {'native_id':native_id,'enabled':body['rule']['enabled']}
        else:
            definition = rule_definition(body['rule'])
            history=body.get('history',False)
            if type(history) is not bool:
                invalid()
            _scope_rule(db,self.service.settings,definition,history)
        current = _current_rule(db,id)
        actual = current['revision'] if current else 0
        if expected!=actual or (not current and 'id' in body and not id.startswith('native:')):
            raise SyncError('CLASSIFICATION_STALE',409)
        if (not current and db.execute("SELECT count(*) FROM of_classification_rules").fetchone()[0]>=MAX_RULES
            or db.execute("SELECT count(*) FROM of_classification_rule_revisions").fetchone()[0]>=MAX_REVISIONS):
            raise SyncError('CLASSIFICATION_LIMIT',409)
        revision = actual+1
        db.execute("""INSERT INTO of_classification_rules(id,revision) VALUES (?,?)
            ON CONFLICT(id) DO UPDATE SET revision=excluded.revision""",(id,revision))
        cutoff = db.execute("SELECT coalesce(max(sequence),0) FROM of_classification_import_order").fetchone()[0]
        db.execute("""INSERT INTO of_classification_rule_revisions(rule_id,revision,after_run,recorded_at,actor,definition_json)
                       VALUES (?,?,?,?,?,?)""",(id,revision,cutoff,stamp,actor,encode(definition)))
        return {'id':id,'revision':revision}

    def manual(self,db,body,actor,stamp):
        _required(body,('identity','event','decision'))
        key = _identity(body['identity'])
        if body['event'] is not None and (type(body['event']) is not int or not 0<body['event']<2**63):
            invalid()
        view = connection_views(db,self.service.settings).get(key[0])
        record = db.execute("""SELECT t.connection_id,t.parent_id,t.external_id,t.payload_json,
                coalesce(s.sequence,0) AS first_sequence,json_extract(a.payload_json,'$.type') AS product
            FROM of_resource_records t JOIN of_resource_records a
                ON a.connection_id=t.connection_id AND a.resource='accounts' AND a.parent_id='' AND a.external_id=t.parent_id
            LEFT JOIN of_classification_import_order s ON s.run_id=t.first_run_id
            WHERE t.connection_id=? AND t.resource='transactions' AND t.parent_id=? AND t.external_id=? AND t.state='PRESENT'""",key).fetchone()
        if view is None or record is None:
            raise SyncError('RESOURCE_NOT_FOUND',404)
        previous, raw = _last(db,key)
        if previous!=body['event']:
            raise SyncError('CLASSIFICATION_STALE',409)
        decision = encode({**result_definition(body['decision']),'origin':'MANUAL','review':'CONFIRMED'})
        if decision==raw:
            return {'event':previous}
        row = {**dict(record),'data':json.loads(record['payload_json'])}
        category = _category_key(row['data'],key[0])
        estimate = Classifier(db,{key[0]}).classify(Facts.from_row(row,view.institution,row['product'],category),category)
        return {'event':_append(db,key,'MANUAL',stamp,actor,decision,previous,raw,effective=encode(estimate))}

    def _plan(self,db,body):
        _required(body,('id','revision','scope'))
        id = string(body['id'],80)
        revision = _revision(body['revision'])
        scope = _scope(body['scope'])
        rule = _current_rule(db,id)
        if not rule or 'native_id' in rule or not rule['enabled'] or revision!=rule['revision']:
            raise SyncError('CLASSIFICATION_STALE',409)
        view = _scope_rule(db,self.service.settings,rule,scope['history'])
        cid = view.id
        condition = rule['conditions']
        if condition.get('currency') and condition['currency']!=scope['currency']:
            invalid()
        classifier = Classifier(db,{cid})
        latest = [_current_rule(db,row['id']) for row in db.execute(
            "SELECT id FROM of_classification_rules WHERE id<>? AND id NOT LIKE 'native:%' ORDER BY id",(id,))]
        competitors = [(r,normalize(r['conditions']['description'])) for r in latest if r['enabled'] and
                       r['conditions']['connection_id']==cid and r['priority']>=rule['priority']]
        query = """SELECT t.connection_id,t.parent_id,t.external_id,t.payload_json,t.payload_hash,
                    coalesce(s.sequence,0) AS first_sequence,json_extract(a.payload_json,'$.type') AS product
            FROM of_resource_records t JOIN of_resource_records a
                ON a.connection_id=t.connection_id AND a.resource='accounts' AND a.parent_id='' AND a.external_id=t.parent_id
            LEFT JOIN of_classification_import_order s ON s.run_id=t.first_run_id
            WHERE t.connection_id=? AND t.resource='transactions' AND t.state='PRESENT'
              AND json_extract(t.payload_json,'$.currencyCode')=?
              AND substr(json_extract(t.payload_json,'$.date'),1,10) BETWEEN ? AND ?
            ORDER BY t.parent_id,t.external_id LIMIT ?"""
        snapshots = db.execute(query,(cid,scope['currency'],scope['start'],scope['end'],MAX_MATCHES+1)).fetchall()
        if len(snapshots)>MAX_MATCHES:
            raise SyncError('CLASSIFICATION_LIMIT',409)
        signature = sha256(encode([id,revision,scope,latest]).encode())
        plan = []
        counts = Counter()
        categories = Counter()
        natures = Counter()
        samples = {state:[] for state in ('apply','manual','conflict','unchanged')}
        target = custom_decision(id,revision,rule)
        encoded_target = encode(target)
        normalized = normalize(condition['description'])
        for snapshot in snapshots:
            row = {**dict(snapshot),'data':json.loads(snapshot['payload_json'])}
            data = row['data']
            day = civil(data.get('date'))
            if day is None:
                continue
            category = _category_key(data,cid)
            facts = Facts.from_row(row,view.institution,row['product'],category)
            if not matches(condition,facts,normalized):
                continue
            classification = classifier.classify(facts,category)
            previous, raw = classifier.overrides.get(facts.key,(None,None))
            counts['matched']+=1
            categories[classification['category'] or data.get('category') or 'Sem categoria']+=1
            natures[classification['nature']]+=1
            proposed = [r for r,term in competitors if matches(r['conditions'],facts,term)
                        and (r['priority']>rule['priority'] or r['result']!=rule['result'])]
            if classification['origin']=='MANUAL':
                state = 'manual'
            elif proposed or (classification['origin']=='CUSTOM' and classification.get('priority',-1)>rule['priority']):
                state = 'conflict'
            elif raw==encoded_target:
                state = 'unchanged'
            else:
                state = 'apply'
                plan.append((facts.key,previous,raw,encode(classification)))
            counts[state]+=1
            signature.update(encode([facts.key,snapshot['payload_hash'],previous,state,classification]).encode())
            if len(samples[state])<4:
                samples[state].append({'description':facts.description,'date':day,'category':classification['category'] or data.get('category'),
                               'nature':classification['nature'],'state':state})
        preview = {'digest':signature.hexdigest(),'counts':dict(counts),'categories':dict(categories),
                   'natures':dict(natures),'sample':[row for rows in samples.values() for row in rows],'target':target,'institution':view.institution,'scope':scope}
        return preview,plan,encoded_target

    def preview(self,db,body):
        preview,_,_ = self._plan(db,body)
        return preview

    def apply(self,db,body,actor,stamp):
        _required(body,('id','revision','scope','digest','confirmed'))
        digest = string(body['digest'],64)
        if body['confirmed'] is not True:
            invalid('CLASSIFICATION_CONFIRMATION_REQUIRED')
        request = {key:body[key] for key in ('id','revision','scope')}
        already = db.execute("SELECT * FROM of_classification_batches WHERE preview_digest=?",(digest,)).fetchone()
        if already:
            if (already['rule_id'],already['rule_revision'],already['scope_json']) != (
                request['id'],request['revision'],encode(request['scope'])
            ):
                raise SyncError('CLASSIFICATION_STALE',409)
            return {'id':already['id'],'replayed':True}
        preview,plan,decision = self._plan(db,request)
        if preview['digest']!=digest:
            raise SyncError('CLASSIFICATION_STALE',409)
        batch = uuid4().hex
        db.execute("""INSERT INTO of_classification_batches(id,preview_digest,rule_id,rule_revision,created_at,actor,scope_json)
            VALUES (?,?,?,?,?,?,?)""",(batch,digest,request['id'],request['revision'],stamp,actor,encode(request['scope'])))
        for key,previous,previous_json,effective in plan:
            _append(db,key,'BATCH',stamp,actor,decision,previous,previous_json,effective=effective,batch=batch)
        return {'id':batch,'applied':len(plan),'replayed':False}

    def undo(self,db,body,actor,stamp):
        _required(body,('id','confirmed'))
        id = string(body['id'],40)
        if body['confirmed'] is not True:
            invalid('CLASSIFICATION_CONFIRMATION_REQUIRED')
        if not db.execute("SELECT 1 FROM of_classification_batches WHERE id=?",(id,)).fetchone():
            raise SyncError('RESOURCE_NOT_FOUND',404)
        counts = Counter()
        events = db.execute("""SELECT * FROM of_classification_events WHERE batch_id=? AND action='BATCH' ORDER BY id""",(id,)).fetchall()
        for event in events:
            key = tuple(event[field] for field in ('connection_id','account_id','transaction_id'))
            current, raw = _last(db,key)
            if current==event['id']:
                _append(db,key,'UNDO',stamp,actor,event['previous_json'],current,raw,batch=id,reverses=current)
                counts['restored']+=1
            elif db.execute("SELECT 1 FROM of_classification_events WHERE reverses_event=?",(event['id'],)).fetchone():
                counts['already_restored']+=1
            else:
                counts['conflicts']+=1
        return dict(counts)

    def audit(self,db,before):
        events = []
        for row in db.execute("""SELECT id,action,connection_id,batch_id,previous_event,reverses_event,coalesce(previous_effective_json,previous_json) AS previous_json,decision_json,recorded_at,actor
                                  FROM of_classification_events WHERE id<? ORDER BY id DESC LIMIT 50""",(before,)):
            event = dict(row)
            for key in ('decision','previous'):
                value = event.pop(key+'_json')
                event[key] = json.loads(value) if value else None
            events.append(event)
        batches = [{**dict(row),'scope':json.loads(row['scope_json'])} for row in db.execute(
            "SELECT id,rule_id,rule_revision,created_at,actor,scope_json FROM of_classification_batches ORDER BY rowid DESC LIMIT 50")]
        rules = [{**dict(row),'definition':json.loads(row['definition_json'])} for row in db.execute(
            "SELECT rule_id,revision,recorded_at,actor,definition_json FROM of_classification_rule_revisions ORDER BY rowid DESC LIMIT 50")]
        for row in batches+rules:
            row.pop('scope_json',None)
            row.pop('definition_json',None)
        return {'events':events,'batches':batches,'rules':rules,'before':events[-1]['id'] if len(events)==50 else None}


def dispatch(app,operation,identity,body,query):
    action = operation.removeprefix('classification_')
    if identity.role!='UI' or identity.client_id!='UI:local' or not identity.csrf:
        raise SyncError('FORBIDDEN',403)
    try:
        return ClassificationAdmin(OpenFinanceService(app.settings,app.clock)).dispatch(action,body,query,identity.client_id),200
    except sqlite3.Error:
        raise SyncError('CLASSIFICATION_STORAGE_UNAVAILABLE',503) from None
