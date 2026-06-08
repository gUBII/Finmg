"""Round-trip CRUD tests for queries_estate.py against a fresh migrated DB."""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.db.database import get_connection, init_db
from src.db.queries import insert_pdf_and_transactions
from src.db.queries_estate import (
    backfill_transactions_account_id,
    find_significant_person_by_name,
    get_account_by_number,
    get_managed_person,
    insert_account,
    insert_managed_person,
    insert_private_manager,
    insert_significant_person,
    list_accounts,
    list_managed_persons,
    list_private_managers,
    list_significant_people,
)
from src.models.estate import (
    Account,
    ManagedPerson,
    PrivateManager,
    SignificantPerson,
)
from src.models.transaction import AccountMeta, Transaction


def _conn(tmp_path):
    conn = get_connection(tmp_path / "test.db")
    init_db(conn)
    return conn


def _seed_ron(conn) -> int:
    ron = ManagedPerson(
        surname="GENTILI",
        given_names="Renato",
        dob="1955-01-01",
        disability_flags='["physical","brain_injury"]',
    )
    return insert_managed_person(conn, ron)


# ---------------------------------------------------------------------------
# managed_persons
# ---------------------------------------------------------------------------


class TestManagedPersons:
    def test_round_trip(self, tmp_path):
        conn = _conn(tmp_path)
        mp_id = _seed_ron(conn)
        assert mp_id == 1

        fetched = get_managed_person(conn, mp_id)
        assert fetched is not None
        assert fetched.surname == "GENTILI"
        assert fetched.given_names == "Renato"
        assert fetched.disability_flags == '["physical","brain_injury"]'
        conn.close()

    def test_get_missing_returns_none(self, tmp_path):
        conn = _conn(tmp_path)
        assert get_managed_person(conn, 999) is None
        conn.close()

    def test_list_orders_by_surname(self, tmp_path):
        conn = _conn(tmp_path)
        insert_managed_person(
            conn, ManagedPerson(surname="ZED", given_names="A")
        )
        insert_managed_person(
            conn, ManagedPerson(surname="ALPHA", given_names="B")
        )
        results = list_managed_persons(conn)
        assert [r.surname for r in results] == ["ALPHA", "ZED"]
        conn.close()

    def test_interpreter_required_round_trips_as_bool(self, tmp_path):
        conn = _conn(tmp_path)
        mp_id = insert_managed_person(
            conn,
            ManagedPerson(
                surname="X",
                given_names="Y",
                interpreter_required=True,
                interpreter_language="Italian",
            ),
        )
        fetched = get_managed_person(conn, mp_id)
        assert fetched.interpreter_required in (True, 1)  # SQLite stores as int
        assert fetched.interpreter_language == "Italian"
        conn.close()


# ---------------------------------------------------------------------------
# private_managers
# ---------------------------------------------------------------------------


class TestPrivateManagers:
    def test_insert_and_list(self, tmp_path):
        conn = _conn(tmp_path)
        ron_id = _seed_ron(conn)
        linda = PrivateManager(
            managed_person_id=ron_id,
            surname="TRAVIA",
            given_name="Linda",
            relationship="Lifelong partner",
            appointment_type="sole",
        )
        pm_id = insert_private_manager(conn, linda)
        assert pm_id == 1

        results = list_private_managers(conn, ron_id)
        assert len(results) == 1
        assert results[0].surname == "TRAVIA"
        assert results[0].appointment_type == "sole"
        conn.close()

    def test_fk_cascade_on_managed_person_delete(self, tmp_path):
        conn = _conn(tmp_path)
        ron_id = _seed_ron(conn)
        insert_private_manager(
            conn,
            PrivateManager(managed_person_id=ron_id, surname="T", given_name="L"),
        )
        conn.execute("DELETE FROM managed_persons WHERE id = ?", (ron_id,))
        conn.commit()
        results = list_private_managers(conn, ron_id)
        assert results == []
        conn.close()


# ---------------------------------------------------------------------------
# significant_people
# ---------------------------------------------------------------------------


