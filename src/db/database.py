"""SQLite database initialisation and connection management."""

from __future__ import annotations

import sqlite3
from pathlib import Path

DEFAULT_DB_PATH = Path(__file__).parent.parent.parent / "data" / "finmg.db"


def get_connection(db_path: str | Path | None = None) -> sqlite3.Connection:
    """Return a SQLite connection, creating the database file if needed."""
    path = Path(db_path) if db_path else DEFAULT_DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    """Apply every pending migration in `src/db/schema/`.

    Schema is owned by versioned SQL files (`001_baseline.sql`, ...). Re-running
    is a no-op once all migrations are recorded in `schema_migrations`.
    """
    from src.db.migrations import apply_all

    apply_all(conn, db_path=None)
