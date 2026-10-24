-- Additive bank staging. No official financial table is read or changed.
CREATE TABLE of_resource_records (
    connection_id TEXT NOT NULL REFERENCES of_connections(id),
    resource TEXT NOT NULL CHECK(resource IN ('item','resources','consents','accounts','transactions','investments','investment_transactions','loans','bills','statements')),
    parent_id TEXT NOT NULL,
    parent_resource TEXT GENERATED ALWAYS AS (CASE resource WHEN 'transactions' THEN 'accounts' WHEN 'bills' THEN 'accounts' WHEN 'statements' THEN 'accounts' WHEN 'investment_transactions' THEN 'investments' END) VIRTUAL,
    parent_parent_id TEXT GENERATED ALWAYS AS ('') VIRTUAL,
    external_id TEXT NOT NULL CHECK(length(external_id) BETWEEN 1 AND 200),
    payload_json TEXT NOT NULL CHECK(json_valid(payload_json)),
    payload_hash TEXT NOT NULL CHECK(length(payload_hash)=64),
    state TEXT NOT NULL CHECK(state IN ('PRESENT','NOT_SEEN')),
    first_run_id TEXT NOT NULL,
    last_run_id TEXT NOT NULL,
    observed_at TEXT NOT NULL,
    PRIMARY KEY(connection_id,resource,parent_id,external_id),
    FOREIGN KEY(first_run_id,connection_id) REFERENCES of_sync_runs(id,connection_id),
    FOREIGN KEY(last_run_id,connection_id) REFERENCES of_sync_runs(id,connection_id),
    FOREIGN KEY(connection_id,parent_resource,parent_parent_id,parent_id) REFERENCES of_resource_records(connection_id,resource,parent_id,external_id)
);
CREATE TABLE of_resource_revisions (
    id INTEGER PRIMARY KEY,
    connection_id TEXT NOT NULL,
    resource TEXT NOT NULL,
    parent_id TEXT NOT NULL,
    external_id TEXT NOT NULL,
    run_id TEXT NOT NULL,
    observed_at TEXT NOT NULL,
    payload_json TEXT NOT NULL CHECK(json_valid(payload_json)),
    payload_hash TEXT NOT NULL CHECK(length(payload_hash)=64),
    state TEXT NOT NULL CHECK(state IN ('PRESENT','NOT_SEEN')),
    FOREIGN KEY(connection_id,resource,parent_id,external_id) REFERENCES of_resource_records(connection_id,resource,parent_id,external_id),
    FOREIGN KEY(run_id,connection_id) REFERENCES of_sync_runs(id,connection_id)
);
CREATE TABLE of_resource_coverage (
    connection_id TEXT NOT NULL REFERENCES of_connections(id),
    resource TEXT NOT NULL,
    parent_id TEXT NOT NULL,
    run_id TEXT NOT NULL,
    state TEXT NOT NULL CHECK(state IN ('RUNNING','AVAILABLE','EMPTY','NOT_AUTHORIZED','NOT_AVAILABLE','NOT_COLLECTED','FAILED')),
    page_count INTEGER NOT NULL DEFAULT 0 CHECK(page_count>=0),
    record_count INTEGER NOT NULL DEFAULT 0 CHECK(record_count>=0),
    omitted_field_count INTEGER NOT NULL DEFAULT 0 CHECK(omitted_field_count>=0),
    error_code TEXT,
    observed_at TEXT NOT NULL,
    PRIMARY KEY(connection_id,resource,parent_id),
    FOREIGN KEY(run_id,connection_id) REFERENCES of_sync_runs(id,connection_id)
);
CREATE INDEX of_resource_record_order ON of_resource_records(resource,connection_id,parent_id,external_id);
CREATE INDEX of_resource_revision_order ON of_resource_revisions(connection_id,resource,observed_at,id);
