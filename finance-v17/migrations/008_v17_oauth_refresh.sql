-- Durable, single-use refresh rotation. Bearer values are never persisted.
CREATE TABLE oauth_refresh_token_families (
    family_id TEXT PRIMARY KEY CHECK(length(family_id)>0),
    request_id TEXT NOT NULL UNIQUE REFERENCES oauth_authorization_requests(request_id),
    created_at INTEGER NOT NULL CHECK(typeof(created_at)='integer' AND created_at>=0),
    expires_at INTEGER NOT NULL CHECK(typeof(expires_at)='integer' AND expires_at>created_at),
    revoked_at INTEGER CHECK(revoked_at IS NULL OR (typeof(revoked_at)='integer' AND revoked_at>=created_at)),
    revocation_reason TEXT CHECK(revocation_reason IS NULL OR revocation_reason IN ('reuse','code_replay','owner'))
);
CREATE TABLE oauth_refresh_tokens (
    token_hash TEXT PRIMARY KEY CHECK(length(token_hash)=64 AND token_hash NOT GLOB '*[^0-9a-f]*'),
    family_id TEXT NOT NULL REFERENCES oauth_refresh_token_families(family_id),
    parent_hash TEXT UNIQUE REFERENCES oauth_refresh_tokens(token_hash),
    scopes TEXT NOT NULL CHECK(scopes IN ('finance:read','finance:write','finance:read finance:write')),
    created_at INTEGER NOT NULL CHECK(typeof(created_at)='integer' AND created_at>=0),
    expires_at INTEGER NOT NULL CHECK(typeof(expires_at)='integer' AND expires_at>created_at),
    consumed_at INTEGER CHECK(consumed_at IS NULL OR (typeof(consumed_at)='integer' AND consumed_at>=created_at)),
    revoked_at INTEGER CHECK(revoked_at IS NULL OR (typeof(revoked_at)='integer' AND revoked_at>=created_at))
);
ALTER TABLE oauth_access_tokens ADD COLUMN family_id TEXT REFERENCES oauth_refresh_token_families(family_id);
ALTER TABLE oauth_access_tokens ADD COLUMN scopes TEXT CHECK(scopes IS NULL OR scopes IN ('finance:read','finance:write','finance:read finance:write'));
CREATE INDEX oauth_refresh_family ON oauth_refresh_tokens(family_id);
CREATE INDEX oauth_access_family ON oauth_access_tokens(family_id);
CREATE UNIQUE INDEX oauth_refresh_one_active ON oauth_refresh_tokens(family_id)
    WHERE consumed_at IS NULL AND revoked_at IS NULL;
