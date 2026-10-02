from __future__ import annotations

from datetime import date
import sqlite3
from typing import Any

from ..db import immediate_transaction
from .clock import Clock, utc_text
from .errors import ActivePaymentExists, Conflict, InvalidState, NewDueDateRequired, ValidationError
from .idempotent import execute_financial
from .invoices import get_or_create_open_invoice, normalize_invoice_state
from .money import require_positive_cents
from .support import audit_event, require_active, require_row


NON_CARD_METHODS = {"PIX", "BANK_TRANSFER", "DEBIT", "CASH", "BANK_SLIP", "AUTO_DEBIT"}


def active_payment(connection: sqlite3.Connection, expense_id: int) -> sqlite3.Row | None:
    return connection.execute("SELECT * FROM expense_payments WHERE expense_id=? AND reversed_at IS NULL", (expense_id,)).fetchone()


def effective_status(connection: sqlite3.Connection, expense_id: int, today: date) -> str:
    expense = require_row(connection, "SELECT * FROM expenses WHERE id=?", (expense_id,), "expense")
    if expense["lifecycle_state"] == "CANCELLED":
        return "CANCELLED"
    if expense["lifecycle_state"] == "SUPERSEDED":
        return "SUPERSEDED"
    if expense["lifecycle_state"] == "DELETED":
        return "DELETED"
    if active_payment(connection, expense_id):
        return "PAID"
    return "OVERDUE" if expense["due_date"] is not None and expense["due_date"] < today.isoformat() else "PENDING"


def _validate_dependencies(connection: sqlite3.Connection, method: str, account_id: int | None, card_id: int | None) -> None:
    if method not in NON_CARD_METHODS | {"CREDIT_CARD"}:
        raise ValidationError("invalid planned payment method")
    if method in {"PIX", "BANK_TRANSFER", "DEBIT", "AUTO_DEBIT"}:
        if account_id is None or card_id is not None:
            raise ValidationError("method requires account and forbids card")
        require_active(connection, "accounts", account_id)
    elif method == "CASH":
        if account_id is not None or card_id is not None:
            raise ValidationError("cash forbids account and card")
    elif method == "BANK_SLIP":
        if card_id is not None:
            raise ValidationError("bank slip forbids card")
        if account_id is not None:
            require_active(connection, "accounts", account_id)
    else:
        if card_id is None or account_id is not None:
            raise ValidationError("credit card requires card and forbids account")
        require_active(connection, "cards", card_id)


def _create_expense(connection: sqlite3.Connection, *, description: str, amount_cents: int, expense_date: date, due_date: date | None, planned_payment_method: str, category_id: int, account_id: int | None, card_id: int | None, notes: str | None, actor: str, correlation_id: str, clock: Clock, tags: tuple[int, ...] = ()) -> int:
    require_positive_cents(amount_cents)
    if not description.strip():
        raise ValidationError("description cannot be blank")
    require_active(connection, "categories", category_id)
    _validate_dependencies(connection, planned_payment_method, account_id, card_id)
    invoice_id = None
    if planned_payment_method == "CREDIT_CARD":
        if due_date is not None:
            raise ValidationError("credit card expense has no individual due date")
        invoice_id = get_or_create_open_invoice(connection, card_id, expense_date, clock)
    elif due_date is None:
        raise ValidationError("ordinary pending expense requires due date")
    now = utc_text(clock.now_utc())
    expense_id = connection.execute(
        "INSERT INTO expenses(description,amount_cents,expense_date,due_date,planned_payment_method,category_id,account_id,card_id,invoice_id,lifecycle_state,notes,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,'ACTIVE',?,?,?)",
        (description.strip(), amount_cents, expense_date.isoformat(), due_date.isoformat() if due_date else None, planned_payment_method, category_id, account_id, card_id, invoice_id, notes, now, now),
    ).lastrowid
    for tag_id in tags:
        require_active(connection, "tags", tag_id)
        connection.execute("INSERT INTO expense_tags(expense_id,tag_id) VALUES(?,?)", (expense_id, tag_id))
    audit_event(connection, "EXPENSE", expense_id, "CREATE", actor, correlation_id, clock, {"amount_cents": amount_cents})
    return expense_id


