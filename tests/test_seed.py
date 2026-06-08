"""Tests for scripts/seed.py — idempotent v3 seed data."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.db.database import get_connection, init_db
from src.db.queries_estate import (
    get_account_by_number,
    list_managed_persons,
    list_private_managers,
    list_significant_people,
)
from scripts.seed import seed


def _conn(tmp_path):
    conn = get_connection(tmp_path / "test.db")
    init_db(conn)
    return conn


class TestSeed:
    def test_seed_creates_ron_linda_accounts_and_people(self, tmp_path):
        conn = _conn(tmp_path)
        summary = seed(conn)

        # Ron
        people = list_managed_persons(conn)
        assert len(people) == 1
        assert people[0].surname == "GENTILI"

        # Linda
        pms = list_private_managers(conn, summary["managed_person_id"])
        assert len(pms) == 1
        assert pms[0].surname == "TRAVIA"
        assert pms[0].appointment_type == "sole"

        # Three ANZ accounts
        for acc_num, expected_role in [
            ("437669532", "living"),
            ("178865319", "spending"),
            ("178870011", "savings"),
        ]:
            acc = get_account_by_number(conn, acc_num)
            assert acc is not None
            assert acc.role_label == expected_role

        # Significant people from gift table (≥10 entries)
        sp = list_significant_people(conn, summary["managed_person_id"])
        assert len(sp) >= 10
        names = {(p.given_name, p.surname) for p in sp}
        assert ("Sebastian", "GENTILI") in names
        assert ("Nathan", "GENTILI") in names
        assert ("Margaret", "TRAVIA") in names

        conn.close()

    def test_seed_is_idempotent(self, tmp_path):
        conn = _conn(tmp_path)
        first = seed(conn)
        second = seed(conn)

        assert first["significant_people_added"] >= 10
        assert first["accounts_added"] == 3

        # Re-running adds nothing
        assert second["significant_people_added"] == 0
        assert second["accounts_added"] == 0
        assert first["managed_person_id"] == second["managed_person_id"]
        assert first["private_manager_id"] == second["private_manager_id"]

        # Counts in DB stay stable
        assert len(list_managed_persons(conn)) == 1
        assert len(list_private_managers(conn, first["managed_person_id"])) == 1
        conn.close()
