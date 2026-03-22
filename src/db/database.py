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
    """Create tables and indexes if they don't already exist."""
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS uploaded_pdfs (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            filename        TEXT    NOT NULL,
            file_hash       TEXT    UNIQUE NOT NULL,
            account_number  TEXT    NOT NULL,
            account_type    TEXT    NOT NULL,
            bsb             TEXT    NOT NULL,
            report_start    TEXT,
            report_end      TEXT,
            transaction_count INTEGER NOT NULL DEFAULT 0,
            parsed_withdrawals REAL NOT NULL DEFAULT 0,
            parsed_deposits    REAL NOT NULL DEFAULT 0,
            uploaded_at     TEXT    NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS transactions (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            date                TEXT    NOT NULL,
            description         TEXT    NOT NULL,
            withdrawal          REAL,
            deposit             REAL,
            account_number      TEXT    NOT NULL,
            account_type        TEXT    NOT NULL,
            category            TEXT    NOT NULL DEFAULT 'Uncategorised',
            month               TEXT    NOT NULL,
            is_internal_transfer INTEGER NOT NULL DEFAULT 0,
            pdf_id              INTEGER REFERENCES uploaded_pdfs(id),
            created_at          TEXT    NOT NULL DEFAULT (datetime('now'))
        );

        CREATE INDEX IF NOT EXISTS idx_txn_month_account
            ON transactions(month, account_number);
        CREATE INDEX IF NOT EXISTS idx_txn_category
            ON transactions(category);
        CREATE INDEX IF NOT EXISTS idx_txn_month
            ON transactions(month);

        CREATE TABLE IF NOT EXISTS category_overrides (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            transaction_id  INTEGER NOT NULL REFERENCES transactions(id),
            old_category    TEXT    NOT NULL,
            new_category    TEXT    NOT NULL,
            changed_at      TEXT    NOT NULL DEFAULT (datetime('now'))
        );
        """
    )
    conn.commit()
