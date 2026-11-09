-- Additive external-domain metadata. No official financial tables are changed.
CREATE TABLE of_resource_links (
    connection_id TEXT NOT NULL,
    source_resource TEXT NOT NULL CHECK(source_resource='transactions'),
    source_parent_id TEXT NOT NULL,
    source_external_id TEXT NOT NULL,
    kind TEXT NOT NULL CHECK(kind='TRANSACTION_BILL'),
    referenced_external_id TEXT,
    target_resource TEXT NOT NULL DEFAULT 'bills' CHECK(target_resource='bills'),
    target_parent_id TEXT NOT NULL,
    target_external_id TEXT,
    state TEXT NOT NULL CHECK(state IN ('MATCHED','MISSING_REFERENCE','UNRESOLVED')),
    run_id TEXT NOT NULL,
    observed_at TEXT NOT NULL,
    PRIMARY KEY(connection_id,source_resource,source_parent_id,source_external_id,kind),
    CHECK(target_parent_id=source_parent_id),
    CHECK((state='MATCHED' AND target_external_id IS NOT NULL AND referenced_external_id IS NOT NULL AND target_external_id=referenced_external_id)
       OR (state='MISSING_REFERENCE' AND target_external_id IS NULL AND referenced_external_id IS NULL)
       OR (state='UNRESOLVED' AND target_external_id IS NULL AND referenced_external_id IS NOT NULL)),
    FOREIGN KEY(connection_id,source_resource,source_parent_id,source_external_id)
      REFERENCES of_resource_records(connection_id,resource,parent_id,external_id),
    FOREIGN KEY(connection_id,target_resource,target_parent_id,target_external_id)
      REFERENCES of_resource_records(connection_id,resource,parent_id,external_id),
    FOREIGN KEY(run_id,connection_id) REFERENCES of_sync_runs(id,connection_id)
);
CREATE TABLE of_resource_link_revisions (
    id INTEGER PRIMARY KEY,
    connection_id TEXT NOT NULL,
    source_resource TEXT NOT NULL,
    source_parent_id TEXT NOT NULL,
    source_external_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    state TEXT NOT NULL CHECK(state IN ('MATCHED','MISSING_REFERENCE','UNRESOLVED')),
    referenced_external_id TEXT,
    target_external_id TEXT,
    run_id TEXT NOT NULL,
    observed_at TEXT NOT NULL,
    FOREIGN KEY(connection_id,source_resource,source_parent_id,source_external_id,kind)
      REFERENCES of_resource_links(connection_id,source_resource,source_parent_id,source_external_id,kind),
    FOREIGN KEY(run_id,connection_id) REFERENCES of_sync_runs(id,connection_id)
);
CREATE TABLE of_collection_checkpoints (
    connection_id TEXT NOT NULL REFERENCES of_connections(id),
    resource TEXT NOT NULL CHECK(resource IN ('item','resources','consents','accounts','transactions','investments','investment_transactions','loans','bills','statements')),
    parent_id TEXT NOT NULL,
    parent_resource TEXT GENERATED ALWAYS AS (CASE resource WHEN 'transactions' THEN 'accounts' WHEN 'bills' THEN 'accounts' WHEN 'statements' THEN 'accounts' WHEN 'investment_transactions' THEN 'investments' END) VIRTUAL,
    parent_parent_id TEXT GENERATED ALWAYS AS ('') VIRTUAL,
    run_id TEXT NOT NULL,
    last_complete_run_id TEXT,
    state TEXT NOT NULL CHECK(state IN ('RUNNING','COMPLETE','EMPTY','NOT_AVAILABLE','NOT_AUTHORIZED','NOT_COLLECTED','FAILED','INTERRUPTED')),
    page_count INTEGER NOT NULL DEFAULT 0 CHECK(page_count>=0),
    record_count INTEGER NOT NULL DEFAULT 0 CHECK(record_count>=0),
    last_complete_page_count INTEGER NOT NULL DEFAULT 0 CHECK(last_complete_page_count>=0),
    last_complete_record_count INTEGER NOT NULL DEFAULT 0 CHECK(last_complete_record_count>=0),
    contract_sha256 TEXT NOT NULL CHECK(length(contract_sha256)=64),
    error_code TEXT,
    observed_at TEXT NOT NULL,
    PRIMARY KEY(connection_id,resource,parent_id),
    FOREIGN KEY(run_id,connection_id) REFERENCES of_sync_runs(id,connection_id),
    FOREIGN KEY(last_complete_run_id,connection_id) REFERENCES of_sync_runs(id,connection_id),
    FOREIGN KEY(connection_id,parent_resource,parent_parent_id,parent_id)
      REFERENCES of_resource_records(connection_id,resource,parent_id,external_id)
);
CREATE TABLE of_domain_sync_audit (
    run_id TEXT PRIMARY KEY,
    connection_id TEXT NOT NULL,
    mode TEXT NOT NULL CHECK(mode IN ('FULL','INCREMENTAL','RESUME')),
    resumed_from_run_id TEXT,
    strategy TEXT NOT NULL CHECK(strategy='BOUNDED_FULL_RECONCILIATION'),
    created_at TEXT NOT NULL,
    FOREIGN KEY(run_id,connection_id) REFERENCES of_sync_runs(id,connection_id),
    FOREIGN KEY(resumed_from_run_id,connection_id) REFERENCES of_sync_runs(id,connection_id)
);
CREATE INDEX of_links_target ON of_resource_links(connection_id,target_resource,target_parent_id,target_external_id);
CREATE INDEX of_link_revisions_source ON of_resource_link_revisions(connection_id,source_parent_id,source_external_id,id);
CREATE INDEX of_checkpoints_state ON of_collection_checkpoints(connection_id,state,resource,parent_id);
