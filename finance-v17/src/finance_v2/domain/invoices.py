from __future__ import annotations

from datetime import date, timedelta
import sqlite3
from typing import Any

from ..db import immediate_transaction
from .calendar import add_months, clamp_day
from .clock import Clock, utc_text
from .errors import CardCalendarNotCovered, Conflict, InvoicePaid, InvalidState, Overpayment, ValidationError
from .idempotent import execute_financial
from .money import require_positive_cents
from .support import audit_event, require_active, require_row


def _calendar_for(connection: sqlite3.Connection, card_id: int, on: date) -> sqlite3.Row:
    row = connection.execute(
        "SELECT * FROM card_calendar_versions WHERE card_id=? AND effective_from<=? AND (effective_to IS NULL OR effective_to>=?) ORDER BY effective_from DESC LIMIT 1",
        (card_id, on.isoformat(), on.isoformat()),
    ).fetchone()
    if not row:
        raise CardCalendarNotCovered("no historical card calendar covers this date")
    return row


def resolve_cycle(connection: sqlite3.Connection, card_id: int, purchase_date: date) -> dict[str, date]:
    require_active(connection, "cards", card_id)
    config = _calendar_for(connection, card_id, purchase_date)
    this_close = clamp_day(purchase_date.year, purchase_date.month, config["closing_day"])
    closing = this_close if purchase_date <= this_close else add_months(this_close, 1, config["closing_day"])
    closing_config = _calendar_for(connection, card_id, closing)
    previous_probe = add_months(closing, -1, closing_config["closing_day"])
    first = connection.execute("SELECT * FROM card_calendar_versions WHERE card_id=? ORDER BY effective_from,id LIMIT 1", (card_id,)).fetchone()
    # SPEC 33.3: the first cycle's prior closing is computed with its own
    # calendar. This does not authorize purchases before initial coverage.
    previous_config = first if previous_probe.isoformat() < first["effective_from"] else _calendar_for(connection, card_id, previous_probe)
    previous_close = clamp_day(previous_probe.year, previous_probe.month, previous_config["closing_day"])
    due = clamp_day(closing.year, closing.month, closing_config["due_day"])
    if due <= closing:
        next_month = add_months(closing, 1, closing.day)
        due = clamp_day(next_month.year, next_month.month, closing_config["due_day"])
    return {"closing_date": closing, "period_start": previous_close + timedelta(days=1), "period_end": closing, "due_date": due}


def get_or_create_open_invoice(connection: sqlite3.Connection, card_id: int, purchase_date: date, clock: Clock) -> int:
    cycle = resolve_cycle(connection, card_id, purchase_date)
    row = connection.execute("SELECT id,state FROM invoices WHERE card_id=? AND closing_date=?", (card_id, cycle["closing_date"].isoformat())).fetchone()
    if row:
        if row["state"] != "OPEN":
            raise InvalidState("historical purchase requires explicit invoice correction")
        return row["id"]
    card = require_active(connection, "cards", card_id)
    return connection.execute(
        "INSERT INTO invoices(card_id,closing_date,due_date,period_start,period_end,state,payment_mode,payment_account_id,created_at) VALUES(?,?,?,?,?,'OPEN',?,?,?)",
        (card_id, cycle["closing_date"].isoformat(), cycle["due_date"].isoformat(), cycle["period_start"].isoformat(), cycle["period_end"].isoformat(), card["invoice_payment_mode"], card["invoice_payment_account_id"], utc_text(clock.now_utc())),
    ).lastrowid


def effective_total(connection: sqlite3.Connection, invoice_id: int) -> int:
    invoice = require_row(connection, "SELECT * FROM invoices WHERE id=?", (invoice_id,), "invoice")
    if invoice["state"] == "OPEN":
        return connection.execute("SELECT COALESCE(SUM(amount_cents),0) FROM expenses WHERE invoice_id=? AND lifecycle_state='ACTIVE'", (invoice_id,)).fetchone()[0]
    revision = connection.execute("SELECT new_total_cents FROM invoice_total_revisions WHERE invoice_id=? ORDER BY id DESC LIMIT 1", (invoice_id,)).fetchone()
    return revision[0] if revision else invoice["closed_total_cents"]


