"""Tests for the SQLite database layer."""

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.db.database import get_connection, init_db
from src.db.queries import (
    delete_account_transactions_in_range,
    get_all_transactions,
    get_category_totals,
    get_distinct_accounts,
    get_distinct_months,
    get_month_account_coverage,
    get_monthly_totals,
    get_transaction_count,
    get_uploaded_pdfs,
    insert_pdf_and_transactions,
    is_pdf_already_uploaded,
    rows_to_transactions,
    update_transaction_category,
)
from src.models.transaction import AccountMeta, Transaction


def _make_meta(**overrides):
    defaults = dict(
        account_type="ACCESS ACCOUNT",
        account_name="TEST USER",
        bsb="012401",
        account_number="178865319",
        balance=1000.0,
        report_start="15 November 2025",
        report_end="15 March 2026",
    )
    defaults.update(overrides)
    return AccountMeta(**defaults)


def _make_txn(**overrides):
    defaults = dict(
        date=date(2025, 12, 1),
        description="WOOLWORTHS",
        withdrawal=50.0,
        deposit=None,
        account_number="178865319",
        account_type="ACCESS ACCOUNT",
        category="Groceries",
        month="2025-12",
        is_internal_transfer=False,
    )
    defaults.update(overrides)
    return Transaction(**defaults)


class TestDatabaseInit:
    def test_init_creates_tables(self, tmp_path):
        db_path = tmp_path / "test.db"
        conn = get_connection(db_path)
        init_db(conn)
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()
        names = {r["name"] for r in tables}
        assert "uploaded_pdfs" in names
        assert "transactions" in names
        assert "category_overrides" in names
        conn.close()

    def test_init_is_idempotent(self, tmp_path):
        db_path = tmp_path / "test.db"
        conn = get_connection(db_path)
        init_db(conn)
        init_db(conn)  # Should not raise
        conn.close()


