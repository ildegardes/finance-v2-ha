"""Shared capability policy for legacy clients and future OAuth identities."""

READ_SCOPE = "finance:read"
WRITE_SCOPE = "finance:write"
FINANCE_SCOPES = frozenset({READ_SCOPE, WRITE_SCOPE})


def required_capabilities(*, write: bool = False) -> frozenset[str]:
    return FINANCE_SCOPES if write else frozenset({READ_SCOPE})


def missing_capabilities(capabilities: frozenset[str], *, write: bool = False) -> frozenset[str]:
    return required_capabilities(write=write) - capabilities
