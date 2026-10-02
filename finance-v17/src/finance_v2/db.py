from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
import sqlite3
from typing import Iterator


def connect(database_path: Path, busy_timeout_ms: int = 5000, *, allow_create: bool = False) -> sqlite3.Connection:
    database_path = database_path.resolve()
    if database_path == Path(":memory:"):
        raise ValueError("ephemeral database paths are not allowed by runtime bootstrap")
    if not database_path.exists() and not allow_create:
        raise FileNotFoundError(f"database does not exist; run migrations first: {database_path}")
    if allow_create:
        database_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(database_path, timeout=busy_timeout_ms / 1000, isolation_level=None)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys=ON")
    connection.execute(f"PRAGMA busy_timeout={busy_timeout_ms:d}")
    connection.execute("PRAGMA journal_mode=WAL")
    return connection


@contextmanager
def immediate_transaction(connection: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
    """Expose the explicit transaction mode required by critical V16 operations."""
    connection.execute("BEGIN IMMEDIATE")
    try:
        yield connection
    except BaseException:
        connection.rollback()
        raise
    else:
        connection.commit()


def database_is_healthy(connection: sqlite3.Connection) -> bool:
    return connection.execute("SELECT 1").fetchone()[0] == 1
