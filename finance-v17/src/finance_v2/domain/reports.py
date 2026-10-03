from __future__ import annotations

from datetime import date
import sqlite3

from .invoices import effective_total, paid_cents

def revenue_expected(connection, start: date, end: date) -> int:
    return connection.execute("SELECT COALESCE(SUM(amount_cents),0) FROM revenues WHERE lifecycle_state='ACTIVE' AND expected_on BETWEEN ? AND ?", (start.isoformat(), end.isoformat())).fetchone()[0]

def revenue_received(connection, start: date, end: date) -> int:
    return connection.execute("SELECT COALESCE(SUM(amount_cents),0) FROM revenue_receipts WHERE reversed_at IS NULL AND received_on BETWEEN ? AND ?", (start.isoformat(), end.isoformat())).fetchone()[0]


def revenue_realized(connection, start: date, end: date) -> int:
    """Cash flow by receipt/reversal date, not by current receipt status."""
    return connection.execute(
        "SELECT COALESCE(SUM(CASE WHEN received_on BETWEEN ? AND ? THEN amount_cents ELSE 0 END),0) "
        "- COALESCE(SUM(CASE WHEN reversed_on BETWEEN ? AND ? THEN amount_cents ELSE 0 END),0) FROM revenue_receipts",
        (start.isoformat(), end.isoformat(), start.isoformat(), end.isoformat()),
    ).fetchone()[0]


def recognized_expenses(connection: sqlite3.Connection, start: date, end: date, *, include_cancelled: bool = False) -> int:
    states = ("ACTIVE", "CANCELLED") if include_cancelled else ("ACTIVE",)
    marks = ",".join("?" for _ in states)
    return connection.execute(
        f"SELECT COALESCE(SUM(amount_cents),0) FROM expenses WHERE lifecycle_state IN ({marks}) AND expense_date BETWEEN ? AND ?",
        (*states, start.isoformat(), end.isoformat()),
    ).fetchone()[0]


def pending_total(connection: sqlite3.Connection, start: date, end: date) -> int:
    direct = connection.execute(
        "SELECT COALESCE(SUM(e.amount_cents),0) FROM expenses e WHERE e.lifecycle_state='ACTIVE' "
        "AND e.planned_payment_method<>'CREDIT_CARD' AND e.due_date BETWEEN ? AND ? "
        "AND NOT EXISTS(SELECT 1 FROM expense_payments p WHERE p.expense_id=e.id AND p.reversed_at IS NULL)",
        (start.isoformat(), end.isoformat()),
    ).fetchone()[0]
    invoice_total = 0
    invoices = connection.execute(
        "SELECT id,state FROM invoices WHERE state IN('OPEN','CLOSED','PAID') AND due_date BETWEEN ? AND ?",
        (start.isoformat(), end.isoformat()),
    ).fetchall()
    for invoice in invoices:
        invoice_total += max(0, effective_total(connection, invoice["id"]) - paid_cents(connection, invoice["id"]))
    return direct + invoice_total


def overdue_total(connection: sqlite3.Connection, today: date) -> int:
    return pending_total(connection, date.min, today.fromordinal(today.toordinal() - 1))


def net_paid(connection: sqlite3.Connection, start: date, end: date) -> int:
    parameters = (start.isoformat(), end.isoformat(), start.isoformat(), end.isoformat())
    expense_flow = connection.execute(
        "SELECT COALESCE(SUM(CASE WHEN paid_on BETWEEN ? AND ? THEN amount_cents ELSE 0 END),0) "
        "- COALESCE(SUM(CASE WHEN reversed_on BETWEEN ? AND ? THEN amount_cents ELSE 0 END),0) FROM expense_payments",
        parameters,
    ).fetchone()[0]
    invoice_flow = connection.execute(
        "SELECT COALESCE(SUM(CASE WHEN paid_on BETWEEN ? AND ? THEN amount_cents ELSE 0 END),0) "
        "- COALESCE(SUM(CASE WHEN reversed_on BETWEEN ? AND ? THEN amount_cents ELSE 0 END),0) FROM invoice_payments",
        parameters,
    ).fetchone()[0]
    return expense_flow + invoice_flow


def requires_attention(connection: sqlite3.Connection, obligation_type: str, obligation_id: int) -> bool:
    if obligation_type == "EXPENSE":
        obligation = connection.execute("SELECT lifecycle_state,planned_payment_method,account_id FROM expenses WHERE id=?", (obligation_id,)).fetchone()
        paid = connection.execute("SELECT 1 FROM expense_payments WHERE expense_id=? AND reversed_at IS NULL", (obligation_id,)).fetchone()
        if not obligation or obligation["lifecycle_state"] != "ACTIVE" or paid or obligation["planned_payment_method"] != "AUTO_DEBIT": return False
        account_id = obligation["account_id"]
    elif obligation_type == "INVOICE":
        obligation = connection.execute("SELECT state,payment_mode,payment_account_id FROM invoices WHERE id=?", (obligation_id,)).fetchone()
        if not obligation or obligation["state"] not in {"OPEN", "CLOSED"} or obligation["payment_mode"] != "AUTO_DEBIT": return False
        account_id = obligation["payment_account_id"]
    else:
        return False
    account = connection.execute("SELECT active FROM accounts WHERE id=?", (account_id,)).fetchone()
    if not account or not account[0]: return True
    latest = connection.execute(
        "SELECT ae.result FROM settlements s LEFT JOIN settlements successor ON successor.supersedes_settlement_id=s.id "
        "LEFT JOIN automation_executions ae ON ae.settlement_id=s.id "
        "WHERE s.obligation_type=? AND s.obligation_id=? AND successor.id IS NULL ORDER BY ae.id DESC LIMIT 1",
        (obligation_type, obligation_id),
    ).fetchone()
    return bool(latest and latest[0] == "REQUIRES_ATTENTION")


def requires_manual_action(connection: sqlite3.Connection, obligation_type: str, obligation_id: int) -> bool:
    """Derive the V16 manual-action flag; it is never stored as a projection."""
    if obligation_type == "EXPENSE":
        obligation = connection.execute("SELECT lifecycle_state,planned_payment_method FROM expenses WHERE id=?", (obligation_id,)).fetchone()
        if not obligation or obligation["lifecycle_state"] != "ACTIVE": return False
        if connection.execute("SELECT 1 FROM expense_payments WHERE expense_id=? AND reversed_at IS NULL", (obligation_id,)).fetchone(): return False
        return obligation["planned_payment_method"] in {"PIX", "DEBIT", "CASH", "BANK_SLIP", "BANK_TRANSFER"}
    if obligation_type == "INVOICE":
        obligation = connection.execute("SELECT state,payment_mode FROM invoices WHERE id=?", (obligation_id,)).fetchone()
        if not obligation or obligation["state"] not in {"OPEN", "CLOSED"}: return False
        return obligation["payment_mode"] == "MANUAL" and effective_total(connection, obligation_id) > paid_cents(connection, obligation_id)
    return False
