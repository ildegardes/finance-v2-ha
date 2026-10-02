from __future__ import annotations

from calendar import monthrange
from datetime import date, timedelta

from ..db import immediate_transaction
from .clock import utc_text
from .errors import InvalidState, ValidationError
from .idempotent import execute_financial
from .revenues import _create
from .support import audit_event, require_active, require_row


MONTH_STEPS = {"MONTHLY": 1, "BIMONTHLY": 2, "QUARTERLY": 3, "SEMIANNUAL": 6, "ANNUAL": 12}
FREQUENCIES = frozenset({"WEEKLY", "BIWEEKLY", *MONTH_STEPS})


def next_occurrence(current: date, frequency: str, anchor_day: int) -> date:
    if frequency in {"WEEKLY", "BIWEEKLY"}:
        return current + timedelta(days=7 if frequency == "WEEKLY" else 14)
    raw_month = current.month + MONTH_STEPS[frequency]
    year = current.year + (raw_month - 1) // 12
    month = (raw_month - 1) % 12 + 1
    return date(year, month, min(anchor_day, monthrange(year, month)[1]))


def _validate(description, amount_cents, start_date, end_date, frequency, expected_day):
    if not isinstance(description, str) or not description.strip() or amount_cents <= 0 or frequency not in FREQUENCIES:
        raise ValidationError("invalid revenue recurrence")
    if not 1 <= expected_day <= 31 or end_date is not None and end_date < start_date:
        raise ValidationError("invalid revenue recurrence dates")


def _create_series(connection, *, description, amount_cents, start_date, end_date,
                   frequency, expected_day, category_id, account_id, tags,
                   actor, correlation_id, clock):
    _validate(description, amount_cents, start_date, end_date, frequency, expected_day)
    require_active(connection, "categories", category_id)
    if account_id is not None:
        require_active(connection, "accounts", account_id)
    series_id = connection.execute(
        "INSERT INTO revenue_recurring_series(description,amount_cents,start_date,end_date,frequency,category_id,account_id,expected_day,active,created_at) VALUES(?,?,?,?,?,?,?,?,1,?)",
        (description.strip(), amount_cents, start_date.isoformat(), end_date.isoformat() if end_date else None, frequency, category_id, account_id, expected_day, utc_text(clock.now_utc())),
    ).lastrowid
    for tag_id in tuple(dict.fromkeys(tags)):
        require_active(connection, "tags", tag_id)
        connection.execute("INSERT INTO revenue_recurring_series_tags VALUES(?,?)", (series_id, tag_id))
    connection.execute("INSERT INTO revenue_recurring_series_versions(series_id,description,amount_cents,start_date,end_date,frequency,expected_day,category_id,account_id,effective_from,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)", (series_id, description.strip(), amount_cents, start_date.isoformat(), end_date.isoformat() if end_date else None, frequency, expected_day, category_id, account_id, start_date.isoformat(), utc_text(clock.now_utc())))
    audit_event(connection, "REVENUE_RECURRING_SERIES", series_id, "CREATE", actor, correlation_id, clock)
    return series_id


def create_revenue_series_idempotent(connection, *, client_id, idempotency_key, **kwargs):
    payload = {k: (v.isoformat() if isinstance(v, date) else list(v) if isinstance(v, tuple) else v) for k, v in kwargs.items() if k not in {"clock", "actor"}}
    def effect():
        series_id = _create_series(connection, **kwargs)
        return "REVENUE_RECURRING_SERIES", series_id, {"id": series_id, "correlation_id": kwargs["correlation_id"]}
    response, replayed = execute_financial(connection, client_id=client_id, operation="revenue_series_create", key=idempotency_key, payload=payload, clock=kwargs["clock"], effect=effect)
    return response.get("id", response.get("resource_id")), replayed


def _materialize(connection, *, series_id, through, actor, correlation_id, clock):
    series = require_row(connection, "SELECT * FROM revenue_recurring_series WHERE id=?", (series_id,), "revenue series")
    if not series["active"]:
        return []
    last = connection.execute("SELECT MAX(occurrence_date) FROM revenue_recurring_occurrences WHERE series_id=?", (series_id,)).fetchone()[0]
    current = next_occurrence(date.fromisoformat(last), series["frequency"], series["expected_day"]) if last else date.fromisoformat(series["start_date"])
    end = min(through, date.fromisoformat(series["end_date"])) if series["end_date"] else through
    tags = tuple(row[0] for row in connection.execute("SELECT tag_id FROM revenue_recurring_series_tags WHERE series_id=? ORDER BY tag_id", (series_id,)))
    revenue_ids = []
    while current <= end:
        version = connection.execute("SELECT * FROM revenue_recurring_series_versions WHERE series_id=? AND effective_from<=? AND (effective_to IS NULL OR effective_to>=?) ORDER BY effective_from DESC,id DESC LIMIT 1", (series_id, current.isoformat(), current.isoformat())).fetchone()
        if version:
            series = version
        revenue_id = _create(
            connection, description=series["description"], amount_cents=series["amount_cents"],
            competence_date=current, expected_on=current, category_id=series["category_id"],
            account_id=series["account_id"], notes=None, tags=tags, actor=actor,
            correlation_id=correlation_id, clock=clock,
        )
        connection.execute(
            "INSERT INTO revenue_recurring_occurrences(series_id,revenue_id,occurrence_date) VALUES(?,?,?)",
            (series_id, revenue_id, current.isoformat()),
        )
        revenue_ids.append(revenue_id)
        current = next_occurrence(current, series["frequency"], series["expected_day"])
    return revenue_ids


