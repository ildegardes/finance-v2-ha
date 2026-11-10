"""Schema-11 guards reused from the isolated recovery qualification. No database I/O on import."""

import sqlite3,re

TABLES=('of_connections', 'of_sync_runs', 'of_accounts', 'of_categories', 'of_transactions', 'of_transaction_revisions', 'of_resource_records', 'of_resource_revisions', 'of_resource_coverage', 'of_resource_links', 'of_resource_link_revisions', 'of_collection_checkpoints', 'of_domain_sync_audit')

class Blocked(Exception): pass

def require(ok,code):
    if not ok:raise Blocked(code)

def authorizer(action,a,b,db,origin):
    if action in (sqlite3.SQLITE_SELECT,sqlite3.SQLITE_READ):return sqlite3.SQLITE_OK
    if action==sqlite3.SQLITE_FUNCTION:return sqlite3.SQLITE_DENY if (b or '').lower()=='load_extension' else sqlite3.SQLITE_OK
    if action==sqlite3.SQLITE_TRANSACTION:return sqlite3.SQLITE_OK if a in ('BEGIN','ROLLBACK') else sqlite3.SQLITE_DENY
    if action==sqlite3.SQLITE_PRAGMA and (a or '').lower() in ('user_version','table_xinfo','foreign_key_list','foreign_key_check','integrity_check','index_list','index_xinfo'):
        if (a or '').lower()=='user_version' and b is not None:return sqlite3.SQLITE_DENY
        return sqlite3.SQLITE_OK
    return sqlite3.SQLITE_DENY

