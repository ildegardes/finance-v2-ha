from __future__ import annotations

from datetime import timedelta
import json
import sqlite3
from typing import Any, Callable

from ..db import immediate_transaction
from ..idempotency import IdempotencyConflict, canonical_payload_hash, validate_key
from .clock import Clock, utc_text


def execute_financial(
    connection: sqlite3.Connection,
    *,
    client_id: str,
    operation: str,
    key: str,
    payload: Any,
    clock: Clock,
    effect: Callable[[], tuple[str, int, dict[str, Any]]],
) -> tuple[dict[str, Any], bool]:
    """Execute cache, permanent identity and effect in one BEGIN IMMEDIATE."""
    validate_key(key)
    if not client_id.strip() or not operation.strip():
        raise ValueError("authenticated client and operation are required")
    fingerprint = canonical_payload_hash(payload)
    with immediate_transaction(connection):
        cached = connection.execute(
            "SELECT request_hash,state,response_json FROM idempotency_records WHERE client_id=? AND operation=? AND idempotency_key=?",
            (client_id, operation, key),
        ).fetchone()
        if cached:
            if cached["request_hash"] != fingerprint:
                raise IdempotencyConflict("same scoped key was used with a different payload")
            if cached["state"] == "COMPLETED":
                return json.loads(cached["response_json"]), True
        permanent = connection.execute(
            "SELECT request_hash,resource_type,resource_id FROM permanent_operation_keys WHERE client_id=? AND operation=? AND operation_key=?",
            (client_id, operation, key),
        ).fetchone()
        if permanent:
            if permanent["request_hash"] != fingerprint:
                raise IdempotencyConflict("permanent key payload conflict")
            return {"resource_type": permanent["resource_type"], "resource_id": permanent["resource_id"]}, True
        now = clock.now_utc()
        if not cached:
            connection.execute(
                "INSERT INTO idempotency_records(client_id,operation,idempotency_key,request_hash,state,created_at,expires_at) VALUES(?,?,?,?, 'IN_PROGRESS',?,?)",
                (client_id, operation, key, fingerprint, utc_text(now), utc_text(now + timedelta(days=90))),
            )
        resource_type, resource_id, response = effect()
        connection.execute(
            "INSERT INTO permanent_operation_keys(client_id,operation,operation_key,request_hash,resource_type,resource_id,correlation_id,created_at) VALUES(?,?,?,?,?,?,?,?)",
            (client_id, operation, key, fingerprint, resource_type, resource_id, response.get("correlation_id"), utc_text(now)),
        )
        response_json = json.dumps(response, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        connection.execute(
            "UPDATE idempotency_records SET state='COMPLETED',response_json=?,completed_at=? WHERE client_id=? AND operation=? AND idempotency_key=?",
            (response_json, utc_text(now), client_id, operation, key),
        )
        return response, False
