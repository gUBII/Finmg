-- Migration 005: Add nullable account_id FK to transactions.
--
-- Backfill is the responsibility of scripts/seed.py (or a dedicated backfill
-- step) once the `accounts` table is populated. The FK stays nullable so this
-- migration is safe to run on a DB whose transactions table already has rows
-- but whose accounts table is empty.

ALTER TABLE transactions ADD COLUMN account_id INTEGER REFERENCES accounts(id);

CREATE INDEX IF NOT EXISTS idx_txn_account_id ON transactions(account_id);