def create_expense(connection: sqlite3.Connection, **kwargs) -> int:
    with immediate_transaction(connection):
        return _create_expense(connection, **kwargs)


def create_expense_idempotent(connection: sqlite3.Connection, *, client_id: str, idempotency_key: str, clock: Clock, **kwargs) -> tuple[int, bool]:
    kwargs = {**kwargs, "clock": clock}
    payload = {key: value.isoformat() if isinstance(value, date) else value for key, value in kwargs.items() if key not in {"actor", "correlation_id", "clock"}}
    response, replayed = execute_financial(connection, client_id=client_id, operation="assistant_expense_create", key=idempotency_key, payload=payload, clock=clock, effect=lambda: _assistant_expense_effect(connection, kwargs))
    return int(response["resource_id"]), replayed


def _assistant_expense_effect(connection: sqlite3.Connection, kwargs: dict) -> tuple[str, int, dict]:
    resource_id = _create_expense(connection, **kwargs)
    return "EXPENSE", resource_id, {"resource_id": resource_id, "correlation_id": kwargs["correlation_id"]}


def edit_expense(connection: sqlite3.Connection, expense_id: int, *, description: str | None, amount_cents: int | None, due_date: date | None, actor: str, correlation_id: str, clock: Clock, category_id: int | None = None, notes: str | None = None, tags: tuple[int, ...] | None = None) -> None:
    with immediate_transaction(connection):
        expense = require_row(connection, "SELECT * FROM expenses WHERE id=?", (expense_id,), "expense")
        if expense["lifecycle_state"] != "ACTIVE":
            raise InvalidState("only active expense can be edited")
        paid = active_payment(connection, expense_id)
        if paid and (amount_cents is not None or due_date is not None):
            raise ActivePaymentExists("reverse active payment before editing financial fields")
        new_description = expense["description"] if description is None else description.strip()
        new_amount = expense["amount_cents"] if amount_cents is None else require_positive_cents(amount_cents)
        if not new_description:
            raise ValidationError("description cannot be blank")
        new_due = due_date.isoformat() if due_date else expense["due_date"]
        new_category = expense["category_id"] if category_id is None else category_id
        require_active(connection, "categories", new_category)
        new_notes = expense["notes"] if notes is None else notes
        connection.execute("UPDATE expenses SET description=?,amount_cents=?,due_date=?,category_id=?,notes=?,updated_at=? WHERE id=?", (new_description, new_amount, new_due, new_category, new_notes, utc_text(clock.now_utc()), expense_id))
        if tags is not None:
            connection.execute("DELETE FROM expense_tags WHERE expense_id=?", (expense_id,))
            for tag_id in tags:
                require_active(connection, "tags", tag_id)
                connection.execute("INSERT INTO expense_tags(expense_id,tag_id) VALUES(?,?)", (expense_id, tag_id))
        audit_event(connection, "EXPENSE", expense_id, "EDIT", actor, correlation_id, clock, {"amount_cents": new_amount})


def cancel_expense(connection: sqlite3.Connection, expense_id: int, actor: str, correlation_id: str, clock: Clock) -> None:
    with immediate_transaction(connection):
        expense = require_row(connection, "SELECT * FROM expenses WHERE id=?", (expense_id,), "expense")
        if expense["lifecycle_state"] == "CANCELLED":
            return
        if expense["lifecycle_state"] != "ACTIVE":
            raise InvalidState("superseded expense cannot be cancelled")
        if active_payment(connection, expense_id):
            raise ActivePaymentExists("reverse active payment before cancellation")
        connection.execute("UPDATE expenses SET lifecycle_state='CANCELLED',updated_at=? WHERE id=?", (utc_text(clock.now_utc()), expense_id))
        if expense["invoice_id"] is not None:
            normalize_invoice_state(connection, expense["invoice_id"], clock)
        audit_event(connection, "EXPENSE", expense_id, "CANCEL", actor, correlation_id, clock)


