"""HA options adapter. Its private stdout is captured by run.sh, never logged."""
import json
from pathlib import Path
import sys

from .pluggy_config import PluggyConnection, PluggyConfigurationError, connections_from_json, _unique_object


class HaPluggyConfigurationError(ValueError):
    """Only static diagnostics; no option value is included in errors."""


# Presentation presets belong to HA, not the provider client/service model.
PRESETS = (('itau','Ita\u00fa'), ('santander','Santander'))


def registry_from_options(options):
    if not isinstance(options,dict):raise HaPluggyConfigurationError('OPEN_FINANCE_INVALID_OPTIONS')
    enabled=options.get('open_finance_enabled',False)
    automatic=options.get('open_finance_auto_sync_enabled',False)
    if type(enabled) is not bool or type(automatic) is not bool:
        raise HaPluggyConfigurationError('OPEN_FINANCE_INVALID_FLAGS')
    for slug,_ in PRESETS:
        if type(options.get('pluggy_'+slug+'_enabled',False)) is not bool:
            raise HaPluggyConfigurationError('OPEN_FINANCE_INVALID_FLAGS')
    if automatic:
        raise HaPluggyConfigurationError('OPEN_FINANCE_AUTO_SYNC_UNAVAILABLE')
    if not enabled:return '{}'
    registry={}
    for slug,institution in PRESETS:
        # Disabled connections have no runtime credentials, including partially
        # entered credentials. Stored HA options are not removed or rewritten.
        if not options.get('pluggy_'+slug+'_enabled',False):continue
        values={field:options.get('pluggy_'+slug+'_'+field,'') for field in ('client_id','client_secret','item_id')}
        try:connection=PluggyConnection(slug,institution,**values,enabled=True)
        except (PluggyConfigurationError,TypeError):
            raise HaPluggyConfigurationError('OPEN_FINANCE_CONNECTION_INVALID_'+slug.upper()) from None
        registry[connection.id]={'institution':connection.institution,'client_id':connection.client_id,
            'client_secret':connection.client_secret,'item_id':connection.item_id,'enabled':connection.enabled}
    result=json.dumps(registry,separators=(',',':'))
    # Use precisely the Lote-2 parser, rather than a second internal contract.
    try:connections_from_json(result)
    except PluggyConfigurationError:raise HaPluggyConfigurationError('OPEN_FINANCE_INVALID_OPTIONS') from None
    return result


def load_registry(path):
    try:
        with Path(path).open('rb') as source:raw=source.read(1_000_001)
        if len(raw)>1_000_000:raise ValueError()
        def reject_constant(_):raise ValueError()
        options=json.loads(raw,object_pairs_hook=_unique_object,parse_constant=reject_constant)
    except (OSError,ValueError,UnicodeError,RecursionError):
        raise HaPluggyConfigurationError('OPEN_FINANCE_INVALID_OPTIONS_FILE') from None
    return registry_from_options(options)


def main(argv=None):
    args=sys.argv[1:] if argv is None else argv
    if len(args)!=1:
        print('OPEN_FINANCE_OPTIONS_PATH_REQUIRED',file=sys.stderr);return 1
    try:registry=load_registry(args[0])
    except HaPluggyConfigurationError as error:
        print(str(error),file=sys.stderr);return 1
    # Credential transport to the parent shell, not a diagnostic/report.
    # Never invoke this private helper standalone in a logged terminal.
    print(registry)
    return 0


if __name__=='__main__':raise SystemExit(main())
