from __future__ import annotations

import sqlite3

from ..db import immediate_transaction
from .clock import Clock, utc_text
from .errors import AutoDebitRequiresAttention, Conflict, InvalidState
from .invoices import effective_total, normalize_invoice_state, paid_cents
from .reports import requires_attention
from .support import audit_event, require_row
from .idempotent import execute_financial


def _execution(connection, settlement_id, group, number, result, error, clock):
    now = utc_text(clock.now_utc())
    return connection.execute(
        "INSERT INTO automation_executions(settlement_id,attempt_group_key,attempt_number,result,started_at,finished_at,error_code) VALUES(?,?,?,?,?,?,?)",
        (settlement_id, group, number, result, now, now, error),
    ).lastrowid


def _settlement(connection, key, obligation_type, obligation_id, clock, supersedes=None):
    existing = connection.execute("SELECT * FROM settlements WHERE settlement_key=?", (key,)).fetchone()
    if existing:
        return existing["id"], False
    return connection.execute(
        "INSERT INTO settlements(settlement_key,obligation_type,obligation_id,supersedes_settlement_id,created_at,actor) VALUES(?,?,?,?,?,'SCHEDULER:internal')",
        (key, obligation_type, obligation_id, supersedes, utc_text(clock.now_utc())),
    ).lastrowid, True


def execute_expense_auto_debit(connection: sqlite3.Connection, *, expense_id: int, attempt_group_key: str, attempt_number: int, clock: Clock) -> str:
    with immediate_transaction(connection):
        expense = require_row(connection, "SELECT * FROM expenses WHERE id=?", (expense_id,), "expense")
        key = f"expense:{expense_id}:auto-settlement"
        settlement_id, created = _settlement(connection, key, "EXPENSE", expense_id, clock)
        previous = connection.execute("SELECT result FROM automation_executions WHERE settlement_id=? ORDER BY id DESC LIMIT 1", (settlement_id,)).fetchone()
        terminal_attention = connection.execute("SELECT 1 FROM automation_executions WHERE settlement_id=? AND result='REQUIRES_ATTENTION' LIMIT 1", (settlement_id,)).fetchone()
        if previous and previous[0] == "SUCCESS": return "SUCCESS"
        if terminal_attention:
            if previous and previous[0] != "SKIPPED": _execution(connection, settlement_id, attempt_group_key, attempt_number, "SKIPPED", None, clock)
            return "SKIPPED"
        active_payment = connection.execute("SELECT 1 FROM expense_payments WHERE expense_id=? AND reversed_at IS NULL", (expense_id,)).fetchone()
        if expense["lifecycle_state"] != "ACTIVE" or active_payment:
            _execution(connection, settlement_id, attempt_group_key, attempt_number, "SKIPPED", None, clock)
            return "SKIPPED"
        if expense["due_date"] is None or expense["due_date"] > clock.today().isoformat():
            _execution(connection, settlement_id, attempt_group_key, attempt_number, "SKIPPED", None, clock)
            return "SKIPPED"
        account = connection.execute("SELECT active FROM accounts WHERE id=?", (expense["account_id"],)).fetchone()
        if expense["planned_payment_method"] != "AUTO_DEBIT" or not account or not account[0]:
            _execution(connection, settlement_id, attempt_group_key, attempt_number, "REQUIRES_ATTENTION", "INACTIVE_ACCOUNT", clock)
            return "REQUIRES_ATTENTION"
        payment_id = connection.execute(
            "INSERT INTO expense_payments(expense_id,amount_cents,paid_on,payment_method,account_id,source,settlement_id,correlation_id) VALUES(?,?,?,'AUTO_DEBIT',?,'AUTOMATIC',?,?)",
            (expense_id, expense["amount_cents"], clock.today().isoformat(), expense["account_id"], settlement_id, attempt_group_key),
        ).lastrowid
        _execution(connection, settlement_id, attempt_group_key, attempt_number, "SUCCESS", None, clock)
        audit_event(connection, "EXPENSE", expense_id, "AUTO_PAYMENT_CREATED", "SCHEDULER:internal", attempt_group_key, clock, {"payment_id": payment_id, "settlement_id": settlement_id})
        return "SUCCESS"