def logical_delete_expense(connection: sqlite3.Connection, expense_id: int, actor: str, correlation_id: str, clock: Clock) -> None:
    """Hide an erroneous unpaid manual entry while retaining its audit row."""
    with immediate_transaction(connection):
        expense = require_row(connection, "SELECT * FROM expenses WHERE id=?", (expense_id,), "expense")
        if expense["lifecycle_state"] != "ACTIVE":
            raise InvalidState("only active expense can be deleted")
        if active_payment(connection, expense_id):
            raise ActivePaymentExists("reverse active payment before deleting expense")
        if expense["invoice_id"] is not None:
            raise Conflict("invoice expense requires protected cancellation flow")
        if expense["installment_series_id"] is not None:
            raise Conflict("installment expense must be handled from its series")
        connection.execute("UPDATE expenses SET lifecycle_state='DELETED',updated_at=? WHERE id=?", (utc_text(clock.now_utc()), expense_id))
        audit_event(connection, "EXPENSE", expense_id, "DELETED", actor, correlation_id, clock, {"reason": "ERRONEOUS_ENTRY"})


def reactivate_expense(connection: sqlite3.Connection, expense_id: int, actor: str, correlation_id: str, clock: Clock) -> None:
    with immediate_transaction(connection):
        expense = require_row(connection, "SELECT * FROM expenses WHERE id=?", (expense_id,), "expense")
        if expense["lifecycle_state"] != "CANCELLED":
            raise InvalidState("only cancelled expense can be reactivated")
        require_active(connection, "categories", expense["category_id"])
        if expense["account_id"] is not None:
            require_active(connection, "accounts", expense["account_id"])
        if expense["card_id"] is not None:
            require_active(connection, "cards", expense["card_id"])
        connection.execute("UPDATE expenses SET lifecycle_state='ACTIVE',updated_at=? WHERE id=?", (utc_text(clock.now_utc()), expense_id))
        audit_event(connection, "EXPENSE", expense_id, "REACTIVATE", actor, correlation_id, clock)


def pay_expense(connection: sqlite3.Connection, *, expense_id: int, paid_on: date, payment_method: str, account_id: int | None, actor: str, correlation_id: str, clock: Clock, client_id: str, idempotency_key: str) -> tuple[int, bool]:
    payload = {"expense_id": expense_id, "paid_on": paid_on.isoformat(), "payment_method": payment_method, "account_id": account_id}
    def effect():
        expense = require_row(connection, "SELECT * FROM expenses WHERE id=?", (expense_id,), "expense")
        if expense["lifecycle_state"] != "ACTIVE" or expense["planned_payment_method"] == "CREDIT_CARD":
            raise InvalidState("expense cannot be paid directly")
        if active_payment(connection, expense_id):
            raise ActivePaymentExists("ordinary expense already has active payment")
        if payment_method not in {"PIX", "DEBIT", "BANK_TRANSFER", "CASH"}:
            raise ValidationError("invalid manual settlement method")
        if payment_method == "CASH":
            if account_id is not None:
                raise ValidationError("cash payment forbids account")
        else:
            if account_id is None:
                raise ValidationError("payment method requires account")
            require_active(connection, "accounts", account_id)
        payment_id = connection.execute(
            "INSERT INTO expense_payments(expense_id,amount_cents,paid_on,payment_method,account_id,source,settlement_id,correlation_id) VALUES(?,?,?,?,?,'MANUAL',NULL,?)",
            (expense_id, expense["amount_cents"], paid_on.isoformat(), payment_method, account_id, correlation_id),
        ).lastrowid
        audit_event(connection, "EXPENSE", expense_id, "PAYMENT_CREATED", actor, correlation_id, clock, {"payment_id": payment_id})
        return "EXPENSE_PAYMENT", payment_id, {"payment_id": payment_id, "expense_id": expense_id, "correlation_id": correlation_id}
    response, replayed = execute_financial(connection, client_id=client_id, operation="pay_expense", key=idempotency_key, payload=payload, clock=clock, effect=effect)
    return int(response.get("payment_id", response.get("resource_id"))), replayed


