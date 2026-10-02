class DomainError(RuntimeError):
    code = "DOMAIN_ERROR"


class ValidationError(DomainError):
    code = "VALIDATION_ERROR"


class NotFound(DomainError):
    code = "NOT_FOUND"


class Conflict(DomainError):
    code = "CONFLICT"


class InvalidState(Conflict):
    code = "INVALID_STATE_TRANSITION"


class CardCalendarNotCovered(Conflict):
    code = "CARD_CALENDAR_NOT_COVERED"


class ActivePaymentExists(Conflict):
    code = "ACTIVE_PAYMENT_EXISTS"


class InactiveAccount(Conflict):
    code = "INACTIVE_ACCOUNT"


class Overpayment(Conflict):
    code = "OVERPAYMENT"


class InvoicePaid(Conflict):
    code = "INVOICE_PAID"


class AutoDebitRequiresAttention(Conflict):
    code = "AUTO_DEBIT_REQUIRES_ATTENTION"


class NewDueDateRequired(ValidationError):
    code = "NEW_DUE_DATE_REQUIRED"
