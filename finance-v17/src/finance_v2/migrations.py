from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
import sqlite3

from .db import connect


PROJECT_ROOT = Path(__file__).resolve().parents[2]
MIGRATIONS_DIR = PROJECT_ROOT / "migrations"
V16_SCHEMA_SHA256 = "4d007847de4a76b0d190de065782831e94a1de698feedb8be0cb14e42df014b7"


class MigrationError(RuntimeError):
    pass


@dataclass(frozen=True)
class Migration:
    version: int
    name: str
    path: Path
    expected_sha256: str
    rebuilds_tables: bool = False


MIGRATIONS = (
    Migration(1, "v16_schema", MIGRATIONS_DIR / "001_v16_schema.sql", V16_SCHEMA_SHA256),
    Migration(2, "v17_revenues", MIGRATIONS_DIR / "002_v17_revenues.sql", "e4c8972dbfe6271f0ad02897ffddf5b1a3544ee5074b7315f390f1e9bd2b70c0"),
    Migration(3, "v17_recurring_revenues", MIGRATIONS_DIR / "003_v17_recurring_revenues.sql", "f5f6d6aabf85f66b1af2e44436e193404ec2fe6b6078edb559272ac6166c6fd6"),
    Migration(4, "v17_multimethod_installments", MIGRATIONS_DIR / "004_v17_multimethod_installments.sql", "500b389c804c259e5953b7e4719e07ff543e65d0edf5d4c8ccb0b908f92620c8", True),
    Migration(5, "v17_expense_tombstone", MIGRATIONS_DIR / "005_v17_expense_tombstone.sql", "7d29c5151ad4703001f2c1f76482a48650efd2d92e8976d7b93c3c54282b2f86", True),
    Migration(6, "v17_revenue_recurrence_versions", MIGRATIONS_DIR / "006_v17_revenue_recurrence_versions.sql", "e7daa63b8b8174d416368062832efc9ef57fbd841958311b3dbd3bc4ac8fc421"),
)


def _digest(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def _ensure_history(connection: sqlite3.Connection) -> None:
    connection.execute(
        """CREATE TABLE IF NOT EXISTS _finance_v2_schema_migrations(
        version INTEGER PRIMARY KEY,
        name TEXT NOT NULL UNIQUE,
        sha256 TEXT NOT NULL CHECK(length(sha256)=64),
        applied_at TEXT NOT NULL CHECK(
          strftime('%Y-%m-%dT%H:%M:%SZ',applied_at) IS NOT NULL
          AND applied_at=strftime('%Y-%m-%dT%H:%M:%SZ',applied_at,'+0 seconds')
        )
        )"""
    )


def migrate(database_path: Path, busy_timeout_ms: int = 5000) -> list[int]:
    connection = connect(database_path, busy_timeout_ms, allow_create=True)
    applied_now: list[int] = []
    try:
        _ensure_history(connection)
        applied = {
            row["version"]: row
            for row in connection.execute(
                "SELECT version,name,sha256 FROM _finance_v2_schema_migrations ORDER BY version"
            )
        }
        known_versions = {migration.version for migration in MIGRATIONS}
        unknown = set(applied) - known_versions
        if unknown:
            raise MigrationError(f"database contains unknown migration versions: {sorted(unknown)}")
        for migration in MIGRATIONS:
            actual_hash = _digest(migration.path)
            if actual_hash != migration.expected_sha256:
                raise MigrationError(
                    f"migration {migration.version} checksum mismatch: {actual_hash}"
                )
            previous = applied.get(migration.version)
            if previous:
                if previous["name"] != migration.name or previous["sha256"] != actual_hash:
                    raise MigrationError(f"migration {migration.version} history is inconsistent")
                continue
            sql = migration.path.read_text(encoding="utf-8")
            escaped_name = migration.name.replace("'", "''")
            script = (
                "BEGIN IMMEDIATE;\n"
                + sql
                + "\nCREATE TEMP TABLE _migration_fk_assert(ok INTEGER CHECK(ok=1));\nINSERT INTO _migration_fk_assert SELECT NOT EXISTS(SELECT 1 FROM pragma_foreign_key_check);\nDROP TABLE _migration_fk_assert;\n"
                + "\nINSERT INTO _finance_v2_schema_migrations(version,name,sha256,applied_at) "
                + f"VALUES({migration.version},'{escaped_name}','{actual_hash}',strftime('%Y-%m-%dT%H:%M:%SZ','now'));\n"
                + f"PRAGMA user_version={migration.version};\nCOMMIT;"
            )
            try:
                if migration.rebuilds_tables:
                    connection.execute("PRAGMA foreign_keys=OFF")
                connection.executescript(script)
            except sqlite3.Error as exc:
                if connection.in_transaction:
                    connection.rollback()
                raise MigrationError(f"migration {migration.version} failed: {exc}") from exc
            finally:
                connection.execute("PRAGMA foreign_keys=ON")
            applied_now.append(migration.version)
        return applied_now
    finally:
        connection.close()


def migration_status(connection: sqlite3.Connection) -> dict[str, object]:
    exists = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='_finance_v2_schema_migrations'"
    ).fetchone()
    if not exists:
        return {
            "current_version": 0,
            "expected_version": MIGRATIONS[-1].version if MIGRATIONS else 0,
            "applied_count": 0,
            "expected_count": len(MIGRATIONS),
            "up_to_date": False,
        }
    rows = connection.execute(
        "SELECT version,name,sha256,applied_at FROM _finance_v2_schema_migrations ORDER BY version"
    ).fetchall()
    expected = len(MIGRATIONS)
    return {
        "current_version": rows[-1]["version"] if rows else 0,
        "expected_version": MIGRATIONS[-1].version if MIGRATIONS else 0,
        "applied_count": len(rows),
        "expected_count": expected,
        "up_to_date": len(rows) == expected and all(
            row["version"] == migration.version and row["sha256"] == migration.expected_sha256
            for row, migration in zip(rows, MIGRATIONS)
        ),
    }
