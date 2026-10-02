CREATE TABLE revenues(
 id INTEGER PRIMARY KEY, description TEXT NOT NULL CHECK(length(trim(description))>0), amount_cents INTEGER NOT NULL CHECK(amount_cents>0),
 competence_date TEXT NOT NULL, expected_on TEXT NOT NULL,
 category_id INTEGER NOT NULL REFERENCES categories(id), account_id INTEGER REFERENCES accounts(id), lifecycle_state TEXT NOT NULL CHECK(lifecycle_state IN('ACTIVE','CANCELLED')),
 notes TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
 CHECK(date(competence_date,'+0 days') IS NOT NULL AND competence_date=date(competence_date,'+0 days')),
 CHECK(date(expected_on,'+0 days') IS NOT NULL AND expected_on=date(expected_on,'+0 days')),
 CHECK(strftime('%Y-%m-%dT%H:%M:%SZ',created_at)=created_at AND strftime('%Y-%m-%dT%H:%M:%SZ',updated_at)=updated_at)
);
CREATE TABLE revenue_tags(revenue_id INTEGER NOT NULL REFERENCES revenues(id),tag_id INTEGER NOT NULL REFERENCES tags(id),PRIMARY KEY(revenue_id,tag_id));
CREATE TABLE revenue_receipts(
 id INTEGER PRIMARY KEY,revenue_id INTEGER NOT NULL REFERENCES revenues(id),amount_cents INTEGER NOT NULL CHECK(amount_cents>0),received_on TEXT NOT NULL,
 account_id INTEGER NOT NULL REFERENCES accounts(id),created_at TEXT NOT NULL,reversed_at TEXT,reversed_on TEXT,reversed_by_actor TEXT,reversal_reason TEXT,correlation_id TEXT NOT NULL CHECK(length(trim(correlation_id))>0),
 CHECK(date(received_on,'+0 days') IS NOT NULL AND received_on=date(received_on,'+0 days')),
 CHECK(strftime('%Y-%m-%dT%H:%M:%SZ',created_at)=created_at),
 CHECK((reversed_at IS NULL AND reversed_on IS NULL AND reversed_by_actor IS NULL AND reversal_reason IS NULL) OR (reversed_at IS NOT NULL AND reversed_on IS NOT NULL AND reversed_by_actor IS NOT NULL AND reversal_reason IS NOT NULL)),
 CHECK(reversed_at IS NULL OR strftime('%Y-%m-%dT%H:%M:%SZ',reversed_at)=reversed_at),
 CHECK(reversed_on IS NULL OR (date(reversed_on,'+0 days') IS NOT NULL AND reversed_on=date(reversed_on,'+0 days') AND reversed_on>=received_on)),
 CHECK(reversed_by_actor IS NULL OR length(trim(reversed_by_actor))>0),CHECK(reversal_reason IS NULL OR length(trim(reversal_reason))>0)
);
CREATE UNIQUE INDEX ux_active_revenue_receipt ON revenue_receipts(revenue_id) WHERE reversed_at IS NULL;
CREATE INDEX ix_revenues_expected_on ON revenues(expected_on);