class TestSignificantPeople:
    def test_default_active_status_filtered_by_list(self, tmp_path):
        conn = _conn(tmp_path)
        ron_id = _seed_ron(conn)
        insert_significant_person(
            conn,
            SignificantPerson(
                managed_person_id=ron_id,
                surname="GENTILI",
                given_name="Sebastian",
                relationship="Son",
            ),
        )
        insert_significant_person(
            conn,
            SignificantPerson(
                managed_person_id=ron_id,
                surname="GHOST",
                given_name="Old",
                consultation_status="deceased",
            ),
        )
        active = list_significant_people(conn, ron_id)
        assert {r.given_name for r in active} == {"Sebastian"}
        with_deceased = list_significant_people(
            conn, ron_id, include_deceased=True
        )
        assert {r.given_name for r in with_deceased} == {"Sebastian", "Old"}
        conn.close()

    def test_find_by_name(self, tmp_path):
        conn = _conn(tmp_path)
        ron_id = _seed_ron(conn)
        insert_significant_person(
            conn,
            SignificantPerson(
                managed_person_id=ron_id,
                surname="GENTILI",
                given_name="Nathan",
                relationship="Son",
            ),
        )
        match = find_significant_person_by_name(conn, ron_id, "Nathan", "GENTILI")
        assert match is not None
        assert match.relationship == "Son"
        assert find_significant_person_by_name(conn, ron_id, "NotAPerson", "X") is None
        conn.close()


# ---------------------------------------------------------------------------
# accounts
# ---------------------------------------------------------------------------


class TestAccounts:
    def _seeded(self, tmp_path):
        conn = _conn(tmp_path)
        ron_id = _seed_ron(conn)
        # Three real-world ANZ accounts (mapping confirmed by Linda 2026-06-08).
        insert_account(
            conn,
            Account(
                managed_person_id=ron_id,
                institution="ANZ",
                account_number="437669532",
                bsb="013711",
                account_type="ACCESS ACCOUNT",
                role_label="living",
                inception_date="2025-05-01",
            ),
        )
        insert_account(
            conn,
            Account(
                managed_person_id=ron_id,
                institution="ANZ",
                account_number="178865319",
                bsb="012401",
                account_type="ACCESS ACCOUNT",
                role_label="spending",
                inception_date="2025-09-01",  # Linda: card didn't exist until Aug 2025
            ),
        )
        insert_account(
            conn,
            Account(
                managed_person_id=ron_id,
                institution="ANZ",
                account_number="178870011",
                bsb="012401",
                account_type="PROGRESS SAVER",
                role_label="savings",
                inception_date="2025-09-01",
            ),
        )
        return conn, ron_id

    def test_three_accounts_inserted_and_listed(self, tmp_path):
        conn, ron_id = self._seeded(tmp_path)
        accounts = list_accounts(conn, ron_id)
        assert len(accounts) == 3
        role_to_num = {a.role_label: a.account_number for a in accounts}
        assert role_to_num == {
            "living": "437669532",
            "spending": "178865319",
            "savings": "178870011",
        }
        conn.close()

    def test_get_by_number(self, tmp_path):
        conn, _ = self._seeded(tmp_path)
        living = get_account_by_number(conn, "437669532")
        assert living is not None
        assert living.role_label == "living"
        assert living.bsb == "013711"
        assert get_account_by_number(conn, "nonexistent") is None
        conn.close()

    def test_account_number_uniqueness(self, tmp_path):
        conn, ron_id = self._seeded(tmp_path)
        with pytest.raises(Exception):
            insert_account(
                conn,
                Account(
                    managed_person_id=ron_id,
                    institution="ANZ",
                    account_number="437669532",  # duplicate
                ),
            )
        conn.close()


# ---------------------------------------------------------------------------
# transactions.account_id backfill
# ---------------------------------------------------------------------------


class TestInsertSetsAccountIdInline:
    """`insert_pdf_and_transactions` must FK-link each transaction to its
    `accounts` row when the row exists at upload time. Without this, every
    new upload silently produces account_id=NULL rows."""

    def test_new_upload_populates_account_id_when_account_seeded(self, tmp_path):
        conn = _conn(tmp_path)
        ron_id = _seed_ron(conn)
        living_acc_id = insert_account(
            conn,
            Account(
                managed_person_id=ron_id,
                institution="ANZ",
                account_number="437669532",
                role_label="living",
            ),
        )

        meta = AccountMeta(
            account_type="ACCESS ACCOUNT",
            account_name="GENTILI RENATO",
            bsb="013711",
            account_number="437669532",
            balance=10000.0,
            report_start="01 May 2025",
            report_end="30 Jun 2025",
        )
        insert_pdf_and_transactions(
            conn,
            meta,
            [Transaction(
                date=date(2025, 5, 5),
                description="X",
                deposit=1.0,
                account_number="437669532",
                account_type="ACCESS ACCOUNT",
                category="Other",
                month="2025-05",
            )],
            "x.pdf",
            "h_inline",
        )

        rows = conn.execute("SELECT account_id FROM transactions").fetchall()
        assert all(r["account_id"] == living_acc_id for r in rows)
        conn.close()

    def test_account_id_stays_null_when_account_not_seeded(self, tmp_path):
        conn = _conn(tmp_path)
        _seed_ron(conn)  # but NO accounts row inserted

        meta = AccountMeta(
            account_type="ACCESS ACCOUNT",
            account_name="GENTILI RENATO",
            bsb="013711",
            account_number="437669532",
            balance=10000.0,
            report_start="01 May 2025",
            report_end="30 Jun 2025",
        )
        insert_pdf_and_transactions(
            conn,
            meta,
            [Transaction(
                date=date(2025, 5, 5),
                description="X",
                deposit=1.0,
                account_number="437669532",
                account_type="ACCESS ACCOUNT",
                category="Other",
                month="2025-05",
            )],
            "x.pdf",
            "h_noacc",
        )

        rows = conn.execute("SELECT account_id FROM transactions").fetchall()
        assert all(r["account_id"] is None for r in rows)
        conn.close()


