from __future__ import annotations

from datetime import date
from contextlib import nullcontext
import sqlite3

from ..db import immediate_transaction
from .calendar import add_months
from .clock import Clock, utc_text
from .errors import ActivePaymentExists, Conflict, InvalidState, ValidationError
from .invoices import effective_total, get_or_create_open_invoice, normalize_invoice_state, paid_cents
from .money import distribute_installments
from .expenses import _validate_dependencies, active_payment
from .idempotent import execute_financial
from .support import audit_event, require_active, require_row


def create_installment_series(connection: sqlite3.Connection, *, purchase_date: date, card_id: int | None, total_cents: int, count: int, category_id: int, description: str, actor: str, correlation_id: str, clock: Clock, payment_method: str = "CREDIT_CARD", account_id: int | None = None, first_due_date: date | None = None, tags: tuple[int, ...] = ()) -> tuple[int, tuple[int, ...]]:
    if count > 60:
        raise ValidationError("A quantidade máxima permitida é de 60 parcelas.")
    amounts = distribute_installments(total_cents, count)
    # execute_financial owns the atomic transaction when a key is supplied.
    with (nullcontext() if connection.in_transaction else immediate_transaction(connection)):
        if not description.strip():
            raise ValidationError("description cannot be blank")
        _validate_dependencies(connection, payment_method, account_id, card_id)
        if payment_method == "CREDIT_CARD" and first_due_date is not None:
            raise ValidationError("card installments use invoice due dates")
        if payment_method != "CREDIT_CARD" and first_due_date is None:
            raise ValidationError("non-card installments require first due date")
        require_active(connection, "categories", category_id)
        for tag_id in tags:
            require_active(connection, "tags", tag_id)
        series_id = connection.execute(
            "INSERT INTO installment_series(purchase_date,card_id,original_total_cents,installment_count,payment_method,account_id,first_due_date) VALUES(?,?,?,?,?,?,?)",
            (purchase_date.isoformat(), card_id, total_cents, count, payment_method, account_id, first_due_date.isoformat() if first_due_date else None),
        ).lastrowid
        expense_ids = []
        now = utc_text(clock.now_utc())
        for index, amount in enumerate(amounts, start=1):
            competence = add_months(purchase_date, index - 1, purchase_date.day)
            invoice_id = get_or_create_open_invoice(connection, card_id, competence, clock) if payment_method == "CREDIT_CARD" else None
            due = add_months(first_due_date, index - 1, first_due_date.day).isoformat() if first_due_date else None
            expense_id = connection.execute(
                "INSERT INTO expenses(description,amount_cents,expense_date,due_date,planned_payment_method,category_id,account_id,card_id,invoice_id,installment_series_id,installment_number,lifecycle_state,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,'ACTIVE',?,?)",
                (f"{description.strip()} ({index}/{count})", amount, competence.isoformat(), due, payment_method, category_id, account_id, card_id, invoice_id, series_id, index, now, now),
            ).lastrowid
            for tag_id in tags:
                connection.execute("INSERT INTO expense_tags(expense_id,tag_id) VALUES(?,?)", (expense_id, tag_id))
            expense_ids.append(expense_id)
        audit_event(connection, "INSTALLMENT_SERIES", series_id, "CREATE", actor, correlation_id, clock, {"expense_ids": expense_ids})
        return series_id, tuple(expense_ids)


def create_installments_idempotent(connection, *, client_id, idempotency_key, **values):
    payload = {k:(v.isoformat() if isinstance(v,date) else v) for k,v in values.items() if k not in {"clock","actor","correlation_id"}}
    def effect():
        sid, ids = create_installment_series(connection, **values)
        return "INSTALLMENT_SERIES", sid, {"id":sid,"expense_ids":list(ids)}
    result, replay = execute_financial(connection, client_id=client_id, operation="installments_create", key=idempotency_key, payload=payload, clock=values["clock"], effect=effect)
    if "id" not in result:
        sid = result["resource_id"]
        result = {"id":sid,"expense_ids":[row[0] for row in connection.execute("SELECT id FROM expenses WHERE installment_series_id=? ORDER BY installment_number",(sid,))]}
    return result, replay


def cancel_remaining(connection: sqlite3.Connection, *, series_id: int, from_installment: int, actor: str, correlation_id: str, clock: Clock) -> None:
    with immediate_transaction(connection):
        series = require_row(connection, "SELECT * FROM installment_series WHERE id=?", (series_id,), "installment series")
        if series["ended_at"] is not None:
            if series["ended_from_installment"] == from_installment:
                return
            raise InvalidState("installment series is terminal")
        if not 1 <= from_installment <= series["installment_count"]:
            raise ValidationError("invalid installment cut")
        expenses = connection.execute(
            "SELECT * FROM expenses WHERE installment_series_id=? AND installment_number>=? ORDER BY installment_number",
            (series_id, from_installment),
        ).fetchall()
        for expense in expenses:
            if active_payment(connection, expense["id"]):
                raise ActivePaymentExists("paid installment blocks cancellation")
            if expense["lifecycle_state"] == "CANCELLED":
                continue
            if expense["invoice_id"] is None:
                connection.execute("UPDATE expenses SET lifecycle_state='CANCELLED',updated_at=? WHERE id=?", (utc_text(clock.now_utc()), expense["id"]))
                audit_event(connection, "EXPENSE", expense["id"], "CANCEL", actor, correlation_id, clock, {"installment_series_id": series_id})
                continue
            invoice = require_row(connection, "SELECT * FROM invoices WHERE id=?", (expense["invoice_id"],), "invoice")
            if invoice["state"] == "PAID" or invoice["state"] == "CANCELLED":
                raise InvalidState("protected invoice blocks installment cancellation")
            if invoice["state"] == "CLOSED":
                proposed = effective_total(connection, invoice["id"]) - expense["amount_cents"]
                if proposed < paid_cents(connection, invoice["id"]):
                    raise Conflict("cancellation would undercut invoice payments")
                previous = effective_total(connection, invoice["id"])
                connection.execute(
                    "INSERT INTO invoice_total_revisions(invoice_id,previous_total_cents,new_total_cents,reason_code,correlation_id,actor,created_at) VALUES(?,?,?,?,?,?,?)",
                    (invoice["id"], previous, proposed, "INSTALLMENT_CANCEL", correlation_id, actor, utc_text(clock.now_utc())),
                )
                connection.execute("UPDATE expenses SET lifecycle_state='CANCELLED',updated_at=? WHERE id=?", (utc_text(clock.now_utc()), expense["id"]))
                normalize_invoice_state(connection, invoice["id"], clock)
            elif invoice["state"] == "OPEN":
                connection.execute("UPDATE expenses SET lifecycle_state='CANCELLED',updated_at=? WHERE id=?", (utc_text(clock.now_utc()), expense["id"]))
            audit_event(connection, "EXPENSE", expense["id"], "CANCEL", actor, correlation_id, clock, {"installment_series_id": series_id})
        connection.execute("UPDATE installment_series SET ended_from_installment=?,ended_at=? WHERE id=?", (from_installment, utc_text(clock.now_utc()), series_id))
        audit_event(connection, "INSTALLMENT_SERIES", series_id, "END", actor, correlation_id, clock, {"from_installment": from_installment})
