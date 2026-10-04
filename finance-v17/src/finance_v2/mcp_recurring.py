"""MCP contracts only: all effects are delegated to canonical API/domain operations."""
from datetime import date
from .domain.errors import ValidationError

PAYMENT_METHODS = ["PIX", "DEBIT", "CASH", "BANK_SLIP", "AUTO_DEBIT", "CREDIT_CARD"]
FREQUENCIES = ["WEEKLY", "BIWEEKLY", "MONTHLY", "BIMONTHLY", "QUARTERLY", "SEMIANNUAL", "ANNUAL"]
DUE_RULES = ["SAME_DAY", "OFFSET", "DAY_OF_MONTH", "INVOICE"]
ID = {"type": "integer", "minimum": 1}
DATE = {"type": "string", "format": "date"}
KEY = {"type": "string", "minLength": 16, "maxLength": 128}
FIELDS = {
    "description": {"type": "string", "minLength": 1}, "category_id": ID,
    "amount_cents": ID, "frequency": {"type": "string", "enum": FREQUENCIES},
    "base_day": {"type": ["integer", "null"], "minimum": 1, "maximum": 31},
    "payment_method": {"type": "string", "enum": PAYMENT_METHODS},
    "account_id": {"type": ["integer", "null"], "minimum": 1},
    "card_id": {"type": ["integer", "null"], "minimum": 1},
    "due_rule": {"type": "string", "enum": DUE_RULES},
    "due_offset_days": {"type": ["integer", "null"], "minimum": 0},
    "due_day": {"type": ["integer", "null"], "minimum": 1, "maximum": 31},
    "tag_ids": {"type": "array", "items": ID, "uniqueItems": True},
}
REQUIRED = ["description", "category_id", "amount_cents", "frequency", "payment_method", "due_rule"]
# (method, path, canonical operation, identifier argument). No SQL or effects here.
OPERATIONS = {
    "finance_recurring_expense_list": ("GET", "/api/v2/recurring-series", "series_list", None),
    "finance_recurring_expense_get": ("GET", "/api/v2/recurring-series/{id}", "series_detail", "series_id"),
    "finance_recurring_expense_create": ("POST", "/api/v2/recurring-series", "series_create", None),
    "finance_recurring_expense_change_from": ("POST", "/api/v2/recurring-series/{id}/change-from", "series_change_from", "series_id"),
    "finance_recurring_expense_this_and_future": ("POST", "/api/v2/recurring-occurrences/{id}/this-and-future", "occurrence_change_future", "expense_id"),
    "finance_recurring_occurrence_payment_method": ("POST", "/api/v2/recurring-occurrences/{id}/payment-method", "occurrence_payment_method", "expense_id"),
    "finance_recurring_expense_end": ("POST", "/api/v2/recurring-series/{id}/end", "series_end", "series_id"),
}