def paid_cents(connection: sqlite3.Connection, invoice_id: int) -> int:
    return connection.execute("SELECT COALESCE(SUM(amount_cents),0) FROM invoice_payments WHERE invoice_id=? AND reversed_at IS NULL", (invoice_id,)).fetchone()[0]


def close_invoice(connection: sqlite3.Connection, invoice_id: int, actor: str, correlation_id: str, clock: Clock) -> str:
    with immediate_transaction(connection):
        invoice = require_row(connection, "SELECT * FROM invoices WHERE id=?", (invoice_id,), "invoice")
        if invoice["state"] != "OPEN":
            if invoice["state"] in {"CLOSED", "PAID", "CANCELLED"}:
                return invoice["state"]
            raise InvalidState("invoice is not open")
        total = effective_total(connection, invoice_id)
        now = utc_text(clock.now_utc())
        if total == 0:
            connection.execute("UPDATE invoices SET state='CANCELLED',cancelled_at=? WHERE id=?", (now, invoice_id))
            audit_event(connection, "INVOICE", invoice_id, "CANCEL", actor, correlation_id, clock, {"reason": "EMPTY_AT_CLOSE"})
            return "CANCELLED"
        connection.execute("UPDATE invoices SET state='CLOSED',closed_total_cents=?,closed_at=? WHERE id=?", (total, now, invoice_id))
        audit_event(connection, "INVOICE", invoice_id, "CLOSE", actor, correlation_id, clock, {"closed_total_cents": total})
        return "CLOSED"


def cancel_invoice(connection: sqlite3.Connection, invoice_id: int, actor: str, correlation_id: str, clock: Clock) -> None:
    with immediate_transaction(connection):
        invoice = require_row(connection, "SELECT * FROM invoices WHERE id=?", (invoice_id,), "invoice")
        if invoice["state"] == "CANCELLED":
            return
        if invoice["state"] == "PAID":
            raise InvoicePaid("paid invoice cannot be cancelled before payment reversal")
        if paid_cents(connection, invoice_id) > 0:
            raise InvalidState("invoice with active payments cannot be cancelled")
        if invoice["state"] not in {"OPEN", "CLOSED"}:
            raise InvalidState("invoice cannot be cancelled")
        connection.execute("UPDATE invoices SET state='CANCELLED',cancelled_at=? WHERE id=?", (utc_text(clock.now_utc()), invoice_id))
        audit_event(connection, "INVOICE", invoice_id, "CANCEL", actor, correlation_id, clock)


def normalize_invoice_state(connection: sqlite3.Connection, invoice_id: int, clock: Clock) -> str:
    invoice = require_row(connection, "SELECT * FROM invoices WHERE id=?", (invoice_id,), "invoice")
    if invoice["state"] == "CANCELLED":
        return "CANCELLED"
    total, paid = effective_total(connection, invoice_id), paid_cents(connection, invoice_id)
    if invoice["state"] == "OPEN":
        if total == 0 and paid == 0:
            connection.execute("UPDATE invoices SET state='CANCELLED',paid_at=NULL,cancelled_at=? WHERE id=?", (utc_text(clock.now_utc()), invoice_id))
            return "CANCELLED"
        return "OPEN"
    if total < paid:
        raise Overpayment("effective total cannot be below active payments")
    if total == 0 and paid == 0:
        connection.execute("UPDATE invoices SET state='CANCELLED',paid_at=NULL,cancelled_at=? WHERE id=?", (utc_text(clock.now_utc()), invoice_id))
        return "CANCELLED"
    if total == paid and paid > 0:
        paid_at = connection.execute("SELECT MAX(paid_on) FROM invoice_payments WHERE invoice_id=? AND reversed_at IS NULL", (invoice_id,)).fetchone()[0]
        connection.execute("UPDATE invoices SET state='PAID',paid_at=?,cancelled_at=NULL WHERE id=?", (paid_at, invoice_id))
        return "PAID"
    connection.execute("UPDATE invoices SET state='CLOSED',paid_at=NULL,cancelled_at=NULL WHERE id=?", (invoice_id,))
    return "CLOSED"


