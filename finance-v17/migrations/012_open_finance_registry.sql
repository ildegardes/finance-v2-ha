-- Preserve all existing staging identifiers and historical references.
CREATE TABLE of_connection_registry (
    connection_id TEXT PRIMARY KEY REFERENCES of_connections(id),
    source TEXT NOT NULL CHECK(source IN ('LEGACY','MANAGED')),
    lifecycle TEXT NOT NULL CHECK(lifecycle IN ('DRAFT','ACTIVE','DISABLED','ARCHIVED','REMOVED')),
    label TEXT NOT NULL CHECK(length(trim(label)) BETWEEN 1 AND 200),
    revision INTEGER NOT NULL DEFAULT 0 CHECK(revision >= 0),
    replaces_id TEXT REFERENCES of_connection_registry(connection_id),
    updated_at TEXT NOT NULL,
    CHECK(replaces_id IS NULL OR replaces_id <> connection_id)
);

INSERT INTO of_connection_registry(connection_id, source, lifecycle, label, updated_at)
SELECT id, 'LEGACY', CASE enabled WHEN 1 THEN 'ACTIVE' ELSE 'DISABLED' END,
       institution, updated_at
FROM of_connections;

CREATE TABLE of_connection_admin_events (
    event_id TEXT PRIMARY KEY,
    connection_id TEXT NOT NULL,
    actor TEXT NOT NULL,
    operation TEXT NOT NULL,
    previous_state TEXT,
    resulting_state TEXT,
    revision INTEGER NOT NULL CHECK(revision >= 0),
    recorded_at TEXT NOT NULL
);
CREATE INDEX of_connection_admin_events_history
ON of_connection_admin_events(connection_id, recorded_at, event_id);

CREATE TABLE of_pluggy_applications (
    id TEXT PRIMARY KEY NOT NULL CHECK(length(id) BETWEEN 2 AND 64),
    label TEXT NOT NULL CHECK(length(trim(label)) BETWEEN 1 AND 200),
    environment TEXT NOT NULL CHECK(environment IN ('PERSONAL','SANDBOX','STRICT'))
);

CREATE TABLE of_connection_credentials (
    application_id TEXT NOT NULL REFERENCES of_pluggy_applications(id),
    revision INTEGER NOT NULL CHECK(revision > 0),
    key_id TEXT NOT NULL CHECK(length(key_id) BETWEEN 1 AND 32),
    nonce BLOB NOT NULL CHECK(typeof(nonce)='blob' AND length(nonce)=12),
    ciphertext BLOB NOT NULL CHECK(typeof(ciphertext)='blob' AND length(ciphertext) BETWEEN 16 AND 12312),
    created_at TEXT NOT NULL,
    PRIMARY KEY(application_id, revision),
    UNIQUE(key_id, nonce)
);

CREATE TABLE of_managed_pluggy_items (
    connection_id TEXT PRIMARY KEY NOT NULL REFERENCES of_connection_registry(connection_id),
    application_id TEXT NOT NULL,
    credential_revision INTEGER NOT NULL,
    item_id TEXT NOT NULL CHECK(length(trim(item_id)) BETWEEN 1 AND 200),
    auto_sync_enabled INTEGER NOT NULL DEFAULT 0 CHECK(auto_sync_enabled IN (0,1)),
    FOREIGN KEY(application_id, credential_revision)
        REFERENCES of_connection_credentials(application_id, revision),
    UNIQUE(application_id, item_id)
);
