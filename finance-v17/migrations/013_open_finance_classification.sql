-- Owner annotations over stable staging identities, with append-only revisions.
CREATE TABLE of_classification_rules (
    id TEXT PRIMARY KEY,
    revision INTEGER NOT NULL CHECK(revision > 0)
);

CREATE TABLE of_classification_rule_revisions (
    rule_id TEXT NOT NULL REFERENCES of_classification_rules(id),
    revision INTEGER NOT NULL CHECK(revision > 0),
    after_run INTEGER NOT NULL CHECK(after_run >= 0),
    recorded_at TEXT NOT NULL,
    actor TEXT NOT NULL,
    definition_json TEXT NOT NULL CHECK(json_valid(definition_json)),
    PRIMARY KEY(rule_id, revision)
);

CREATE TABLE of_classification_batches (
    id TEXT PRIMARY KEY,
    preview_digest TEXT NOT NULL UNIQUE CHECK(length(preview_digest) = 64),
    rule_id TEXT NOT NULL,
    rule_revision INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    actor TEXT NOT NULL,
    scope_json TEXT NOT NULL CHECK(json_valid(scope_json)),
    FOREIGN KEY(rule_id,rule_revision) REFERENCES of_classification_rule_revisions(rule_id,revision)
);

CREATE TABLE of_classification_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    connection_id TEXT NOT NULL,
    resource TEXT NOT NULL DEFAULT 'transactions' CHECK(resource = 'transactions'),
    account_id TEXT NOT NULL,
    transaction_id TEXT NOT NULL,
    batch_id TEXT REFERENCES of_classification_batches(id),
    action TEXT NOT NULL CHECK(action IN ('MANUAL','BATCH','UNDO')),
    previous_event INTEGER REFERENCES of_classification_events(id),
    reverses_event INTEGER UNIQUE REFERENCES of_classification_events(id),
    previous_json TEXT CHECK(previous_json IS NULL OR json_valid(previous_json)),
    previous_effective_json TEXT CHECK(previous_effective_json IS NULL OR json_valid(previous_effective_json)),
    decision_json TEXT CHECK(decision_json IS NULL OR json_valid(decision_json)),
    recorded_at TEXT NOT NULL,
    actor TEXT NOT NULL,
    FOREIGN KEY(connection_id,resource,account_id,transaction_id)
      REFERENCES of_resource_records(connection_id,resource,parent_id,external_id)
);

CREATE INDEX of_classification_identity ON of_classification_events(connection_id,account_id,transaction_id,id DESC);
CREATE INDEX of_classification_by_batch ON of_classification_events(batch_id,id) WHERE batch_id IS NOT NULL;
CREATE INDEX of_classification_rule_cutoff ON of_classification_rule_revisions(rule_id,after_run,revision DESC);

CREATE VIEW of_classification_current AS
SELECT e.* FROM of_classification_events e
WHERE e.id = (SELECT max(r.id) FROM of_classification_events r
              WHERE r.connection_id=e.connection_id AND r.account_id=e.account_id AND r.transaction_id=e.transaction_id);


-- A durable order of collections makes prospective rule versions independent of VACUUM and time ties.
CREATE TABLE of_classification_import_order (
    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL UNIQUE REFERENCES of_sync_runs(id) ON DELETE RESTRICT
);

CREATE TRIGGER of_classification_new_run AFTER INSERT ON of_sync_runs
BEGIN
    INSERT INTO of_classification_import_order(run_id) VALUES (NEW.id);
END;
