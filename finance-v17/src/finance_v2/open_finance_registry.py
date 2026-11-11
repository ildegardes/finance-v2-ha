"""Resolve the selected credential version for an active managed Item."""
import base64
import binascii
from dataclasses import dataclass
import json
import os
import stat

from .pluggy_config import PluggyConfigurationError, PluggyConnection, _unique_object
from .pluggy_credential_protection import (
    CredentialProtectionError,
    CredentialProtector,
    ProtectedCredential,
)


ACCESS_MODES = {
    "PERSONAL": "meupluggy_personal",
    "SANDBOX": "sandbox",
    "STRICT": "strict",
}


@dataclass(frozen=True)
class ConnectionView:
    id: str
    institution: str
    enabled: bool
    historical: bool
    access_mode: str
    auto_sync_enabled: bool


def connection_views(db, settings):
    """Owner-facing metadata only, including retained historical connections."""
    legacy = {cfg.id: cfg for cfg in settings.pluggy_connections}
    views = {
        cid: ConnectionView(cid, cfg.institution, cfg.enabled, False, cfg.access_mode, cfg.auto_sync_enabled)
        for cid, cfg in legacy.items()
    }
    for row in db.execute(
        """SELECT r.connection_id,r.source,r.lifecycle,r.label,a.environment,i.auto_sync_enabled
           FROM of_connection_registry r
           LEFT JOIN of_managed_pluggy_items i ON i.connection_id=r.connection_id
           LEFT JOIN of_pluggy_applications a ON a.id=i.application_id"""
    ):
        cid = row["connection_id"]
        if row["lifecycle"] == "REMOVED":
            views.pop(cid, None)
            continue
        active = row["lifecycle"] == "ACTIVE"
        if row["source"] == "MANAGED":
            mode = ACCESS_MODES.get(row["environment"])
            enabled = active and mode is not None
            auto = bool(row["auto_sync_enabled"])
        else:
            cfg = legacy.get(cid)
            mode = cfg.access_mode if cfg else None
            enabled = active and bool(cfg and cfg.enabled)
            auto = bool(cfg and cfg.auto_sync_enabled)
        views[cid] = ConnectionView(
            cid, row["label"], enabled, row["lifecycle"] == "ARCHIVED" or mode is None,
            mode or "strict", auto and enabled,
        )
    return views


def load_keyring(path):
    if path is None or not hasattr(os, "O_NOFOLLOW") or not hasattr(os, "geteuid"):
        raise CredentialProtectionError("CREDENTIAL_KEY_UNAVAILABLE")
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(descriptor, "rb") as stream:
            metadata = os.fstat(stream.fileno())
            if (
                not stat.S_ISREG(metadata.st_mode)
                or metadata.st_uid != os.geteuid()
                or metadata.st_mode & 0o077
                or metadata.st_nlink != 1
            ):
                raise ValueError
            raw = stream.read(8193)
            if len(raw) > 8192:
                raise ValueError
            payload = json.loads(raw, object_pairs_hook=_unique_object)
            if not isinstance(payload, dict) or set(payload) != {"active", "keys"}:
                raise ValueError
            if not isinstance(payload["keys"], dict) or len(payload["keys"]) > 8:
                raise ValueError
            keys = {key: base64.b64decode(value, validate=True) for key, value in payload["keys"].items()}
            return CredentialProtector(payload["active"], keys)
    except (OSError, ValueError, TypeError, binascii.Error):
        raise CredentialProtectionError("CREDENTIAL_KEY_CONFIGURATION_INVALID") from None


def managed_connection(db, connection_id, registry_revision, protector, *, lifecycle="ACTIVE"):
    row = db.execute(
        """SELECT r.label, a.id AS application_id, a.environment,
                  i.item_id, i.auto_sync_enabled, i.credential_revision,
                  v.key_id, v.nonce, v.ciphertext
           FROM of_connection_registry AS r
           JOIN of_managed_pluggy_items AS i ON i.connection_id=r.connection_id
           JOIN of_pluggy_applications AS a ON a.id=i.application_id
           JOIN of_connection_credentials AS v
             ON v.application_id=a.id AND v.revision=i.credential_revision
           WHERE r.connection_id=? AND r.revision=?
             AND r.source='MANAGED' AND r.lifecycle=?""",
        (connection_id, registry_revision, lifecycle),
    ).fetchone()
    if row is None:
        raise CredentialProtectionError("MANAGED_CONNECTION_UNAVAILABLE")
    client_id, client_secret = protector.open(
        row["application_id"], row["credential_revision"],
        ProtectedCredential(row["key_id"], row["nonce"], row["ciphertext"]),
    )
    try:
        return PluggyConnection(
            id=connection_id, institution=row["label"], client_id=client_id,
            client_secret=client_secret, item_id=row["item_id"], enabled=lifecycle == "ACTIVE",
            auto_sync_enabled=lifecycle == "ACTIVE" and bool(row["auto_sync_enabled"]),
            access_mode=ACCESS_MODES[row["environment"]],
            registry_revision=registry_revision,
        )
    except (KeyError, PluggyConfigurationError):
        raise CredentialProtectionError("MANAGED_CONNECTION_UNAVAILABLE") from None
