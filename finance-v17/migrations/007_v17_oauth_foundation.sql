-- Stage 1 storage only. No issuer, code/token generation or refresh lifecycle.
-- Sensitive bearer values are never stored: only lowercase SHA-256 digests.
CREATE TABLE oauth_clients (
    oauth_client_id TEXT PRIMARY KEY CHECK(length(oauth_client_id)>0),
    identity_client_id TEXT NOT NULL UNIQUE CHECK(length(identity_client_id)>0),
    redirect_uris_json TEXT NOT NULL,
    token_endpoint_auth_method TEXT NOT NULL DEFAULT 'none' CHECK(token_endpoint_auth_method='none'),
    created_at INTEGER NOT NULL CHECK(typeof(created_at)='integer' AND created_at>=0),
    disabled_at INTEGER CHECK(disabled_at IS NULL OR (typeof(disabled_at)='integer' AND disabled_at>=created_at))
);

-- Immutable after consent/code issuance. Future token lookup joins this record
-- to obtain client, subject, exact redirect, resource and granted capabilities.
CREATE TABLE oauth_authorization_requests (
    request_id TEXT PRIMARY KEY CHECK(length(request_id)>0),
    oauth_client_id TEXT NOT NULL REFERENCES oauth_clients(oauth_client_id),
    redirect_uri TEXT NOT NULL CHECK(length(redirect_uri)>0),
    state TEXT NOT NULL CHECK(length(state)>0),
    browser_binding_hash TEXT NOT NULL CHECK(length(browser_binding_hash)=64 AND browser_binding_hash NOT GLOB '*[^0-9a-f]*'),
    requested_scopes TEXT NOT NULL CHECK(requested_scopes IN ('','finance:read','finance:write','finance:read finance:write')),
    granted_scopes TEXT NOT NULL DEFAULT '' CHECK(granted_scopes IN ('','finance:read','finance:write','finance:read finance:write')),
    owner_subject TEXT,
    resource TEXT NOT NULL CHECK(resource='https://finance.diversaoemcamadas.com.br/mcp'),
    pkce_challenge TEXT NOT NULL CHECK(length(pkce_challenge)=43 AND pkce_challenge NOT GLOB '*[^A-Za-z0-9_-]*' AND substr(pkce_challenge,-1) IN ('A','E','I','M','Q','U','Y','c','g','k','o','s','w','0','4','8')),
    pkce_method TEXT NOT NULL CHECK(pkce_method='S256'),
    created_at INTEGER NOT NULL CHECK(typeof(created_at)='integer' AND created_at>=0),
    expires_at INTEGER NOT NULL CHECK(typeof(expires_at)='integer' AND expires_at>created_at),
    completed_at INTEGER CHECK(completed_at IS NULL OR (typeof(completed_at)='integer' AND completed_at>=created_at)),
    revoked_at INTEGER CHECK(revoked_at IS NULL OR (typeof(revoked_at)='integer' AND revoked_at>=created_at)),
    CHECK(granted_scopes='' OR (owner_subject IS NOT NULL AND length(owner_subject)>0)),
    CHECK(granted_scopes='' OR granted_scopes=requested_scopes OR
          (requested_scopes='finance:read finance:write' AND granted_scopes IN ('finance:read','finance:write')))
);

CREATE TABLE oauth_authorization_codes (
    code_hash TEXT PRIMARY KEY CHECK(length(code_hash)=64 AND code_hash NOT GLOB '*[^0-9a-f]*'),
    request_id TEXT NOT NULL UNIQUE REFERENCES oauth_authorization_requests(request_id),
    created_at INTEGER NOT NULL CHECK(typeof(created_at)='integer' AND created_at>=0),
    expires_at INTEGER NOT NULL CHECK(typeof(expires_at)='integer' AND expires_at>created_at),
    consumed_at INTEGER CHECK(consumed_at IS NULL OR (typeof(consumed_at)='integer' AND consumed_at>=created_at)),
    revoked_at INTEGER CHECK(revoked_at IS NULL OR (typeof(revoked_at)='integer' AND revoked_at>=created_at))
);

CREATE TABLE oauth_access_tokens (
    token_hash TEXT PRIMARY KEY CHECK(length(token_hash)=64 AND token_hash NOT GLOB '*[^0-9a-f]*'),
    request_id TEXT NOT NULL REFERENCES oauth_authorization_requests(request_id),
    issuer TEXT NOT NULL CHECK(issuer='https://finance.diversaoemcamadas.com.br'),
    created_at INTEGER NOT NULL CHECK(typeof(created_at)='integer' AND created_at>=0),
    expires_at INTEGER NOT NULL CHECK(typeof(expires_at)='integer' AND expires_at>created_at),
    revoked_at INTEGER CHECK(revoked_at IS NULL OR (typeof(revoked_at)='integer' AND revoked_at>=created_at))
);
CREATE INDEX oauth_requests_expiry ON oauth_authorization_requests(expires_at);
CREATE INDEX oauth_tokens_request ON oauth_access_tokens(request_id);
CREATE INDEX oauth_tokens_expiry ON oauth_access_tokens(expires_at);
