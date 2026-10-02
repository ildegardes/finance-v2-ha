from __future__ import annotations

from datetime import date, timedelta
import sqlite3
from uuid import uuid4

from ..db import immediate_transaction
from .calendar import due_date_for, lineage_key, occurrence_date
from .clock import Clock, utc_text
from .errors import Conflict, InvalidState, ValidationError
from .idempotent import execute_financial
from .invoices import effective_total, get_or_create_open_invoice, normalize_invoice_state, paid_cents, resolve_cycle
from .money import require_positive_cents
from .support import audit_event, require_active, require_row


FREQUENCIES = {"WEEKLY", "BIWEEKLY", "MONTHLY", "BIMONTHLY", "QUARTERLY", "SEMIANNUAL", "ANNUAL"}


def _validate_version(connection, frequency, base_day, method, account_id, card_id, due_rule, offset, due_day):
    if frequency not in FREQUENCIES:
        raise ValidationError("invalid recurrence frequency")
    if frequency in {"WEEKLY", "BIWEEKLY"} and base_day is not None:
        raise ValidationError("weekly recurrence has no base_day")
    if frequency not in {"WEEKLY", "BIWEEKLY"} and not (base_day and 1 <= base_day <= 31):
        raise ValidationError("monthly recurrence requires base_day")
    due_date_for(date(2026, 1, 20), due_rule, offset, due_day)
    if (method == "CREDIT_CARD") != (due_rule == "INVOICE"):
        raise ValidationError("credit card iff invoice due rule")
    if method in {"PIX", "DEBIT", "AUTO_DEBIT"}:
        if account_id is None or card_id is not None: raise ValidationError("method requires account")
        require_active(connection, "accounts", account_id)
    elif method == "CASH":
        if account_id is not None or card_id is not None: raise ValidationError("cash dependencies invalid")
    elif method == "BANK_SLIP":
        if card_id is not None: raise ValidationError("bank slip forbids card")
    elif method == "CREDIT_CARD":
        if card_id is None or account_id is not None: raise ValidationError("card dependencies invalid")
        require_active(connection, "cards", card_id)
    else:
        raise ValidationError("invalid payment method")


def create_series(connection: sqlite3.Connection, *, start_date: date, description: str, category_id: int, frequency: str, base_day: int | None, amount_cents: int, payment_method: str, account_id: int | None, card_id: int | None, due_rule: str, due_offset_days: int | None, due_day: int | None, tags: tuple[int, ...], actor: str, correlation_id: str, clock: Clock, end_date: date | None = None) -> tuple[int, int]:
    require_positive_cents(amount_cents)
    if frequency not in {"WEEKLY", "BIWEEKLY"} and base_day is None:
        base_day = start_date.day
    with immediate_transaction(connection):
        require_active(connection, "categories", category_id)
        _validate_version(connection, frequency, base_day, payment_method, account_id, card_id, due_rule, due_offset_days, due_day)
        epoch = str(uuid4())
        series_id = connection.execute("INSERT INTO recurring_series(lineage_epoch_uuid,start_date,end_date) VALUES(?,?,?)", (epoch, start_date.isoformat(), end_date.isoformat() if end_date else None)).lastrowid
        occurrence_key = str(uuid4())
        version_id = connection.execute(
            "INSERT INTO recurring_series_versions(recurring_series_id,lifecycle_state,description,category_id,created_at,effective_from,effective_to,anchor_occurrence_key,anchor_logical_date,anchor_logical_ordinal,frequency,base_day,amount_cents,planned_payment_method,account_id,card_id,due_rule,due_offset_days,due_day) VALUES(?,'ACTIVE',?,?,?,?,NULL,?,?,0,?,?,?,?,?,?,?,?,?)",
            (series_id, description.strip(), category_id, utc_text(clock.now_utc()), start_date.isoformat(), occurrence_key, start_date.isoformat(), frequency, base_day, amount_cents, payment_method, account_id, card_id, due_rule, due_offset_days, due_day),
        ).lastrowid
        for tag_id in tags:
            require_active(connection, "tags", tag_id)
            connection.execute("INSERT INTO recurring_version_tags(recurring_version_id,tag_id) VALUES(?,?)", (version_id, tag_id))
        audit_event(connection, "RECURRING_SERIES", series_id, "CREATE", actor, correlation_id, clock, {"version_id": version_id})
        return series_id, version_id


