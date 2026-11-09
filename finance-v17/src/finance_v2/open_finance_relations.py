"""External staging relationships/checkpoints; caller owns the fenced SQL transaction."""
import json
from .open_finance import SyncError
from .pluggy_coverage import CONTRACT_SHA256, RESOURCES


def _transaction(c):
    if not c.in_transaction:raise SyncError('STORAGE_TRANSACTION_REQUIRED',503)


def begin_collection(c,connection,resource,parent,run_id,stamp,*,reset_coverage=True):
    _transaction(c)
    if resource not in RESOURCES:raise SyncError('INVALID_RESOURCE',422)
    c.execute("INSERT INTO of_collection_checkpoints(connection_id,resource,parent_id,run_id,state,contract_sha256,observed_at) "
        "VALUES(?,?,?,?,'RUNNING',?,?) ON CONFLICT(connection_id,resource,parent_id) DO UPDATE SET "
        "run_id=excluded.run_id,state='RUNNING',page_count=0,record_count=0,error_code=NULL,"
        "contract_sha256=excluded.contract_sha256,observed_at=excluded.observed_at",
        (connection,resource,parent,run_id,CONTRACT_SHA256,stamp))
    if not reset_coverage:return
    c.execute("INSERT INTO of_resource_coverage(connection_id,resource,parent_id,run_id,state,observed_at) "
        "VALUES(?,?,?,?,'RUNNING',?) ON CONFLICT(connection_id,resource,parent_id) DO UPDATE SET "
        "run_id=excluded.run_id,state='RUNNING',page_count=0,record_count=0,omitted_field_count=0,error_code=NULL,observed_at=excluded.observed_at",
        (connection,resource,parent,run_id,stamp))


def record_batch(c,connection,batch,run_id,stamp):
    _transaction(c)
    resource,parent=batch['resource'],batch['parent']
    # Custom synthetic/client adapters without an observer retain the same contract.
    if not c.execute('SELECT 1 FROM of_collection_checkpoints WHERE connection_id=? AND resource=? AND parent_id=? AND run_id=?',
        (connection,resource,parent,run_id)).fetchone():
        begin_collection(c,connection,resource,parent,run_id,stamp,reset_coverage=False)
    c.execute('UPDATE of_collection_checkpoints SET page_count=page_count+1,record_count=record_count+?,observed_at=? '
        'WHERE connection_id=? AND resource=? AND parent_id=? AND run_id=?',
        (len(batch['rows']),stamp,connection,resource,parent,run_id))
    if batch['last']:
        state=batch['state']
        if state=='AVAILABLE':
            row=c.execute('SELECT record_count FROM of_collection_checkpoints WHERE connection_id=? AND resource=? AND parent_id=?',
                (connection,resource,parent)).fetchone()
            state='COMPLETE' if row[0] else 'EMPTY'
        c.execute('UPDATE of_collection_checkpoints SET state=?,observed_at=? WHERE connection_id=? AND resource=? AND parent_id=? AND run_id=?',
            (state,stamp,connection,resource,parent,run_id))
        if state in ('COMPLETE','EMPTY'):
            c.execute('UPDATE of_collection_checkpoints SET last_complete_run_id=?,last_complete_page_count=page_count,last_complete_record_count=record_count '
                'WHERE connection_id=? AND resource=? AND parent_id=? AND run_id=?',
                (run_id,connection,resource,parent,run_id))


def fail_collection(c,connection,resource,parent,run_id,error,stamp,interrupted=False):
    _transaction(c)
    c.execute("UPDATE of_collection_checkpoints SET state=?,error_code=?,observed_at=? WHERE connection_id=? AND resource=? AND parent_id=? AND run_id=?",
        ('INTERRUPTED' if interrupted else 'FAILED',error,stamp,connection,resource,parent,run_id))
    c.execute("UPDATE of_resource_coverage SET state='FAILED',error_code=?,observed_at=? WHERE connection_id=? AND resource=? AND parent_id=? AND run_id=?",
        (error,stamp,connection,resource,parent,run_id))


def reconcile_bill_links(c,connection,run_id,stamp,parent=None):
    _transaction(c)
    condition=' AND t.parent_id=?' if parent is not None else ''
    rows=c.execute("SELECT t.* FROM of_resource_records t JOIN of_resource_records a ON "
        "a.connection_id=t.connection_id AND a.resource='accounts' AND a.parent_id='' AND a.external_id=t.parent_id "
        "WHERE t.connection_id=? AND t.resource='transactions' AND t.state='PRESENT' "
        "AND json_extract(a.payload_json,'$.type')='CREDIT'"+condition,
        (connection,parent) if parent is not None else (connection,)).fetchall()
    for row in rows:
        data=json.loads(row['payload_json']);meta=data.get('creditCardMetadata')
        if meta is not None and not isinstance(meta,dict):raise SyncError('INVALID_CARD_METADATA')
        reference=(meta or {}).get('billId')
        if reference is not None and (not isinstance(reference,str) or not reference or len(reference)>200):
            raise SyncError('INVALID_BILL_REFERENCE')
        target=None;state='MISSING_REFERENCE'
        if reference is not None:
            known=c.execute("SELECT parent_id FROM of_resource_records WHERE connection_id=? AND resource='bills' AND external_id=?",
                (connection,reference)).fetchall()
            if any(x[0]==row['parent_id'] for x in known):target=reference;state='MATCHED'
            elif known:raise SyncError('BILL_SCOPE_MISMATCH')
            else:state='UNRESOLVED'
        identity=(connection,'transactions',row['parent_id'],row['external_id'],'TRANSACTION_BILL')
        old=c.execute('SELECT state,referenced_external_id,target_external_id FROM of_resource_links WHERE '
            'connection_id=? AND source_resource=? AND source_parent_id=? AND source_external_id=? AND kind=?',identity).fetchone()
        c.execute('INSERT INTO of_resource_links(connection_id,source_resource,source_parent_id,source_external_id,kind,'
            'referenced_external_id,target_parent_id,target_external_id,state,run_id,observed_at) VALUES(?,?,?,?,?,?,?,?,?,?,?) '
            'ON CONFLICT(connection_id,source_resource,source_parent_id,source_external_id,kind) DO UPDATE SET '
            'referenced_external_id=excluded.referenced_external_id,target_external_id=excluded.target_external_id,state=excluded.state,'
            'run_id=excluded.run_id,observed_at=excluded.observed_at',identity+(reference,row['parent_id'],target,state,run_id,stamp))
        if old is None or tuple(old)!=(state,reference,target):
            c.execute('INSERT INTO of_resource_link_revisions(connection_id,source_resource,source_parent_id,source_external_id,kind,'
                'state,referenced_external_id,target_external_id,run_id,observed_at) VALUES(?,?,?,?,?,?,?,?,?,?)',
                identity+(state,reference,target,run_id,stamp))


def audit_mode(c,connection,run_id,mode,stamp):
    _transaction(c)
    previous=None
    if mode=='RESUME':
        row=c.execute("SELECT id FROM of_sync_runs WHERE connection_id=? AND id<>? AND state IN ('FAILED','INTERRUPTED') ORDER BY rowid DESC LIMIT 1",
            (connection,run_id)).fetchone()
        previous=row[0] if row else None
    c.execute('INSERT INTO of_domain_sync_audit(run_id,connection_id,mode,resumed_from_run_id,strategy,created_at) '
        "VALUES(?,?,?,?,'BOUNDED_FULL_RECONCILIATION',?)",(run_id,connection,mode,previous,stamp))