def execute_invoice_auto_debit(connection: sqlite3.Connection, *, invoice_id: int, attempt_group_key: str, attempt_number: int, clock: Clock) -> str:
    with immediate_transaction(connection):
        invoice = require_row(connection, "SELECT * FROM invoices WHERE id=?", (invoice_id,), "invoice")
        key = f"invoice:{invoice_id}:due:{invoice['due_date']}:auto-settlement"
        settlement_id, _ = _settlement(connection, key, "INVOICE", invoice_id, clock)
        previous = connection.execute("SELECT result FROM automation_executions WHERE settlement_id=? ORDER BY id DESC LIMIT 1", (settlement_id,)).fetchone()
        terminal_attention = connection.execute("SELECT 1 FROM automation_executions WHERE settlement_id=? AND result='REQUIRES_ATTENTION' LIMIT 1", (settlement_id,)).fetchone()
        if previous and previous[0] == "SUCCESS": return "SUCCESS"
        if terminal_attention:
            if previous and previous[0] != "SKIPPED": _execution(connection, settlement_id, attempt_group_key, attempt_number, "SKIPPED", None, clock)
            return "SKIPPED"
        if invoice["due_date"] > clock.today().isoformat():
            _execution(connection, settlement_id, attempt_group_key, attempt_number, "SKIPPED", None, clock)
            return "SKIPPED"
        if invoice["state"] == "OPEN" and clock.today().isoformat() > invoice["closing_date"]:
            total = effective_total(connection, invoice_id)
            if total == 0:
                connection.execute("UPDATE invoices SET state='CANCELLED',cancelled_at=? WHERE id=?", (utc_text(clock.now_utc()), invoice_id))
                _execution(connection, settlement_id, attempt_group_key, attempt_number, "SKIPPED", None, clock)
                return "SKIPPED"
            connection.execute("UPDATE invoices SET state='CLOSED',closed_total_cents=?,closed_at=? WHERE id=?", (total, utc_text(clock.now_utc()), invoice_id))
            invoice = connection.execute("SELECT * FROM invoices WHERE id=?", (invoice_id,)).fetchone()
        balance = effective_total(connection, invoice_id) - paid_cents(connection, invoice_id) if invoice["state"] in {"CLOSED", "PAID"} else 0
        if invoice["state"] != "CLOSED" or balance <= 0:
            _execution(connection, settlement_id, attempt_group_key, attempt_number, "SKIPPED", None, clock); return "SKIPPED"
        account = connection.execute("SELECT active FROM accounts WHERE id=?", (invoice["payment_account_id"],)).fetchone()
        if invoice["payment_mode"] != "AUTO_DEBIT" or not account or not account[0]:
            _execution(connection, settlement_id, attempt_group_key, attempt_number, "REQUIRES_ATTENTION", "INACTIVE_ACCOUNT", clock); return "REQUIRES_ATTENTION"
        payment_id = connection.execute(
            "INSERT INTO invoice_payments(invoice_id,amount_cents,paid_on,payment_method,account_id,source,settlement_id,correlation_id) VALUES(?,?,?,'AUTO_DEBIT',?,'AUTOMATIC',?,?)",
            (invoice_id, balance, clock.today().isoformat(), invoice["payment_account_id"], settlement_id, attempt_group_key),
        ).lastrowid
        normalize_invoice_state(connection, invoice_id, clock)
        _execution(connection, settlement_id, attempt_group_key, attempt_number, "SUCCESS", None, clock)
        audit_event(connection, "INVOICE", invoice_id, "AUTO_PAYMENT_CREATED", "SCHEDULER:internal", attempt_group_key, clock, {"payment_id": payment_id, "settlement_id": settlement_id})
        return "SUCCESS"


def reverse_auto_payment(connection: sqlite3.Connection, *, obligation_type: str, payment_id: int, reason: str, actor: str, correlation_id: str, clock: Clock) -> None:
    table = "expense_payments" if obligation_type == "EXPENSE" else "invoice_payments"
    owner = "expense_id" if obligation_type == "EXPENSE" else "invoice_id"
    with immediate_transaction(connection):
        payment = require_row(connection, f"SELECT * FROM {table} WHERE id=?", (payment_id,), "payment")
        if payment["source"] != "AUTOMATIC" or payment["reversed_at"] is not None: raise Conflict("automatic payment cannot be reversed")
        connection.execute(f"UPDATE {table} SET reversed_at=?,reversed_on=?,reversed_by_actor=?,reversal_reason=? WHERE id=?", (utc_text(clock.now_utc()), clock.today().isoformat(), actor, reason, payment_id))
        if obligation_type == "INVOICE": normalize_invoice_state(connection, payment[owner], clock)
        group = f"reversal:{correlation_id}"
        last_attempt = connection.execute("SELECT COALESCE(MAX(attempt_number),0) FROM automation_executions WHERE settlement_id=? AND attempt_group_key=?", (payment["settlement_id"], group)).fetchone()[0]
        _execution(connection, payment["settlement_id"], group, last_attempt + 1, "REQUIRES_ATTENTION", "AUTO_SETTLEMENT_REVERSED", clock)
        audit_event(connection, obligation_type, payment[owner], "AUTO_PAYMENT_REVERSED", actor, correlation_id, clock, {"payment_id": payment_id})