def tools():
    schemas = {
        "series_list": ({"month": {"type": "string", "pattern": "^[0-9]{4}-[0-9]{2}$"}}, []),
        "series_detail": ({"series_id": ID}, ["series_id"]),
        "series_create": ({**FIELDS, "start_date": DATE, "end_date": {"type": ["string", "null"], "format": "date"}}, REQUIRED + ["start_date"]),
        "series_change_from": ({**FIELDS, "series_id": ID, "effective_from": DATE}, REQUIRED + ["series_id", "effective_from"]),
        "occurrence_change_future": ({**{k: v for k, v in FIELDS.items() if k != "category_id"}, "expense_id": ID}, [k for k in REQUIRED if k != "category_id"] + ["expense_id"]),
        "occurrence_payment_method": ({"expense_id": ID, "payment_method": FIELDS["payment_method"], "account_id": FIELDS["account_id"], "card_id": FIELDS["card_id"], "due_date": {"type": ["string", "null"], "format": "date"}}, ["expense_id", "payment_method"]),
        "series_end": ({"series_id": ID, "cut_date": DATE}, ["series_id", "cut_date"]),
    }
    descriptions = {
        "series_list": "List recurring expense rules, including ended series, with optional forecast month. This is read-only, not materialization.",
        "series_detail": "Get a recurring expense series, versions, materialized occurrences, overrides and audit history.",
        "series_create": "Create ONE recurring expense RULE/SERIES, not N manual expenses. Use for monthly/recurring bills; domain/scheduler materializes occurrences. Resolve category/account/card IDs using catalog tools; never guess IDs. Six methods only; BANK_TRANSFER unsupported. Monthly base_day defaults to start day; day 31 clamps to month end; weekly base_day must be null. CREDIT_CARD requires card_id and INVOICE; PIX/DEBIT/AUTO_DEBIT require account_id; CASH forbids account/card. Due rules: SAME_DAY, OFFSET (due_offset_days), DAY_OF_MONTH (due_day 1..31, clamped), INVOICE. end_date null means open-ended. Reuse the same idempotency_key on retry. Multiple rules require independent calls/results, not a global transaction; never substitute failures with one-shot expenses or report failed items as successful.",
        "series_change_from": "Prospective series version from effective_from. Requires complete replacement settings. FAILS if occurrences are already materialized on/after that date; does not edit history. Use this-and-future instead only with an explicit occurrence anchor and user intent.",
        "occurrence_change_future": "Change THIS occurrence and future eligible occurrences using expense_id as explicit anchor. Complete replacement settings; category is inherited, not changed. Canonical reconciliation preserves paid/protected history and logical slots. Not a prospective-only edit or individual occurrence edit.",
        "occurrence_payment_method": "Change ONLY this active unpaid recurring occurrence's planned payment association. Canonical operation creates/preserves an override; it does not pay the expense. Non-card requires due_date; card forbids it. Paid/terminal invoices fail closed. No series/future change.",
        "series_end": "Terminally end a series at cut_date (exclusive end). Cancel eligible occurrences on/after cut; preserve paid/override-protected history. Cannot reactivate terminal series. Reuse the key for retries.",
    }
    result = []
    for name, (method, _, operation, _) in OPERATIONS.items():
        properties, required = schemas[operation]
        write = method == "POST"
        if write:
            properties = {**properties, "idempotency_key": KEY}
            required = required + ["idempotency_key"]
        result.append({"name": name, "description": descriptions[operation],
                       "inputSchema": {"type": "object", "additionalProperties": False, "properties": properties, "required": required},
                       "annotations": {"readOnlyHint": not write, "destructiveHint": operation == "series_end", "idempotentHint": True}})
    return result


def validate_arguments(name, arguments):
    """Validate MCP boundary types; financial/calendar rules stay in the domain."""
    schema = next(tool["inputSchema"] for tool in tools() if tool["name"] == name)
    if not isinstance(arguments, dict) or set(arguments) - set(schema["properties"]) or set(schema["required"]) - set(arguments):
        raise ValidationError("missing or unsupported recurring tool fields")
    def check(value, spec):
        kind = "null" if value is None else "boolean" if isinstance(value, bool) else "integer" if isinstance(value, int) else "string" if isinstance(value, str) else "array" if isinstance(value, list) else "unsupported"
        types = spec["type"] if isinstance(spec["type"], list) else [spec["type"]]
        if kind not in types: raise ValidationError("invalid recurring field type")
        if value is None: return
        if "enum" in spec and value not in spec["enum"]: raise ValidationError("unsupported recurring enum")
        if kind == "integer" and (value < spec.get("minimum", value) or value > spec.get("maximum", value)): raise ValidationError("recurring integer out of range")
        if kind == "string":
            if not spec.get("minLength", 0) <= len(value.strip()) <= spec.get("maxLength", len(value)): raise ValidationError("invalid recurring string length")
            if spec.get("format") == "date":
                try:
                    if date.fromisoformat(value).isoformat() != value: raise ValueError()
                except ValueError: raise ValidationError("recurring dates must be YYYY-MM-DD") from None
        if kind == "array":
            for item in value: check(item, spec["items"])
            if spec.get("uniqueItems") and len(set(value)) != len(value): raise ValidationError("duplicate recurring tags")
    for field, value in arguments.items(): check(value, schema["properties"][field])
    if arguments.get("end_date") and arguments["end_date"] < arguments["start_date"]:
        raise ValidationError("end_date precedes start_date")
    if name == "finance_recurring_expense_list" and "month" in arguments:
        try:
            if date.fromisoformat(arguments["month"] + "-01").strftime("%Y-%m") != arguments["month"]: raise ValueError()
        except ValueError: raise ValidationError("month must be YYYY-MM") from None
