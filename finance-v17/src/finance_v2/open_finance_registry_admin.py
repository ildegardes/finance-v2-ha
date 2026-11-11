"""Administrative enrollment of managed Pluggy connections."""
from contextlib import closing
from dataclasses import replace
import re
import sqlite3
from uuid import uuid4

from .open_finance import SyncError
from .open_finance_recovery import EXPECTED, SantanderBindingRecovery
from .open_finance_recovery_checks import Blocked, dependencies, schema_check
from .open_finance_registry import ACCESS_MODES, load_keyring, managed_connection
from .pluggy_access_policy import validate_access_context
from .pluggy_client import PluggyError
from .pluggy_config import PluggyConfigurationError, PluggyConnection
from .pluggy_coverage import CONTRACT, _expired, collection_batches
from .pluggy_credential_protection import CredentialProtectionError


def _event(db, connection_id, operation, previous, resulting, revision, stamp):
    db.execute(
        """INSERT INTO of_connection_admin_events
           (event_id,connection_id,actor,operation,previous_state,resulting_state,revision,recorded_at)
           VALUES (?,?,'UI:local',?,?,?,?,?)""",
        (uuid4().hex, connection_id, operation, previous, resulting, revision, stamp),
    )


def _registered_row(db, connection_id, revision, states):
    row = db.execute(
        """SELECT r.source,r.lifecycle,r.revision,r.label,r.replaces_id,
                  c.sync_state,c.lease_token,c.binding_hash
           FROM of_connection_registry r JOIN of_connections c ON c.id=r.connection_id
           WHERE r.connection_id=?""", (connection_id,),
    ).fetchone()
    if row is None:
        raise SyncError("CONNECTION_NOT_FOUND", 404)
    if row["revision"] != revision or row["lifecycle"] not in states:
        raise SyncError("CONNECTION_CONFIGURATION_CHANGED")
    return row


