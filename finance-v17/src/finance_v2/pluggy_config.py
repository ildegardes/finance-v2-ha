"""Private Pluggy configuration; no networking, database or credential logging."""
from dataclasses import dataclass, field
import json
import re


class PluggyConfigurationError(ValueError):
    pass


@dataclass(frozen=True)
class PluggyConnection:
    id: str
    institution: str
    client_id: str = field(repr=False)
    client_secret: str = field(repr=False)
    item_id: str = field(repr=False)
    enabled: bool = False

    def __post_init__(self):
        valid = isinstance(self.id, str) and re.fullmatch(r'[a-z][a-z0-9-]{1,63}', self.id)
        for value in (self.institution, self.client_id, self.client_secret, self.item_id):
            valid = valid and isinstance(value, str) and 0 < len(value) <= 512
            valid = valid and value == value.strip() and not any(ord(c) < 32 or ord(c) == 127 for c in value)
        if not valid or not isinstance(self.enabled, bool) or len(self.institution)>200 or len(self.item_id)>200:
            raise PluggyConfigurationError('invalid Pluggy connection configuration')


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError()
        result[key] = value
    return result


def connections_from_json(raw: str | None) -> tuple[PluggyConnection, ...]:
    try:
        if raw is not None and (not isinstance(raw, str) or len(raw) > 65536):
            raise ValueError()
        payload = json.loads(raw or '{}', object_pairs_hook=_unique_object)
        if not isinstance(payload, dict) or len(payload) > 20:
            raise ValueError()
        result = []
        required = {'institution', 'client_id', 'client_secret', 'item_id'}
        for slug, values in payload.items():
            if not isinstance(values, dict) or not required <= set(values) or set(values) - required - {'enabled'}:
                raise ValueError()
            result.append(PluggyConnection(slug, **values))
        return tuple(result)
    except (ValueError, TypeError):
        raise PluggyConfigurationError('invalid Pluggy connection configuration') from None
