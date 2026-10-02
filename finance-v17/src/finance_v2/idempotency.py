from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
import re
import sqlite3
from typing import Any

from .db import immediate_transaction


KEY_PATTERN = re.compile(r"^[!-~]{16,128}$")


class IdempotencyConflict(RuntimeError):
    pass


class InvalidIdempotencyKey(ValueError):
    pass


@dataclass(frozen=True)
class ReplayResult:
    replayed: bool
    response: Any | None


def canonical_payload_hash(payload: Any) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return sha256(encoded).hexdigest()


def validate_key(key: str) -> None:
    if not KEY_PATTERN.fullmatch(key):
        raise InvalidIdempotencyKey("key must contain 16..128 visible ASCII characters")


def _utc_text(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class IdempotencyStore:
    def __init__(self, connection: sqlite3.Connection, retention_days: int = 90):
        if retention_days < 90:
            raise ValueError("V16 requires retention of at least 90 days")
        self.connection = connection
        self.retention_days = retention_days

    def reserve_or_replay(self, client_id: str, operation: str, key: str, payload: Any) -> ReplayResult:
        validate_key(key)
        if not client_id.strip() or not operation.strip():
            raise ValueError("authenticated client and operation are required")
        request_hash = canonical_payload_hash(payload)
        now = datetime.now(timezone.utc).replace(microsecond=0)
        with immediate_transaction(self.connection):
            row = self.connection.execute(
                "SELECT request_hash,state,response_json FROM idempotency_records "
                "WHERE client_id=? AND operation=? AND idempotency_key=?",
                (client_id, operation, key),
            ).fetchone()
            if row:
                if row["request_hash"] != request_hash:
                    raise IdempotencyConflict("same scoped key was used with a different payload")
                if row["state"] == "COMPLETED":
                    return ReplayResult(True, json.loads(row["response_json"]))
                return ReplayResult(True, None)
            self.connection.execute(
                "INSERT INTO idempotency_records(client_id,operation,idempotency_key,request_hash,state,created_at,expires_at) "
                "VALUES(?,?,?,?, 'IN_PROGRESS',?,?)",
                (client_id, operation, key, request_hash, _utc_text(now), _utc_text(now + timedelta(days=self.retention_days))),
            )
        return ReplayResult(False, None)

    def complete(self, client_id: str, operation: str, key: str, payload: Any, response: Any) -> None:
        request_hash = canonical_payload_hash(payload)
        response_json = json.dumps(response, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        now = _utc_text(datetime.now(timezone.utc).replace(microsecond=0))
        with immediate_transaction(self.connection):
            row = self.connection.execute(
                "SELECT request_hash,state FROM idempotency_records WHERE client_id=? AND operation=? AND idempotency_key=?",
                (client_id, operation, key),
            ).fetchone()
            if not row:
                raise LookupError("idempotency reservation does not exist")
            if row["request_hash"] != request_hash:
                raise IdempotencyConflict("payload differs from the reservation")
            if row["state"] == "COMPLETED":
                return
            self.connection.execute(
                "UPDATE idempotency_records SET state='COMPLETED',response_json=?,completed_at=? "
                "WHERE client_id=? AND operation=? AND idempotency_key=?",
                (response_json, now, client_id, operation, key),
            )

    def reserve_permanent_operation(
        self,
        client_id: str,
        operation: str,
        key: str,
        payload: Any,
        resource_type: str,
        resource_id: int,
        correlation_id: str | None = None,
    ) -> bool:
        """Reserve a permanent financial-operation identity inside the caller's transaction.

        Returns False for an exact replay and raises on payload conflict. The caller must
        wrap this method and the financial effect in one ``immediate_transaction``.
        """
        validate_key(key)
        if not client_id.strip() or not operation.strip() or not resource_type.strip():
            raise ValueError("client, operation and resource type are required")
        if not self.connection.in_transaction:
            raise RuntimeError("permanent operation reservation requires an active transaction")
        request_hash = canonical_payload_hash(payload)
        row = self.connection.execute(
            "SELECT request_hash FROM permanent_operation_keys "
            "WHERE client_id=? AND operation=? AND operation_key=?",
            (client_id, operation, key),
        ).fetchone()
        if row:
            if row["request_hash"] != request_hash:
                raise IdempotencyConflict("permanent operation key was used with a different payload")
            return False
        now = _utc_text(datetime.now(timezone.utc).replace(microsecond=0))
        self.connection.execute(
            "INSERT INTO permanent_operation_keys(client_id,operation,operation_key,request_hash,resource_type,resource_id,correlation_id,created_at) "
            "VALUES(?,?,?,?,?,?,?,?)",
            (client_id, operation, key, request_hash, resource_type, resource_id, correlation_id, now),
        )
        return True
