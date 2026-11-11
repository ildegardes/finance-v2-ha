from contextlib import closing
from dataclasses import replace
import hashlib
import hmac
from io import BytesIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from finance_v2.api import Application
from finance_v2.config import ConfigurationError, Settings
from finance_v2.migrations import migrate
from finance_v2.open_finance import OpenFinanceService, SyncError
from finance_v2.open_finance_http import RegistryRateLimiter
from finance_v2.open_finance_registry_admin import RegistryAdmin
from finance_v2.pluggy_client import PluggyClient
from finance_v2.pluggy_credential_protection import CredentialProtector


class RegistryEnrollmentTests(unittest.TestCase):
    def setUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        path = Path(directory.name) / "fixture.sqlite3"
        migrate(path)
        self.operations = []
        self.expected_secret = "fixture-secret"
        self.item = {
            "id": "fixture-item",
            "status": "UPDATED",
            "connector": {"id": 200, "isSandbox": False, "isOpenFinance": False},
        }
        self.service = OpenFinanceService(
            Settings(path, "UTC", "127.0.0.1", 8766, 5000),
            client_factory=lambda config: PluggyClient(config, send=self.send),
        )
        self.protector = CredentialProtector("fixture", {"fixture": AESGCM.generate_key(bit_length=256)})
        self.admin = RegistryAdmin(self.service, keyring_loader=lambda _: self.protector)

    def send(self, method, path, headers, body, timeout):
        self.operations.append((method, path))
        if (method, path) == ("POST", "/auth"):
            self.assertEqual(json.loads(body), {"clientId": "fixture-client", "clientSecret": self.expected_secret})
            return 200, {"apiKey": "fixture-token"}
        self.assertEqual((method, path), ("GET", "/items/fixture-item"))
        self.assertEqual(headers["X-API-KEY"], "fixture-token")
        return 200, self.item

    def draft(self, actor="UI:local", replaces_id=None):
        return self.admin.create_draft(
            actor=actor, label="Fixture", environment="PERSONAL",
            client_id="fixture-client", client_secret="fixture-secret", item_id="fixture-item",
            replaces_id=replaces_id,
        )

    def seed_santander(self):
        with closing(self.service._db()) as db, self.service._write(db):
            db.execute(
                """INSERT INTO of_connections(id,institution,enabled,binding_hash,sync_state,updated_at)
                   VALUES ('santander','Santander',1,?,'FAILED','fixture')""", ("1" * 64,),
            )
            db.execute(
                """INSERT INTO of_connection_registry(connection_id,source,lifecycle,label,updated_at)
                   VALUES ('santander','LEGACY','ACTIVE','Santander','fixture')""",
            )
            db.executemany(
                """INSERT INTO of_sync_runs(id,connection_id,actor,started_at,finished_at,state,error_code)
                   VALUES (?,'santander','UI:local','fixture','fixture','FAILED','AUTH_FAILED')""",
                [(f"old-{index}",) for index in range(26)],
            )

    def archive_santander(self):
        return self.admin.archive("santander", actor="UI:local", revision=0, confirmed=True)

    def test_owner_confirms_item_before_activating_without_import(self):
        draft = self.draft()
        self.assertEqual(self.operations, [])
        result = self.admin.validate_and_activate(draft["id"], actor="UI:local", revision=0, confirmed=True)
        self.assertEqual(result, {"id": draft["id"], "lifecycle": "ACTIVE", "revision": 1})
        self.assertEqual(self.operations, [("POST", "/auth"), ("GET", "/items/fixture-item")])
        with closing(self.service._db()) as db:
            self.assertEqual(db.execute("SELECT count(*) FROM of_sync_runs").fetchone()[0], 0)
            self.assertEqual(db.execute("SELECT auto_sync_enabled FROM of_managed_pluggy_items").fetchone()[0], 0)
            self.assertEqual([r[0] for r in db.execute("SELECT operation FROM of_connection_admin_events ORDER BY rowid")],
                             ["CREATE_DRAFT", "ACTIVATE"])
            self.assertNotIn("fixture-secret", "\n".join(db.iterdump()))

    def test_foreign_item_keeps_draft_inactive(self):
        draft = self.draft()
        self.item["id"] = "other-item"
        with self.assertRaisesRegex(SyncError, "^ITEM_ID_DIFFERENT$"):
            self.admin.validate_and_activate(draft["id"], actor="UI:local", revision=0, confirmed=True)
        with closing(self.service._db()) as db:
            self.assertEqual(db.execute("SELECT lifecycle FROM of_connection_registry").fetchone()[0], "DRAFT")
            self.assertEqual(db.execute("SELECT enabled FROM of_connections").fetchone()[0], 0)

    def test_catalog_details_and_selected_connector_are_scoped_to_draft(self):
        draft = self.draft()
        connection_id = draft["id"]
        def send(method, path, headers, body, timeout):
            if path == "/connectors":
                self.assertEqual((method, headers["X-API-KEY"]), ("GET", "fixture-token"))
                return 200, {"totalPages": 2, "results": [
                    {"id": 200, "name": "MeuPluggy", "isSandbox": False, "credentials": ["private"]},
                    {"id": 201, "name": "Other bank", "isSandbox": False},
                    {"id": 200, "name": "fixture-token", "isSandbox": False},
                ]}
            return self.send(method, path, headers, body, timeout)
        self.service.client_factory = lambda config: PluggyClient(config, send=send)
        args = dict(actor="UI:local", revision=0)
        catalog = self.admin.connector_catalog(connection_id, **args)
        self.assertEqual(catalog, {"connectors": [{"id": 200, "name": "MeuPluggy"}], "catalog_complete": False})
        with self.assertRaisesRegex(SyncError, "ITEM_CONNECTOR_DIFFERENT"):
            self.admin.validate_and_activate(connection_id, **args, confirmed=True, connector_id=201)
        detail = self.admin.connection_details(connection_id, **args)
        self.assertEqual(detail["lifecycle"], "DRAFT")
        self.assertNotIn("fixture-item", json.dumps(detail))
        self.assertNotIn("fixture-secret", json.dumps(detail))
        self.assertEqual(self.admin.validate_and_activate(connection_id, **args, confirmed=True, connector_id=200)["lifecycle"], "ACTIVE")

    def test_preview_reports_only_known_capabilities_and_does_not_activate_or_import(self):
        draft = self.draft()

        def send(method, path, headers, body, timeout):
            if path.startswith("/items/fixture-item/resources?"):
                self.operations.append((method, path))
                return 200, {"page": 1, "totalPages": 2, "total": 3, "results": [
                    {"resourceId": "private-resource-id", "type": "ACCOUNT", "status": "AVAILABLE"},
                    {"resourceId": "private-resource-id-2", "type": "fixture-secret", "status": "AVAILABLE"},
                ]}
            return self.send(method, path, headers, body, timeout)

        self.service.client_factory = lambda config: PluggyClient(config, send=send)
        result = self.admin.validate_connection(draft["id"], actor="UI:local", revision=0, confirmed=True)
        self.assertEqual(result["capabilities"], [{"type": "ACCOUNT", "status": "AVAILABLE"}])
        self.assertEqual(result["capabilities_state"], "PARTIAL")
        self.assertNotIn("private-resource-id", json.dumps(result))
        self.assertNotIn("fixture-secret", json.dumps(result))
        self.assertEqual(len(self.operations), 3)
        with closing(self.service._db()) as db:
            self.assertEqual(db.execute("SELECT lifecycle FROM of_connection_registry").fetchone()[0], "DRAFT")
            self.assertEqual(db.execute("SELECT count(*) FROM of_sync_runs").fetchone()[0], 0)

    def test_owner_confirmation_and_duplicate_binding_guards(self):
        with self.assertRaisesRegex(SyncError, "^OWNER_REQUIRED$"):
            self.draft(actor="CLIENT:fixture")
        draft = self.draft()
        with self.assertRaisesRegex(SyncError, "^CONNECTION_BINDING_ALREADY_REGISTERED$"):
            self.draft()
        with self.assertRaisesRegex(SyncError, "^ACTIVATION_CONFIRMATION_REQUIRED$"):
            self.admin.validate_and_activate(draft["id"], actor="UI:local", revision=0, confirmed=False)
        self.assertEqual(self.operations, [])

    def test_sandbox_cannot_be_enrolled_as_personal(self):
        draft = self.draft()
        self.item["connector"]["isSandbox"] = True
        with self.assertRaisesRegex(SyncError, "^ITEM_ENVIRONMENT_NOT_VERIFIED$"):
            self.admin.validate_and_activate(draft["id"], actor="UI:local", revision=0, confirmed=True)
        with closing(self.service._db()) as db:
            self.assertEqual(db.execute("SELECT lifecycle FROM of_connection_registry").fetchone()[0], "DRAFT")

    def test_rename_disable_and_reactivate_preserve_binding_and_require_current_revision(self):
        cid = self.draft()["id"]
        self.admin.validate_and_activate(cid, actor="UI:local", revision=0, confirmed=True)
        with closing(self.service._db()) as db:
            before = db.execute("SELECT binding_hash FROM of_connections WHERE id=?", (cid,)).fetchone()[0]
        self.assertEqual(self.admin.rename(cid, actor="UI:local", revision=1, label="Nome novo")["revision"], 2)
        self.assertEqual(self.admin.rename(cid, actor="UI:local", revision=2, label="Nome novo")["revision"], 2)
        with self.assertRaisesRegex(SyncError, "^CONNECTION_CONFIGURATION_CHANGED$"):
            self.admin.disable(cid, actor="UI:local", revision=1, confirmed=True)
        self.assertEqual(self.admin.disable(cid, actor="UI:local", revision=2, confirmed=True)["lifecycle"], "DISABLED")
        with self.assertRaisesRegex(SyncError, "^CONNECTION_NOT_ACTIVE$"):
            self.service.resolve_config(cid)
        self.assertEqual(len(self.operations), 2)
        self.assertEqual(self.admin.validate_and_activate(cid, actor="UI:local", revision=3, confirmed=True)["revision"], 4)
        self.assertEqual(len(self.operations), 4)
        with closing(self.service._db()) as db:
            self.assertEqual(db.execute("SELECT binding_hash FROM of_connections WHERE id=?", (cid,)).fetchone()[0], before)
            self.assertEqual(db.execute("SELECT label FROM of_connection_registry WHERE connection_id=?", (cid,)).fetchone()[0], "Nome novo")
            self.assertEqual(db.execute("SELECT count(*) FROM of_sync_runs").fetchone()[0], 0)

    def test_rotation_keeps_identity_and_other_items_on_their_credential_revision(self):
        cid = self.draft()["id"]
        self.admin.validate_and_activate(cid, actor="UI:local", revision=0, confirmed=True)
        with closing(self.service._db()) as db, self.service._write(db):
            db.execute(
                """INSERT INTO of_connections(id,institution,binding_hash,updated_at)
                   VALUES ('conn-sibling','Fixture',?,'fixture')""", ("1" * 64,),
            )
            db.execute(
                """INSERT INTO of_connection_registry(connection_id,source,lifecycle,label,updated_at)
                   VALUES ('conn-sibling','MANAGED','ACTIVE','Fixture','fixture')""",
            )
            db.execute(
                """INSERT INTO of_managed_pluggy_items(connection_id,application_id,credential_revision,item_id)
                   SELECT 'conn-sibling',application_id,credential_revision,'other-item'
                   FROM of_managed_pluggy_items WHERE connection_id=?""", (cid,),
            )
        args = dict(actor="UI:local", revision=1, confirmed=True, client_secret="rotated-fixture-secret")
        with self.assertRaisesRegex(SyncError, "^CONNECTION_BINDING_CHANGED$"):
            self.admin.rotate_credentials(cid, client_id="different-client", **args)
        self.assertEqual(len(self.operations), 2)
        self.expected_secret = args["client_secret"]
        self.item["id"] = "foreign-item"
        with self.assertRaisesRegex(SyncError, "^ITEM_ID_DIFFERENT$"):
            self.admin.rotate_credentials(cid, client_id="fixture-client", **args)
        with closing(self.service._db()) as db:
            self.assertEqual(db.execute("SELECT count(*) FROM of_connection_credentials").fetchone()[0], 1)
        self.item["id"] = "fixture-item"
        with patch("finance_v2.open_finance.load_keyring", return_value=self.protector):
            stale = self.service.resolve_config(cid)
            self.assertEqual(self.admin.rotate_credentials(cid, client_id="fixture-client", **args)["revision"], 2)
            self.assertEqual(self.service.resolve_config(cid).client_secret, self.expected_secret)
            self.assertEqual(self.service.resolve_config("conn-sibling").client_secret, "fixture-secret")
        with closing(self.service._db()) as db:
            with self.assertRaisesRegex(SyncError, "^CONNECTION_CONFIGURATION_CHANGED$"):
                self.service._claim(db, stale, "UI:local", None, None)
            self.assertEqual(db.execute("SELECT count(*) FROM of_sync_runs").fetchone()[0], 0)
            self.assertEqual(db.execute("SELECT count(*) FROM of_connection_credentials").fetchone()[0], 2)
            self.assertNotIn(self.expected_secret, "\n".join(db.iterdump()))

    def test_concurrent_revision_change_during_provider_io_blocks_activation(self):
        draft = self.draft()

        def racing_send(method, path, headers, body, timeout):
            if method == "GET":
                with closing(self.service._db()) as db, self.service._write(db):
                    db.execute("UPDATE of_connection_registry SET revision=1 WHERE connection_id=?", (draft["id"],))
            return self.send(method, path, headers, body, timeout)

        self.service.client_factory = lambda config: PluggyClient(config, send=racing_send)
        with self.assertRaisesRegex(SyncError, "^CONNECTION_CONFIGURATION_CHANGED$"):
            self.admin.validate_and_activate(draft["id"], actor="UI:local", revision=0, confirmed=True)
        with closing(self.service._db()) as db:
            self.assertEqual(db.execute("SELECT lifecycle FROM of_connection_registry").fetchone()[0], "DRAFT")
            self.assertEqual(db.execute("SELECT count(*) FROM of_connection_admin_events").fetchone()[0], 1)

    def test_archive_and_replace_preserves_unrecognized_binding_and_history(self):
        self.seed_santander()
        with self.assertRaisesRegex(SyncError, "^PREDECESSOR_NOT_ARCHIVED$"):
            self.draft(replaces_id="santander")
        self.assertEqual(self.archive_santander()["dependencies"], "NO_FINANCIAL_ROWS_WITH_HISTORY")
        draft = self.draft(replaces_id="santander")
        self.assertNotEqual(draft["id"], "santander")
        self.admin.validate_and_activate(draft["id"], actor="UI:local", revision=0, confirmed=True)
        with closing(self.service._db()) as db:
            self.assertEqual(
                tuple(db.execute(
                    "SELECT lifecycle,binding_hash FROM of_connection_registry JOIN of_connections "
                    "ON connection_id=id WHERE id='santander'"
                ).fetchone()), ("ARCHIVED", "1" * 64),
            )
            self.assertEqual(db.execute("SELECT replaces_id FROM of_connection_registry WHERE connection_id=?",
                                        (draft["id"],)).fetchone()[0], "santander")
            self.assertEqual(db.execute("SELECT count(*) FROM of_sync_runs WHERE connection_id='santander' AND error_code='AUTH_FAILED'").fetchone()[0], 26)
            self.assertEqual(db.execute("SELECT count(*) FROM of_sync_runs WHERE connection_id=?", (draft["id"],)).fetchone()[0], 0)
            self.assertEqual(db.execute("PRAGMA foreign_key_check").fetchall(), [])
            connections = {row["id"]: row for row in self.service.connections(db)}
            self.assertFalse(connections["santander"]["enabled"])
            self.assertEqual(connections["santander"]["last_run"]["error_code"], "AUTH_FAILED")
            self.assertTrue(connections[draft["id"]]["enabled"])
            self.assertEqual(connections[draft["id"]]["staged_account_count"], 0)
            self.assertEqual(connections[draft["id"]]["observed_resources"], [])
        with self.assertRaisesRegex(SyncError, "^CONNECTION_NOT_ACTIVE$"):
            self.service.resolve_config("santander")

    def test_prepare_archive_reports_dependencies_and_rechecks_active_lease(self):
        self.seed_santander()
        report = self.admin.inspect_archive("santander", actor="UI:local", revision=0)
        self.assertEqual(report["dependencies"], "NO_FINANCIAL_ROWS_WITH_HISTORY")
        self.assertEqual(report["counts"]["of_sync_runs"], 26)
        with closing(self.service._db()) as db:
            self.assertEqual(db.execute("SELECT count(*) FROM of_connection_admin_events").fetchone()[0], 0)
            db.execute("UPDATE of_connections SET sync_state='RUNNING',lease_token='fixture',lease_until=9999999999 WHERE id='santander'")
        with self.assertRaisesRegex(SyncError, "SYNC_BUSY"):
            self.archive_santander()

    def test_archive_preserves_partial_rows_and_blocks_replacement(self):
        self.seed_santander()
        with closing(self.service._db()) as db:
            db.execute("INSERT INTO of_accounts(connection_id,external_id) VALUES ('santander','fixture-account')")
        self.assertEqual(self.archive_santander()["dependencies"], "PRESENT")
        with self.assertRaisesRegex(SyncError, "^REPLACEMENT_DEPENDENCIES_PRESENT$"):
            self.draft(replaces_id="santander")
        with closing(self.service._db()) as db:
            self.assertEqual(db.execute("SELECT count(*) FROM of_accounts WHERE connection_id='santander'").fetchone()[0], 1)
        self.assertEqual(self.operations, [])

    def test_deletion_requires_backup_attestation_and_keeps_durable_audit(self):
        self.seed_santander()
        cid = self.draft()["id"]
        self.admin.archive(cid, actor="UI:local", revision=0, confirmed=True)
        self.assertTrue(self.admin.inspect_deletion(cid, actor="UI:local", revision=1)["eligible"])
        args = dict(actor="UI:local", revision=1, confirmation="EXCLUIR DEFINITIVAMENTE")
        with self.assertRaisesRegex(SyncError, "^DELETION_CONFIRMATION_REQUIRED$"):
            self.admin.delete(cid, backup_confirmed=False, **args)
        self.assertEqual(self.admin.delete(cid, backup_confirmed=True, **args)["lifecycle"], "REMOVED")
        with closing(self.service._db()) as db:
            self.assertEqual(db.execute("SELECT count(*) FROM of_connections WHERE id=?", (cid,)).fetchone()[0], 0)
            self.assertEqual(db.execute("SELECT count(*) FROM of_connection_credentials").fetchone()[0], 0)
            self.assertEqual(db.execute("SELECT count(*) FROM of_sync_runs WHERE connection_id='santander'").fetchone()[0], 26)
            self.assertEqual(db.execute("SELECT resulting_state FROM of_connection_admin_events WHERE connection_id=? AND operation='DELETE'", (cid,)).fetchone()[0], "REMOVED")
            self.assertEqual(db.execute("PRAGMA foreign_key_check").fetchall(), [])
        self.assertEqual(self.operations, [])

    def test_deletion_rechecks_new_dependencies_after_inspection(self):
        cid = self.draft()["id"]
        self.admin.archive(cid, actor="UI:local", revision=0, confirmed=True)
        self.assertTrue(self.admin.inspect_deletion(cid, actor="UI:local", revision=1)["eligible"])
        with closing(self.service._db()) as db:
            db.execute("INSERT INTO of_accounts(connection_id,external_id) VALUES (?,'fixture-account')", (cid,))
        with self.assertRaisesRegex(SyncError, "^DELETION_RETENTION_REQUIRED$"):
            self.admin.delete(cid, actor="UI:local", revision=1, backup_confirmed=True,
                              confirmation="EXCLUIR DEFINITIVAMENTE")
        with closing(self.service._db()) as db:
            self.assertEqual(db.execute("SELECT count(*) FROM of_accounts WHERE connection_id=?", (cid,)).fetchone()[0], 1)
            self.assertEqual(db.execute("SELECT lifecycle FROM of_connection_registry WHERE connection_id=?", (cid,)).fetchone()[0], "ARCHIVED")
            self.assertEqual(db.execute("SELECT count(*) FROM of_connection_admin_events WHERE operation='DELETE'").fetchone()[0], 0)

    def test_legacy_history_requires_retention(self):
        self.seed_santander()
        self.archive_santander()
        report = self.admin.inspect_deletion("santander", actor="UI:local", revision=1)
        self.assertFalse(report["eligible"])
        self.assertEqual(report["counts"]["of_sync_runs"], 26)
        self.assertIn("LEGACY_RETENTION_REQUIRED", report["blockers"])

    def test_pending_legacy_audit_and_live_lease_block_archive(self):
        self.seed_santander()
        with patch("finance_v2.open_finance_registry_admin.SantanderBindingRecovery.records",
                   return_value=[{"phase": "PREPARED"}]):
            with self.assertRaisesRegex(SyncError, "^AUDIT_RECONCILIATION_REQUIRED$"):
                self.archive_santander()
        with closing(self.service._db()) as db:
            db.execute(
                """UPDATE of_connections SET sync_state='RUNNING',lease_token='fixture',lease_until=9999999999
                   WHERE id='santander'""",
            )
        with self.assertRaisesRegex(SyncError, "^SYNC_BUSY$"):
            self.archive_santander()
        with closing(self.service._db()) as db:
            self.assertEqual(db.execute("SELECT lifecycle FROM of_connection_registry").fetchone()[0], "ACTIVE")

    def test_http_requires_private_cookie_origin_and_csrf_before_reading_body(self):
        origin = "http://127.0.0.1:8766"
        settings = replace(self.service.settings, ui_token="fixture-owner-token",
                           pluggy_admin_origin=origin, cors_origins=("https://example.invalid",))
        app = Application(settings)
        csrf = "fixture-csrf"
        signature = hmac.new(settings.ui_token.encode(), csrf.encode(), hashlib.sha256).hexdigest()
        default = {
            "REQUEST_METHOD": "POST", "PATH_INFO": "/api/v2/open-finance/registry/drafts",
            "CONTENT_TYPE": "application/json", "wsgi.url_scheme": "http",
            "HTTP_HOST": "127.0.0.1:8766", "REMOTE_ADDR": "127.0.0.1", "HTTP_ORIGIN": origin,
            "HTTP_COOKIE": f"finance_v2_session={csrf}.{signature}", "HTTP_X_CSRF_TOKEN": csrf,
        }
        payload = {"label": "Fixture", "environment": "PERSONAL", "client_id": "fixture-client",
                   "client_secret": "fixture-secret", "item_id": "fixture-item"}

        def invoke(application=app, *, endpoint="drafts", extra=None, body=payload):
            raw = json.dumps(body).encode()
            stream = BytesIO(raw)
            environ = {**default, **(extra or {}), "CONTENT_LENGTH": str(len(raw)), "wsgi.input": stream,
                       "PATH_INFO": "/api/v2/open-finance/registry/" + endpoint}
            calls = []
            response = b"".join(application(environ, lambda status, headers: calls.append((status, dict(headers)))))
            status, headers = calls[0]
            self.assertNotIn("Access-Control-Allow-Origin", headers)
            self.assertEqual(headers["Cache-Control"], "no-store")
            for value in ("fixture-client", "fixture-secret", "fixture-item", settings.ui_token):
                self.assertNotIn(value.encode(), response)
            return int(status.split()[0]), json.loads(response), stream.tell()

        for update in (
            {"HTTP_X_CSRF_TOKEN": "bad"},
            {"HTTP_ORIGIN": ""},
            {"HTTP_ORIGIN": "https://example.invalid"},
            {"HTTP_X_FORWARDED_PROTO": "https"},
            {"HTTP_CF_ACCESS_JWT_ASSERTION": "synthetic"},
            {"REMOTE_ADDR": "203.0.113.7"},
            {"HTTP_HOST": "finance.example.invalid"},
            {"HTTP_AUTHORIZATION": "Bearer fixture-owner-token"},
        ):
            with self.subTest(update=update):
                status, _, read = invoke(extra=update)
                self.assertEqual((status, read), (403, 0))
        disabled = Application(replace(settings, pluggy_admin_origin=None))
        self.assertEqual(invoke(disabled)[0], 403)
        self.assertEqual(invoke(extra={"HTTP_COOKIE": ""})[0], 401)
        self.assertEqual(invoke(body={**payload, "confirmed": True})[0], 422)
        self.assertEqual(invoke(body={**payload, "label": "A" * 8200})[0], 413)
        with patch.object(RegistryAdmin, "_keyring", return_value=self.protector), patch(
            "finance_v2.open_finance_http.OpenFinanceService", return_value=self.service,
        ):
            status, response, _ = invoke()
            self.assertEqual(status, 201)
            self.assertEqual(response["lifecycle"], "DRAFT")
            detail = {"connection_id": response["id"], "revision": 0}
            self.assertEqual(invoke(endpoint="details", extra={"HTTP_X_FORWARDED_PROTO": "https"}, body=detail)[0], 403)
            self.assertEqual(invoke(endpoint="connectors", extra={"HTTP_X_CSRF_TOKEN": "bad"}, body=detail)[0], 403)
            self.assertEqual(invoke(endpoint="details", body=detail)[1]["lifecycle"], "DRAFT")
            self.assertEqual(self.operations, [])
            body = {"connection_id": response["id"], "revision": 0, "confirmed": True}
            status, active, _ = invoke(endpoint="activate", body=body)
            self.assertEqual((status, active["lifecycle"]), (200, "ACTIVE"))
            self.assertEqual(self.operations, [("POST", "/auth"), ("GET", "/items/fixture-item")])
            inspection = {"connection_id": response["id"], "revision": 1}
            self.assertEqual(invoke(endpoint="archive/inspect", extra={"HTTP_X_CSRF_TOKEN": "bad"}, body=inspection)[0], 403)
            status, report, _ = invoke(endpoint="archive/inspect", body=inspection)
            self.assertEqual((status, report["dependencies"]), (200, "NO_ASSOCIATED_DEPENDENTS"))
            self.assertEqual(invoke(endpoint="archive", body=body)[0], 409)
            status, archived, _ = invoke(endpoint="archive", body={**body, "revision": 1})
            self.assertEqual((status, archived["lifecycle"]), (200, "ARCHIVED"))
        with self.assertRaises(ConfigurationError):
            replace(settings, pluggy_admin_origin="https://finance.example.invalid")
        with self.assertRaises(ConfigurationError):
            replace(settings, pluggy_admin_origin="http://192.168.1.5:8766")

        ticks = [100.0]
        app.registry_rate_limit = RegistryRateLimiter(now=lambda: ticks[0], provider_limit=1, local_limit=1)
        self.assertEqual(invoke(extra={"HTTP_X_CSRF_TOKEN": "bad"})[0], 403)
        self.assertEqual(invoke(body={**payload, "unexpected": True})[0], 422)
        status, limited, read = invoke()
        self.assertEqual((status, limited["error"]["code"], read), (429, "REGISTRY_RATE_LIMITED", 0))
        self.assertEqual(invoke(endpoint="activate", body={})[0], 422)
        self.assertEqual(invoke(endpoint="rotate-credentials", body={})[0], 429)
        ticks[0] += 60
        self.assertEqual(invoke(endpoint="activate", body={})[0], 422)