class TestTransactionAccountFkBackfill:
    """Backfill is for the legacy case: transactions ingested by an older
    code path (or by `insert_pdf_and_transactions` before the matching
    `accounts` row existed) and now need their `account_id` populated.
    """

    def test_backfill_links_legacy_transactions_to_accounts(self, tmp_path):
        conn = _conn(tmp_path)
        ron_id = _seed_ron(conn)

        # 1. Insert transactions FIRST, before the account exists → NULL account_id.
        meta = AccountMeta(
            account_type="ACCESS ACCOUNT",
            account_name="GENTILI RENATO",
            bsb="013711",
            account_number="437669532",
            balance=10000.0,
            report_start="01 May 2025",
            report_end="30 Jun 2025",
        )
        insert_pdf_and_transactions(
            conn,
            meta,
            [Transaction(
                date=date(2025, 5, 5),
                description="LACTALIS WAGES",
                deposit=2500.0,
                account_number="437669532",
                account_type="ACCESS ACCOUNT",
                category="Other",
                month="2025-05",
            )],
            "living.pdf",
            "h1",
        )

        before = conn.execute(
            "SELECT account_id FROM transactions"
        ).fetchall()
        assert all(r["account_id"] is None for r in before)

        # 2. Now insert the account and run backfill.
        living_acc_id = insert_account(
            conn,
            Account(
                managed_person_id=ron_id,
                institution="ANZ",
                account_number="437669532",
                role_label="living",
            ),
        )
        updated = backfill_transactions_account_id(conn)
        assert updated == 1

        after = conn.execute(
            "SELECT account_id FROM transactions"
        ).fetchall()
        assert all(r["account_id"] == living_acc_id for r in after)
        conn.close()

    def test_backfill_is_idempotent(self, tmp_path):
        conn = _conn(tmp_path)
        ron_id = _seed_ron(conn)
        meta = AccountMeta(
            account_type="ACCESS ACCOUNT",
            account_name="GENTILI RENATO",
            bsb="013711",
            account_number="437669532",
            balance=10000.0,
            report_start="01 May 2025",
            report_end="30 Jun 2025",
        )
        # Insert before account exists so backfill has work to do.
        insert_pdf_and_transactions(
            conn,
            meta,
            [Transaction(
                date=date(2025, 5, 5),
                description="X",
                deposit=1.0,
                account_number="437669532",
                account_type="ACCESS ACCOUNT",
                category="Other",
                month="2025-05",
            )],
            "x.pdf",
            "h1",
        )
        insert_account(
            conn,
            Account(
                managed_person_id=ron_id,
                institution="ANZ",
                account_number="437669532",
                role_label="living",
            ),
        )

        first = backfill_transactions_account_id(conn)
        second = backfill_transactions_account_id(conn)
        assert first == 1
        assert second == 0
        conn.close()

    def test_backfill_skips_transactions_with_no_matching_account(self, tmp_path):
        conn = _conn(tmp_path)
        ron_id = _seed_ron(conn)
        # Account exists but NOT for the transaction's account_number
        insert_account(
            conn,
            Account(
                managed_person_id=ron_id,
                institution="ANZ",
                account_number="999999999",
            ),
        )
        meta = AccountMeta(
            account_type="ACCESS ACCOUNT",
            account_name="X",
            bsb="013711",
            account_number="437669532",
            balance=0.0,
            report_start="01 May 2025",
            report_end="30 Jun 2025",
        )
        insert_pdf_and_transactions(
            conn,
            meta,
            [Transaction(
                date=date(2025, 5, 5),
                description="X",
                deposit=1.0,
                account_number="437669532",
                account_type="ACCESS ACCOUNT",
                category="Other",
                month="2025-05",
            )],
            "x.pdf",
            "h1",
        )
        updated = backfill_transactions_account_id(conn)
        assert updated == 0
        conn.close()
