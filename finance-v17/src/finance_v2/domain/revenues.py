from __future__ import annotations

from datetime import date

from ..db import immediate_transaction
from .clock import Clock, utc_text
from .errors import InvalidState, ValidationError
from .idempotent import execute_financial
from .support import audit_event, require_active, require_row


def _active_receipt(connection, revenue_id):
    return connection.execute(
        "SELECT * FROM revenue_receipts WHERE revenue_id=? AND reversed_at IS NULL",
        (revenue_id,),
    ).fetchone()


def revenue_status(connection, revenue, today: date) -> str:
    if revenue["lifecycle_state"] == "CANCELLED":
        return "CANCELLED"
    if _active_receipt(connection, revenue["id"]):
        return "RECEIVED"
    return "OVERDUE" if revenue["expected_on"] < today.isoformat() else "PENDING"


def _create(connection, *, description, amount_cents, competence_date, expected_on,
            category_id, account_id, notes, tags, actor, correlation_id, clock):
    if not isinstance(description, str) or not description.strip() or amount_cents <= 0:
        raise ValidationError("invalid revenue")
    require_active(connection, "categories", category_id)
    if account_id is not None:
        require_active(connection, "accounts", account_id)
    now = utc_text(clock.now_utc())
    revenue_id = connection.execute(
        "INSERT INTO revenues(description,amount_cents,competence_date,expected_on,category_id,account_id,lifecycle_state,notes,created_at,updated_at) VALUES(?,?,?,?,?,?, 'ACTIVE',?,?,?)",
        (description.strip(), amount_cents, competence_date.isoformat(), expected_on.isoformat(), category_id, account_id, notes, now, now),
    ).lastrowid
    for tag_id in tuple(dict.fromkeys(tags)):
        require_active(connection, "tags", tag_id)
        connection.execute("INSERT INTO revenue_tags VALUES(?,?)", (revenue_id, tag_id))
    audit_event(connection, "REVENUE", revenue_id, "CREATE", actor, correlation_id, clock, {"amount_cents": amount_cents})
    return revenue_id


def create_revenue(connection, **kwargs):
    with immediate_transaction(connection):
        return _create(connection, **kwargs)


def create_revenue_idempotent(connection, *, client_id, idempotency_key, **kwargs):
    payload = {k: (v.isoformat() if isinstance(v, date) else list(v) if isinstance(v, tuple) else v) for k, v in kwargs.items() if k not in {"clock", "actor"}}
    def effect():
        revenue_id = _create(connection, **kwargs)
        return "REVENUE", revenue_id, {"id": revenue_id, "correlation_id": kwargs["correlation_id"]}
    response, replayed = execute_financial(connection, client_id=client_id, operation="revenue_create", key=idempotency_key, payload=payload, clock=kwargs["clock"], effect=effect)
    return response.get("id", response.get("resource_id")), replayed


def edit_revenue(connection, revenue_id, *, description=None, amount_cents=None,
                 competence_date=None, expected_on=None, category_id=None,
                 account_id=None, notes=None, tags=None, actor, correlation_id, clock):
    with immediate_transaction(connection):
        revenue = require_row(connection, "SELECT * FROM revenues WHERE id=?", (revenue_id,), "revenue")
        if revenue["lifecycle_state"] != "ACTIVE" or _active_receipt(connection, revenue_id):
            raise InvalidState("only pending active revenue can be edited")
        new_description = revenue["description"] if description is None else str(description).strip()
        new_amount = revenue["amount_cents"] if amount_cents is None else amount_cents
        if not new_description or new_amount <= 0:
            raise ValidationError("invalid revenue")
        category = revenue["category_id"] if category_id is None else category_id
        require_active(connection, "categories", category)
        account = revenue["account_id"] if account_id is None else account_id
        if account is not None:
            require_active(connection, "accounts", account)
        values = (new_description, new_amount,
                  revenue["competence_date"] if competence_date is None else competence_date.isoformat(),
                  revenue["expected_on"] if expected_on is None else expected_on.isoformat(),
                  category, account, revenue["notes"] if notes is None else notes,
                  utc_text(clock.now_utc()), revenue_id)
        connection.execute("UPDATE revenues SET description=?,amount_cents=?,competence_date=?,expected_on=?,category_id=?,account_id=?,notes=?,updated_at=? WHERE id=?", values)
        if tags is not None:
            connection.execute("DELETE FROM revenue_tags WHERE revenue_id=?", (revenue_id,))
            for tag_id in tuple(dict.fromkeys(tags)):
                require_active(connection, "tags", tag_id)
                connection.execute("INSERT INTO revenue_tags VALUES(?,?)", (revenue_id, tag_id))
        audit_event(connection, "REVENUE", revenue_id, "EDIT", actor, correlation_id, clock, {"amount_cents": new_amount})