def _version_for(connection, series_id: int, logical_date: date):
    return connection.execute(
        "SELECT * FROM recurring_series_versions WHERE recurring_series_id=? AND lifecycle_state='ACTIVE' AND effective_from<=? AND (effective_to IS NULL OR effective_to>=?) ORDER BY effective_from DESC LIMIT 1",
        (series_id, logical_date.isoformat(), logical_date.isoformat()),
    ).fetchone()


def resolve_logical_slot(versions, ordinal):
    """One calendar resolver shared by materialization and read-only forecasts."""
    candidate, version = None, None
    for possible in versions:
        if ordinal < possible["anchor_logical_ordinal"]:
            continue
        computed = occurrence_date(date.fromisoformat(possible["anchor_logical_date"]), possible["anchor_logical_ordinal"], ordinal, possible["frequency"], possible["base_day"])
        if possible["effective_from"] <= computed.isoformat() and (possible["effective_to"] is None or possible["effective_to"] >= computed.isoformat()):
            candidate, version = computed, possible
    return candidate, version


def materialize(connection: sqlite3.Connection, *, series_id: int, through: date, actor: str, correlation_id: str, clock: Clock) -> list[int]:
    with immediate_transaction(connection):
        series = require_row(connection, "SELECT * FROM recurring_series WHERE id=?", (series_id,), "series")
        timeline_versions = connection.execute("SELECT * FROM recurring_series_versions WHERE recurring_series_id=? ORDER BY effective_from,id", (series_id,)).fetchall()
        if not timeline_versions or not any(v["effective_from"] <= series["start_date"] and (v["effective_to"] is None or v["effective_to"] >= series["start_date"]) for v in timeline_versions):
            raise Conflict("series must retain a version applicable from start_date")
        active_versions = [v for v in timeline_versions if v["lifecycle_state"] == "ACTIVE"]
        for previous, current in zip(active_versions, active_versions[1:]):
            expected = (date.fromisoformat(previous["effective_to"]) + timedelta(days=1)).isoformat() if previous["effective_to"] else None
            if expected is None or current["effective_from"] != expected:
                raise Conflict("active recurrence versions must be adjacent and non-overlapping")
        limit = min(through, series["end_date"] and date.fromisoformat(series["end_date"]) or through)
        if limit < date.fromisoformat(series["start_date"]):
            return []
        created = []
        ordinal = 0
        while True:
            version = _version_for(connection, series_id, date.fromisoformat(series["start_date"])) if ordinal == 0 else None
            versions = connection.execute("SELECT * FROM recurring_series_versions WHERE recurring_series_id=? ORDER BY (lifecycle_state='ACTIVE'),effective_from,id", (series_id,)).fetchall()
            if not versions: break
            candidate, version = resolve_logical_slot(versions, ordinal)
            if candidate is None:
                ordinal += 1
                if ordinal > 10000: raise Conflict("recurrence could not resolve ordinal")
                continue
            if candidate > limit: break
            material_key = f"v{version['id']}:o{ordinal}"
            existing = connection.execute("SELECT expense_id FROM recurrence_slot_resolutions WHERE recurring_series_id=? AND recurring_version_id=? AND materialization_slot_key=? AND resolution_state='ACTIVE'", (series_id, version["id"], material_key)).fetchone()
            if not existing:
                due = due_date_for(candidate, version["due_rule"], version["due_offset_days"], version["due_day"])
                invoice_id = get_or_create_open_invoice(connection, version["card_id"], candidate, clock) if version["planned_payment_method"] == "CREDIT_CARD" else None
                expense_id = connection.execute(
                    "INSERT INTO expenses(description,amount_cents,expense_date,due_date,planned_payment_method,category_id,account_id,card_id,invoice_id,recurring_series_id,recurring_version_id,recurrence_occurrence_key,logical_slot_lineage_key,materialization_slot_key,lifecycle_state,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,'ACTIVE',?,?)",
                    (version["description"], version["amount_cents"], candidate.isoformat(), due.isoformat() if due else None, version["planned_payment_method"], version["category_id"], version["account_id"], version["card_id"], invoice_id, series_id, version["id"], version["anchor_occurrence_key"] if ordinal == version["anchor_logical_ordinal"] else str(uuid4()), lineage_key(series["lineage_epoch_uuid"], ordinal), material_key, utc_text(clock.now_utc()), utc_text(clock.now_utc())),
                ).lastrowid
                connection.execute("INSERT INTO expense_tags(expense_id,tag_id) SELECT ?,tag_id FROM recurring_version_tags WHERE recurring_version_id=?", (expense_id, version["id"]))
                connection.execute(
                    "INSERT INTO recurrence_slot_resolutions(recurring_series_id,recurring_version_id,materialization_slot_key,logical_slot_lineage_key,logical_ordinal,logical_occurrence_date,resolution,resolution_state,reason_code,correlation_id,created_at,expense_id) VALUES(?,?,?,?,?,?,'CREATED','ACTIVE','MATERIALIZED',?,?,?)",
                    (series_id, version["id"], material_key, lineage_key(series["lineage_epoch_uuid"], ordinal), ordinal, candidate.isoformat(), correlation_id, utc_text(clock.now_utc()), expense_id),
                )
                created.append(expense_id)
            ordinal += 1
        connection.execute("UPDATE recurring_series SET reconciled_through=? WHERE id=?", (limit.isoformat(), series_id))
        return created


