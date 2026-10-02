from __future__ import annotations

import calendar as month_calendar
from datetime import date, timedelta

from .errors import ValidationError


MONTH_STEP = {
    "MONTHLY": 1,
    "BIMONTHLY": 2,
    "QUARTERLY": 3,
    "SEMIANNUAL": 6,
    "ANNUAL": 12,
}


def add_months(value: date, months: int, base_day: int | None = None) -> date:
    index = value.year * 12 + value.month - 1 + months
    year, month0 = divmod(index, 12)
    month = month0 + 1
    desired = value.day if base_day is None else base_day
    return date(year, month, min(desired, month_calendar.monthrange(year, month)[1]))


def clamp_day(year: int, month: int, day: int) -> date:
    if not 1 <= day <= 31:
        raise ValidationError("calendar day must be between 1 and 31")
    return date(year, month, min(day, month_calendar.monthrange(year, month)[1]))


def occurrence_date(anchor: date, anchor_ordinal: int, target_ordinal: int, frequency: str, base_day: int | None) -> date:
    delta = target_ordinal - anchor_ordinal
    if delta < 0:
        raise ValidationError("target ordinal precedes the version anchor")
    if frequency == "WEEKLY":
        return anchor + timedelta(days=7 * delta)
    if frequency == "BIWEEKLY":
        return anchor + timedelta(days=14 * delta)
    if frequency not in MONTH_STEP or base_day is None:
        raise ValidationError("invalid frequency/base_day combination")
    return add_months(anchor, MONTH_STEP[frequency] * delta, base_day)


def due_date_for(occurrence: date, rule: str, offset_days: int | None = None, due_day: int | None = None) -> date | None:
    if rule == "SAME_DAY" and offset_days is None and due_day is None:
        return occurrence
    if rule == "OFFSET" and offset_days is not None and offset_days >= 0 and due_day is None:
        return occurrence + timedelta(days=offset_days)
    if rule == "DAY_OF_MONTH" and due_day is not None and offset_days is None:
        target = occurrence if due_day >= occurrence.day else add_months(occurrence, 1, occurrence.day)
        return clamp_day(target.year, target.month, due_day)
    if rule == "INVOICE" and offset_days is None and due_day is None:
        return None
    raise ValidationError("invalid due rule parameters")


def lineage_key(epoch_uuid: str, ordinal: int) -> str:
    from hashlib import sha256
    return sha256(f"finance-v2-lineage-v1|{epoch_uuid}|{ordinal}".encode("utf-8")).hexdigest()