def revise_total(connection: sqlite3.Connection, invoice_id: int, new_total_cents: int, reason: str, actor: str, correlation_id: str, clock: Clock) -> int:
    if new_total_cents < 0 or not reason.strip():
        raise ValidationError("invalid revision")
    with immediate_transaction(connection):
        invoice = require_row(connection, "SELECT * FROM invoices WHERE id=?", (invoice_id,), "invoice")
        if invoice["state"] not in {"CLOSED"}:
            raise InvalidState("only CLOSED invoice can be structurally corrected")
        previous = effective_total(connection, invoice_id)
        if new_total_cents < paid_cents(connection, invoice_id):
            raise Overpayment("revision would undercut payments")
        revision_id = connection.execute(
            "INSERT INTO invoice_total_revisions(invoice_id,previous_total_cents,new_total_cents,reason_code,correlation_id,actor,created_at) VALUES(?,?,?,?,?,?,?)",
            (invoice_id, previous, new_total_cents, reason.strip(), correlation_id, actor, utc_text(clock.now_utc())),
        ).lastrowid
        normalize_invoice_state(connection, invoice_id, clock)
        audit_event(connection, "INVOICE", invoice_id, "TOTAL_REVISED", actor, correlation_id, clock, {"previous": previous, "new": new_total_cents, "revision_id": revision_id})
        return revision_id


def revise_total_idempotent(connection: sqlite3.Connection, *, invoice_id: int, new_total_cents: int, reason: str, actor: str, correlation_id: str, clock: Clock, client_id: str, idempotency_key: str) -> tuple[int,bool]:
    if new_total_cents < 0 or not reason.strip(): raise ValidationError("invalid revision")
    payload={"invoice_id":invoice_id,"new_total_cents":new_total_cents,"reason":reason.strip()}
    def effect():
        invoice=require_row(connection,"SELECT * FROM invoices WHERE id=?",(invoice_id,),"invoice")
        if invoice["state"]!="CLOSED": raise InvalidState("only CLOSED invoice can be structurally corrected")
        previous=effective_total(connection,invoice_id)
        if new_total_cents<paid_cents(connection,invoice_id): raise Overpayment("revision would undercut payments")
        revision_id=connection.execute("INSERT INTO invoice_total_revisions(invoice_id,previous_total_cents,new_total_cents,reason_code,correlation_id,actor,created_at) VALUES(?,?,?,?,?,?,?)",(invoice_id,previous,new_total_cents,reason.strip(),correlation_id,actor,utc_text(clock.now_utc()))).lastrowid
        normalize_invoice_state(connection,invoice_id,clock)
        audit_event(connection,"INVOICE",invoice_id,"TOTAL_REVISED",actor,correlation_id,clock,{"previous":previous,"new":new_total_cents,"revision_id":revision_id})
        return "INVOICE_REVISION",revision_id,{"revision_id":revision_id,"invoice_id":invoice_id,"correlation_id":correlation_id}
    response,replayed=execute_financial(connection,client_id=client_id,operation="revise_invoice_total",key=idempotency_key,payload=payload,clock=clock,effect=effect)
    return int(response.get("revision_id",response.get("resource_id"))),replayed


def override_invoice_payment_config(connection: sqlite3.Connection, *, invoice_id: int, payment_mode: str, payment_account_id: int|None, actor: str, correlation_id: str, clock: Clock, client_id: str, idempotency_key: str) -> tuple[int,bool]:
    if payment_mode not in {"MANUAL","AUTO_DEBIT"}: raise ValidationError("invalid invoice payment mode")
    payload={"invoice_id":invoice_id,"payment_mode":payment_mode,"payment_account_id":payment_account_id}
    def effect():
        invoice=require_row(connection,"SELECT * FROM invoices WHERE id=?",(invoice_id,),"invoice")
        if invoice["state"] in {"PAID","CANCELLED"}: raise InvalidState("terminal invoice configuration cannot change")
        if payment_mode=="AUTO_DEBIT":
            if payment_account_id is None: raise ValidationError("auto debit requires account")
            require_active(connection,"accounts",payment_account_id)
        elif payment_account_id is not None: raise ValidationError("manual invoice cannot have payment account")
        connection.execute("UPDATE invoices SET payment_mode=?,payment_account_id=? WHERE id=?",(payment_mode,payment_account_id,invoice_id))
        audit_event(connection,"INVOICE",invoice_id,"PAYMENT_CONFIG_OVERRIDDEN",actor,correlation_id,clock,{"payment_mode":payment_mode,"payment_account_id":payment_account_id})
        return "INVOICE",invoice_id,{"invoice_id":invoice_id,"payment_mode":payment_mode,"payment_account_id":payment_account_id,"correlation_id":correlation_id}
    response,replayed=execute_financial(connection,client_id=client_id,operation="override_invoice_payment_config",key=idempotency_key,payload=payload,clock=clock,effect=effect)
    return int(response.get("invoice_id",response.get("resource_id"))),replayed


