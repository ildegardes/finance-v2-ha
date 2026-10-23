-- Open Finance staging only. No alteration of official financial entities.
CREATE TABLE of_connections (
    id TEXT PRIMARY KEY NOT NULL CHECK(length(trim(id)) BETWEEN 1 AND 64),
    provider TEXT NOT NULL DEFAULT 'PLUGGY' CHECK(provider='PLUGGY'),
    institution TEXT NOT NULL CHECK(length(trim(institution)) BETWEEN 1 AND 200),
    enabled INTEGER NOT NULL DEFAULT 0 CHECK(enabled IN(0,1)),
    binding_hash TEXT NOT NULL CHECK(length(binding_hash)=64),
    sync_state TEXT NOT NULL DEFAULT 'IDLE' CHECK(sync_state IN('IDLE','RUNNING','SUCCEEDED','FAILED','INTERRUPTED')),
    lease_token TEXT,
    lease_until REAL,
    updated_at TEXT NOT NULL,
    CHECK((lease_token IS NULL AND lease_until IS NULL) OR
          (lease_token IS NOT NULL AND length(lease_token)>0 AND lease_until IS NOT NULL)),
    CHECK((sync_state='RUNNING' AND lease_token IS NOT NULL) OR
          (sync_state<>'RUNNING' AND lease_token IS NULL))
);

CREATE TABLE of_accounts (
    connection_id TEXT NOT NULL REFERENCES of_connections(id),
    external_id TEXT NOT NULL CHECK(length(trim(external_id)) BETWEEN 1 AND 200),
    name TEXT,
    type TEXT,
    subtype TEXT,
    currency TEXT,
    provider_updated_at TEXT,
    PRIMARY KEY(connection_id,external_id)
);

CREATE TABLE of_categories (
    connection_id TEXT NOT NULL REFERENCES of_connections(id),
    category_key TEXT NOT NULL CHECK(length(trim(category_key)) BETWEEN 1 AND 200),
    provider TEXT NOT NULL DEFAULT 'PLUGGY' CHECK(provider='PLUGGY'),
    external_id TEXT,
    original_name TEXT,
    display_name_pt TEXT,
    translation_status TEXT NOT NULL DEFAULT 'UNVERIFIED'
        CHECK(translation_status IN('UNVERIFIED','VERIFIED','OWNER_OVERRIDE')),
    updated_at TEXT NOT NULL,
    PRIMARY KEY(connection_id,category_key),
    UNIQUE(connection_id,external_id),
    CHECK(external_id IS NULL OR length(trim(external_id))>0),
    CHECK(translation_status='UNVERIFIED' OR
          (display_name_pt IS NOT NULL AND length(trim(display_name_pt))>0))
);

CREATE TABLE of_sync_runs (
    id TEXT PRIMARY KEY NOT NULL,
    connection_id TEXT NOT NULL REFERENCES of_connections(id),
    actor TEXT NOT NULL CHECK(length(trim(actor))>0),
    started_at TEXT NOT NULL,
    finished_at TEXT,
    state TEXT NOT NULL CHECK(state IN('RUNNING','SUCCEEDED','FAILED','INTERRUPTED')),
    date_from TEXT,
    date_to TEXT,
    inserted_count INTEGER NOT NULL DEFAULT 0 CHECK(inserted_count>=0),
    updated_count INTEGER NOT NULL DEFAULT 0 CHECK(updated_count>=0),
    page_count INTEGER NOT NULL DEFAULT 0 CHECK(page_count>=0),
    error_code TEXT,
    UNIQUE(id,connection_id),
    CHECK((state='RUNNING' AND finished_at IS NULL) OR
          (state<>'RUNNING' AND finished_at IS NOT NULL)),
    CHECK(date_from IS NULL OR date_to IS NULL OR date_from<=date_to)
);
CREATE UNIQUE INDEX of_sync_one_running ON of_sync_runs(connection_id) WHERE state='RUNNING';

CREATE TABLE of_transactions (
    id INTEGER PRIMARY KEY,
    connection_id TEXT NOT NULL,
    external_account_id TEXT NOT NULL,
    external_id TEXT NOT NULL CHECK(length(trim(external_id)) BETWEEN 1 AND 200),
    transaction_date TEXT NOT NULL,
    amount_decimal TEXT NOT NULL CHECK(length(trim(amount_decimal))>0),
    currency TEXT NOT NULL CHECK(length(trim(currency))>0),
    type TEXT,
    status TEXT,
    description_original TEXT,
    merchant_name TEXT,
    category_key TEXT,
    provider_created_at TEXT,
    provider_updated_at TEXT,
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    UNIQUE(connection_id,external_account_id,external_id),
    UNIQUE(id,connection_id),
    FOREIGN KEY(connection_id,external_account_id)
        REFERENCES of_accounts(connection_id,external_id),
    FOREIGN KEY(connection_id,category_key)
        REFERENCES of_categories(connection_id,category_key)
);

CREATE TABLE of_transaction_revisions (
    id INTEGER PRIMARY KEY,
    transaction_id INTEGER NOT NULL,
    connection_id TEXT NOT NULL,
    revision_number INTEGER NOT NULL CHECK(revision_number>=1),
    run_id TEXT NOT NULL,
    observed_at TEXT NOT NULL,
    amount_decimal TEXT NOT NULL,
    currency TEXT NOT NULL,
    transaction_date TEXT NOT NULL,
    type TEXT,
    status TEXT,
    description_original TEXT,
    merchant_name TEXT,
    category_key TEXT,
    provider_updated_at TEXT,
    UNIQUE(transaction_id,revision_number),
    FOREIGN KEY(transaction_id,connection_id) REFERENCES of_transactions(id,connection_id),
    FOREIGN KEY(run_id,connection_id) REFERENCES of_sync_runs(id,connection_id),
    FOREIGN KEY(connection_id,category_key) REFERENCES of_categories(connection_id,category_key)
);
CREATE INDEX of_transaction_period ON of_transactions(connection_id,transaction_date);
CREATE INDEX of_sync_history ON of_sync_runs(connection_id,started_at);
