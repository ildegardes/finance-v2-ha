CREATE TABLE st_state (
    singleton INTEGER PRIMARY KEY CHECK(singleton=1),
    auto_enabled INTEGER NOT NULL DEFAULT 0 CHECK(auto_enabled IN (0,1)),
    interval_hours INTEGER NOT NULL DEFAULT 24 CHECK(interval_hours IN (1,2,4,6,12,24,48)),
    revision INTEGER NOT NULL DEFAULT 0,
    lease_token TEXT, lease_until INTEGER, next_attempt INTEGER NOT NULL DEFAULT 0,
    last_attempt TEXT, last_success TEXT, error_code TEXT
);
INSERT INTO st_state(singleton) VALUES(1);

CREATE TABLE st_credentials (
    singleton INTEGER PRIMARY KEY CHECK(singleton=1),
    revision INTEGER NOT NULL,
    key_id TEXT NOT NULL, nonce TEXT NOT NULL, ciphertext TEXT NOT NULL
);

CREATE TABLE st_connections (
    id TEXT PRIMARY KEY, institution TEXT NOT NULL, brokerage TEXT NOT NULL,
    permission TEXT, provider_state TEXT NOT NULL, observed_at TEXT NOT NULL,
    archived INTEGER NOT NULL DEFAULT 0 CHECK(archived IN (0,1)),
    paused INTEGER NOT NULL DEFAULT 0 CHECK(paused IN (0,1)),
    excluded INTEGER NOT NULL DEFAULT 0 CHECK(excluded IN (0,1))
);

CREATE TABLE st_accounts (
    id TEXT PRIMARY KEY, connection_id TEXT NOT NULL REFERENCES st_connections(id),
    label TEXT NOT NULL, kind TEXT, suffix TEXT, fingerprint TEXT, state TEXT NOT NULL,
    provider_updated_at TEXT, observed_at TEXT NOT NULL,
    net_value TEXT, net_currency TEXT
);
CREATE INDEX st_accounts_connection ON st_accounts(connection_id,state);

CREATE TABLE st_positions (
    account_id TEXT NOT NULL REFERENCES st_accounts(id), instrument_id TEXT NOT NULL,
    ticker TEXT, label TEXT, kind TEXT NOT NULL, exchange TEXT, country TEXT, currency TEXT,
    units TEXT, price TEXT, market_value TEXT, cost TEXT, unrealized TEXT,
    reference_at TEXT, observed_at TEXT NOT NULL, cash_equivalent INTEGER NOT NULL,
    lots_json TEXT, PRIMARY KEY(account_id,instrument_id)
);
CREATE INDEX st_positions_scope ON st_positions(currency,kind,account_id);

CREATE TABLE st_balances (
    account_id TEXT NOT NULL REFERENCES st_accounts(id), currency TEXT NOT NULL,
    cash TEXT, buying_power TEXT, margin_debit TEXT, reference_at TEXT,
    observed_at TEXT NOT NULL, PRIMARY KEY(account_id,currency)
);

CREATE TABLE st_activities (
    account_id TEXT NOT NULL REFERENCES st_accounts(id), activity_id TEXT NOT NULL,
    kind TEXT NOT NULL, provider_kind TEXT NOT NULL, date TEXT NOT NULL, settled TEXT,
    ticker TEXT, instrument_id TEXT, description TEXT, currency TEXT, amount TEXT, units TEXT,
    price TEXT, fee TEXT, observed_at TEXT NOT NULL, PRIMARY KEY(account_id,activity_id)
);
CREATE INDEX st_activities_period ON st_activities(account_id,date,activity_id);

CREATE TABLE st_activity_rules (
    id INTEGER PRIMARY KEY, account_id TEXT NOT NULL REFERENCES st_accounts(id),
    provider_kind TEXT NOT NULL, description_key TEXT NOT NULL, kind TEXT NOT NULL,
    observed_at TEXT NOT NULL, UNIQUE(account_id,provider_kind,description_key)
);

CREATE TABLE st_checkpoints (
    account_id TEXT NOT NULL REFERENCES st_accounts(id), resource TEXT NOT NULL,
    state TEXT NOT NULL, observed_at TEXT NOT NULL, error_code TEXT,
    window_start TEXT, window_end TEXT, next_offset INTEGER NOT NULL DEFAULT 0,
    page_anchor TEXT, first_date TEXT, last_date TEXT,
    PRIMARY KEY(account_id,resource)
);

CREATE TABLE st_snapshots (
    account_id TEXT NOT NULL REFERENCES st_accounts(id), currency TEXT NOT NULL,
    reference_date TEXT NOT NULL, reference_at TEXT NOT NULL,
    observed_at TEXT NOT NULL, market_value TEXT NOT NULL, cash TEXT,
    PRIMARY KEY(account_id,currency,reference_date)
);

CREATE TABLE st_position_snapshots (
    account_id TEXT NOT NULL REFERENCES st_accounts(id), instrument_id TEXT NOT NULL,
    currency TEXT NOT NULL, reference_date TEXT NOT NULL, reference_at TEXT NOT NULL,
    observed_at TEXT NOT NULL, market_value TEXT NOT NULL,
    PRIMARY KEY(account_id,instrument_id,currency,reference_date)
);

CREATE TABLE st_events (
    id INTEGER PRIMARY KEY, observed_at TEXT NOT NULL, action TEXT NOT NULL,
    target TEXT, outcome TEXT NOT NULL
);

CREATE TABLE portfolio_fx_rates (
    quote_date TEXT PRIMARY KEY, rate TEXT NOT NULL, observed_at TEXT NOT NULL,
    source TEXT NOT NULL CHECK(source='BCB_PTAX_SELL')
);
