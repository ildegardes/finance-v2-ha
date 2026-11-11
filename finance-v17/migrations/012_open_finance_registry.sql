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
