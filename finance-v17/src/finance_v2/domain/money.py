from __future__ import annotations

from .errors import ValidationError


def require_positive_cents(value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValidationError("money must be a positive integer number of cents")
    return value


def distribute_installments(total_cents: int, count: int) -> tuple[int, ...]:
    require_positive_cents(total_cents)
    if isinstance(count, bool) or not isinstance(count, int) or count <= 0:
        raise ValidationError("installment count must be a positive integer")
    base, remainder = divmod(total_cents, count)
    if base == 0:
        raise ValidationError("each installment must be at least one cent")
    return tuple([base] * (count - 1) + [base + remainder])
