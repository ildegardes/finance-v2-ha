CREATE TABLE revenue_recurring_series_versions(
 id INTEGER PRIMARY KEY, series_id INTEGER NOT NULL REFERENCES revenue_recurring_series(id),
 description TEXT NOT NULL, amount_cents INTEGER NOT NULL CHECK(amount_cents>0), start_date TEXT NOT NULL, end_date TEXT,
 frequency TEXT NOT NULL, expected_day INTEGER NOT NULL CHECK(expected_day BETWEEN 1 AND 31), category_id INTEGER NOT NULL REFERENCES categories(id), account_id INTEGER REFERENCES accounts(id), effective_from TEXT NOT NULL, effective_to TEXT, created_at TEXT NOT NULL
);
ALTER TABLE revenue_recurring_occurrences ADD COLUMN version_id INTEGER REFERENCES revenue_recurring_series_versions(id);
CREATE INDEX ix_revenue_series_versions_lookup ON revenue_recurring_series_versions(series_id,effective_from);
