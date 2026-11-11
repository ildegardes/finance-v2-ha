"""Authenticated encryption for managed Pluggy credential versions."""
from dataclasses import dataclass, field
import json
import os
import re

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM


class CredentialProtectionError(ValueError):
    """A sanitized failure; no key, identifier or envelope in the message."""


@dataclass(frozen=True)
class ProtectedCredential:
    key_id: str
    nonce: bytes = field(repr=False)
    ciphertext: bytes = field(repr=False)


def _associated_data(application_id: str, revision: int, key_id: str) -> bytes:
    if (
        not isinstance(application_id, str)
        or not re.fullmatch(r"[a-z][a-z0-9-]{1,63}", application_id)
        or type(revision) is not int
        or not 1 <= revision <= 2**63 - 1
    ):
        raise CredentialProtectionError("CREDENTIAL_CONTEXT_INVALID")
    return json.dumps(
        ["finance-v17/pluggy/credential/v1", application_id, revision, key_id],
        separators=(",", ":"),
    ).encode("ascii")


class CredentialProtector:
    def __init__(self, active_key_id: str, keys: dict[str, bytes]):
        if (
            not isinstance(active_key_id, str)
            or not isinstance(keys, dict)
            or not 1 <= len(keys) <= 8
            or active_key_id not in keys
            or any(
                not isinstance(key_id, str)
                or not re.fullmatch(r"[a-zA-Z0-9_-]{1,32}", key_id)
                or not isinstance(key, bytes)
                or len(key) != 32
                for key_id, key in keys.items()
            )
        ):
            raise CredentialProtectionError("CREDENTIAL_KEY_CONFIGURATION_INVALID")
        self._active_key_id = active_key_id
        self._keys = {key_id: AESGCM(key) for key_id, key in keys.items()}

    def seal(
        self, application_id: str, revision: int, client_id: str, client_secret: str,
    ) -> ProtectedCredential:
        associated_data = _associated_data(application_id, revision, self._active_key_id)
        if any(
            not isinstance(value, str)
            or not 1 <= len(value) <= 512
            or value != value.strip()
            or any(ord(character) < 32 or ord(character) == 127 for character in value)
            for value in (client_id, client_secret)
        ):
            raise CredentialProtectionError("CREDENTIAL_INPUT_INVALID")
        nonce = os.urandom(12)
        plaintext = json.dumps([client_id, client_secret], separators=(",", ":")).encode("ascii")
        ciphertext = self._keys[self._active_key_id].encrypt(nonce, plaintext, associated_data)
        return ProtectedCredential(self._active_key_id, nonce, ciphertext)

    def open(
        self, application_id: str, revision: int, record: ProtectedCredential,
    ) -> tuple[str, str]:
        if not isinstance(record, ProtectedCredential) or not isinstance(record.key_id, str):
            raise CredentialProtectionError("CREDENTIAL_DECRYPTION_FAILED")
        cipher = self._keys.get(record.key_id)
        if cipher is None:
            raise CredentialProtectionError("CREDENTIAL_KEY_UNAVAILABLE")
        associated_data = _associated_data(application_id, revision, record.key_id)
        if (
            not isinstance(record.nonce, bytes)
            or len(record.nonce) != 12
            or not isinstance(record.ciphertext, bytes)
            or not 16 <= len(record.ciphertext) <= 12312
        ):
            raise CredentialProtectionError("CREDENTIAL_DECRYPTION_FAILED")
        try:
            client_id, client_secret = json.loads(
                cipher.decrypt(record.nonce, record.ciphertext, associated_data)
            )
        except (InvalidTag, ValueError, TypeError):
            raise CredentialProtectionError("CREDENTIAL_DECRYPTION_FAILED") from None
        return client_id, client_secret