def end_series(connection: sqlite3.Connection, *, series_id: int, cut_date: date, actor: str, correlation_id: str, clock: Clock) -> None:
    with immediate_transaction(connection):
        series = require_row(connection, "SELECT * FROM recurring_series WHERE id=?", (series_id,), "series")
        if series["ended_at"] is not None:
            raise InvalidState("series is already terminal")
        end_date = cut_date - timedelta(days=1)
        if end_date < date.fromisoformat(series["start_date"]):
            raise ValidationError("cut precedes series")
        expenses = connection.execute("SELECT id FROM expenses WHERE recurring_series_id=? AND expense_date>=? AND lifecycle_state='ACTIVE'", (series_id, cut_date.isoformat())).fetchall()
        for expense in expenses:
            paid = connection.execute("SELECT 1 FROM expense_payments WHERE expense_id=? AND reversed_at IS NULL", (expense["id"],)).fetchone()
            override = connection.execute("SELECT 1 FROM occurrence_overrides WHERE expense_id=? AND removed_at IS NULL", (expense["id"],)).fetchone()
            if not paid and not override:
                connection.execute("UPDATE expenses SET lifecycle_state='CANCELLED',updated_at=? WHERE id=?", (utc_text(clock.now_utc()), expense["id"]))
                audit_event(connection, "EXPENSE", expense["id"], "CANCEL", actor, correlation_id, clock, {"reason": "SERIES_ENDED"})
        connection.execute("UPDATE recurring_series SET end_date=?,ended_at=? WHERE id=?", (end_date.isoformat(), utc_text(clock.now_utc()), series_id))
        audit_event(connection, "RECURRING_SERIES", series_id, "END", actor, correlation_id, clock, {"cut_date": cut_date.isoformat()})


def end_series_idempotent(connection: sqlite3.Connection, *, series_id: int, cut_date: date, actor: str, correlation_id: str, clock: Clock, client_id: str, idempotency_key: str) -> tuple[int,bool]:
    payload={"series_id":series_id,"cut_date":cut_date.isoformat()}
    def effect():
        series=require_row(connection,"SELECT * FROM recurring_series WHERE id=?",(series_id,),"series")
        if series["ended_at"] is not None: raise InvalidState("series is already terminal")
        end_date=cut_date-timedelta(days=1)
        if end_date<date.fromisoformat(series["start_date"]): raise ValidationError("cut precedes series")
        for expense in connection.execute("SELECT id FROM expenses WHERE recurring_series_id=? AND expense_date>=? AND lifecycle_state='ACTIVE'",(series_id,cut_date.isoformat())).fetchall():
            paid=connection.execute("SELECT 1 FROM expense_payments WHERE expense_id=? AND reversed_at IS NULL",(expense["id"],)).fetchone()
            override=connection.execute("SELECT 1 FROM occurrence_overrides WHERE expense_id=? AND removed_at IS NULL",(expense["id"],)).fetchone()
            if not paid and not override:
                connection.execute("UPDATE expenses SET lifecycle_state='CANCELLED',updated_at=? WHERE id=?",(utc_text(clock.now_utc()),expense["id"]))
                audit_event(connection,"EXPENSE",expense["id"],"CANCEL",actor,correlation_id,clock,{"reason":"SERIES_ENDED"})
        connection.execute("UPDATE recurring_series SET end_date=?,ended_at=? WHERE id=?",(end_date.isoformat(),utc_text(clock.now_utc()),series_id))
        audit_event(connection,"RECURRING_SERIES",series_id,"END",actor,correlation_id,clock,{"cut_date":cut_date.isoformat()})
        return "RECURRING_SERIES",series_id,{"series_id":series_id,"correlation_id":correlation_id}
    response,replayed=execute_financial(connection,client_id=client_id,operation="end_series",key=idempotency_key,payload=payload,clock=clock,effect=effect)
    return int(response.get("series_id",response.get("resource_id"))),replayed


