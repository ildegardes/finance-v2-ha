from contextlib import closing
from dataclasses import replace
import os
from pathlib import Path
import shutil
import sqlite3
import stat
from tempfile import TemporaryDirectory
import unittest

from finance_v2.config import Settings
from finance_v2.db import connect
from finance_v2.migrations import migrate
from finance_v2.open_finance_registry import load_keyring
from finance_v2.pluggy_credential_protection import CredentialProtectionError, ProtectedCredential
from finance_v2.pluggy_keyring import provision


@unittest.skipUnless(hasattr(os, "O_NOFOLLOW"), "requires Linux/POSIX keyring file permissions")
class KeyringProvisioningTests(unittest.TestCase):
    def setUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        root = Path(directory.name)
        self.settings = Settings(
            root / "fixture.sqlite3", "UTC", "127.0.0.1", 8766, 5000,
            pluggy_admin_origin="http://127.0.0.1:8766",
            pluggy_keyring_path=root / "fixture-keyring.json",
        )
        migrate(self.settings.database_path)

    def _seed_credential(self):
        provision(self.settings)
        record = load_keyring(self.settings.pluggy_keyring_path).seal(
            "app-fixture", 1, "synthetic-client", "synthetic-secret",
        )
        with closing(connect(self.settings.database_path)) as db:
            db.execute("INSERT INTO of_pluggy_applications VALUES ('app-fixture','Synthetic','PERSONAL')")
            db.execute(
                "INSERT INTO of_connection_credentials VALUES ('app-fixture',1,?,?,?,'fixture')",
                (record.key_id, record.nonce, record.ciphertext),
            )

    def test_opt_in_owner_permissions_and_idempotent_restarts(self):
        path = self.settings.pluggy_keyring_path
        self.assertEqual(provision(replace(self.settings, pluggy_admin_origin=None)), "CREDENTIAL_PROVISIONING_DISABLED")
        self.assertFalse(path.exists())
        self.assertEqual(provision(self.settings), "CREDENTIAL_KEYRING_PROVISIONED")
        self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
        original = path.read_bytes()
        self.assertEqual(provision(self.settings), "CREDENTIAL_KEYRING_PRESENT")
        self.assertEqual(path.read_bytes(), original)
        self.assertEqual(list(path.parent.glob(".pluggy-keyring-*")), [])

    def test_missing_key_with_encrypted_credentials_never_creates_replacement(self):
        self._seed_credential()
        self.settings.pluggy_keyring_path.unlink()
        with self.assertRaisesRegex(CredentialProtectionError, "^CREDENTIAL_KEY_RESTORE_REQUIRED$"):
            provision(self.settings)
        self.assertFalse(self.settings.pluggy_keyring_path.exists())

    def test_insecure_file_or_symlink_fails_closed(self):
        provision(self.settings)
        path = self.settings.pluggy_keyring_path
        path.chmod(0o644)
        with self.assertRaisesRegex(CredentialProtectionError, "^CREDENTIAL_KEY_CONFIGURATION_INVALID$"):
            provision(self.settings)
        original = path.with_name("other-keyring.json")
        path.rename(original)
        original.chmod(0o600)
        path.symlink_to(original)
        with self.assertRaisesRegex(CredentialProtectionError, "^CREDENTIAL_KEY_CONFIGURATION_INVALID$"):
            provision(self.settings)

    def test_sqlite_snapshot_and_matching_private_key_restore_credentials(self):
        self._seed_credential()
        root = self.settings.database_path.parent / "restored"
        root.mkdir()
        restored = replace(self.settings, database_path=root / "restored.sqlite3",
                           pluggy_keyring_path=root / "restored-keyring.json")
        with closing(connect(self.settings.database_path)) as source, closing(sqlite3.connect(restored.database_path)) as target:
            source.backup(target)
        with self.assertRaisesRegex(CredentialProtectionError, "^CREDENTIAL_KEY_RESTORE_REQUIRED$"):
            provision(restored)
        shutil.copy2(self.settings.pluggy_keyring_path, restored.pluggy_keyring_path)
        self.assertEqual(provision(restored), "CREDENTIAL_KEYRING_PRESENT")
        with closing(connect(restored.database_path)) as db:
            record = ProtectedCredential(*db.execute(
                "SELECT key_id,nonce,ciphertext FROM of_connection_credentials",
            ).fetchone())
            self.assertEqual(db.execute("PRAGMA integrity_check").fetchone()[0], "ok")
            self.assertEqual(db.execute("PRAGMA foreign_key_check").fetchall(), [])
        self.assertEqual(load_keyring(restored.pluggy_keyring_path).open("app-fixture", 1, record),
                         ("synthetic-client", "synthetic-secret"))
