-- Complete investment collections, observed prospectively.
CREATE TABLE of_portfolio_snapshots (
    run_id TEXT NOT NULL,
    connection_id TEXT NOT NULL,
    external_id TEXT NOT NULL,
    currency TEXT NOT NULL,
    value TEXT NOT NULL,
    reference_date TEXT,
    observed_at TEXT NOT NULL,
    PRIMARY KEY(run_id,connection_id,external_id),
    FOREIGN KEY(run_id,connection_id) REFERENCES of_sync_runs(id,connection_id)
);

CREATE INDEX of_portfolio_by_scope ON of_portfolio_snapshots(connection_id,currency,observed_at,run_id);