def reverse_expense_payment(connection: sqlite3.Connection, *, payment_id: int, reversed_on: date, reason: str, actor: str, correlation_id: str, clock: Clock, client_id: str, idempotency_key: str, new_due_date: date | None = None) -> tuple[int, bool]:
    payload = {"payment_id": payment_id, "reversed_on": reversed_on.isoformat(), "reason": reason, "new_due_date": new_due_date.isoformat() if new_due_date else None}
    def effect():
        payment = require_row(connection, "SELECT * FROM expense_payments WHERE id=?", (payment_id,), "expense payment")
        if payment["reversed_at"] is not None:
            raise Conflict("payment already reversed")
        if reversed_on.isoformat() < payment["paid_on"] or not reason.strip():
            raise ValidationError("invalid reversal")
        expense = require_row(connection, "SELECT * FROM expenses WHERE id=?", (payment["expense_id"],), "expense")
        other_active = connection.execute("SELECT 1 FROM expense_payments WHERE expense_id=? AND id<>? AND reversed_at IS NULL", (expense["id"], payment_id)).fetchone()
        if expense["lifecycle_state"] == "ACTIVE" and expense["due_date"] is None and not other_active:
            if new_due_date is None:
                raise NewDueDateRequired("new due date is required when reversal reopens an expense")
            connection.execute("UPDATE expenses SET due_date=?,updated_at=? WHERE id=?", (new_due_date.isoformat(), utc_text(clock.now_utc()), expense["id"]))
        connection.execute("UPDATE expense_payments SET reversed_at=?,reversed_on=?,reversed_by_actor=?,reversal_reason=? WHERE id=?", (utc_text(clock.now_utc()), reversed_on.isoformat(), actor, reason.strip(), payment_id))
        audit_event(connection, "EXPENSE", payment["expense_id"], "PAYMENT_REVERSED", actor, correlation_id, clock, {"payment_id": payment_id})
        return "EXPENSE_PAYMENT_REVERSAL", payment_id, {"payment_id": payment_id, "expense_id": payment["expense_id"], "correlation_id": correlation_id}
    response, replayed = execute_financial(connection, client_id=client_id, operation="reverse_expense_payment", key=idempotency_key, payload=payload, clock=clock, effect=effect)
    return int(response.get("payment_id", response.get("resource_id"))), replayed


def replace_expense_payment(connection: sqlite3.Connection, *, payment_id: int, reversed_on: date, reason: str, new_paid_on: date, new_method: str, new_account_id: int | None, actor: str, correlation_id: str, clock: Clock, client_id: str, idempotency_key: str) -> tuple[int, bool]:
    payload = {"payment_id": payment_id, "reversed_on": reversed_on.isoformat(), "reason": reason, "new_paid_on": new_paid_on.isoformat(), "new_method": new_method, "new_account_id": new_account_id}
    def effect():
        old = require_row(connection, "SELECT * FROM expense_payments WHERE id=?", (payment_id,), "expense payment")
        if old["reversed_at"] is not None or reversed_on.isoformat() < old["paid_on"]:
            raise Conflict("payment cannot be replaced")
        if new_method == "CASH":
            if new_account_id is not None: raise ValidationError("cash forbids account")
        elif new_method in {"PIX", "DEBIT", "BANK_TRANSFER"} and new_account_id is not None:
            require_active(connection, "accounts", new_account_id)
        else:
            raise ValidationError("invalid replacement method/account")
        connection.execute(
            "UPDATE expense_payments SET reversed_at=?,reversed_on=?,reversed_by_actor=?,reversal_reason=? WHERE id=?",
            (utc_text(clock.now_utc()), reversed_on.isoformat(), actor, reason, payment_id),
        )
        new_id = connection.execute(
            "INSERT INTO expense_payments(expense_id,amount_cents,paid_on,payment_method,account_id,source,settlement_id,correlation_id) VALUES(?,?,?,?,?,'MANUAL',NULL,?)",
            (old["expense_id"], old["amount_cents"], new_paid_on.isoformat(), new_method, new_account_id, correlation_id),
        ).lastrowid
        connection.execute("UPDATE expense_payments SET replacement_payment_id=? WHERE id=?", (new_id, payment_id))
        audit_event(connection, "EXPENSE", old["expense_id"], "PAYMENT_REPLACED", actor, correlation_id, clock, {"old_payment_id": payment_id, "new_payment_id": new_id})
        return "EXPENSE_PAYMENT", new_id, {"payment_id": new_id, "expense_id": old["expense_id"], "correlation_id": correlation_id}
    response, replayed = execute_financial(connection, client_id=client_id, operation="replace_expense_payment", key=idempotency_key, payload=payload, clock=clock, effect=effect)
    return int(response.get("payment_id", response.get("resource_id"))), replayed