def reverse_auto_payment_idempotent(connection: sqlite3.Connection, *, obligation_type: str, payment_id: int, reason: str, actor: str, correlation_id: str, clock: Clock, client_id: str, idempotency_key: str) -> tuple[int,bool]:
    if obligation_type not in {"EXPENSE","INVOICE"}: raise Conflict("invalid obligation type")
    payload={"obligation_type":obligation_type,"payment_id":payment_id,"reason":reason}
    def effect():
        table="expense_payments" if obligation_type=="EXPENSE" else "invoice_payments";owner="expense_id" if obligation_type=="EXPENSE" else "invoice_id"
        payment=require_row(connection,f"SELECT * FROM {table} WHERE id=?",(payment_id,),"payment")
        if payment["source"]!="AUTOMATIC" or payment["reversed_at"] is not None: raise Conflict("automatic payment cannot be reversed")
        connection.execute(f"UPDATE {table} SET reversed_at=?,reversed_on=?,reversed_by_actor=?,reversal_reason=? WHERE id=?",(utc_text(clock.now_utc()),clock.today().isoformat(),actor,reason,payment_id))
        if obligation_type=="INVOICE": normalize_invoice_state(connection,payment[owner],clock)
        group=f"reversal:{correlation_id}";last=connection.execute("SELECT COALESCE(MAX(attempt_number),0) FROM automation_executions WHERE settlement_id=? AND attempt_group_key=?",(payment["settlement_id"],group)).fetchone()[0]
        _execution(connection,payment["settlement_id"],group,last+1,"REQUIRES_ATTENTION","AUTO_SETTLEMENT_REVERSED",clock)
        audit_event(connection,obligation_type,payment[owner],"AUTO_PAYMENT_REVERSED",actor,correlation_id,clock,{"payment_id":payment_id})
        return "AUTO_PAYMENT_REVERSAL",payment_id,{"payment_id":payment_id,"correlation_id":correlation_id}
    response,replayed=execute_financial(connection,client_id=client_id,operation="reverse_auto_payment",key=idempotency_key,payload=payload,clock=clock,effect=effect)
    return int(response.get("payment_id",response.get("resource_id"))),replayed


def reactivate_auto_settlement(connection: sqlite3.Connection, *, previous_settlement_id: int, new_settlement_key: str, actor: str, correlation_id: str, clock: Clock) -> int:
    with immediate_transaction(connection):
        previous = require_row(connection, "SELECT * FROM settlements WHERE id=?", (previous_settlement_id,), "settlement")
        latest=connection.execute("SELECT result FROM automation_executions WHERE settlement_id=? ORDER BY id DESC LIMIT 1",(previous_settlement_id,)).fetchone()
        if not latest or latest["result"]!="REQUIRES_ATTENTION": raise AutoDebitRequiresAttention("settlement is not awaiting explicit reactivation")
        successor = connection.execute("SELECT id FROM settlements WHERE supersedes_settlement_id=?", (previous_settlement_id,)).fetchone()
        if successor: return successor[0]
        settlement_id = connection.execute("INSERT INTO settlements(settlement_key,obligation_type,obligation_id,supersedes_settlement_id,created_at,actor) VALUES(?,?,?,?,?,?)", (new_settlement_key, previous["obligation_type"], previous["obligation_id"], previous_settlement_id, utc_text(clock.now_utc()), actor)).lastrowid
        audit_event(connection, previous["obligation_type"], previous["obligation_id"], "AUTO_SETTLEMENT_REACTIVATED", actor, correlation_id, clock, {"old_settlement_id": previous_settlement_id, "new_settlement_id": settlement_id})
        return settlement_id


def reactivate_auto_settlement_idempotent(connection: sqlite3.Connection, *, previous_settlement_id: int, new_settlement_key: str, actor: str, correlation_id: str, clock: Clock, client_id: str, idempotency_key: str) -> tuple[int,bool]:
    payload={"previous_settlement_id":previous_settlement_id,"new_settlement_key":new_settlement_key}
    def effect():
        previous=require_row(connection,"SELECT * FROM settlements WHERE id=?",(previous_settlement_id,),"settlement")
        latest=connection.execute("SELECT result FROM automation_executions WHERE settlement_id=? ORDER BY id DESC LIMIT 1",(previous_settlement_id,)).fetchone()
        if not latest or latest["result"]!="REQUIRES_ATTENTION": raise AutoDebitRequiresAttention("settlement is not awaiting explicit reactivation")
        if connection.execute("SELECT id FROM settlements WHERE supersedes_settlement_id=?",(previous_settlement_id,)).fetchone(): raise Conflict("settlement already reactivated")
        settlement_id=connection.execute("INSERT INTO settlements(settlement_key,obligation_type,obligation_id,supersedes_settlement_id,created_at,actor) VALUES(?,?,?,?,?,?)",(new_settlement_key,previous["obligation_type"],previous["obligation_id"],previous_settlement_id,utc_text(clock.now_utc()),actor)).lastrowid
        audit_event(connection,previous["obligation_type"],previous["obligation_id"],"AUTO_SETTLEMENT_REACTIVATED",actor,correlation_id,clock,{"old_settlement_id":previous_settlement_id,"new_settlement_id":settlement_id})
        return "SETTLEMENT",settlement_id,{"settlement_id":settlement_id,"previous_settlement_id":previous_settlement_id,"correlation_id":correlation_id}
    response,replayed=execute_financial(connection,client_id=client_id,operation="reactivate_auto_settlement",key=idempotency_key,payload=payload,clock=clock,effect=effect)
    return int(response.get("settlement_id",response.get("resource_id"))),replayed
