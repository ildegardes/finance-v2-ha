from __future__ import annotations

from datetime import date, timedelta
import sqlite3

from ..db import immediate_transaction
from .clock import Clock
from .errors import Conflict, ValidationError
from .support import audit_event, require_active, require_row
from .idempotent import execute_financial
from .calendar import add_months, clamp_day


def _validate_calendar_transition(current: sqlite3.Row | None, effective_from: date, closing_day: int) -> None:
    if not current or closing_day == current["closing_day"]:
        return
    old_day = current["closing_day"]
    prior_purchase = effective_from - timedelta(days=1)
    old_close = clamp_day(prior_purchase.year, prior_purchase.month, old_day)
    if prior_purchase > old_close:
        old_close = add_months(old_close, 1, old_day)
    new_close = clamp_day(effective_from.year, effective_from.month, closing_day)
    if effective_from > new_close:
        new_close = add_months(new_close, 1, closing_day)
    old_boundary = clamp_day(effective_from.year, effective_from.month, old_day)
    previous_probe = add_months(new_close, -1, closing_day)
    previous_day = closing_day if previous_probe >= effective_from else old_day
    previous_close = clamp_day(previous_probe.year, previous_probe.month, previous_day)
    if new_close <= old_close or (effective_from != old_boundary and effective_from < previous_close + timedelta(days=1)):
        raise Conflict("card calendar transition would overlap or invert cycles")


def normalize_name(name: str) -> str:
    normalized = " ".join(name.strip().casefold().split())
    if not normalized:
        raise ValidationError("name cannot be blank")
    return normalized


def create_account(connection: sqlite3.Connection, name: str) -> int:
    if not name.strip():
        raise ValidationError("name cannot be blank")
    with immediate_transaction(connection):
        return connection.execute("INSERT INTO accounts(name,active) VALUES(?,1)", (name.strip(),)).lastrowid

def create_account_idempotent(connection: sqlite3.Connection, *, name: str, client_id: str, idempotency_key: str, clock: Clock) -> tuple[int, bool]:
    def effect():
        if not name.strip(): raise ValidationError("name cannot be blank")
        resource_id=connection.execute("INSERT INTO accounts(name,active) VALUES(?,1)", (name.strip(),)).lastrowid
        return "ACCOUNT",resource_id,{"id":resource_id}
    response,replayed=execute_financial(connection,client_id=client_id,operation="create_account",key=idempotency_key,payload={"name":name.strip()},clock=clock,effect=effect)
    return int(response.get("id",response.get("resource_id"))),replayed


def create_category(connection: sqlite3.Connection, name: str) -> int:
    with immediate_transaction(connection):
        return connection.execute("INSERT INTO categories(name,normalized_name,active) VALUES(?,?,1)", (name.strip(), normalize_name(name))).lastrowid

def create_category_idempotent(connection: sqlite3.Connection, *, name: str, client_id: str, idempotency_key: str, clock: Clock) -> tuple[int, bool]:
    def effect():
        resource_id=connection.execute("INSERT INTO categories(name,normalized_name,active) VALUES(?,?,1)", (name.strip(),normalize_name(name))).lastrowid
        return "CATEGORY",resource_id,{"id":resource_id}
    response,replayed=execute_financial(connection,client_id=client_id,operation="create_category",key=idempotency_key,payload={"name":name.strip()},clock=clock,effect=effect)
    return int(response.get("id",response.get("resource_id"))),replayed


def create_tag(connection: sqlite3.Connection, name: str) -> int:
    with immediate_transaction(connection):
        return connection.execute("INSERT INTO tags(name,normalized_name,active) VALUES(?,?,1)", (name.strip(), normalize_name(name))).lastrowid


def set_active(connection: sqlite3.Connection, table: str, entity_id: int, active: bool) -> None:
    if table not in {"accounts", "categories", "cards", "tags"}:
        raise ValueError("unsupported entity")
    with immediate_transaction(connection):
        require_row(connection, f"SELECT id FROM {table} WHERE id=?", (entity_id,), table)
        connection.execute(f"UPDATE {table} SET active=? WHERE id=?", (int(active), entity_id))