class TestInsertAndQuery:
    def _setup_db(self, tmp_path):
        db_path = tmp_path / "test.db"
        conn = get_connection(db_path)
        init_db(conn)
        return conn

    def test_insert_pdf_and_transactions(self, tmp_path):
        conn = self._setup_db(tmp_path)
        meta = _make_meta()
        txns = [
            _make_txn(description="WOOLWORTHS", withdrawal=50.0),
            _make_txn(description="SALARY", withdrawal=None, deposit=2000.0,
                      category="Other", month="2025-12"),
        ]
        pdf_id = insert_pdf_and_transactions(conn, meta, txns, "test.pdf", "abc123")
        assert pdf_id == 1

        rows = get_all_transactions(conn)
        assert len(rows) == 2
        conn.close()

    def test_duplicate_pdf_detection(self, tmp_path):
        conn = self._setup_db(tmp_path)
        meta = _make_meta()
        txns = [_make_txn()]
        insert_pdf_and_transactions(conn, meta, txns, "test.pdf", "hash1")

        assert is_pdf_already_uploaded(conn, "hash1") is True
        assert is_pdf_already_uploaded(conn, "hash2") is False
        conn.close()

    def test_get_distinct_months(self, tmp_path):
        conn = self._setup_db(tmp_path)
        meta = _make_meta()
        txns = [
            _make_txn(month="2025-11", date=date(2025, 11, 1)),
            _make_txn(month="2025-12"),
        ]
        insert_pdf_and_transactions(conn, meta, txns, "test.pdf", "hash1")

        months = get_distinct_months(conn)
        assert months == ["2025-11", "2025-12"]
        conn.close()

    def test_get_distinct_accounts(self, tmp_path):
        conn = self._setup_db(tmp_path)
        meta = _make_meta()
        txns = [_make_txn()]
        insert_pdf_and_transactions(conn, meta, txns, "test.pdf", "hash1")

        accounts = get_distinct_accounts(conn)
        assert "178865319" in accounts
        conn.close()

    def test_filter_by_month(self, tmp_path):
        conn = self._setup_db(tmp_path)
        meta = _make_meta()
        txns = [
            _make_txn(month="2025-11", date=date(2025, 11, 5)),
            _make_txn(month="2025-12"),
        ]
        insert_pdf_and_transactions(conn, meta, txns, "test.pdf", "hash1")

        rows = get_all_transactions(conn, month="2025-12")
        assert len(rows) == 1
        assert rows[0]["month"] == "2025-12"
        conn.close()

    def test_monthly_totals(self, tmp_path):
        conn = self._setup_db(tmp_path)
        meta = _make_meta()
        txns = [
            _make_txn(withdrawal=100.0, deposit=None, month="2025-12"),
            _make_txn(withdrawal=None, deposit=500.0, month="2025-12",
                      category="Other"),
        ]
        insert_pdf_and_transactions(conn, meta, txns, "test.pdf", "hash1")

        totals = get_monthly_totals(conn)
        assert len(totals) == 1
        assert totals[0]["expenses"] == 100.0
        assert totals[0]["income"] == 500.0
        conn.close()

    def test_category_totals(self, tmp_path):
        conn = self._setup_db(tmp_path)
        meta = _make_meta()
        txns = [
            _make_txn(category="Groceries", withdrawal=50.0),
            _make_txn(category="Groceries", withdrawal=30.0),
            _make_txn(category="Rent", withdrawal=200.0),
        ]
        insert_pdf_and_transactions(conn, meta, txns, "test.pdf", "hash1")

        cats = get_category_totals(conn)
        groceries = next(c for c in cats if c["category"] == "Groceries")
        assert groceries["count"] == 2
        assert groceries["total_withdrawals"] == 80.0
        conn.close()

    def test_month_account_coverage(self, tmp_path):
        conn = self._setup_db(tmp_path)
        meta = _make_meta()
        txns = [_make_txn(month="2025-12")]
        insert_pdf_and_transactions(conn, meta, txns, "test.pdf", "hash1")

        coverage = get_month_account_coverage(conn)
        assert ("178865319", "2025-12") in coverage
        conn.close()

    def test_get_transaction_count(self, tmp_path):
        conn = self._setup_db(tmp_path)
        assert get_transaction_count(conn) == 0

        meta = _make_meta()
        txns = [_make_txn(), _make_txn(), _make_txn()]
        insert_pdf_and_transactions(conn, meta, txns, "test.pdf", "hash1")
        assert get_transaction_count(conn) == 3
        conn.close()

    def test_get_uploaded_pdfs(self, tmp_path):
        conn = self._setup_db(tmp_path)
        meta = _make_meta()
        txns = [_make_txn()]
        insert_pdf_and_transactions(conn, meta, txns, "test.pdf", "hash1")

        pdfs = get_uploaded_pdfs(conn)
        assert len(pdfs) == 1
        assert pdfs[0]["filename"] == "test.pdf"
        conn.close()


class TestUpdateCategory:
    def test_update_category_logs_override(self, tmp_path):
        db_path = tmp_path / "test.db"
        conn = get_connection(db_path)
        init_db(conn)

        meta = _make_meta()
        txns = [_make_txn(category="Uncategorised")]
        insert_pdf_and_transactions(conn, meta, txns, "test.pdf", "hash1")

        rows = get_all_transactions(conn)
        txn_id = rows[0]["id"]

        update_transaction_category(conn, txn_id, "Groceries", "Uncategorised")

        updated = get_all_transactions(conn)
        assert updated[0]["category"] == "Groceries"

        overrides = conn.execute(
            "SELECT * FROM category_overrides WHERE transaction_id = ?", (txn_id,)
        ).fetchall()
        assert len(overrides) == 1
        assert overrides[0]["old_category"] == "Uncategorised"
        assert overrides[0]["new_category"] == "Groceries"
        conn.close()

    def test_update_to_internal_transfer_sets_flag(self, tmp_path):
        db_path = tmp_path / "test.db"
        conn = get_connection(db_path)
        init_db(conn)

        meta = _make_meta()
        txns = [_make_txn(category="Uncategorised")]
        insert_pdf_and_transactions(conn, meta, txns, "test.pdf", "hash1")

        rows = get_all_transactions(conn)
        txn_id = rows[0]["id"]

        update_transaction_category(conn, txn_id, "Internal Transfer", "Uncategorised")

        updated = get_all_transactions(conn)
        assert updated[0]["is_internal_transfer"] == 1
        conn.close()