def change_revenue_series_from_date(connection, *, series_id, effective_from, description, amount_cents, frequency, expected_day, category_id, account_id, actor, correlation_id, clock, client_id, idempotency_key):
    payload = {"series_id": series_id, "effective_from": effective_from.isoformat(), "description": description, "amount_cents": amount_cents, "frequency": frequency, "expected_day": expected_day, "category_id": category_id, "account_id": account_id}
    def effect():
        series = require_row(connection, "SELECT * FROM revenue_recurring_series WHERE id=?", (series_id,), "revenue series")
        _validate(description, amount_cents, effective_from, date.fromisoformat(series["end_date"]) if series["end_date"] else None, frequency, expected_day)
        require_active(connection, "categories", category_id)
        old = connection.execute("SELECT id FROM revenue_recurring_series_versions WHERE series_id=? AND effective_from<? AND (effective_to IS NULL OR effective_to>=?) ORDER BY effective_from DESC,id DESC LIMIT 1", (series_id, effective_from.isoformat(), effective_from.isoformat())).fetchone()
        if old:
            connection.execute("UPDATE revenue_recurring_series_versions SET effective_to=? WHERE id=?", ((effective_from - timedelta(days=1)).isoformat(), old[0]))
        vid = connection.execute("INSERT INTO revenue_recurring_series_versions(series_id,description,amount_cents,start_date,end_date,frequency,expected_day,category_id,account_id,effective_from,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)", (series_id, description.strip(), amount_cents, effective_from.isoformat(), series["end_date"], frequency, expected_day, category_id, account_id, effective_from.isoformat(), utc_text(clock.now_utc()))).lastrowid
        connection.execute("UPDATE revenue_recurring_series SET description=?,amount_cents=?,frequency=?,expected_day=?,category_id=?,account_id=? WHERE id=?", (description.strip(), amount_cents, frequency, expected_day, category_id, account_id, series_id))
        audit_event(connection, "REVENUE_RECURRING_SERIES", series_id, "CHANGE_FROM", actor, correlation_id, clock)
        return "REVENUE_RECURRING_SERIES", series_id, {"id": series_id, "version_id": vid, "correlation_id": correlation_id}
    response, replayed = execute_financial(connection, client_id=client_id, operation="revenue_series_change_from", key=idempotency_key, payload=payload, clock=clock, effect=effect)
    return response.get("version_id"), replayed


def materialize_revenue_series(connection, *, series_id, through, actor, correlation_id, clock):
    with immediate_transaction(connection):
        return _materialize(connection, series_id=series_id, through=through, actor=actor, correlation_id=correlation_id, clock=clock)


def materialize_revenue_series_idempotent(connection, *, series_id, through, actor,
                                          correlation_id, clock, client_id, idempotency_key):
    payload = {"series_id": series_id, "through": through.isoformat(), "correlation_id": correlation_id}
    def effect():
        revenue_ids = _materialize(connection, series_id=series_id, through=through, actor=actor, correlation_id=correlation_id, clock=clock)
        return "REVENUE_RECURRING_SERIES", series_id, {"series_id": series_id, "revenue_ids": revenue_ids, "correlation_id": correlation_id}
    response, replayed = execute_financial(connection, client_id=client_id, operation="revenue_series_materialize", key=idempotency_key, payload=payload, clock=clock, effect=effect)
    if "revenue_ids" in response:
        revenue_ids = response["revenue_ids"]
    else:
        revenue_ids = [row[0] for row in connection.execute(
            "SELECT revenue_id FROM revenue_recurring_occurrences WHERE series_id=? AND occurrence_date<=? ORDER BY occurrence_date",
            (series_id, through.isoformat()),
        )]
    return revenue_ids, replayed


def end_revenue_series_idempotent(connection, *, series_id, actor, correlation_id,
                                  clock, client_id, idempotency_key):
    payload = {"series_id": series_id, "correlation_id": correlation_id}
    def effect():
        series = require_row(connection, "SELECT * FROM revenue_recurring_series WHERE id=?", (series_id,), "revenue series")
        if not series["active"]:
            raise InvalidState("revenue series is already ended")
        connection.execute("UPDATE revenue_recurring_series SET active=0,ended_at=? WHERE id=?", (utc_text(clock.now_utc()), series_id))
        audit_event(connection, "REVENUE_RECURRING_SERIES", series_id, "END", actor, correlation_id, clock)
        return "REVENUE_RECURRING_SERIES", series_id, {"id": series_id, "correlation_id": correlation_id}
    response, replayed = execute_financial(connection, client_id=client_id, operation="revenue_series_end", key=idempotency_key, payload=payload, clock=clock, effect=effect)
    return response.get("id", response.get("resource_id")), replayed
