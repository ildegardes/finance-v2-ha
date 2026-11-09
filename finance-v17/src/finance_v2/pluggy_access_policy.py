"""Explicit personal-proxy policy. No networking, credentials or log output."""
from uuid import UUID
from urllib.parse import urlencode

from .pluggy_client import PluggyError, _identifier


def validate_access_context(connection, item):
    connector = item.get('connector')
    if connection.access_mode == 'strict':
        return
    if not isinstance(connector, dict):
        raise PluggyError('ACCESS_CONTEXT_NOT_VERIFIED')
    if connection.access_mode == 'sandbox':
        if connector.get('isSandbox') is not True:
            raise PluggyError('SANDBOX_CONTEXT_MISMATCH')
    elif (type(connector.get('id')) is not int or connector['id'] != 200
          or connector.get('isSandbox') is not False
          or connector.get('isOpenFinance') is not False):
        raise PluggyError('PERSONAL_PROXY_CONTEXT_MISMATCH')


def personal_consents(client, item, item_id, get):
    """Observe foreign associations without accepting or persisting their rows.

    Only an explicit personal profile uses this policy. Financial scope guards
    stay in the original collection validator, including this consent validator.
    """
    from .pluggy_coverage import _collection_batches, _expired, _whole_number, _notify
    try:
        expected_uuid = UUID(item_id)
    except (ValueError, AttributeError):
        raise PluggyError('CONSENT_ASSOCIATION_INVALID') from None
    _notify(client, 'consents', '')
    path = '/consents?' + urlencode({'itemId': item_id})
    data, state = get(path, True)
    if state != 'AVAILABLE':
        yield dict(resource='consents',parent='',rows=[],state=state,last=True)
        return
    rows = client._rows(data)
    # Validate completeness and identities BEFORE classifying association.
    for key in ('total', 'totalPages', 'page'):
        if not _whole_number(data.get(key)):
            raise PluggyError('INVALID_RESPONSE')
    if (data['page'] != 1 or data['total'] != len(rows)
        or data['totalPages'] not in (0,1) or (data['totalPages']==0 and rows)):
        raise PluggyError('INVALID_RESPONSE')
    ids = [_identifier(row.get('id')) for row in rows]
    if len(set(ids)) != len(ids):
        raise PluggyError('INVALID_RESPONSE')
    foreign = False
    for row in rows:
        association = row.get('itemId')
        try:
            if not isinstance(association,str): raise ValueError()
            association_uuid = UUID(association)
        except (ValueError, AttributeError):
            raise PluggyError('CONSENT_ASSOCIATION_INVALID') from None
        # Observational UUID equivalence is NOT an authorization normalization.
        # Preserve the historical rejection, including any applicable revocation.
        if association != item_id and association_uuid == expected_uuid:
            raise PluggyError('ACCOUNT_SCOPE_MISMATCH')
        # Validate every expiry: no all()/any() short-circuit hiding later rows.
        expired = _expired(row.get('expiresAt'))
        if association == item_id:
            if expired or row.get('revokedAt') is not None:
                raise PluggyError('CONSENT_NOT_ACTIVE')
        else:
            foreign = True
    try:
        batches = list(_collection_batches(client,item,item_id,
            lambda current,optional=False:(data,state),PluggyError,_identifier,
            'consents','','/consents',{'itemId':item_id},True))
    except PluggyError as error:
        if not foreign or error.code != 'ACCOUNT_SCOPE_MISMATCH':
            raise
        # Failed audit does not overwrite previous accepted consent snapshots.
        yield dict(resource='consents',parent='',rows=[],state='FAILED',last=True,
                   error_code='ITEM_ID_DIFFERENT')
        return
    yield from batches
