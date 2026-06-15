"""Auto-registration of accounts on upload + DB-driven friendly names.

Verifies that uploading a statement for an unknown account number registers a
row in `accounts` (so transactions FK-link and friendly names resolve), and
that `get_account_display_names` prefers `accounts.role_label` over the static
fallback dict.
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.db.database import get_connection, init_db
from src.db.queries import (
    ensure_account_for_upload,
    get_account_display_names,
    insert_pdf_and_transactions,
)
from src.db.queries_estate import get_account_by_number, insert_account, insert_managed_person
from src.models.estate import Account, ManagedPerson
from src.models.transaction import AccountMeta, Transaction


def _conn(tmp_path):
    conn = get_connection(tmp_path / "test.db")
    init_db(conn)
    return conn


def _ron(conn) -> int:
    return insert_managed_person(conn, ManagedPerson(surname="GENTILI", given_names="Renato"))


def _meta(account_number="999888777", account_type="ACCESS ACCOUNT", bsb="013999"):
    return AccountMeta(
        account_type=account_type,
        account_name="GENTILI RENATO",
        bsb=bsb,
        account_number=account_number,
        balance=0.0,
        report_start="2026-02-01",
        report_end="2026-05-31",
    )


def _txns(account_number="999888777"):
    return [
        Transaction(
            date=date(2026, 3, 1),
            description="WOOLWORTHS",
            withdrawal=50.0,
            deposit=None,
            account_number=account_number,
            account_type="ACCESS ACCOUNT",
            month="2026-03",
            category="Groceries",
            is_internal_transfer=False,
        )
    ]


# --------------------------------------------------------------------------- ensure_account
class TestEnsureAccount:
    def test_creates_row_for_new_account(self, tmp_path):
        conn = _conn(tmp_path)
        _ron(conn)
        acc_id = ensure_account_for_upload(conn, _meta())
        assert acc_id is not None
        acc = get_account_by_number(conn, "999888777")
        assert acc is not None
        assert acc.institution == "ANZ"
        assert acc.bsb == "013999"
        assert acc.account_type == "ACCESS ACCOUNT"
        # ACCESS ACCOUNT is ambiguous → role left unset for the user.
        assert acc.role_label is None

    def test_returns_existing_without_duplicating(self, tmp_path):
        conn = _conn(tmp_path)
        mp = _ron(conn)
        first = insert_account(
            conn,
            Account(managed_person_id=mp, institution="ANZ", account_number="999888777"),
        )
        again = ensure_account_for_upload(conn, _meta())
        assert again == first
        rows = conn.execute(
            "SELECT COUNT(*) AS n FROM accounts WHERE account_number = ?", ("999888777",)
        ).fetchone()
        assert rows["n"] == 1

    def test_returns_none_without_managed_person(self, tmp_path):
        conn = _conn(tmp_path)  # no managed person seeded
        assert ensure_account_for_upload(conn, _meta()) is None

    def test_savings_role_guessed_from_type(self, tmp_path):
        conn = _conn(tmp_path)
        _ron(conn)
        ensure_account_for_upload(conn, _meta(account_type="PROGRESS SAVER"))
        acc = get_account_by_number(conn, "999888777")
        assert acc.role_label == "savings"


# --------------------------------------------------------------------------- upload linkage
class TestUploadLinksAccountId:
    def test_new_account_transactions_get_account_id(self, tmp_path):
        conn = _conn(tmp_path)
        _ron(conn)
        fhash = ("ac" + "0" * 62)[:64]
        insert_pdf_and_transactions(conn, _meta(), _txns(), "new.pdf", fhash)
        acc = get_account_by_number(conn, "999888777")
        row = conn.execute(
            "SELECT account_id FROM transactions WHERE account_number = ?", ("999888777",)
        ).fetchone()
        assert row["account_id"] == acc.id

    def test_no_managed_person_leaves_account_id_null(self, tmp_path):
        conn = _conn(tmp_path)  # no managed person → graceful NULL, no crash
        fhash = ("bd" + "0" * 62)[:64]
        insert_pdf_and_transactions(conn, _meta(), _txns(), "new.pdf", fhash)
        row = conn.execute(
            "SELECT account_id FROM transactions WHERE account_number = ?", ("999888777",)
        ).fetchone()
        assert row["account_id"] is None


# --------------------------------------------------------------------------- display names
class TestDisplayNames:
    def test_role_label_drives_name(self, tmp_path):
        conn = _conn(tmp_path)
        mp = _ron(conn)
        insert_account(
            conn,
            Account(
                managed_person_id=mp,
                institution="ANZ",
                account_number="437669532",
                account_type="ACCESS ACCOUNT",
                role_label="living",
            ),
        )
        names = get_account_display_names(conn)
        assert names["437669532"] == "Living Account"

    def test_unlabelled_account_falls_back_to_type(self, tmp_path):
        conn = _conn(tmp_path)
        _ron(conn)
        # Auto-register an unknown number with no role → name falls back to type.
        ensure_account_for_upload(conn, _meta(account_number="555000111"))
        names = get_account_display_names(conn)
        assert names["555000111"] == "ACCESS ACCOUNT"

    def test_transaction_only_account_uses_static_fallback(self, tmp_path):
        conn = _conn(tmp_path)  # no managed person → no accounts row created
        fhash = ("ce" + "0" * 62)[:64]
        # 178870011 is in the static fallback dict but not in `accounts`.
        insert_pdf_and_transactions(conn, _meta(account_number="178870011"), _txns("178870011"), "x.pdf", fhash)
        names = get_account_display_names(conn)
        assert names["178870011"] == "Savings Account"
