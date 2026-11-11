from dataclasses import replace
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from finance_v2.config import Settings
from finance_v2.migrations import migrate
from finance_v2.open_finance import OpenFinanceService, SyncError
from finance_v2.pluggy_credential_protection import (
    CredentialProtectionError,
    CredentialProtector,
    ProtectedCredential,
)


class CredentialProtectionTests(unittest.TestCase):
    def setUp(self):
        self.key = AESGCM.generate_key(bit_length=256)
        self.protector = CredentialProtector("old", {"old": self.key})
        self.values = ("fixture-client", "fixture-secret")
        self.record = self.protector.seal("app-itau", 1, *self.values)

    def test_round_trip_and_fresh_nonce(self):
        self.assertEqual(self.protector.open("app-itau", 1, self.record), self.values)
        second = self.protector.seal("app-itau", 1, *self.values)
        self.assertNotEqual(self.record.nonce, second.nonce)
        self.assertNotEqual(self.record.ciphertext, second.ciphertext)
        for value in self.values:
            self.assertNotIn(value, repr(self.record))
            self.assertNotIn(value.encode(), self.record.ciphertext)

    def test_cross_application_and_revision_replay_fail(self):
        for application, revision in (("app-santander", 1), ("app-itau", 2)):
            with self.subTest(application=application, revision=revision):
                with self.assertRaisesRegex(CredentialProtectionError, "^CREDENTIAL_DECRYPTION_FAILED$"):
                    self.protector.open(application, revision, self.record)

    def test_corruption_and_wrong_key_fail(self):
        corrupted = bytes([self.record.ciphertext[0] ^ 1]) + self.record.ciphertext[1:]
        wrong = CredentialProtector("old", {"old": AESGCM.generate_key(bit_length=256)})
        for protector, record in (
            (self.protector, replace(self.record, ciphertext=corrupted)),
            (self.protector, replace(self.record, nonce=b"")),
            (wrong, self.record),
        ):
            with self.assertRaisesRegex(CredentialProtectionError, "^CREDENTIAL_DECRYPTION_FAILED$"):
                protector.open("app-itau", 1, record)

    def test_rotation_can_read_old_versions_until_old_key_is_removed(self):
        new_key = AESGCM.generate_key(bit_length=256)
        rotating = CredentialProtector("new", {"old": self.key, "new": new_key})
        self.assertEqual(rotating.open("app-itau", 1, self.record), self.values)
        new_record = rotating.seal("app-itau", 1, *self.values)
        self.assertEqual(new_record.key_id, "new")
        new_only = CredentialProtector("new", {"new": new_key})
        self.assertEqual(new_only.open("app-itau", 1, new_record), self.values)
        with self.assertRaisesRegex(CredentialProtectionError, "^CREDENTIAL_KEY_UNAVAILABLE$"):
            new_only.open("app-itau", 1, self.record)

    def test_invalid_inputs_are_sanitized(self):
        with self.assertRaisesRegex(CredentialProtectionError, "^CREDENTIAL_KEY_CONFIGURATION_INVALID$"):
            CredentialProtector("missing", {"old": self.key})
        with self.assertRaisesRegex(CredentialProtectionError, "^CREDENTIAL_INPUT_INVALID$"):
            self.protector.seal("app-itau", 1, self.values[0], "fixture-secret\n")
        with self.assertRaisesRegex(CredentialProtectionError, "^CREDENTIAL_CONTEXT_INVALID$"):
            self.protector.seal("app-itau", True, *self.values)

    def test_migrated_database_stores_only_the_credential_envelope(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "synthetic.sqlite3"
            self.assertIn(12, migrate(path))
            self.assertEqual(migrate(path), [])
            db = sqlite3.connect(path)
            try:
                db.execute("PRAGMA foreign_keys=ON")
                db.execute("INSERT INTO of_pluggy_applications VALUES ('app-itau','Test app','PERSONAL')")
                record = self.record
                db.execute(
                    """INSERT INTO of_connection_credentials
                       VALUES ('app-itau',1,?,?,?,'2026-01-01T00:00:00Z')""",
                    (record.key_id, record.nonce, record.ciphertext),
                )
                stored = ProtectedCredential(*db.execute(
                    "SELECT key_id,nonce,ciphertext FROM of_connection_credentials"
                ).fetchone())
                self.assertEqual(self.protector.open("app-itau", 1, stored), self.values)
                db.commit()
                self.assertEqual(db.execute("PRAGMA foreign_key_check").fetchall(), [])
                self.assertEqual(db.execute("PRAGMA integrity_check").fetchone(), ("ok",))
                for value in self.values:
                    self.assertNotIn(value, "\n".join(db.iterdump()))
            finally:
                db.close()

    def test_managed_sync_resolves_pinned_credentials_and_fences_stale_revision(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "synthetic.sqlite3"
            migrate(path)
            service = OpenFinanceService(Settings(path, "UTC", "127.0.0.1", 8766, 5000))
            db = service._db()
            try:
                db.execute("INSERT INTO of_pluggy_applications VALUES ('app-itau','Fixture','PERSONAL')")
                db.execute(
                    "INSERT INTO of_connection_credentials VALUES ('app-itau',1,?,?,?,'fixture')",
                    (self.record.key_id, self.record.nonce, self.record.ciphertext),
                )
                db.execute(
                    """INSERT INTO of_connections(id,institution,enabled,binding_hash,updated_at)
                       VALUES ('conn-fixture','Fixture',1,?,'fixture')""",
                    ("0" * 64,),
                )
                db.execute(
                    """INSERT INTO of_connection_registry(connection_id,source,lifecycle,label,updated_at)
                       VALUES ('conn-fixture','MANAGED','ACTIVE','Fixture','fixture')"""
                )
                db.execute("INSERT INTO of_managed_pluggy_items VALUES ('conn-fixture','app-itau',1,'fixture-item',0)")
                with patch("finance_v2.open_finance.load_keyring", return_value=self.protector):
                    config = service.resolve_config("conn-fixture")
                    self.assertEqual((config.client_id, config.client_secret), self.values)
                    self.assertEqual(config.item_id, "fixture-item")
                    self.assertEqual(config.access_mode, "meupluggy_personal")
                    self.assertFalse(config.auto_sync_enabled)
                    db.execute("UPDATE of_connection_registry SET revision=1 WHERE connection_id='conn-fixture'")
                    with self.assertRaisesRegex(SyncError, "^CONNECTION_CONFIGURATION_CHANGED$"):
                        service._claim(db, config, "UI:local", None, None)
                    db.execute("UPDATE of_connection_registry SET lifecycle='ARCHIVED' WHERE connection_id='conn-fixture'")
                    with self.assertRaisesRegex(SyncError, "^CONNECTION_NOT_ACTIVE$"):
                        service.resolve_config("conn-fixture")
                self.assertEqual(db.execute("SELECT count(*) FROM of_sync_runs").fetchone()[0], 0)
            finally:
                db.close()
