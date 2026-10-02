"""OAuth contract and validated records shared by discovery and the server."""
from __future__ import annotations

from dataclasses import dataclass, field
import re
from urllib.parse import urlsplit, urlunsplit

from .authorization import FINANCE_SCOPES

ISSUER = "https://finance.diversaoemcamadas.com.br"
RESOURCE = ISSUER + "/mcp"
RESOURCE_METADATA_PATH = "/.well-known/oauth-protected-resource/mcp"
RESOURCE_METADATA_URL = ISSUER + RESOURCE_METADATA_PATH
AUTHORIZATION_METADATA_PATH = "/.well-known/oauth-authorization-server"
PKCE_METHODS = ("S256",)


def validate_scopes(scopes: frozenset[str]) -> frozenset[str]:
    if not isinstance(scopes, frozenset) or not scopes <= FINANCE_SCOPES:
        raise ValueError("unsupported Finance scopes")
    return scopes


def validate_https_uri(value: str) -> str:
    # Never normalize redirects: their original spelling is used for exact match.
    if not isinstance(value, str) or not value or any(ord(c) <= 32 or ord(c) >= 127 for c in value):
        raise ValueError("invalid HTTPS URI")
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError:
        raise ValueError("invalid HTTPS URI") from None
    if parsed.scheme.lower() != "https" or not parsed.hostname or parsed.username is not None or parsed.password is not None or "#" in value or "\\" in value:
        raise ValueError("invalid HTTPS URI")
    if port is not None and not 1 <= port <= 65535:
        raise ValueError("invalid HTTPS URI")
    return value


def validate_resource(value: str) -> str:
    validate_https_uri(value)
    parsed = urlsplit(value)
    # Only scheme/host case is normalized; no path, query or port aliases.
    normalized = urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), parsed.path, parsed.query, ""))
    if normalized != RESOURCE or "?" in value:
        raise ValueError("unsupported Finance resource")
    return RESOURCE


def validate_hash(value: str) -> str:
    if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise ValueError("expected SHA-256 digest")
    return value


def validate_lifetime(created_at: int, expires_at: int) -> None:
    if type(created_at) is not int or type(expires_at) is not int or created_at < 0 or expires_at <= created_at:
        raise ValueError("invalid UTC epoch lifetime")


@dataclass(frozen=True)
class OAuthClient:
    oauth_client_id: str
    identity_client_id: str
    redirect_uris: tuple[str, ...]
    token_endpoint_auth_method: str = "none"

    def __post_init__(self):
        if not isinstance(self.oauth_client_id, str) or not self.oauth_client_id or len(self.oauth_client_id)>2048 or any(ord(c) <= 32 or ord(c)>=127 for c in self.oauth_client_id):
            raise ValueError("invalid OAuth client identity")
        if re.fullmatch(r"CLIENT:[a-z][a-z0-9-]{1,63}", self.identity_client_id) is None:
            raise ValueError("invalid stable Finance client identity")
        if self.token_endpoint_auth_method != "none":
            raise ValueError("Finance supports public clients only")
        if not isinstance(self.redirect_uris, tuple) or not self.redirect_uris or len(set(self.redirect_uris)) != len(self.redirect_uris):
            raise ValueError("invalid redirect allowlist")
        for uri in self.redirect_uris:
            validate_https_uri(uri)

    def allows_redirect(self, uri: str) -> bool:
        return uri in self.redirect_uris

    @property
    def client_id(self) -> str:
        return self.oauth_client_id


@dataclass(frozen=True)
class AuthorizationRequest:
    request_id: str
    client: OAuthClient
    redirect_uri: str
    requested_scopes: frozenset[str]
    resource: str
    state: str | None = field(repr=False)
    browser_binding_hash: str = field(repr=False)
    pkce_challenge: str = field(repr=False)
    created_at: int
    expires_at: int
    pkce_method: str = "S256"
    granted_scopes: frozenset[str] = frozenset()
    owner_subject: str | None = None

    def __post_init__(self):
        if not self.request_id or self.state is not None and (not isinstance(self.state, str) or not self.state):
            raise ValueError("request identity and state required")
        validate_https_uri(self.redirect_uri)
        if not self.client.allows_redirect(self.redirect_uri):
            raise ValueError("redirect URI is not an exact registered match")
        validate_scopes(self.requested_scopes)
        validate_scopes(self.granted_scopes)
        if not self.granted_scopes <= self.requested_scopes:
            raise ValueError("granted scopes exceed request")
        if self.granted_scopes and not self.owner_subject:
            raise ValueError("grant requires an authenticated owner")
        object.__setattr__(self, "resource", validate_resource(self.resource))
        validate_hash(self.browser_binding_hash)
        # S256 is a base64url encoded SHA-256 digest, without padding.
        if self.pkce_method != "S256" or re.fullmatch(r"[A-Za-z0-9_-]{42}[AEIMQUYcgkosw048]", self.pkce_challenge) is None:
            raise ValueError("PKCE S256 challenge required")
        validate_lifetime(self.created_at, self.expires_at)


@dataclass(frozen=True)
class AuthorizationCodeRecord:
    code_hash: str = field(repr=False)
    request_id: str
    created_at: int
    expires_at: int
    consumed_at: int | None = None
    revoked_at: int | None = None

    def __post_init__(self):
        validate_hash(self.code_hash)
        validate_lifetime(self.created_at, self.expires_at)
        if not self.request_id:
            raise ValueError("authorization request required")
        for timestamp in (self.consumed_at, self.revoked_at):
            if timestamp is not None and (type(timestamp) is not int or timestamp < self.created_at):
                raise ValueError("invalid lifecycle timestamp")


@dataclass(frozen=True)
class AccessTokenRecord:
    token_hash: str = field(repr=False)
    request_id: str
    issuer: str
    created_at: int
    expires_at: int
    revoked_at: int | None = None

    def __post_init__(self):
        validate_hash(self.token_hash)
        validate_lifetime(self.created_at, self.expires_at)
        if self.issuer != ISSUER or not self.request_id:
            raise ValueError("invalid issuer or grant reference")
        if self.revoked_at is not None and (type(self.revoked_at) is not int or self.revoked_at < self.created_at):
            raise ValueError("invalid revocation timestamp")


def protected_resource_metadata() -> dict[str, object]:
    return {"resource": RESOURCE, "authorization_servers": [ISSUER],
            "scopes_supported": sorted(FINANCE_SCOPES), "bearer_methods_supported": ["header"]}


def authorization_server_contract() -> dict[str, object]:
    """RFC 8414 metadata for the implemented authorization-code server."""
    return {"issuer": ISSUER, "authorization_endpoint": ISSUER + "/oauth/authorize",
            "token_endpoint": ISSUER + "/oauth/token", "response_types_supported": ["code"],
            "grant_types_supported": ["authorization_code"], "scopes_supported": sorted(FINANCE_SCOPES),
            "code_challenge_methods_supported": list(PKCE_METHODS),
            "token_endpoint_auth_methods_supported": ["none"]}


def bearer_challenge(*, invalid_token: bool = False) -> str:
    error = 'error="invalid_token", ' if invalid_token else ""
    return f'Bearer {error}resource_metadata="{RESOURCE_METADATA_URL}", scope="finance:read"'
