"""Tests for src/db/migrations.py — the versioned SQLite migration runner."""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.db.database import get_connection, init_db
from src.db.migrations import (
    apply_all,
    apply_migration,
    applied_versions,
    backup_db,
    discover_migrations,
)


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------


class TestDiscoverMigrations:
    def test_real_schema_dir_has_five_migrations(self):
        migrations = discover_migrations()
        versions = [v for v, _ in migrations]
        assert "001" in versions
        assert "002" in versions
        assert "003" in versions
        assert "004" in versions
        assert "005" in versions

    def test_versions_returned_in_sorted_order(self):
        migrations = discover_migrations()
        versions = [v for v, _ in migrations]
        assert versions == sorted(versions)

    def test_ignores_non_matching_filenames(self, tmp_path):
        (tmp_path / "001_real.sql").write_text("-- ok")
        (tmp_path / "README.md").write_text("ignore")
        (tmp_path / "not_a_migration.sql").write_text("ignore")
        migrations = discover_migrations(tmp_path)
        assert [v for v, _ in migrations] == ["001"]


# ---------------------------------------------------------------------------
# Apply
# ---------------------------------------------------------------------------


def _fresh_conn(tmp_path: Path) -> sqlite3.Connection:
    return get_connection(tmp_path / "test.db")


class TestApplyAll:
    def test_fresh_db_applies_every_migration(self, tmp_path):
        conn = _fresh_conn(tmp_path)
        applied = apply_all(conn)
        assert "001" in applied
        assert "002" in applied
        assert "003" in applied
        assert "004" in applied
        assert "005" in applied
        conn.close()

    def test_second_apply_is_noop(self, tmp_path):
        conn = _fresh_conn(tmp_path)
        apply_all(conn)
        second = apply_all(conn)
        assert second == []
        conn.close()

    def test_creates_all_v3_tables(self, tmp_path):
        conn = _fresh_conn(tmp_path)
        apply_all(conn)
        tables = {
            r["name"]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        expected = {
            # baseline
            "schema_migrations",
            "uploaded_pdfs",
            "transactions",
            "category_overrides",
            # estate
            "managed_persons",
            "private_managers",
            "significant_people",
            "accounts",
            "real_estate",
            "investments",
            "motor_vehicles",
            "accommodation_bonds",
            "debts_liabilities",
            # forecast
            "forecast_categories",
            "forecasts",
            "one_off_events",
            # compliance
            "consultation_log",
            "submissions",
            "acknowledgements",
            "submission_attachments",
            "gifts",
            "notifications_log",
            "audit_log",
        }
        missing = expected - tables
        assert not missing, f"missing tables after migration: {missing}"
        conn.close()

    def test_records_versions_in_schema_migrations(self, tmp_path):
        conn = _fresh_conn(tmp_path)
        apply_all(conn)
        recorded = applied_versions(conn)
        assert {"001", "002", "003", "004", "005"}.issubset(recorded)
        conn.close()

    def test_transactions_table_has_account_id_column(self, tmp_path):
        """Migration 005 must add the nullable account_id FK column."""
        conn = _fresh_conn(tmp_path)
        apply_all(conn)
        cols = {
            r["name"]
            for r in conn.execute("PRAGMA table_info(transactions)").fetchall()
        }
        assert "account_id" in cols
        conn.close()


# ---------------------------------------------------------------------------
# Backup
# ---------------------------------------------------------------------------


class TestBackupDb:
    def test_no_op_when_db_missing(self, tmp_path):
        missing = tmp_path / "doesnt_exist.db"
        backup_dir = tmp_path / "backups"
        result = backup_db(missing, backup_dir)
        assert result is None
        assert not backup_dir.exists() or not any(backup_dir.iterdir())

    def test_creates_timestamped_copy(self, tmp_path):
        db_path = tmp_path / "src.db"
        db_path.write_bytes(b"hello")
        backup_dir = tmp_path / "backups"
        result = backup_db(db_path, backup_dir)
        assert result is not None
        assert result.exists()
        assert result.read_bytes() == b"hello"
        assert result.name.startswith("finmg_")
        assert result.name.endswith(".db")

    def test_apply_all_backs_up_existing_db_before_running_migrations(self, tmp_path):
        """Before applying the first new migration on an existing DB, a backup
        copy must land in the backup directory."""
        db_path = tmp_path / "finmg.db"
        backup_dir = tmp_path / "backups"

        conn = get_connection(db_path)
        # Pretend an older app version already created some tables.
        conn.executescript(
            "CREATE TABLE legacy_table (id INTEGER PRIMARY KEY); "
            "INSERT INTO legacy_table DEFAULT VALUES;"
        )
        conn.commit()
        conn.close()

        conn = get_connection(db_path)
        apply_all(conn, db_path=db_path, backup_dir=backup_dir)
        conn.close()

        backups = list(backup_dir.iterdir()) if backup_dir.exists() else []
        assert len(backups) == 1, f"expected one backup, found {backups}"


# ---------------------------------------------------------------------------
# Audit log immutability
# ---------------------------------------------------------------------------


class TestAuditLogImmutability:
    def _seeded(self, tmp_path):
        conn = _fresh_conn(tmp_path)
        apply_all(conn)
        conn.execute(
            "INSERT INTO audit_log (action, table_name, row_id) VALUES (?, ?, ?)",
            ("insert", "managed_persons", 1),
        )
        conn.commit()
        return conn

    def test_update_blocked_by_trigger(self, tmp_path):
        conn = self._seeded(tmp_path)
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("UPDATE audit_log SET reason = 'tamper' WHERE id = 1")
        conn.close()

    def test_delete_blocked_by_trigger(self, tmp_path):
        conn = self._seeded(tmp_path)
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("DELETE FROM audit_log WHERE id = 1")
        conn.close()


# ---------------------------------------------------------------------------
# init_db wiring
# ---------------------------------------------------------------------------


class TestInitDbWiring:
    def test_init_db_applies_migrations(self, tmp_path):
        """init_db() in src/db/database.py must now apply every migration so
        existing call sites (Streamlit app, tests) pick up v3 tables for free.
        """
        conn = get_connection(tmp_path / "test.db")
        init_db(conn)
        tables = {
            r["name"]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        assert "managed_persons" in tables
        assert "accounts" in tables
        assert "audit_log" in tables
        conn.close()