def pay_invoice(connection: sqlite3.Connection, invoice_id: int, amount_cents: int, paid_on: date, method: str, account_id: int, actor: str, correlation_id: str, clock: Clock) -> int:
    require_positive_cents(amount_cents)
    if method not in {"PIX", "DEBIT", "BANK_TRANSFER"}:
        raise ValidationError("invalid manual invoice payment method")
    with immediate_transaction(connection):
        invoice = require_row(connection, "SELECT * FROM invoices WHERE id=?", (invoice_id,), "invoice")
        if invoice["state"] != "CLOSED":
            raise InvalidState("only CLOSED invoice accepts payment")
        require_active(connection, "accounts", account_id)
        if paid_cents(connection, invoice_id) + amount_cents > effective_total(connection, invoice_id):
            raise Overpayment("invoice overpayment")
        payment_id = connection.execute(
            "INSERT INTO invoice_payments(invoice_id,amount_cents,paid_on,payment_method,account_id,source,settlement_id,correlation_id) VALUES(?,?,?,?,?,'MANUAL',NULL,?)",
            (invoice_id, amount_cents, paid_on.isoformat(), method, account_id, correlation_id),
        ).lastrowid
        state = normalize_invoice_state(connection, invoice_id, clock)
        audit_event(connection, "INVOICE", invoice_id, "PAYMENT_CREATED", actor, correlation_id, clock, {"payment_id": payment_id, "state": state})
        return payment_id


def reverse_invoice_payment(connection: sqlite3.Connection, payment_id: int, reversed_on: date, actor: str, reason: str, correlation_id: str, clock: Clock) -> None:
    with immediate_transaction(connection):
        payment = require_row(connection, "SELECT * FROM invoice_payments WHERE id=?", (payment_id,), "invoice payment")
        if payment["reversed_at"] is not None:
            raise Conflict("payment already reversed")
        if reversed_on.isoformat() < payment["paid_on"] or not reason.strip():
            raise ValidationError("invalid reversal")
        connection.execute("UPDATE invoice_payments SET reversed_at=?,reversed_on=?,reversed_by_actor=?,reversal_reason=? WHERE id=?", (utc_text(clock.now_utc()), reversed_on.isoformat(), actor, reason.strip(), payment_id))
        normalize_invoice_state(connection, payment["invoice_id"], clock)
        audit_event(connection, "INVOICE", payment["invoice_id"], "PAYMENT_REVERSED", actor, correlation_id, clock, {"payment_id": payment_id})


def pay_invoice_idempotent(connection: sqlite3.Connection, *, invoice_id: int, amount_cents: int, paid_on: date, method: str, account_id: int, actor: str, correlation_id: str, clock: Clock, client_id: str, idempotency_key: str) -> tuple[int, bool]:
    require_positive_cents(amount_cents)
    payload = {"invoice_id": invoice_id, "amount_cents": amount_cents, "paid_on": paid_on.isoformat(), "method": method, "account_id": account_id}
    def effect():
        invoice = require_row(connection, "SELECT * FROM invoices WHERE id=?", (invoice_id,), "invoice")
        if invoice["state"] != "CLOSED": raise InvalidState("only CLOSED invoice accepts payment")
        if method not in {"PIX", "DEBIT", "BANK_TRANSFER"}: raise ValidationError("invalid method")
        require_active(connection, "accounts", account_id)
        if paid_cents(connection, invoice_id) + amount_cents > effective_total(connection, invoice_id): raise Overpayment("invoice overpayment")
        payment_id = connection.execute("INSERT INTO invoice_payments(invoice_id,amount_cents,paid_on,payment_method,account_id,source,settlement_id,correlation_id) VALUES(?,?,?,?,?,'MANUAL',NULL,?)", (invoice_id, amount_cents, paid_on.isoformat(), method, account_id, correlation_id)).lastrowid
        state = normalize_invoice_state(connection, invoice_id, clock)
        audit_event(connection, "INVOICE", invoice_id, "PAYMENT_CREATED", actor, correlation_id, clock, {"payment_id": payment_id, "state": state})
        return "INVOICE_PAYMENT", payment_id, {"payment_id": payment_id, "invoice_id": invoice_id, "correlation_id": correlation_id}
    response, replayed = execute_financial(connection, client_id=client_id, operation="pay_invoice", key=idempotency_key, payload=payload, clock=clock, effect=effect)
    return int(response.get("payment_id", response.get("resource_id"))), replayed


