from __future__ import annotations

import json
import sqlite3
from typing import Any

from .clock import Clock, utc_text
from .errors import InactiveAccount, NotFound, ValidationError


def require_row(connection: sqlite3.Connection, query: str, parameters: tuple[Any, ...], name: str) -> sqlite3.Row:
    row = connection.execute(query, parameters).fetchone()
    if not row:
        raise NotFound(f"{name} not found")
    return row


def require_active(connection: sqlite3.Connection, table: str, entity_id: int) -> sqlite3.Row:
    if table not in {"accounts", "categories", "cards", "tags"}:
        raise ValueError("unsupported active entity")
    row = require_row(connection, f"SELECT * FROM {table} WHERE id=?", (entity_id,), table[:-1])
    if not row["active"]:
        if table == "accounts":
            raise InactiveAccount("account is inactive")
        raise ValidationError(f"{table[:-1]} is inactive")
    return row


def audit_event(connection: sqlite3.Connection, entity_type: str, entity_id: int, event_type: str, actor: str, correlation_id: str, clock: Clock, metadata: dict | None = None) -> int:
    if not actor.strip() or not correlation_id.strip():
        raise ValidationError("actor and correlation are required")
    required_metadata = {
        "PAYMENT_REPLACED": {"old_payment_id", "new_payment_id"},
        "INVOICE_ITEM_MOVED": {"expense_id", "from_invoice_id", "to_invoice_id", "amount_cents", "from_total", "to_total"},
    }
    required = required_metadata.get(event_type)
    if required and (not isinstance(metadata, dict) or any(metadata.get(field) is None for field in required)):
        raise ValidationError(f"incomplete metadata for {event_type}")
    cursor = connection.execute(
        "INSERT INTO lifecycle_events(entity_type,entity_id,event_type,actor,correlation_id,metadata_schema_version,metadata_json,created_at) VALUES(?,?,?,?,?,1,?,?)",
        (entity_type, entity_id, event_type, actor, correlation_id, json.dumps(metadata, sort_keys=True, separators=(",", ":")) if metadata is not None else None, utc_text(clock.now_utc())),
    )
    return cursor.lastrowid