def create_card(connection: sqlite3.Connection, name: str, payment_mode: str, payment_account_id: int | None, effective_from: date, closing_day: int, due_day: int) -> int:
    if not name.strip() or payment_mode not in {"MANUAL", "AUTO_DEBIT"}:
        raise ValidationError("invalid card")
    if payment_mode == "AUTO_DEBIT":
        if payment_account_id is None:
            raise ValidationError("auto debit requires account")
        require_active(connection, "accounts", payment_account_id)
    elif payment_account_id is not None:
        raise ValidationError("manual card cannot have payment account")
    with immediate_transaction(connection):
        card_id = connection.execute(
            "INSERT INTO cards(name,active,invoice_payment_mode,invoice_payment_account_id) VALUES(?,1,?,?)",
            (name.strip(), payment_mode, payment_account_id),
        ).lastrowid
        connection.execute(
            "INSERT INTO card_calendar_versions(card_id,effective_from,effective_to,closing_day,due_day) VALUES(?,?,NULL,?,?)",
            (card_id, effective_from.isoformat(), closing_day, due_day),
        )
        return card_id

def create_card_idempotent(connection: sqlite3.Connection, *, name: str, payment_mode: str, payment_account_id: int | None, effective_from: date, closing_day: int, due_day: int, client_id: str, idempotency_key: str, clock: Clock) -> tuple[int, bool]:
    def effect():
        if not name.strip() or payment_mode not in {"MANUAL","AUTO_DEBIT"}: raise ValidationError("invalid card")
        if payment_mode=="AUTO_DEBIT":
            if payment_account_id is None: raise ValidationError("auto debit requires account")
            require_active(connection,"accounts",payment_account_id)
        elif payment_account_id is not None: raise ValidationError("manual card cannot have payment account")
        card_id=connection.execute("INSERT INTO cards(name,active,invoice_payment_mode,invoice_payment_account_id) VALUES(?,1,?,?)",(name.strip(),payment_mode,payment_account_id)).lastrowid
        connection.execute("INSERT INTO card_calendar_versions(card_id,effective_from,effective_to,closing_day,due_day) VALUES(?,?,NULL,?,?)",(card_id,effective_from.isoformat(),closing_day,due_day))
        return "CARD",card_id,{"id":card_id}
    payload={"name":name.strip(),"payment_mode":payment_mode,"payment_account_id":payment_account_id,"effective_from":effective_from.isoformat(),"closing_day":closing_day,"due_day":due_day}
    response,replayed=execute_financial(connection,client_id=client_id,operation="create_card",key=idempotency_key,payload=payload,clock=clock,effect=effect)
    return int(response.get("id",response.get("resource_id"))),replayed


def edit_card(connection: sqlite3.Connection, card_id: int, *, name: str | None = None,
              payment_mode: str | None = None, payment_account_id: int | None = None,
              actor: str = "system", correlation_id: str = "card-edit", clock: Clock | None = None) -> None:
    """Edit only non-historical card attributes; calendars remain versioned."""
    with immediate_transaction(connection):
        card = require_row(connection, "SELECT * FROM cards WHERE id=?", (card_id,), "card")
        new_name = card["name"] if name is None else name.strip()
        new_mode = card["invoice_payment_mode"] if payment_mode is None else payment_mode
        new_account = card["invoice_payment_account_id"] if payment_account_id is None else payment_account_id
        if not new_name or new_mode not in {"MANUAL", "AUTO_DEBIT"}:
            raise ValidationError("invalid card attributes")
        if new_mode == "AUTO_DEBIT":
            if new_account is None: raise ValidationError("auto debit requires account")
            require_active(connection, "accounts", new_account)
        elif new_account is not None:
            raise ValidationError("manual card cannot have payment account")
        connection.execute("UPDATE cards SET name=?,invoice_payment_mode=?,invoice_payment_account_id=? WHERE id=?", (new_name, new_mode, new_account, card_id))
        if clock is not None:
            audit_event(connection, "CARD", card_id, "EDIT", actor, correlation_id, clock, {"name": new_name, "invoice_payment_mode": new_mode})