def create_occurrence_override(connection: sqlite3.Connection, *, expense_id: int, reason: str, actor: str, correlation_id: str, clock: Clock) -> int:
    with immediate_transaction(connection):
        expense = require_row(connection, "SELECT * FROM expenses WHERE id=?", (expense_id,), "expense")
        if expense["recurring_version_id"] is None:
            raise ValidationError("only recurring occurrences support override")
        override_id = connection.execute(
            "INSERT INTO occurrence_overrides(expense_id,originating_recurring_version_id,reason_code,correlation_id,created_at,created_by_actor) VALUES(?,?,?,?,?,?)",
            (expense_id, expense["recurring_version_id"], reason, correlation_id, utc_text(clock.now_utc()), actor),
        ).lastrowid
        audit_event(connection, "EXPENSE", expense_id, "OVERRIDE_CREATED", actor, correlation_id, clock, {"override_id": override_id})
        return override_id


def remove_occurrence_override(connection: sqlite3.Connection, *, override_id: int, reason: str, actor: str, correlation_id: str, clock: Clock) -> None:
    with immediate_transaction(connection):
        override = require_row(connection, "SELECT * FROM occurrence_overrides WHERE id=?", (override_id,), "override")
        if override["removed_at"] is not None:
            raise Conflict("override already removed")
        connection.execute(
            "UPDATE occurrence_overrides SET removed_at=?,removed_by_actor=?,removal_reason_code=?,removal_correlation_id=? WHERE id=?",
            (utc_text(clock.now_utc()), actor, reason, correlation_id, override_id),
        )
        audit_event(connection, "EXPENSE", override["expense_id"], "OVERRIDE_REMOVED", actor, correlation_id, clock, {"override_id": override_id})


def cancel_occurrence_only(connection: sqlite3.Connection, *, expense_id: int, actor: str, correlation_id: str, clock: Clock) -> None:
    with immediate_transaction(connection):
        expense = require_row(connection, "SELECT * FROM expenses WHERE id=?", (expense_id,), "expense")
        if expense["recurring_series_id"] is None or expense["lifecycle_state"] != "ACTIVE":
            raise InvalidState("occurrence is not cancellable")
        paid = connection.execute("SELECT 1 FROM expense_payments WHERE expense_id=? AND reversed_at IS NULL", (expense_id,)).fetchone()
        if paid:
            raise Conflict("paid occurrence requires reversal before cancellation")
        connection.execute("UPDATE expenses SET lifecycle_state='CANCELLED',updated_at=? WHERE id=?", (utc_text(clock.now_utc()), expense_id))
        audit_event(connection, "EXPENSE", expense_id, "CANCEL", actor, correlation_id, clock, {"scope": "ONLY_THIS"})


