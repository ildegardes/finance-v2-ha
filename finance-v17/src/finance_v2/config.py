from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from .authorization import FINANCE_SCOPES
from .oauth import OAuthClient


PROJECT_ROOT = Path(__file__).resolve().parents[2]


class ConfigurationError(ValueError):
    """Raised when required runtime configuration is invalid."""


@dataclass(frozen=True)
class ExternalClientCredential:
    client_id: str
    token: str
    capabilities: frozenset[str]
    enabled: bool = True
    previous_token: str | None = None


def _external_clients_from_env(raw: str | None) -> tuple[ExternalClientCredential, ...]:
    if not raw:
        return ()
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ConfigurationError("FINANCE_V2_EXTERNAL_CLIENTS_JSON must be valid JSON") from exc
    if not isinstance(payload, dict):
        raise ConfigurationError("FINANCE_V2_EXTERNAL_CLIENTS_JSON must be an object")
    clients: list[ExternalClientCredential] = []
    seen_tokens: set[str] = set()
    for client_id, value in payload.items():
        if not isinstance(client_id, str) or not re.fullmatch(r"[a-z][a-z0-9-]{1,63}", client_id):
            raise ConfigurationError("external client id must be a lower-case slug")
        if not isinstance(value, dict):
            raise ConfigurationError(f"external client {client_id} must be an object")
        token = value.get("token")
        previous = value.get("previous_token")
        capabilities = value.get("capabilities", [])
        enabled = value.get("enabled", True)
        if not isinstance(token, str) or len(token) < 16:
            raise ConfigurationError(f"external client {client_id} token must contain at least 16 characters")
        if previous is not None and (not isinstance(previous, str) or len(previous) < 16):
            raise ConfigurationError(f"external client {client_id} previous_token must contain at least 16 characters")
        if not isinstance(enabled, bool):
            raise ConfigurationError(f"external client {client_id} enabled must be boolean")
        if not isinstance(capabilities, list) or not all(isinstance(item, str) for item in capabilities):
            raise ConfigurationError(f"external client {client_id} capabilities must be a string array")
        capability_set = frozenset(capabilities)
        if not capability_set <= FINANCE_SCOPES:
            raise ConfigurationError(f"external client {client_id} has unsupported capabilities")
        for candidate in (token, previous):
            if candidate is not None:
                if candidate in seen_tokens:
                    raise ConfigurationError("external client credentials must be unique")
                seen_tokens.add(candidate)
        clients.append(ExternalClientCredential(client_id, token, capability_set, enabled, previous))
    return tuple(clients)


def _oauth_clients_from_env(raw: str | None) -> tuple[OAuthClient, ...]:
    try:
        payload = json.loads(raw or "{}")
        if not isinstance(payload, dict):raise ValueError("object required")
        clients = []
        identities = set()
        for client_id, value in payload.items():
            if not isinstance(value, dict) or set(value) != {"identity_client_id", "redirect_uris"}:raise ValueError("invalid client fields")
            if not isinstance(value["redirect_uris"], list):raise ValueError("redirect list required")
            client = OAuthClient(client_id, value["identity_client_id"], tuple(value["redirect_uris"]))
            if client.identity_client_id in identities:raise ValueError("duplicate internal identity")
            identities.add(client.identity_client_id)
            clients.append(client)
        return tuple(clients)
    except (ValueError, TypeError, KeyError):
        raise ConfigurationError("invalid explicit OAuth client registry") from None


@dataclass(frozen=True)
class Settings:
    database_path: Path
    timezone: str
    host: str
    port: int
    busy_timeout_ms: int
    ui_token: str | None = None
    scheduler_token: str | None = None
    hermes_token: str | None = None
    cors_origins: tuple[str, ...] = ()
    scheduler_interval_seconds: int = 3600
    external_clients: tuple[ExternalClientCredential, ...] = ()
    oauth_clients: tuple[OAuthClient, ...] = ()

    def __post_init__(self):
        identities=[c.identity_client_id for c in self.oauth_clients]
        client_ids=[c.oauth_client_id for c in self.oauth_clients]
        legacy={"CLIENT:"+c.client_id for c in self.external_clients} | {"CLIENT:hermes"}
        if len(set(identities))!=len(identities) or len(set(client_ids))!=len(client_ids) or legacy & set(identities):
            raise ConfigurationError("OAuth identities must be unique and separate from legacy clients")

    @classmethod
    def from_env(cls) -> "Settings":
        raw_path = os.environ.get("FINANCE_V2_DATABASE_PATH", "data/finance_v2.sqlite3")
        path = Path(raw_path)
        if not path.is_absolute():
            path = PROJECT_ROOT / path
        timezone = os.environ.get("APP_TIMEZONE")
        if not timezone:
            raise ConfigurationError("APP_TIMEZONE is required")
        try:
            ZoneInfo(timezone)
        except ZoneInfoNotFoundError as exc:
            raise ConfigurationError(f"invalid APP_TIMEZONE: {timezone}") from exc
        try:
            port = int(os.environ.get("FINANCE_V2_PORT", "8766"))
            busy_timeout_ms = int(os.environ.get("FINANCE_V2_BUSY_TIMEOUT_MS", "5000"))
            scheduler_interval_seconds = int(os.environ.get("FINANCE_V2_SCHEDULER_INTERVAL_SECONDS", "3600"))
        except ValueError as exc:
            raise ConfigurationError("port and busy timeout must be integers") from exc
        if not 1 <= port <= 65535:
            raise ConfigurationError("FINANCE_V2_PORT must be between 1 and 65535")
        if busy_timeout_ms < 0:
            raise ConfigurationError("FINANCE_V2_BUSY_TIMEOUT_MS cannot be negative")
        if scheduler_interval_seconds <= 0:
            raise ConfigurationError("FINANCE_V2_SCHEDULER_INTERVAL_SECONDS must be positive")
        return cls(
            database_path=path.resolve(),
            timezone=timezone,
            host=os.environ.get("FINANCE_V2_HOST", "127.0.0.1"),
            port=port,
            busy_timeout_ms=busy_timeout_ms,
            scheduler_interval_seconds=scheduler_interval_seconds,
            ui_token=os.environ.get("FINANCE_V2_UI_TOKEN"),
            scheduler_token=os.environ.get("FINANCE_V2_SCHEDULER_TOKEN"),
            hermes_token=os.environ.get("FINANCE_V2_HERMES_TOKEN"),
            cors_origins=tuple(origin.strip() for origin in os.environ.get("FINANCE_V2_CORS_ORIGINS", "").split(",") if origin.strip()),
            external_clients=_external_clients_from_env(os.environ.get("FINANCE_V2_EXTERNAL_CLIENTS_JSON")),
            oauth_clients=_oauth_clients_from_env(os.environ.get("FINANCE_V2_OAUTH_CLIENTS_JSON")),
        )