class TestOverlapPrevention:
    """Rolling-statement re-upload must replace, not duplicate, overlapping dates."""

    def test_re_upload_same_account_replaces_overlapping_transactions(self, tmp_path):
        db_path = tmp_path / "test.db"
        conn = get_connection(db_path)
        init_db(conn)

        meta = _make_meta()
        txns_v1 = [
            _make_txn(date=date(2025, 12, 1), description="WOOLWORTHS"),
            _make_txn(date=date(2025, 12, 15), description="COLES"),
        ]
        insert_pdf_and_transactions(conn, meta, txns_v1, "statement_v1.pdf", "hash1")
        assert get_transaction_count(conn) == 2

        # Upload a newer statement that overlaps the same date range
        txns_v2 = [
            _make_txn(date=date(2025, 12, 1), description="WOOLWORTHS"),   # same
            _make_txn(date=date(2025, 12, 15), description="COLES"),        # same
            _make_txn(date=date(2025, 12, 20), description="ALDI"),         # new
        ]
        insert_pdf_and_transactions(conn, meta, txns_v2, "statement_v2.pdf", "hash2")

        # Should have 3, not 5 (old overlap deleted before new insert)
        assert get_transaction_count(conn) == 3
        descs = {r["description"] for r in get_all_transactions(conn)}
        assert "ALDI" in descs
        conn.close()

    def test_delete_account_transactions_in_range(self, tmp_path):
        db_path = tmp_path / "test.db"
        conn = get_connection(db_path)
        init_db(conn)

        meta = _make_meta()
        txns = [
            _make_txn(date=date(2025, 11, 30), description="NOV"),
            _make_txn(date=date(2025, 12, 5), description="DEC_MID"),
            _make_txn(date=date(2025, 12, 31), description="DEC_END"),
        ]
        insert_pdf_and_transactions(conn, meta, txns, "stmt.pdf", "hash1")

        deleted = delete_account_transactions_in_range(
            conn, meta.account_number, "2025-12-01", "2025-12-31"
        )
        conn.commit()
        assert deleted == 2
        remaining = get_all_transactions(conn)
        assert len(remaining) == 1
        assert remaining[0]["description"] == "NOV"
        conn.close()

    def test_different_account_not_affected_by_overlap_delete(self, tmp_path):
        db_path = tmp_path / "test.db"
        conn = get_connection(db_path)
        init_db(conn)

        meta1 = _make_meta(account_number="178865319")
        meta2 = _make_meta(account_number="178870011", account_type="PROGRESS SAVER")
        txn1 = _make_txn(account_number="178865319")
        txn2 = _make_txn(account_number="178870011", account_type="PROGRESS SAVER")

        insert_pdf_and_transactions(conn, meta1, [txn1], "a.pdf", "h1")
        insert_pdf_and_transactions(conn, meta2, [txn2], "b.pdf", "h2")

        # Re-upload for account 1 only — account 2 row must survive
        insert_pdf_and_transactions(conn, meta1, [txn1], "a_new.pdf", "h3")

        rows = get_all_transactions(conn)
        accounts = {r["account_number"] for r in rows}
        assert "178870011" in accounts
        conn.close()


class TestRowConversion:
    def test_rows_to_transactions(self, tmp_path):
        db_path = tmp_path / "test.db"
        conn = get_connection(db_path)
        init_db(conn)

        meta = _make_meta()
        txns = [_make_txn(description="COLES", withdrawal=75.0)]
        insert_pdf_and_transactions(conn, meta, txns, "test.pdf", "hash1")

        rows = get_all_transactions(conn)
        converted = rows_to_transactions(rows)
        assert len(converted) == 1
        assert isinstance(converted[0], Transaction)
        assert converted[0].description == "COLES"
        assert converted[0].withdrawal == 75.0
        assert converted[0].date == date(2025, 12, 1)
        conn.close()