class RegistryAdmin:
    def __init__(self, service, *, keyring_loader=load_keyring):
        self.service = service
        self.keyring_loader = keyring_loader

    def _keyring(self):
        try:
            return self.keyring_loader(self.service.settings.pluggy_keyring_path)
        except CredentialProtectionError as exc:
            raise SyncError(str(exc), 503) from None

    @staticmethod
    def _owner(actor):
        if actor != "UI:local":
            raise SyncError("OWNER_REQUIRED", 403)

    def _dependency_report(self, db, connection_id):
        try:
            schema_check(db, EXPECTED, registry=True)
            report = dependencies(db, connection_id)
            if connection_id == "santander":
                recovery = SantanderBindingRecovery(self.service.settings)
                if recovery.pending_receipts(recovery.records()):
                    raise SyncError("AUDIT_RECONCILIATION_REQUIRED")
        except (Blocked, OSError):
            raise SyncError("REGISTRY_INTEGRITY_NOT_VERIFIED") from None
        if report["RISK"] == "BLOCKED_INTEGRITY_OR_CROSS_CONNECTION":
            raise SyncError("REGISTRY_INTEGRITY_NOT_VERIFIED")
        return report

    @staticmethod
    def _idle(db, connection_id, row):
        if (row["sync_state"] == "RUNNING" or row["lease_token"] is not None
                or db.execute(
                    "SELECT 1 FROM of_sync_runs WHERE connection_id=? AND state='RUNNING'",
                    (connection_id,),
                ).fetchone()):
            raise SyncError("SYNC_BUSY")

    def _deletion_report(self, db, connection_id, revision):
        row = _registered_row(db, connection_id, revision, {"ARCHIVED"})
        report = self._dependency_report(db, connection_id)
        blockers = []
        if row["source"] != "MANAGED":
            blockers.append("LEGACY_RETENTION_REQUIRED")
        try:
            self._idle(db, connection_id, row)
        except SyncError:
            blockers.append("SYNC_BUSY")
        if any(count for table, count in report["COUNTS"].items() if table != "of_connections"):
            blockers.append("DEPENDENCY_RETENTION_REQUIRED")
        if row["replaces_id"] is not None or db.execute(
            "SELECT 1 FROM of_connection_registry WHERE replaces_id=?", (connection_id,),
        ).fetchone():
            blockers.append("REPLACEMENT_HISTORY_REQUIRED")
        return {"id": connection_id, "revision": revision, "eligible": not blockers,
                "blockers": blockers, "counts": report["COUNTS"]}

    def inspect_deletion(self, connection_id, *, actor, revision):
        self._owner(actor)
        if type(revision) is not int or not 0 <= revision < 2**63 - 1:
            raise SyncError("INVALID_REGISTRY_REVISION", 422)
        try:
            with closing(self.service._db()) as db:
                db.execute("BEGIN")
                return self._deletion_report(db, connection_id, revision)
        except sqlite3.Error:
            raise SyncError("REGISTRY_READ_FAILED", 503) from None

    def delete(self, connection_id, *, actor, revision, backup_confirmed, confirmation):
        self._owner(actor)
        if (backup_confirmed is not True or confirmation != "EXCLUIR DEFINITIVAMENTE"
                or type(revision) is not int or not 0 <= revision < 2**63 - 1):
            raise SyncError("DELETION_CONFIRMATION_REQUIRED", 422)
        _, stamp = self.service._time()
        try:
            with closing(self.service._db()) as db, self.service._write(db):
                report = self._deletion_report(db, connection_id, revision)
                if not report["eligible"]:
                    raise SyncError("DELETION_RETENTION_REQUIRED")
                item = db.execute(
                    "SELECT application_id FROM of_managed_pluggy_items WHERE connection_id=?", (connection_id,),
                ).fetchone()
                if item is None:
                    raise SyncError("MANAGED_CONNECTION_UNAVAILABLE")
                application_id = item["application_id"]
                db.execute("DELETE FROM of_managed_pluggy_items WHERE connection_id=?", (connection_id,))
                db.execute("DELETE FROM of_connection_registry WHERE connection_id=?", (connection_id,))
                db.execute("DELETE FROM of_connections WHERE id=?", (connection_id,))
                if not db.execute(
                    "SELECT 1 FROM of_managed_pluggy_items WHERE application_id=?", (application_id,),
                ).fetchone():
                    db.execute("DELETE FROM of_connection_credentials WHERE application_id=?", (application_id,))
                    db.execute("DELETE FROM of_pluggy_applications WHERE id=?", (application_id,))
                _event(db, connection_id, "DELETE", "ARCHIVED", "REMOVED", revision + 1, stamp)
        except sqlite3.Error:
            raise SyncError("REGISTRY_WRITE_FAILED", 503) from None
        return {"id": connection_id, "lifecycle": "REMOVED", "revision": revision + 1}

    def inspect_archive(self, connection_id, *, actor, revision):
        self._owner(actor)
        if type(revision) is not int or not 0 <= revision < 2**63 - 1:
            raise SyncError("INVALID_REGISTRY_REVISION", 422)
        try:
            with closing(self.service._db()) as db:
                db.execute("BEGIN")
                row = _registered_row(db, connection_id, revision, {"ACTIVE", "DISABLED", "DRAFT"})
                self._idle(db, connection_id, row)
                report = self._dependency_report(db, connection_id)
                return {"id": connection_id, "revision": revision, "lifecycle": row["lifecycle"],
                        "dependencies": report["DEPENDENCIES"], "counts": report["COUNTS"]}
        except sqlite3.Error:
            raise SyncError("REGISTRY_READ_FAILED", 503) from None

    def archive(self, connection_id, *, actor, revision, confirmed):
        return self._update_registry(connection_id, actor, revision, confirmed, "ARCHIVE", "ARCHIVED",
                                     {"ACTIVE", "DISABLED", "DRAFT"})

    def disable(self, connection_id, *, actor, revision, confirmed):
        return self._update_registry(connection_id, actor, revision, confirmed, "DISABLE", "DISABLED", {"ACTIVE"})

    def rename(self, connection_id, *, actor, revision, label):
        self._owner(actor)
        if (not isinstance(label, str) or not 1 <= len(label) <= 200 or label != label.strip()
                or any(ord(character) < 32 or ord(character) == 127 for character in label)):
            raise SyncError("INVALID_CONNECTION_LABEL", 422)
        return self._update_registry(connection_id, actor, revision, True, "RENAME", None,
                                     {"DRAFT", "ACTIVE", "DISABLED"}, label=label)

    def _update_registry(self, connection_id, actor, revision, confirmed, operation, target, states, *, label=None):
        self._owner(actor)
        if confirmed is not True or type(revision) is not int or not 0 <= revision < 2**63 - 1:
            raise SyncError(operation + "_CONFIRMATION_REQUIRED", 422)
        _, stamp = self.service._time()
        report = None
        try:
            with closing(self.service._db()) as db, self.service._write(db):
                row = _registered_row(db, connection_id, revision, states)
                self._idle(db, connection_id, row)
                if operation == "ARCHIVE":
                    report = self._dependency_report(db, connection_id)
                resulting = target or row["lifecycle"]
                if label == row["label"]:
                    return {"id": connection_id, "lifecycle": resulting, "revision": revision}
                db.execute(
                    """UPDATE of_connection_registry SET lifecycle=?,label=coalesce(?,label),
                       revision=revision+1,updated_at=? WHERE connection_id=? AND revision=?""",
                    (resulting, label, stamp, connection_id, revision),
                )
                _event(db, connection_id, operation, row["lifecycle"], resulting, revision + 1, stamp)
        except sqlite3.Error:
            raise SyncError("REGISTRY_WRITE_FAILED", 503) from None
        result = {"id": connection_id, "lifecycle": resulting, "revision": revision + 1}
        if report is not None:
            result["dependencies"] = report["DEPENDENCIES"]
        return result

    def _check_replacement(self, db, predecessor, *, successor=None):
        if predecessor is None:
            return
        row = db.execute(
            """SELECT r.lifecycle,c.sync_state,c.lease_token
               FROM of_connection_registry r JOIN of_connections c ON c.id=r.connection_id
               WHERE r.connection_id=?""", (predecessor,),
        ).fetchone()
        if row is None or row["lifecycle"] != "ARCHIVED":
            raise SyncError("PREDECESSOR_NOT_ARCHIVED")
        self._idle(db, predecessor, row)
        report = self._dependency_report(db, predecessor)
        historical_writes = db.execute(
            """SELECT 1 FROM of_sync_runs WHERE connection_id=?
               AND (inserted_count>0 OR updated_count>0)""", (predecessor,),
        ).fetchone()
        if report["DEPENDENCIES"] == "PRESENT" or historical_writes:
            raise SyncError("REPLACEMENT_DEPENDENCIES_PRESENT")
        if db.execute(
            """SELECT 1 FROM of_connection_registry WHERE replaces_id=?
               AND lifecycle NOT IN ('ARCHIVED','REMOVED') AND connection_id IS NOT ?""",
            (predecessor, successor),
        ).fetchone():
            raise SyncError("REPLACEMENT_ALREADY_REGISTERED")

    def create_draft(self, *, actor, label, environment, client_id, client_secret, item_id, replaces_id=None):
        self._owner(actor)
        connection_id = "conn-" + uuid4().hex
        application_id = "app-" + uuid4().hex
        if not isinstance(environment, str) or environment not in ACCESS_MODES:
            raise SyncError("INVALID_ACCESS_CONTEXT", 422)
        if not isinstance(item_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,200}", item_id):
            raise SyncError("INVALID_ITEM_IDENTIFIER", 422)
        try:
            config = PluggyConnection(
                connection_id, label, client_id, client_secret, item_id,
                access_mode=ACCESS_MODES[environment],
            )
            record = self._keyring().seal(application_id, 1, client_id, client_secret)
        except (PluggyConfigurationError, CredentialProtectionError):
            raise SyncError("INVALID_CONNECTION_CONFIGURATION", 422) from None
        _, stamp = self.service._time()
        binding = self.service._binding(config)
        try:
            with closing(self.service._db()) as db, self.service._write(db):
                self._check_replacement(db, replaces_id)
                if db.execute("SELECT 1 FROM of_connections WHERE binding_hash=?", (binding,)).fetchone():
                    raise SyncError("CONNECTION_BINDING_ALREADY_REGISTERED")
                db.execute("INSERT INTO of_pluggy_applications VALUES (?,?,?)", (application_id, label, environment))
                db.execute(
                    """INSERT INTO of_connection_credentials
                       (application_id,revision,key_id,nonce,ciphertext,created_at) VALUES (?,1,?,?,?,?)""",
                    (application_id, record.key_id, record.nonce, record.ciphertext, stamp),
                )
                db.execute(
                    """INSERT INTO of_connections(id,institution,binding_hash,updated_at) VALUES (?,?,?,?)""",
                    (connection_id, label, binding, stamp),
                )
                db.execute(
                    """INSERT INTO of_connection_registry(connection_id,source,lifecycle,label,updated_at,replaces_id)
                       VALUES (?,'MANAGED','DRAFT',?,?,?)""",
                    (connection_id, label, stamp, replaces_id),
                )
                db.execute(
                    """INSERT INTO of_managed_pluggy_items(connection_id,application_id,credential_revision,item_id)
                       VALUES (?,?,1,?)""",
                    (connection_id, application_id, item_id),
                )
                _event(db, connection_id, "CREATE_DRAFT", None, "DRAFT", 0, stamp)
        except sqlite3.Error:
            raise SyncError("REGISTRY_WRITE_FAILED", 503) from None
        return {"id": connection_id, "lifecycle": "DRAFT", "revision": 0}

    def _configuration_for_validation(self, connection_id, revision, states):
        try:
            with closing(self.service._db()) as db:
                original = _registered_row(db, connection_id, revision, states)
                self._idle(db, connection_id, original)
                if original["source"] == "MANAGED":
                    config = managed_connection(
                        db, connection_id, revision, self._keyring(), lifecycle=original["lifecycle"],
                    )
                else:
                    config = self.service.config.get(connection_id)
                    if config is None or not config.enabled:
                        raise SyncError("CONNECTION_DISABLED")
                if self.service._binding(config) != original["binding_hash"]:
                    raise SyncError("CONNECTION_BINDING_CHANGED")
                return original, config
        except CredentialProtectionError as exc:
            raise SyncError(str(exc)) from None
        except sqlite3.Error:
            raise SyncError("REGISTRY_READ_FAILED", 503) from None

    def validate_connection(self, connection_id, *, actor, revision, confirmed):
        self._owner(actor)
        if confirmed is not True or type(revision) is not int or not 0 <= revision < 2**63 - 1:
            raise SyncError("VALIDATION_CONFIRMATION_REQUIRED", 422)
        original, config = self._configuration_for_validation(connection_id, revision, {"DRAFT", "DISABLED", "ACTIVE"})
        client, item = self._validate_item(config)
        try:
            with closing(collection_batches(
                client, item, "resources", "", "/items/" + config.item_id + "/resources", {},
            )) as batches:
                batch = next(batches)
            fields = CONTRACT["resources"]["resources"]["schema"]["properties"]
            capabilities = set()
            for row in batch["rows"]:
                kind, status = row.get("type"), row.get("status")
                if kind in fields["type"]["enum"] and status in fields["status"]["enum"]:
                    capabilities.add((kind, status))
        except PluggyError:
            raise SyncError("PROVIDER_CAPABILITY_QUERY_FAILED", 502) from None
        try:
            with closing(self.service._db()) as db:
                current = _registered_row(db, connection_id, revision, {original["lifecycle"]})
                if current["binding_hash"] != original["binding_hash"]:
                    raise SyncError("CONNECTION_CONFIGURATION_CHANGED")
        except sqlite3.Error:
            raise SyncError("REGISTRY_READ_FAILED", 503) from None
        state = "PARTIAL" if not batch["last"] else batch["state"]
        if state == "AVAILABLE" and not capabilities:
            state = "NONE_REPORTED"
        return {"id": connection_id, "revision": revision, "item_verified": True,
                "capabilities_state": state,
                "capabilities": [{"type": kind, "status": status} for kind, status in sorted(capabilities)]}

    def validate_and_activate(self, connection_id, *, actor, revision, confirmed):
        self._owner(actor)
        if confirmed is not True or type(revision) is not int or not 0 <= revision < 2**63 - 1:
            raise SyncError("ACTIVATION_CONFIRMATION_REQUIRED", 422)
        original, config = self._configuration_for_validation(connection_id, revision, {"DRAFT", "DISABLED"})
        self._validate_item(config)

        _, stamp = self.service._time()
        try:
            with closing(self.service._db()) as db, self.service._write(db):
                row = _registered_row(db, connection_id, revision, {original["lifecycle"]})
                self._idle(db, connection_id, row)
                if row["source"] != original["source"] or row["binding_hash"] != original["binding_hash"]:
                    raise SyncError("CONNECTION_CONFIGURATION_CHANGED")
                self._check_replacement(db, row["replaces_id"], successor=connection_id)
                changed = db.execute(
                    """UPDATE of_connection_registry SET lifecycle='ACTIVE',revision=revision+1,updated_at=?
                       WHERE connection_id=? AND lifecycle=? AND revision=?""",
                    (stamp, connection_id, row["lifecycle"], revision),
                ).rowcount
                if changed != 1:
                    raise SyncError("CONNECTION_CONFIGURATION_CHANGED")
                changed = db.execute(
                    """UPDATE of_connections SET enabled=1,updated_at=? WHERE id=?
                       AND lease_token IS NULL AND sync_state<>'RUNNING' AND binding_hash=?""",
                    (stamp, connection_id, self.service._binding(config)),
                ).rowcount
                if changed != 1:
                    raise SyncError("CONNECTION_CONFIGURATION_CHANGED")
                operation = "ACTIVATE" if row["lifecycle"] == "DRAFT" else "REACTIVATE"
                _event(db, connection_id, operation, row["lifecycle"], "ACTIVE", revision + 1, stamp)
        except sqlite3.Error:
            raise SyncError("REGISTRY_WRITE_FAILED", 503) from None
        return {"id": connection_id, "lifecycle": "ACTIVE", "revision": revision + 1}

    def _validate_item(self, config):
        try:
            client = self.service.client_factory(replace(config, enabled=True))
            item, state = client.coverage_get("/items/" + config.item_id)
            if state != "AVAILABLE" or not isinstance(item, dict) or item.get("id") != config.item_id:
                raise SyncError("ITEM_ID_DIFFERENT")
            connector = item.get("connector")
            if not isinstance(connector, dict) or connector.get("isSandbox") is not (config.access_mode == "sandbox"):
                raise SyncError("ITEM_ENVIRONMENT_NOT_VERIFIED")
            validate_access_context(config, item)
            if item.get("status") not in ("UPDATED", "OUTDATED") or _expired(item.get("consentExpiresAt")):
                raise SyncError("ITEM_NOT_READY")
        except PluggyError:
            raise SyncError("PROVIDER_VALIDATION_FAILED", 502) from None
        return client, item

    def _rotation_context(self, db, connection_id, revision):
        row = _registered_row(db, connection_id, revision, {"DRAFT", "ACTIVE", "DISABLED"})
        if row["source"] != "MANAGED":
            raise SyncError("MANAGED_CONNECTION_REQUIRED")
        self._idle(db, connection_id, row)
        item = db.execute(
            """SELECT i.application_id,i.credential_revision,i.item_id,a.environment
               FROM of_managed_pluggy_items i JOIN of_pluggy_applications a ON a.id=i.application_id
               WHERE i.connection_id=?""", (connection_id,),
        ).fetchone()
        if item is None:
            raise SyncError("MANAGED_CONNECTION_UNAVAILABLE")
        return row, item

    def rotate_credentials(self, connection_id, *, actor, revision, confirmed, client_id, client_secret):
        self._owner(actor)
        if confirmed is not True or type(revision) is not int or not 0 <= revision < 2**63 - 1:
            raise SyncError("ROTATION_CONFIRMATION_REQUIRED", 422)
        protector = self._keyring()
        try:
            with closing(self.service._db()) as db:
                original, item = self._rotation_context(db, connection_id, revision)
            config = PluggyConnection(
                connection_id, original["label"], client_id, client_secret, item["item_id"],
                access_mode=ACCESS_MODES[item["environment"]],
            )
        except PluggyConfigurationError:
            raise SyncError("INVALID_CONNECTION_CONFIGURATION", 422) from None
        except sqlite3.Error:
            raise SyncError("REGISTRY_READ_FAILED", 503) from None
        if self.service._binding(config) != original["binding_hash"]:
            raise SyncError("CONNECTION_BINDING_CHANGED")
        self._validate_item(config)

        _, stamp = self.service._time()
        try:
            with closing(self.service._db()) as db, self.service._write(db):
                observed, current_item = self._rotation_context(db, connection_id, revision)
                if observed != original or current_item != item:
                    raise SyncError("CONNECTION_CONFIGURATION_CHANGED")
                next_revision = db.execute(
                    "SELECT max(revision) FROM of_connection_credentials WHERE application_id=?",
                    (item["application_id"],),
                ).fetchone()[0] + 1
                record = protector.seal(item["application_id"], next_revision, client_id, client_secret)
                db.execute(
                    """INSERT INTO of_connection_credentials
                       (application_id,revision,key_id,nonce,ciphertext,created_at) VALUES (?,?,?,?,?,?)""",
                    (item["application_id"], next_revision, record.key_id, record.nonce, record.ciphertext, stamp),
                )
                db.execute(
                    "UPDATE of_managed_pluggy_items SET credential_revision=? WHERE connection_id=?",
                    (next_revision, connection_id),
                )
                db.execute(
                    "UPDATE of_connection_registry SET revision=revision+1,updated_at=? WHERE connection_id=?",
                    (stamp, connection_id),
                )
                _event(db, connection_id, "ROTATE_CREDENTIALS", original["lifecycle"],
                       original["lifecycle"], revision + 1, stamp)
        except (sqlite3.Error, CredentialProtectionError):
            raise SyncError("REGISTRY_WRITE_FAILED", 503) from None
        return {"id": connection_id, "lifecycle": original["lifecycle"], "revision": revision + 1}
