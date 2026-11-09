"""HTTP projection only. Internal identity, scope guards and storage stay intact."""

_PRIVATE_KEYS=frozenset(('itemid','item_id','clientid','client_id','clientsecret',
                        'client_secret','apikey','api_key','access_token','authorization'))


def public_payload(payload,settings):
    """Do not expose configured credentials/Item IDs in owner-facing HTTP views.

    Optional provider association fields are omitted. Item rows retain their
    connection identity but not the configured provider Item UUID. Financial
    resource IDs used for navigation remain intact. Never reuse this projection
    for provider validation or persistence.
    """
    if not isinstance(payload,dict):return payload
    values=set()
    for config in settings.pluggy_connections:
        for key in ('client_id','client_secret','item_id'):
            value=getattr(config,key,'')
            if value:values.add(value)
        item=getattr(config,'item_id','')
        if item:values.update((item.lower(),item.upper()))
    values=tuple(sorted(values,key=len,reverse=True))

    def clean(value):
        if isinstance(value,dict):
            return {k:clean(v) for k,v in value.items() if k.lower() not in _PRIVATE_KEYS}
        if isinstance(value,list):return [clean(v) for v in value]
        if isinstance(value,str) and any(private in value for private in values):
            return ''  # No fragments, lengths or replacement text containing a secret.
        return value

    # These identifiers are not needed by the UI to navigate a connection.
    # Empty strings preserve the required string identity field contract.
    if payload.get('resource')=='item' and isinstance(payload.get('items'),list):
        items=[]
        for row in payload['items']:
            row=dict(row)
            if 'external_id' in row:row['external_id']=''
            if 'identity' in row:row['identity']={**row['identity'],'external_id':''}
            if 'data' in row:row['data']={k:v for k,v in row['data'].items() if k!='id'}
            items.append(row)
        payload={**payload,'items':items}
    return clean(payload)