def schema_check(c,expected):
    require(c.execute('PRAGMA user_version').fetchone()[0]==11,'SCHEMA_NOT_11')
    all_tables={r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    of_tables={n for n in all_tables if n.startswith('of_')}
    require(of_tables==set(TABLES),'UNEXPECTED_OPEN_FINANCE_SCHEMA')
    for n in TABLES:
        actual={'columns':[list(r) for r in c.execute('PRAGMA table_xinfo("'+n+'")')],'fks':[list(r) for r in c.execute('PRAGMA foreign_key_list("'+n+'")')]}
        actual['ddl']=re.sub(r'\s+',' ',c.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name=?",(n,)).fetchone()[0].strip())
        actual['indexes']=[list(r) for r in c.execute("SELECT name,sql FROM sqlite_master WHERE type='index' AND tbl_name=? ORDER BY name",(n,))]
        # SQLite 3.35 reports TEXT GENERATED ALWAYS for these virtual generated
        # columns; 3.40 reports TEXT. DDL, generated flag, expressions, FKs and
        # indexes still must match EXACTLY. Normalize only this observed spelling.
        def normalize_columns(columns):
            rows=[list(row) for row in columns]
            for row in rows:
                if row[6]==2 and row[2]=='TEXT GENERATED ALWAYS':row[2]='TEXT'
            return rows
        comparable=dict(expected[n])
        comparable['columns']=normalize_columns(comparable['columns'])
        actual['columns']=normalize_columns(actual['columns'])
        require(actual==comparable,'UNEXPECTED_OPEN_FINANCE_SCHEMA')
    require(c.execute("SELECT count(*) FROM sqlite_master WHERE type='trigger' AND tbl_name IN ("+','.join('?' for _ in TABLES)+')',TABLES).fetchone()[0]==0,'UNEXPECTED_OPEN_FINANCE_TRIGGER')
    inbound=0
    for name in all_tables-set(TABLES):
        for fk in c.execute('PRAGMA foreign_key_list("'+name.replace('"','""')+'")'):
            inbound+=fk[2] in TABLES
    require(inbound==0,'UNEXPECTED_EXTERNAL_DEPENDENCY')


import time
RESOURCES=('item', 'resources', 'consents', 'accounts', 'transactions', 'bills', 'statements', 'investments', 'investment_transactions', 'loans')
FINANCIAL=set(RESOURCES)-{'item','resources','consents'}

def dependencies(c,bank):
    out={'COUNTS':{},'INDIRECT_RUN_REFERENCES':{},'CROSS_CONNECTION_RUN_REFERENCES':{},'RESOURCE_COUNTS':{}}
    for table in TABLES:
        key='id' if table=='of_connections' else 'connection_id'
        out['COUNTS'][table]=c.execute('SELECT count(*) FROM '+table+' WHERE '+key+'=?',(bank,)).fetchone()[0]
        if table=='of_connections':continue
        cols={r[1] for r in c.execute('PRAGMA table_xinfo("'+table+'")')}
        refs=[n for n in ('run_id','first_run_id','last_run_id','last_complete_run_id','resumed_from_run_id') if n in cols]
        if refs:
            predicate='EXISTS(SELECT 1 FROM of_sync_runs r WHERE r.connection_id=? AND ('+' OR '.join('r.id=t.'+n for n in refs)+'))'
            out['INDIRECT_RUN_REFERENCES'][table]=c.execute('SELECT count(*) FROM '+table+' t WHERE '+predicate,(bank,)).fetchone()[0]
            out['CROSS_CONNECTION_RUN_REFERENCES'][table]=c.execute('SELECT count(*) FROM '+table+' t WHERE t.connection_id<>? AND '+predicate,(bank,bank)).fetchone()[0]
    out['CROSS_CONNECTION_TRANSACTION_REFERENCES']=c.execute('SELECT count(*) FROM of_transaction_revisions v JOIN of_transactions t ON t.id=v.transaction_id WHERE t.connection_id=? AND v.connection_id<>?',(bank,bank)).fetchone()[0]
    for table in ('of_resource_records','of_resource_revisions'):
        out['RESOURCE_COUNTS'][table]={resource:c.execute('SELECT count(*) FROM '+table+' WHERE connection_id=? AND resource=?',(bank,resource)).fetchone()[0] for resource in RESOURCES}
    out['RUN_COUNTS']={state:c.execute('SELECT count(*) FROM of_sync_runs WHERE connection_id=? AND state=?',(bank,state)).fetchone()[0] for state in ('RUNNING','SUCCEEDED','FAILED','INTERRUPTED')}
    out['AUTH_FAILED_RUNS']=c.execute("SELECT count(*) FROM of_sync_runs WHERE connection_id=? AND error_code='AUTH_FAILED'",(bank,)).fetchone()[0]
    out['FOREIGN_KEY_VIOLATIONS']=sum(1 for _ in c.execute('PRAGMA foreign_key_check'))
    # Messages may contain private cells; retain only a boolean, not their text.
    rows=c.execute('PRAGMA integrity_check').fetchall()
    out['SQLITE_INTEGRITY_OK']=len(rows)==1 and rows[0][0]=='ok'
    financial=any(out['COUNTS'][t] for t in ('of_accounts','of_categories','of_transactions','of_transaction_revisions','of_resource_links','of_resource_link_revisions')) or any(out['RESOURCE_COUNTS'][t][r] for t in out['RESOURCE_COUNTS'] for r in FINANCIAL)
    indirect=any(out['INDIRECT_RUN_REFERENCES'].values())
    cross=any(out['CROSS_CONNECTION_RUN_REFERENCES'].values()) or out['CROSS_CONNECTION_TRANSACTION_REFERENCES']>0
    if out['FOREIGN_KEY_VIOLATIONS'] or cross or not out['SQLITE_INTEGRITY_OK']:
        risk='BLOCKED_INTEGRITY_OR_CROSS_CONNECTION';state='UNKNOWN'
    elif financial:
        risk='FINANCIAL_DEPENDENCIES_PRESENT';state='PRESENT'
    elif any(n for t,n in out['COUNTS'].items() if t!='of_connections') or indirect:
        risk='HISTORY_OR_METADATA_MUST_BE_PRESERVED';state='NO_FINANCIAL_ROWS_WITH_HISTORY'
    else:
        risk='IDENTITY_REVIEW_STILL_REQUIRED';state='NO_ASSOCIATED_DEPENDENTS'
    out.update(DEPENDENCIES=state,RISK=risk,CHECKS_COMPLETE=True)
    return out