def change_this_and_future(connection: sqlite3.Connection, *, anchor_expense_id: int, description: str, amount_cents: int, frequency: str, base_day: int | None, payment_method: str, account_id: int | None, card_id: int | None, due_rule: str, due_offset_days: int | None, due_day: int | None, tags: tuple[int, ...], actor: str, correlation_id: str, clock: Clock, client_id: str, idempotency_key: str) -> tuple[int, bool]:
    """Replace the effective recurrence version and reconcile every materialized lineage."""
    payload = {"anchor_expense_id": anchor_expense_id, "description": description, "amount_cents": amount_cents, "frequency": frequency, "base_day": base_day, "payment_method": payment_method, "account_id": account_id, "card_id": card_id, "due_rule": due_rule, "due_offset_days": due_offset_days, "due_day": due_day, "tags": tags}
    def effect():
        connection.execute("PRAGMA defer_foreign_keys=ON")
        anchor = require_row(connection, "SELECT * FROM expenses WHERE id=?", (anchor_expense_id,), "anchor occurrence")
        if anchor["recurring_series_id"] is None: raise ValidationError("anchor must be recurring")
        require_positive_cents(amount_cents)
        _validate_version(connection, frequency, base_day, payment_method, account_id, card_id, due_rule, due_offset_days, due_day)
        series = require_row(connection, "SELECT * FROM recurring_series WHERE id=?", (anchor["recurring_series_id"],), "series")
        if series["ended_at"] is not None: raise InvalidState("ended series is terminal")
        anchor_resolution = require_row(connection, "SELECT * FROM recurrence_slot_resolutions WHERE expense_id=? AND resolution_state='ACTIVE'", (anchor_expense_id,), "anchor resolution")
        anchor_date = date.fromisoformat(anchor["expense_date"])
        anchor_ordinal = anchor_resolution["logical_ordinal"]
        slots = connection.execute("SELECT r.*,e.lifecycle_state,e.recurrence_occurrence_key,e.invoice_id FROM recurrence_slot_resolutions r LEFT JOIN expenses e ON e.id=r.expense_id WHERE r.recurring_series_id=? AND r.logical_ordinal>=? AND r.resolution_state='ACTIVE' ORDER BY r.logical_ordinal", (series["id"], anchor_ordinal)).fetchall()
        simulated_dates: set[str] = set()
        for slot in slots:
            simulated_date = occurrence_date(anchor_date, anchor_ordinal, slot["logical_ordinal"], frequency, base_day).isoformat()
            if simulated_date in simulated_dates:
                raise Conflict("new recurrence calendar collides")
            simulated_dates.add(simulated_date)
        old_versions = connection.execute("SELECT * FROM recurring_series_versions WHERE recurring_series_id=? AND lifecycle_state='ACTIVE' AND (effective_to IS NULL OR effective_to>=?) ORDER BY effective_from", (series["id"], anchor_date.isoformat())).fetchall()
        new_version_id = connection.execute("SELECT COALESCE(MAX(id),0)+1 FROM recurring_series_versions").fetchone()[0]
        for old in old_versions:
            connection.execute("UPDATE recurring_series_versions SET lifecycle_state='SUPERSEDED',effective_to=?,superseded_at=?,superseded_by_version_id=?,supersession_reason_code='THIS_AND_FUTURE',supersession_correlation_id=? WHERE id=?", ((anchor_date - timedelta(days=1)).isoformat() if old["effective_from"] < anchor_date.isoformat() else old["effective_from"], utc_text(clock.now_utc()), new_version_id, correlation_id, old["id"]))
        anchor_key = anchor["recurrence_occurrence_key"]
        connection.execute(
            "INSERT INTO recurring_series_versions(id,recurring_series_id,lifecycle_state,description,category_id,created_at,effective_from,effective_to,anchor_occurrence_key,anchor_logical_date,anchor_logical_ordinal,frequency,base_day,amount_cents,planned_payment_method,account_id,card_id,due_rule,due_offset_days,due_day) VALUES(?,?,'ACTIVE',?,?,?,?,NULL,?,?,?,?,?,?,?,?,?,?,?,?)",
            (new_version_id, series["id"], description.strip(), anchor["category_id"], utc_text(clock.now_utc()), anchor_date.isoformat(), anchor_key, anchor_date.isoformat(), anchor_ordinal, frequency, base_day, amount_cents, payment_method, account_id, card_id, due_rule, due_offset_days, due_day),
        )
        for tag_id in tags:
            require_active(connection, "tags", tag_id)
            connection.execute("INSERT INTO recurring_version_tags(recurring_version_id,tag_id) VALUES(?,?)", (new_version_id, tag_id))
        used_dates: set[str] = set()
        for slot in slots:
            ordinal = slot["logical_ordinal"]
            new_date = occurrence_date(anchor_date, anchor_ordinal, ordinal, frequency, base_day)
            if new_date.isoformat() in used_dates: raise Conflict("new recurrence calendar collides")
            used_dates.add(new_date.isoformat())
            resolved_expense_id = slot["expense_id"] if slot["expense_id"] is not None else slot["protected_expense_id"]
            expense = connection.execute("SELECT * FROM expenses WHERE id=?", (resolved_expense_id,)).fetchone() if resolved_expense_id is not None else None
            paid = expense and connection.execute("SELECT 1 FROM expense_payments WHERE expense_id=? AND reversed_at IS NULL", (expense["id"],)).fetchone()
            override = expense and connection.execute("SELECT 1 FROM occurrence_overrides WHERE expense_id=? AND removed_at IS NULL", (expense["id"],)).fetchone()
            source_invoice = connection.execute("SELECT * FROM invoices WHERE id=?", (expense["invoice_id"],)).fetchone() if expense and expense["invoice_id"] else None
            invoice_protected = bool(source_invoice and (source_invoice["state"] in {"PAID", "CANCELLED"} or (source_invoice["state"] == "CLOSED" and effective_total(connection, source_invoice["id"]) - expense["amount_cents"] < paid_cents(connection, source_invoice["id"]))))
            protected = not expense or expense["lifecycle_state"] == "CANCELLED" or paid or override or invoice_protected
            new_resolution_id = connection.execute("SELECT COALESCE(MAX(id),0)+1 FROM recurrence_slot_resolutions").fetchone()[0]
            connection.execute("UPDATE recurrence_slot_resolutions SET resolution_state='SUPERSEDED',superseded_at=?,superseded_by_resolution_id=? WHERE id=?", (utc_text(clock.now_utc()), new_resolution_id, slot["id"]))
            material_key = f"v{new_version_id}:o{ordinal}"
            if protected:
                connection.execute("INSERT INTO recurrence_slot_resolutions(id,recurring_series_id,recurring_version_id,materialization_slot_key,logical_slot_lineage_key,logical_ordinal,logical_occurrence_date,resolution,resolution_state,reason_code,correlation_id,created_at,protected_expense_id) VALUES(?,?,?,?,?,?,?,'RESERVED_PROTECTED','ACTIVE','PROTECTED',?,?,?)", (new_resolution_id, series["id"], new_version_id, material_key, lineage_key(series["lineage_epoch_uuid"], ordinal), ordinal, new_date.isoformat(), correlation_id, utc_text(clock.now_utc()), expense["id"] if expense else slot["protected_expense_id"]))
                continue
            due = due_date_for(new_date, due_rule, due_offset_days, due_day)
            invoice_id = None
            target_invoice = None
            if payment_method == "CREDIT_CARD":
                cycle = resolve_cycle(connection, card_id, new_date)
                target_invoice = connection.execute("SELECT * FROM invoices WHERE card_id=? AND closing_date=?", (card_id, cycle["closing_date"].isoformat())).fetchone()
                if target_invoice:
                    if target_invoice["state"] in {"PAID", "CANCELLED"}:
                        connection.execute("INSERT INTO recurrence_slot_resolutions(id,recurring_series_id,recurring_version_id,materialization_slot_key,logical_slot_lineage_key,logical_ordinal,logical_occurrence_date,resolution,resolution_state,reason_code,correlation_id,created_at,protected_expense_id) VALUES(?,?,?,?,?,?,?,'RESERVED_PROTECTED','ACTIVE','PROTECTED_INVOICE_COLLISION',?,?,?)", (new_resolution_id, series["id"], new_version_id, material_key, lineage_key(series["lineage_epoch_uuid"], ordinal), ordinal, new_date.isoformat(), correlation_id, utc_text(clock.now_utc()), expense["id"]))
                        continue
                    invoice_id = target_invoice["id"]
                else:
                    invoice_id = get_or_create_open_invoice(connection, card_id, new_date, clock)
                    target_invoice = connection.execute("SELECT * FROM invoices WHERE id=?", (invoice_id,)).fetchone()
            if source_invoice and source_invoice["state"] == "CLOSED" and source_invoice["id"] != invoice_id:
                source_before = effective_total(connection, source_invoice["id"])
                connection.execute("INSERT INTO invoice_total_revisions(invoice_id,previous_total_cents,new_total_cents,reason_code,correlation_id,actor,created_at) VALUES(?,?,?,?,?,?,?)", (source_invoice["id"], source_before, source_before-expense["amount_cents"], "RECURRENCE_MOVED_OUT", correlation_id, actor, utc_text(clock.now_utc())))
            if target_invoice and target_invoice["state"] == "CLOSED" and target_invoice["id"] != (source_invoice["id"] if source_invoice else None):
                target_before = effective_total(connection, target_invoice["id"])
                connection.execute("INSERT INTO invoice_total_revisions(invoice_id,previous_total_cents,new_total_cents,reason_code,correlation_id,actor,created_at) VALUES(?,?,?,?,?,?,?)", (target_invoice["id"], target_before, target_before+amount_cents, "RECURRENCE_MOVED_IN", correlation_id, actor, utc_text(clock.now_utc())))
            if ordinal == anchor_ordinal:
                connection.execute("UPDATE expenses SET description=?,amount_cents=?,expense_date=?,due_date=?,planned_payment_method=?,account_id=?,card_id=?,invoice_id=?,recurring_version_id=?,materialization_slot_key=?,updated_at=? WHERE id=?", (description, amount_cents, new_date.isoformat(), due.isoformat() if due else None, payment_method, account_id, card_id, invoice_id, new_version_id, material_key, utc_text(clock.now_utc()), expense["id"]))
                new_expense_id = expense["id"]
            else:
                new_expense_id = connection.execute("SELECT COALESCE(MAX(id),0)+1 FROM expenses").fetchone()[0]
                connection.execute("UPDATE expenses SET lifecycle_state='SUPERSEDED',superseded_at=?,superseded_by_expense_id=?,supersession_reason_code='THIS_AND_FUTURE',supersession_correlation_id=?,updated_at=? WHERE id=?", (utc_text(clock.now_utc()), new_expense_id, correlation_id, utc_text(clock.now_utc()), expense["id"]))
                connection.execute("INSERT INTO expenses(id,description,amount_cents,expense_date,due_date,planned_payment_method,category_id,account_id,card_id,invoice_id,recurring_series_id,recurring_version_id,recurrence_occurrence_key,logical_slot_lineage_key,materialization_slot_key,lifecycle_state,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,'ACTIVE',?,?)", (new_expense_id, description, amount_cents, new_date.isoformat(), due.isoformat() if due else None, payment_method, expense["category_id"], account_id, card_id, invoice_id, series["id"], new_version_id, str(uuid4()), lineage_key(series["lineage_epoch_uuid"], ordinal), material_key, utc_text(clock.now_utc()), utc_text(clock.now_utc())))
            connection.execute("DELETE FROM expense_tags WHERE expense_id=?", (new_expense_id,))
            connection.execute("INSERT INTO expense_tags(expense_id,tag_id) SELECT ?,tag_id FROM recurring_version_tags WHERE recurring_version_id=?", (new_expense_id, new_version_id))
            connection.execute("INSERT INTO recurrence_slot_resolutions(id,recurring_series_id,recurring_version_id,materialization_slot_key,logical_slot_lineage_key,logical_ordinal,logical_occurrence_date,resolution,resolution_state,reason_code,correlation_id,created_at,expense_id) VALUES(?,?,?,?,?,?,?,'CREATED','ACTIVE','THIS_AND_FUTURE',?,?,?)", (new_resolution_id, series["id"], new_version_id, material_key, lineage_key(series["lineage_epoch_uuid"], ordinal), ordinal, new_date.isoformat(), correlation_id, utc_text(clock.now_utc()), new_expense_id))
            if source_invoice and source_invoice["state"] == "CLOSED" and source_invoice["id"] != invoice_id:
                normalize_invoice_state(connection, source_invoice["id"], clock)
            if target_invoice and target_invoice["state"] == "CLOSED" and target_invoice["id"] != (source_invoice["id"] if source_invoice else None):
                normalize_invoice_state(connection, target_invoice["id"], clock)
        audit_event(connection, "RECURRING_SERIES", series["id"], "THIS_AND_FUTURE", actor, correlation_id, clock, {"old_version_ids": [v["id"] for v in old_versions], "new_version_id": new_version_id, "anchor_expense_id": anchor_expense_id})
        return "RECURRING_VERSION", new_version_id, {"version_id": new_version_id, "series_id": series["id"], "correlation_id": correlation_id}
    response, replayed = execute_financial(connection, client_id=client_id, operation="this_and_future", key=idempotency_key, payload=payload, clock=clock, effect=effect)
    return int(response.get("version_id", response.get("resource_id"))), replayed