def reverse_invoice_payment_idempotent(connection: sqlite3.Connection, *, payment_id: int, reversed_on: date, actor: str, reason: str, correlation_id: str, clock: Clock, client_id: str, idempotency_key: str) -> tuple[int, bool]:
    payload = {"payment_id": payment_id, "reversed_on": reversed_on.isoformat(), "reason": reason}
    def effect():
        payment = require_row(connection, "SELECT * FROM invoice_payments WHERE id=?", (payment_id,), "invoice payment")
        if payment["reversed_at"] is not None: raise Conflict("payment already reversed")
        if reversed_on.isoformat() < payment["paid_on"] or not reason.strip(): raise ValidationError("invalid reversal")
        connection.execute("UPDATE invoice_payments SET reversed_at=?,reversed_on=?,reversed_by_actor=?,reversal_reason=? WHERE id=?", (utc_text(clock.now_utc()), reversed_on.isoformat(), actor, reason.strip(), payment_id))
        normalize_invoice_state(connection, payment["invoice_id"], clock)
        audit_event(connection, "INVOICE", payment["invoice_id"], "PAYMENT_REVERSED", actor, correlation_id, clock, {"payment_id": payment_id})
        return "INVOICE_PAYMENT_REVERSAL", payment_id, {"payment_id": payment_id, "invoice_id": payment["invoice_id"], "correlation_id": correlation_id}
    response, replayed = execute_financial(connection, client_id=client_id, operation="reverse_invoice_payment", key=idempotency_key, payload=payload, clock=clock, effect=effect)
    return int(response.get("payment_id", response.get("resource_id"))), replayed


def move_card_expense(connection: sqlite3.Connection, *, expense_id: int, target_invoice_id: int, actor: str, correlation_id: str, clock: Clock) -> None:
    """Explicit historical correction preserving both invoice snapshots via revisions."""
    with immediate_transaction(connection):
        expense = require_row(connection, "SELECT * FROM expenses WHERE id=?", (expense_id,), "expense")
        if expense["planned_payment_method"] != "CREDIT_CARD": raise ValidationError("only card items can move between invoices")
        source = require_row(connection, "SELECT * FROM invoices WHERE id=?", (expense["invoice_id"],), "source invoice")
        target = require_row(connection, "SELECT * FROM invoices WHERE id=?", (target_invoice_id,), "target invoice")
        if source["card_id"] != target["card_id"] or source["card_id"] != expense["card_id"]: raise Conflict("invoice card mismatch")
        if source["state"] in {"PAID", "CANCELLED"} or target["state"] in {"PAID", "CANCELLED"}: raise InvalidState("paid/cancelled invoice is protected")
        source_before = effective_total(connection, source["id"]); target_before = effective_total(connection, target["id"])
        source_after = source_before - expense["amount_cents"]; target_after = target_before + expense["amount_cents"]
        if source_after < paid_cents(connection, source["id"]): raise Overpayment("move would undercut source payments")
        now = utc_text(clock.now_utc())
        if source["state"] == "CLOSED":
            connection.execute("INSERT INTO invoice_total_revisions(invoice_id,previous_total_cents,new_total_cents,reason_code,correlation_id,actor,created_at) VALUES(?,?,?,?,?,?,?)", (source["id"], source_before, source_after, "ITEM_MOVED_OUT", correlation_id, actor, now))
        if target["state"] == "CLOSED":
            connection.execute("INSERT INTO invoice_total_revisions(invoice_id,previous_total_cents,new_total_cents,reason_code,correlation_id,actor,created_at) VALUES(?,?,?,?,?,?,?)", (target["id"], target_before, target_after, "ITEM_MOVED_IN", correlation_id, actor, now))
        connection.execute("UPDATE expenses SET invoice_id=?,updated_at=? WHERE id=?", (target_invoice_id, now, expense_id))
        if source["state"] == "CLOSED": normalize_invoice_state(connection, source["id"], clock)
        if target["state"] == "CLOSED": normalize_invoice_state(connection, target["id"], clock)
        audit_event(connection, "EXPENSE", expense_id, "INVOICE_ITEM_MOVED", actor, correlation_id, clock, {"expense_id": expense_id, "from_invoice_id": source["id"], "to_invoice_id": target["id"], "amount_cents": expense["amount_cents"], "from_total": source_before, "to_total": target_before})


