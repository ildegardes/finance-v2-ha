from __future__ import annotations

import sqlite3

from ..db import immediate_transaction
from .clock import Clock, utc_text
from .errors import Conflict, ValidationError
from .support import require_row


def create_settlement(connection: sqlite3.Connection, *, settlement_key: str, obligation_type: str, obligation_id: int, actor: str, clock: Clock, supersedes_settlement_id: int | None = None) -> int:
    if obligation_type not in {"EXPENSE", "INVOICE"} or not settlement_key.strip():
        raise ValidationError("invalid settlement identity")
    with immediate_transaction(connection):
        if supersedes_settlement_id is not None:
            previous = require_row(connection, "SELECT * FROM settlements WHERE id=?", (supersedes_settlement_id,), "settlement")
            if previous["obligation_type"] != obligation_type or previous["obligation_id"] != obligation_id:
                raise Conflict("settlement successor must keep the same obligation")
        return connection.execute("INSERT INTO settlements(settlement_key,obligation_type,obligation_id,supersedes_settlement_id,created_at,actor) VALUES(?,?,?,?,?,?)", (settlement_key, obligation_type, obligation_id, supersedes_settlement_id, utc_text(clock.now_utc()), actor)).lastrowid


def record_execution(connection: sqlite3.Connection, *, settlement_id: int, attempt_group_key: str, attempt_number: int, result: str, error_code: str | None, clock: Clock) -> int:
    if attempt_number not in {1, 2, 3}:
        raise ValidationError("automatic retry is limited to three attempts")
    if result not in {"SUCCESS", "RETRYABLE_FAILURE", "REQUIRES_ATTENTION", "SKIPPED"}:
        raise ValidationError("invalid automation result")
    if (result in {"SUCCESS", "SKIPPED"}) != (error_code is None):
        raise ValidationError("error code/result mismatch")
    if result == "RETRYABLE_FAILURE" and attempt_number == 3:
        result = "REQUIRES_ATTENTION"
    with immediate_transaction(connection):
        require_row(connection, "SELECT id FROM settlements WHERE id=?", (settlement_id,), "settlement")
        now = utc_text(clock.now_utc())
        return connection.execute("INSERT INTO automation_executions(settlement_id,attempt_group_key,attempt_number,result,started_at,finished_at,error_code) VALUES(?,?,?,?,?,?,?)", (settlement_id, attempt_group_key, attempt_number, result, now, now, error_code)).lastrowid