def add_card_calendar_version(connection: sqlite3.Connection, card_id: int, effective_from: date, closing_day: int, due_day: int, actor: str, correlation_id: str, clock: Clock) -> int:
    with immediate_transaction(connection):
        require_active(connection, "cards", card_id)
        current = connection.execute(
            "SELECT * FROM card_calendar_versions WHERE card_id=? AND effective_to IS NULL ORDER BY effective_from DESC LIMIT 1",
            (card_id,),
        ).fetchone()
        if current and effective_from.isoformat() <= current["effective_from"]:
            raise Conflict("calendar version must start after current version")
        _validate_calendar_transition(current, effective_from, closing_day)
        existing_invoice = connection.execute(
            "SELECT 1 FROM invoices WHERE card_id=? AND closing_date>=? LIMIT 1", (card_id, effective_from.isoformat())
        ).fetchone()
        if existing_invoice:
            raise Conflict("calendar change would reinterpret an existing invoice")
        if current:
            from datetime import timedelta
            connection.execute("UPDATE card_calendar_versions SET effective_to=? WHERE id=?", ((effective_from - timedelta(days=1)).isoformat(), current["id"]))
        version_id = connection.execute(
            "INSERT INTO card_calendar_versions(card_id,effective_from,effective_to,closing_day,due_day) VALUES(?,?,NULL,?,?)",
            (card_id, effective_from.isoformat(), closing_day, due_day),
        ).lastrowid
        audit_event(connection, "CARD", card_id, "CALENDAR_VERSION_CREATED", actor, correlation_id, clock, {"version_id": version_id})
        return version_id


def add_card_calendar_version_idempotent(connection: sqlite3.Connection, *, card_id: int, effective_from: date, closing_day: int, due_day: int, actor: str, correlation_id: str, clock: Clock, client_id: str, idempotency_key: str) -> tuple[int, bool]:
    payload = {"card_id": card_id, "effective_from": effective_from.isoformat(), "closing_day": closing_day, "due_day": due_day}
    def effect():
        require_active(connection, "cards", card_id)
        current = connection.execute("SELECT * FROM card_calendar_versions WHERE card_id=? AND effective_to IS NULL ORDER BY effective_from DESC LIMIT 1", (card_id,)).fetchone()
        if current and effective_from.isoformat() <= current["effective_from"]: raise Conflict("calendar version must start after current version")
        _validate_calendar_transition(current, effective_from, closing_day)
        if connection.execute("SELECT 1 FROM invoices WHERE card_id=? AND closing_date>=? LIMIT 1", (card_id, effective_from.isoformat())).fetchone(): raise Conflict("calendar change would reinterpret an existing invoice")
        if current:
            from datetime import timedelta
            connection.execute("UPDATE card_calendar_versions SET effective_to=? WHERE id=?", ((effective_from-timedelta(days=1)).isoformat(), current["id"]))
        version_id=connection.execute("INSERT INTO card_calendar_versions(card_id,effective_from,effective_to,closing_day,due_day) VALUES(?,?,NULL,?,?)", (card_id,effective_from.isoformat(),closing_day,due_day)).lastrowid
        audit_event(connection,"CARD",card_id,"CALENDAR_VERSION_CREATED",actor,correlation_id,clock,{"version_id":version_id})
        return "CARD_CALENDAR_VERSION",version_id,{"version_id":version_id,"correlation_id":correlation_id}
    response,replayed=execute_financial(connection,client_id=client_id,operation="add_card_calendar_version",key=idempotency_key,payload=payload,clock=clock,effect=effect)
    return int(response.get("version_id",response.get("resource_id"))),replayed
