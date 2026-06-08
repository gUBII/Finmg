-- Migration 001: Baseline schema (extracted from src/db/database.py init_db()).
-- Idempotent. Re-running is a no-op.

CREATE TABLE IF NOT EXISTS schema_migrations (
    version     TEXT    PRIMARY KEY,
    applied_at  TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS uploaded_pdfs (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    filename            TEXT    NOT NULL,
    file_hash           TEXT    UNIQUE NOT NULL,
    account_number      TEXT    NOT NULL,
    account_type        TEXT    NOT NULL,
    bsb                 TEXT    NOT NULL,
    report_start        TEXT,
    report_end          TEXT,
    transaction_count   INTEGER NOT NULL DEFAULT 0,
    parsed_withdrawals  REAL    NOT NULL DEFAULT 0,
    parsed_deposits     REAL    NOT NULL DEFAULT 0,
    uploaded_at         TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS transactions (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    date                 TEXT    NOT NULL,
    description          TEXT    NOT NULL,
    withdrawal           REAL,
    deposit              REAL,
    account_number       TEXT    NOT NULL,
    account_type         TEXT    NOT NULL,
    category             TEXT    NOT NULL DEFAULT 'Uncategorised',
    month                TEXT    NOT NULL,
    is_internal_transfer INTEGER NOT NULL DEFAULT 0,
    pdf_id               INTEGER REFERENCES uploaded_pdfs(id),
    created_at           TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_txn_month_account ON transactions(month, account_number);
CREATE INDEX IF NOT EXISTS idx_txn_category      ON transactions(category);
CREATE INDEX IF NOT EXISTS idx_txn_month         ON transactions(month);

CREATE TABLE IF NOT EXISTS category_overrides (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    transaction_id  INTEGER NOT NULL REFERENCES transactions(id),
    old_category    TEXT    NOT NULL,
    new_category    TEXT    NOT NULL,
    changed_at      TEXT    NOT NULL DEFAULT (datetime('now'))
);
