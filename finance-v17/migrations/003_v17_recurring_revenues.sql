CREATE TABLE revenue_recurring_series(
 id INTEGER PRIMARY KEY, description TEXT NOT NULL CHECK(length(trim(description))>0), amount_cents INTEGER NOT NULL CHECK(amount_cents>0),
 start_date TEXT NOT NULL, end_date TEXT, frequency TEXT NOT NULL CHECK(frequency IN('WEEKLY','BIWEEKLY','MONTHLY','BIMONTHLY','QUARTERLY','SEMIANNUAL','ANNUAL')),
 category_id INTEGER NOT NULL REFERENCES categories(id), account_id INTEGER REFERENCES accounts(id), expected_day INTEGER NOT NULL CHECK(expected_day BETWEEN 1 AND 31), active INTEGER NOT NULL CHECK(active IN(0,1)),
 created_at TEXT NOT NULL, ended_at TEXT,
 CHECK(date(start_date,'+0 days') IS NOT NULL AND start_date=date(start_date,'+0 days')), CHECK(end_date IS NULL OR date(end_date,'+0 days') IS NOT NULL), CHECK(end_date IS NULL OR end_date>=start_date)
);
CREATE TABLE revenue_recurring_occurrences(
 id INTEGER PRIMARY KEY, series_id INTEGER NOT NULL REFERENCES revenue_recurring_series(id), revenue_id INTEGER NOT NULL UNIQUE REFERENCES revenues(id), occurrence_date TEXT NOT NULL,
 UNIQUE(series_id,occurrence_date), CHECK(date(occurrence_date,'+0 days') IS NOT NULL AND occurrence_date=date(occurrence_date,'+0 days'))
);
CREATE TABLE revenue_recurring_series_tags(
 series_id INTEGER NOT NULL REFERENCES revenue_recurring_series(id),tag_id INTEGER NOT NULL REFERENCES tags(id),PRIMARY KEY(series_id,tag_id)
);
CREATE INDEX ix_revenue_recurring_series_active ON revenue_recurring_series(active);
