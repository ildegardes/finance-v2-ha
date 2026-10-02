"""Read-only recurrence forecasts; never materialize or mutate an obligation."""
from datetime import date

from .calendar import due_date_for
from .recurrence import resolve_logical_slot
from .revenue_recurrence import next_occurrence


def association_name(connection, version):
    table, identifier = ("cards", version.get("card_id")) if version.get("card_id") else ("accounts", version.get("account_id"))
    row = connection.execute(f"SELECT name FROM {table} WHERE id=?", (identifier,)).fetchone() if identifier else None
    return row[0] if row else None


def expense_forecast(connection, series_id, on):
    series = connection.execute("SELECT * FROM recurring_series WHERE id=?", (series_id,)).fetchone()
    if not series or series["ended_at"]:
        return None
    versions = connection.execute("SELECT * FROM recurring_series_versions WHERE recurring_series_id=? ORDER BY (lifecycle_state='ACTIVE'),effective_from,id", (series_id,)).fetchall()
    for ordinal in range(10001):
        candidate, version = resolve_logical_slot(versions, ordinal)
        if candidate is None:
            continue
        if series["end_date"] and candidate > date.fromisoformat(series["end_date"]):
            return None
        if candidate < on:
            continue
        # A cancelled occurrence is not an upcoming charge. Protected slots
        # retain their actual values instead of reinterpreting their history.
        resolved = connection.execute("SELECT e.* FROM recurrence_slot_resolutions r JOIN expenses e ON e.id=COALESCE(r.expense_id,r.protected_expense_id) WHERE r.recurring_series_id=? AND r.logical_ordinal=? AND r.resolution_state='ACTIVE'", (series_id, ordinal)).fetchone()
        if resolved and resolved["lifecycle_state"] == "CANCELLED":
            continue
        values = dict(resolved) if resolved else dict(version)
        due = date.fromisoformat(resolved["due_date"]) if resolved and resolved["due_date"] else due_date_for(candidate, version["due_rule"], version["due_offset_days"], version["due_day"])
        return {"next_occurrence": candidate.isoformat(), "next_due_date": due.isoformat() if due else None, "association_name": association_name(connection, values), "description": values["description"], "amount_cents": values["amount_cents"], "frequency": version["frequency"], "planned_payment_method": values["planned_payment_method"]}
    return None


def revenue_forecast(connection, series, on):
    if not series["active"]:
        return None
    current = date.fromisoformat(series["start_date"])
    for _ in range(10001):
        if series["end_date"] and current > date.fromisoformat(series["end_date"]):
            return None
        if current >= on:
            cancelled = connection.execute("SELECT r.lifecycle_state FROM revenue_recurring_occurrences o JOIN revenues r ON r.id=o.revenue_id WHERE o.series_id=? AND o.occurrence_date=?", (series["id"], current.isoformat())).fetchone()
            if not cancelled or cancelled[0] != "CANCELLED":
                return {"next_occurrence": current.isoformat(), "next_due_date": current.isoformat(), "association_name": association_name(connection, dict(series))}
        current = next_occurrence(current, series["frequency"], series["expected_day"])
    return None
