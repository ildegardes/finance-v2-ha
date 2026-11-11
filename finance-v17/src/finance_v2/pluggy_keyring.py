"""Provision the add-on keyring without printing or exporting key material."""
import base64
from contextlib import closing
import json
import os
from pathlib import Path
import sqlite3
from tempfile import NamedTemporaryFile

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from .config import Settings
from .db import connect, immediate_transaction
from .open_finance_registry import load_keyring
from .pluggy_credential_protection import CredentialProtectionError


def _install_new_keyring(path: Path):
    key = base64.b64encode(AESGCM.generate_key(bit_length=256)).decode("ascii")
    temporary_path = None
    try:
        with NamedTemporaryFile(mode="wb", dir=path.parent, prefix=".pluggy-keyring-", delete=False) as stream:
            temporary_path = Path(stream.name)
            os.fchmod(stream.fileno(), 0o600)
            stream.write(json.dumps({"active": "initial", "keys": {"initial": key}}).encode("ascii"))
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary_path, path, follow_symlinks=False)
    finally:
        if temporary_path is not None:
            temporary_path.unlink()
    directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)


def provision(settings: Settings):
    """Create a first key only for an empty credential store after migration."""
    if settings.pluggy_admin_origin is None:
        return "CREDENTIAL_PROVISIONING_DISABLED"
    path = settings.pluggy_keyring_path
    if path is None or not hasattr(os, "O_NOFOLLOW") or not hasattr(os, "O_DIRECTORY"):
        raise CredentialProtectionError("CREDENTIAL_KEY_UNAVAILABLE")
    try:
        with closing(connect(settings.database_path, settings.busy_timeout_ms)) as db, immediate_transaction(db):
            if os.path.lexists(path):
                load_keyring(path)
                return "CREDENTIAL_KEYRING_PRESENT"
            if db.execute("SELECT 1 FROM of_connection_credentials LIMIT 1").fetchone():
                raise CredentialProtectionError("CREDENTIAL_KEY_RESTORE_REQUIRED")
            _install_new_keyring(path)
            load_keyring(path)
    except (OSError, sqlite3.Error):
        raise CredentialProtectionError("CREDENTIAL_KEY_PROVISIONING_FAILED") from None
    return "CREDENTIAL_KEYRING_PROVISIONED"