def move_card_expense_idempotent(connection: sqlite3.Connection, *, expense_id: int, target_invoice_id: int, actor: str, correlation_id: str, clock: Clock, client_id: str, idempotency_key: str) -> tuple[int,bool]:
    payload={"expense_id":expense_id,"target_invoice_id":target_invoice_id}
    def effect():
        expense=require_row(connection,"SELECT * FROM expenses WHERE id=?",(expense_id,),"expense")
        if expense["planned_payment_method"]!="CREDIT_CARD": raise ValidationError("only card items can move between invoices")
        source=require_row(connection,"SELECT * FROM invoices WHERE id=?",(expense["invoice_id"],),"source invoice");target=require_row(connection,"SELECT * FROM invoices WHERE id=?",(target_invoice_id,),"target invoice")
        if source["card_id"]!=target["card_id"] or source["card_id"]!=expense["card_id"]: raise Conflict("invoice card mismatch")
        if source["state"] in {"PAID","CANCELLED"} or target["state"] in {"PAID","CANCELLED"}: raise InvalidState("paid/cancelled invoice is protected")
        source_before=effective_total(connection,source["id"]);target_before=effective_total(connection,target["id"]);source_after=source_before-expense["amount_cents"];target_after=target_before+expense["amount_cents"]
        if source_after<paid_cents(connection,source["id"]): raise Overpayment("move would undercut source payments")
        now=utc_text(clock.now_utc())
        if source["state"]=="CLOSED": connection.execute("INSERT INTO invoice_total_revisions(invoice_id,previous_total_cents,new_total_cents,reason_code,correlation_id,actor,created_at) VALUES(?,?,?,?,?,?,?)",(source["id"],source_before,source_after,"ITEM_MOVED_OUT",correlation_id,actor,now))
        if target["state"]=="CLOSED": connection.execute("INSERT INTO invoice_total_revisions(invoice_id,previous_total_cents,new_total_cents,reason_code,correlation_id,actor,created_at) VALUES(?,?,?,?,?,?,?)",(target["id"],target_before,target_after,"ITEM_MOVED_IN",correlation_id,actor,now))
        connection.execute("UPDATE expenses SET invoice_id=?,updated_at=? WHERE id=?",(target_invoice_id,now,expense_id))
        if source["state"]=="CLOSED": normalize_invoice_state(connection,source["id"],clock)
        if target["state"]=="CLOSED": normalize_invoice_state(connection,target["id"],clock)
        audit_event(connection,"EXPENSE",expense_id,"INVOICE_ITEM_MOVED",actor,correlation_id,clock,{"expense_id":expense_id,"from_invoice_id":source["id"],"to_invoice_id":target["id"],"amount_cents":expense["amount_cents"],"from_total":source_before,"to_total":target_before})
        return "EXPENSE",expense_id,{"expense_id":expense_id,"target_invoice_id":target_invoice_id,"correlation_id":correlation_id}
    response,replayed=execute_financial(connection,client_id=client_id,operation="move_card_expense",key=idempotency_key,payload=payload,clock=clock,effect=effect)
    return int(response.get("expense_id",response.get("resource_id"))),replayed