def change_series_from_date(connection: sqlite3.Connection, *, series_id: int, effective_from: date,
                            description: str, amount_cents: int, category_id: int, frequency: str, base_day: int | None,
                            payment_method: str, account_id: int | None, card_id: int | None,
                            due_rule: str, due_offset_days: int | None, due_day: int | None,
                            tags: tuple[int, ...], actor: str, correlation_id: str, clock: Clock,
                            client_id: str, idempotency_key: str) -> tuple[int, bool]:
    """Version an active series from an explicit date, even before materialization."""
    payload = {"series_id": series_id, "effective_from": effective_from.isoformat(), "description": description,
               "amount_cents": amount_cents, "frequency": frequency, "base_day": base_day,
               "payment_method": payment_method, "account_id": account_id, "card_id": card_id,
               "due_rule": due_rule, "due_offset_days": due_offset_days, "due_day": due_day, "tags": tags}
    def effect():
        series = require_row(connection, "SELECT * FROM recurring_series WHERE id=?", (series_id,), "series")
        if series["ended_at"] is not None:
            raise InvalidState("ended series is terminal")
        if effective_from < date.fromisoformat(series["start_date"]):
            raise ValidationError("effective date precedes series")
        require_positive_cents(amount_cents)
        normalized_base_day = effective_from.day if frequency not in {"WEEKLY", "BIWEEKLY"} and base_day is None else base_day
        _validate_version(connection, frequency, normalized_base_day, payment_method, account_id, card_id, due_rule, due_offset_days, due_day)
        active = connection.execute("SELECT * FROM recurring_series_versions WHERE recurring_series_id=? AND lifecycle_state='ACTIVE' AND effective_from<=? AND (effective_to IS NULL OR effective_to>=?) ORDER BY effective_from DESC LIMIT 1", (series_id, effective_from.isoformat(), effective_from.isoformat())).fetchone()
        if active and active["effective_from"] == effective_from.isoformat():
            raise Conflict("a version already starts on this date")
        if active:
            from datetime import timedelta
            connection.execute("UPDATE recurring_series_versions SET effective_to=? WHERE id=?", ((effective_from - timedelta(days=1)).isoformat(), active["id"]))
        anchor = str(uuid4())
        require_active(connection, "categories", category_id)
        version = connection.execute("INSERT INTO recurring_series_versions(recurring_series_id,lifecycle_state,description,category_id,created_at,effective_from,effective_to,anchor_occurrence_key,anchor_logical_date,anchor_logical_ordinal,frequency,base_day,amount_cents,planned_payment_method,account_id,card_id,due_rule,due_offset_days,due_day) VALUES(?,'ACTIVE',?,?,?, ?,NULL,?,?,0,?,?,?,?,?,?,?,?,?)", (series_id, description.strip(), category_id, utc_text(clock.now_utc()), effective_from.isoformat(), anchor, effective_from.isoformat(), frequency, normalized_base_day, amount_cents, payment_method, account_id, card_id, due_rule, due_offset_days, due_day)).lastrowid
        for tag_id in tags:
            require_active(connection, "tags", tag_id)
            connection.execute("INSERT INTO recurring_version_tags(recurring_version_id,tag_id) VALUES(?,?)", (version, tag_id))
        audit_event(connection, "RECURRING_SERIES", series_id, "EDIT", actor, correlation_id, clock, {"version_id": version, "effective_from": effective_from.isoformat()})
        return "RECURRING_VERSION", version, {"version_id": version, "correlation_id": correlation_id}
    response, replayed = execute_financial(connection, client_id=client_id, operation="change_series_from_date", key=idempotency_key, payload=payload, clock=clock, effect=effect)
    return int(response.get("version_id", response.get("resource_id"))), replayed