def cancel_revenue_idempotent(connection, revenue_id, *, actor, correlation_id, clock, client_id, idempotency_key):
    payload = {"revenue_id": revenue_id, "correlation_id": correlation_id}
    def effect():
        revenue = require_row(connection, "SELECT * FROM revenues WHERE id=?", (revenue_id,), "revenue")
        if revenue["lifecycle_state"] != "ACTIVE" or _active_receipt(connection, revenue_id):
            raise InvalidState("revenue cannot be cancelled")
        connection.execute("UPDATE revenues SET lifecycle_state='CANCELLED',updated_at=? WHERE id=?", (utc_text(clock.now_utc()), revenue_id))
        audit_event(connection, "REVENUE", revenue_id, "CANCEL", actor, correlation_id, clock)
        return "REVENUE", revenue_id, {"id": revenue_id, "correlation_id": correlation_id}
    response, replayed = execute_financial(connection, client_id=client_id, operation="revenue_cancel", key=idempotency_key, payload=payload, clock=clock, effect=effect)
    return response.get("id", response.get("resource_id")), replayed


def receive_revenue_idempotent(connection, revenue_id, *, received_on, account_id,
                               actor, correlation_id, clock, client_id, idempotency_key):
    payload = {"revenue_id": revenue_id, "received_on": received_on.isoformat(), "account_id": account_id, "correlation_id": correlation_id}
    def effect():
        revenue = require_row(connection, "SELECT * FROM revenues WHERE id=?", (revenue_id,), "revenue")
        if revenue["lifecycle_state"] != "ACTIVE" or _active_receipt(connection, revenue_id):
            raise InvalidState("revenue cannot be received")
        require_active(connection, "accounts", account_id)
        receipt_id = connection.execute(
            "INSERT INTO revenue_receipts(revenue_id,amount_cents,received_on,account_id,created_at,correlation_id) VALUES(?,?,?,?,?,?)",
            (revenue_id, revenue["amount_cents"], received_on.isoformat(), account_id, utc_text(clock.now_utc()), correlation_id),
        ).lastrowid
        audit_event(connection, "REVENUE", revenue_id, "RECEIPT_CREATED", actor, correlation_id, clock, {"receipt_id": receipt_id})
        return "REVENUE_RECEIPT", receipt_id, {"receipt_id": receipt_id, "correlation_id": correlation_id}
    response, replayed = execute_financial(connection, client_id=client_id, operation="revenue_receive", key=idempotency_key, payload=payload, clock=clock, effect=effect)
    return response.get("receipt_id", response.get("resource_id")), replayed


def reverse_revenue_receipt_idempotent(connection, receipt_id, *, reversed_on, reason,
                                       actor, correlation_id, clock, client_id, idempotency_key):
    payload = {"receipt_id": receipt_id, "reversed_on": reversed_on.isoformat(), "reason": reason, "correlation_id": correlation_id}
    def effect():
        receipt = require_row(connection, "SELECT * FROM revenue_receipts WHERE id=?", (receipt_id,), "revenue receipt")
        if receipt["reversed_at"] or not reason.strip() or reversed_on < date.fromisoformat(receipt["received_on"]):
            raise InvalidState("receipt cannot be reversed")
        connection.execute(
            "UPDATE revenue_receipts SET reversed_at=?,reversed_on=?,reversed_by_actor=?,reversal_reason=? WHERE id=?",
            (utc_text(clock.now_utc()), reversed_on.isoformat(), actor, reason.strip(), receipt_id),
        )
        audit_event(connection, "REVENUE", receipt["revenue_id"], "RECEIPT_REVERSED", actor, correlation_id, clock, {"receipt_id": receipt_id})
        return "REVENUE_RECEIPT", receipt_id, {"receipt_id": receipt_id, "correlation_id": correlation_id}
    response, replayed = execute_financial(connection, client_id=client_id, operation="revenue_reverse", key=idempotency_key, payload=payload, clock=clock, effect=effect)
    return response.get("receipt_id", response.get("resource_id")), replayed