def cancel_this_and_future(connection: sqlite3.Connection, *, anchor_expense_id: int, actor: str, correlation_id: str, clock: Clock, client_id: str, idempotency_key: str) -> tuple[int, bool]:
    payload = {"anchor_expense_id": anchor_expense_id}
    def effect():
        anchor = require_row(connection, "SELECT * FROM expenses WHERE id=?", (anchor_expense_id,), "anchor")
        if anchor["recurring_series_id"] is None: raise ValidationError("anchor must be recurring")
        if connection.execute("SELECT 1 FROM expense_payments WHERE expense_id=? AND reversed_at IS NULL", (anchor_expense_id,)).fetchone():
            raise Conflict("paid anchor requires reversal")
        series = require_row(connection, "SELECT * FROM recurring_series WHERE id=?", (anchor["recurring_series_id"],), "series")
        if series["ended_at"] is not None: raise InvalidState("series already ended")
        cut = date.fromisoformat(anchor["expense_date"])
        rows = connection.execute("SELECT id FROM expenses WHERE recurring_series_id=? AND expense_date>=? AND lifecycle_state='ACTIVE'", (series["id"], cut.isoformat())).fetchall()
        for row in rows:
            paid = connection.execute("SELECT 1 FROM expense_payments WHERE expense_id=? AND reversed_at IS NULL", (row["id"],)).fetchone()
            if not paid:
                connection.execute("UPDATE expenses SET lifecycle_state='CANCELLED',updated_at=? WHERE id=?", (utc_text(clock.now_utc()), row["id"]))
                audit_event(connection, "EXPENSE", row["id"], "CANCEL", actor, correlation_id, clock, {"scope": "THIS_AND_FUTURE"})
        connection.execute("UPDATE recurring_series SET end_date=?,ended_at=? WHERE id=?", ((cut-timedelta(days=1)).isoformat(), utc_text(clock.now_utc()), series["id"]))
        audit_event(connection, "RECURRING_SERIES", series["id"], "END", actor, correlation_id, clock, {"cut_date": cut.isoformat()})
        return "RECURRING_SERIES", series["id"], {"series_id": series["id"], "correlation_id": correlation_id}
    response,replayed=execute_financial(connection,client_id=client_id,operation="cancel_this_and_future",key=idempotency_key,payload=payload,clock=clock,effect=effect)
    return int(response.get("series_id",response.get("resource_id"))),replayed
