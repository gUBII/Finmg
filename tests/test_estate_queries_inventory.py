"""Inventory update-path tests for queries_estate.py — S3 acceptance gate.

Covers the 12 helpers added in S3:
  update_account / get_account
  update_real_estate / get_real_estate
  update_investment / get_investment
  update_motor_vehicle / get_motor_vehicle
  update_accommodation_bond / get_accommodation_bond
  update_debt_liability / get_debt_liability

Plus the account-specific evidence-field immutability tests
(institution / account_number / bsb come from parsed PDFs and must not be
mutable through the update API). Mirrors AAA + _conn(tmp_path) conventions
from tests/test_estate_queries_updates.py.
"""

from __future__ import annotations

import sys
import time
from dataclasses import replace
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.db.database import get_connection, init_db
from src.db.queries_estate import (
    get_accommodation_bond,
    get_account,
    get_debt_liability,
    get_investment,
    get_motor_vehicle,
    get_real_estate,
    insert_accommodation_bond,
    insert_account,
    insert_debt_liability,
    insert_investment,
    insert_managed_person,
    insert_motor_vehicle,
    insert_real_estate,
    list_accounts,
    update_accommodation_bond,
    update_account,
    update_debt_liability,
    update_investment,
    update_motor_vehicle,
    update_real_estate,
)
from src.models.estate import (
    AccommodationBond,
    Account,
    DebtLiability,
    Investment,
    ManagedPerson,
    MotorVehicle,
    RealEstate,
)


def _conn(tmp_path):
    conn = get_connection(tmp_path / "test.db")
    init_db(conn)
    return conn


def _seed_ron(conn) -> int:
    return insert_managed_person(
        conn, ManagedPerson(surname="GENTILI", given_names="Renato")
    )


def _seed_account(conn, ron_id: int, **kwargs) -> int:
    defaults = dict(
        managed_person_id=ron_id,
        institution="ANZ",
        account_number="178865319",
        bsb="012-345",
        account_type="ACCESS ACCOUNT",
        role_label="living",
        ownership="sole",
        inception_date="2024-01-01",
        current_balance=1234.56,
        balance_as_of_date="2026-06-01",
        notes="seed",
    )
    defaults.update(kwargs)
    return insert_account(conn, Account(**defaults))


# ---------------------------------------------------------------------------
# TestUpdateAccount  (5 tests — round-trip, hidden-fields, 3 immutability)
# ---------------------------------------------------------------------------


class TestUpdateAccount:
    def test_round_trip_updates_editable_fields(self, tmp_path):
        # Arrange
        conn = _conn(tmp_path)
        ron_id = _seed_ron(conn)
        acc_id = _seed_account(conn, ron_id)

        # Act
        original = get_account(conn, acc_id)
        updated = replace(
            original,
            role_label="savings",
            ownership="joint",
            current_balance=9999.00,
            notes="updated",
        )
        update_account(conn, acc_id, updated)

        # Assert
        fetched = get_account(conn, acc_id)
        assert fetched.role_label == "savings"
        assert fetched.ownership == "joint"
        assert fetched.current_balance == 9999.00
        assert fetched.notes == "updated"
        conn.close()

    def test_replace_pattern_preserves_unrelated_fields(self, tmp_path):
        """Regression: replace(original, only_one_field=...) must not null the
        other editable fields. Mirrors the SP-UPDATE-FIELDS regression test
        from S2 (commit 902f95c) applied to accounts.
        """
        # Arrange
        conn = _conn(tmp_path)
        ron_id = _seed_ron(conn)
        acc_id = _seed_account(
            conn,
            ron_id,
            inception_date="2024-08-15",
            current_balance=500.00,
            notes="original notes",
        )

        # Act — patch only role_label
        original = get_account(conn, acc_id)
        patched = replace(original, role_label="spending")
        update_account(conn, acc_id, patched)

        # Assert — every other editable field survives
        fetched = get_account(conn, acc_id)
        assert fetched.role_label == "spending"
        assert fetched.inception_date == "2024-08-15"
        assert fetched.current_balance == 500.00
        assert fetched.notes == "original notes"
        conn.close()

    def test_update_account_cannot_change_institution(self, tmp_path):
        # Arrange
        conn = _conn(tmp_path)
        ron_id = _seed_ron(conn)
        acc_id = _seed_account(conn, ron_id, institution="ANZ")

        # Act — caller attempts to mutate institution
        original = get_account(conn, acc_id)
        attempted = replace(original, institution="HYPOTHETICAL_BANK", notes="trying")
        update_account(conn, acc_id, attempted)

        # Assert — institution unchanged; notes did update
        fetched = get_account(conn, acc_id)
        assert fetched.institution == "ANZ"
        assert fetched.notes == "trying"
        conn.close()

    def test_update_account_cannot_change_account_number(self, tmp_path):
        # Arrange
        conn = _conn(tmp_path)
        ron_id = _seed_ron(conn)
        acc_id = _seed_account(conn, ron_id, account_number="178865319")

        # Act — caller attempts to mutate account_number
        original = get_account(conn, acc_id)
        attempted = replace(original, account_number="999999999")
        update_account(conn, acc_id, attempted)

        # Assert
        fetched = get_account(conn, acc_id)
        assert fetched.account_number == "178865319"
        conn.close()

    def test_update_account_cannot_change_bsb(self, tmp_path):
        # Arrange
        conn = _conn(tmp_path)
        ron_id = _seed_ron(conn)
        acc_id = _seed_account(conn, ron_id, bsb="012-345")

        # Act
        original = get_account(conn, acc_id)
        attempted = replace(original, bsb="999-999")
        update_account(conn, acc_id, attempted)

        # Assert
        fetched = get_account(conn, acc_id)
        assert fetched.bsb == "012-345"
        conn.close()


# ---------------------------------------------------------------------------
# TestUpdateRealEstate
# ---------------------------------------------------------------------------


class TestUpdateRealEstate:
    def test_round_trip_updates_fields(self, tmp_path):
        # Arrange
        conn = _conn(tmp_path)
        ron_id = _seed_ron(conn)
        re_id = insert_real_estate(
            conn,
            RealEstate(
                managed_person_id=ron_id,
                address="136 MADELINE ST",
                postcode="2191",
                ownership="sole",
                occupancy="managed_person",
                value=1_200_000.00,
                valuation_date="2026-01-01",
            ),
        )

        # Act
        original = get_real_estate(conn, re_id)
        updated = replace(original, value=1_350_000.00, valuation_date="2026-06-01")
        update_real_estate(conn, re_id, updated)

        # Assert
        fetched = get_real_estate(conn, re_id)
        assert fetched.value == 1_350_000.00
        assert fetched.valuation_date == "2026-06-01"
        conn.close()

    def test_replace_pattern_preserves_unchanged_fields(self, tmp_path):
        # Arrange
        conn = _conn(tmp_path)
        ron_id = _seed_ron(conn)
        re_id = insert_real_estate(
            conn,
            RealEstate(
                managed_person_id=ron_id,
                address="136 MADELINE ST",
                postcode="2191",
                ownership="sole",
                occupancy="managed_person",
                value=1_200_000.00,
                valuation_date="2026-01-01",
            ),
        )

        # Act — patch only value
        original = get_real_estate(conn, re_id)
        patched = replace(original, value=1_500_000.00)
        update_real_estate(conn, re_id, patched)

        # Assert — postcode/ownership/occupancy/valuation_date all preserved
        fetched = get_real_estate(conn, re_id)
        assert fetched.value == 1_500_000.00
        assert fetched.address == "136 MADELINE ST"
        assert fetched.postcode == "2191"
        assert fetched.ownership == "sole"
        assert fetched.occupancy == "managed_person"
        assert fetched.valuation_date == "2026-01-01"
        conn.close()


# ---------------------------------------------------------------------------
# TestUpdateInvestment
# ---------------------------------------------------------------------------


class TestUpdateInvestment:
    def test_round_trip_updates_fields(self, tmp_path):
        # Arrange
        conn = _conn(tmp_path)
        ron_id = _seed_ron(conn)
        inv_id = insert_investment(
            conn,
            Investment(
                managed_person_id=ron_id,
                type="term_deposit",
                description="ANZ 12-month TD",
                ownership="sole",
                units=1.0,
                amount=50_000.00,
                last_review_date="2026-01-01",
            ),
        )

        # Act
        original = get_investment(conn, inv_id)
        updated = replace(original, amount=52_500.00, last_review_date="2026-06-01")
        update_investment(conn, inv_id, updated)

        # Assert
        fetched = get_investment(conn, inv_id)
        assert fetched.amount == 52_500.00
        assert fetched.last_review_date == "2026-06-01"
        conn.close()

    def test_replace_pattern_preserves_unchanged_fields(self, tmp_path):
        # Arrange
        conn = _conn(tmp_path)
        ron_id = _seed_ron(conn)
        inv_id = insert_investment(
            conn,
            Investment(
                managed_person_id=ron_id,
                type="term_deposit",
                description="ANZ 12-month TD",
                ownership="sole",
                units=1.0,
                amount=50_000.00,
                last_review_date="2026-01-01",
            ),
        )

        # Act
        original = get_investment(conn, inv_id)
        patched = replace(original, amount=51_000.00)
        update_investment(conn, inv_id, patched)

        # Assert
        fetched = get_investment(conn, inv_id)
        assert fetched.amount == 51_000.00
        assert fetched.type == "term_deposit"
        assert fetched.description == "ANZ 12-month TD"
        assert fetched.ownership == "sole"
        assert fetched.units == 1.0
        assert fetched.last_review_date == "2026-01-01"
        conn.close()


# ---------------------------------------------------------------------------
# TestUpdateMotorVehicle
# ---------------------------------------------------------------------------


class TestUpdateMotorVehicle:
    def test_round_trip_updates_fields(self, tmp_path):
        # Arrange
        conn = _conn(tmp_path)
        ron_id = _seed_ron(conn)
        mv_id = insert_motor_vehicle(
            conn,
            MotorVehicle(
                managed_person_id=ron_id,
                type="sedan",
                model="Toyota Camry",
                year=2018,
                ownership="sole",
                value=22_000.00,
            ),
        )

        # Act
        original = get_motor_vehicle(conn, mv_id)
        updated = replace(original, value=18_500.00)
        update_motor_vehicle(conn, mv_id, updated)

        # Assert
        fetched = get_motor_vehicle(conn, mv_id)
        assert fetched.value == 18_500.00
        conn.close()

    def test_replace_pattern_preserves_unchanged_fields(self, tmp_path):
        # Arrange
        conn = _conn(tmp_path)
        ron_id = _seed_ron(conn)
        mv_id = insert_motor_vehicle(
            conn,
            MotorVehicle(
                managed_person_id=ron_id,
                type="sedan",
                model="Toyota Camry",
                year=2018,
                ownership="sole",
                value=22_000.00,
            ),
        )

        # Act
        original = get_motor_vehicle(conn, mv_id)
        patched = replace(original, value=20_000.00)
        update_motor_vehicle(conn, mv_id, patched)

        # Assert
        fetched = get_motor_vehicle(conn, mv_id)
        assert fetched.value == 20_000.00
        assert fetched.type == "sedan"
        assert fetched.model == "Toyota Camry"
        assert fetched.year == 2018
        assert fetched.ownership == "sole"
        conn.close()


# ---------------------------------------------------------------------------
# TestUpdateAccommodationBond
# ---------------------------------------------------------------------------


class TestUpdateAccommodationBond:
    def test_round_trip_updates_fields(self, tmp_path):
        # Arrange
        conn = _conn(tmp_path)
        ron_id = _seed_ron(conn)
        bond_id = insert_accommodation_bond(
            conn,
            AccommodationBond(
                managed_person_id=ron_id,
                facility_name="Sunnyside Care",
                facility_address="1 Hope St, Sydney",
                date_of_entry="2025-09-01",
                paid_unpaid="paid",
                amount=350_000.00,
            ),
        )

        # Act
        original = get_accommodation_bond(conn, bond_id)
        updated = replace(original, amount=360_000.00)
        update_accommodation_bond(conn, bond_id, updated)

        # Assert
        fetched = get_accommodation_bond(conn, bond_id)
        assert fetched.amount == 360_000.00
        conn.close()

    def test_replace_pattern_preserves_unchanged_fields(self, tmp_path):
        # Arrange
        conn = _conn(tmp_path)
        ron_id = _seed_ron(conn)
        bond_id = insert_accommodation_bond(
            conn,
            AccommodationBond(
                managed_person_id=ron_id,
                facility_name="Sunnyside Care",
                facility_address="1 Hope St, Sydney",
                date_of_entry="2025-09-01",
                paid_unpaid="paid",
                amount=350_000.00,
            ),
        )

        # Act
        original = get_accommodation_bond(conn, bond_id)
        patched = replace(original, paid_unpaid="unpaid")
        update_accommodation_bond(conn, bond_id, patched)

        # Assert
        fetched = get_accommodation_bond(conn, bond_id)
        assert fetched.paid_unpaid == "unpaid"
        assert fetched.facility_name == "Sunnyside Care"
        assert fetched.facility_address == "1 Hope St, Sydney"
        assert fetched.date_of_entry == "2025-09-01"
        assert fetched.amount == 350_000.00
        conn.close()


# ---------------------------------------------------------------------------
# TestUpdateDebtLiability
# ---------------------------------------------------------------------------


class TestUpdateDebtLiability:
    def test_round_trip_updates_fields(self, tmp_path):
        # Arrange
        conn = _conn(tmp_path)
        ron_id = _seed_ron(conn)
        debt_id = insert_debt_liability(
            conn,
            DebtLiability(
                managed_person_id=ron_id,
                lender="ATO",
                type="tax_debt",
                term="ongoing",
                amount=4_500.00,
            ),
        )

        # Act
        original = get_debt_liability(conn, debt_id)
        updated = replace(original, amount=3_200.00)
        update_debt_liability(conn, debt_id, updated)

        # Assert
        fetched = get_debt_liability(conn, debt_id)
        assert fetched.amount == 3_200.00
        conn.close()

    def test_replace_pattern_preserves_unchanged_fields(self, tmp_path):
        # Arrange
        conn = _conn(tmp_path)
        ron_id = _seed_ron(conn)
        debt_id = insert_debt_liability(
            conn,
            DebtLiability(
                managed_person_id=ron_id,
                lender="ATO",
                type="tax_debt",
                term="ongoing",
                amount=4_500.00,
            ),
        )

        # Act
        original = get_debt_liability(conn, debt_id)
        patched = replace(original, amount=4_000.00)
        update_debt_liability(conn, debt_id, patched)

        # Assert
        fetched = get_debt_liability(conn, debt_id)
        assert fetched.amount == 4_000.00
        assert fetched.lender == "ATO"
        assert fetched.type == "tax_debt"
        assert fetched.term == "ongoing"
        conn.close()


# ---------------------------------------------------------------------------
# TestGetByIdReturnsNoneForMissing  (6 — one per class)
# ---------------------------------------------------------------------------


class TestGetByIdReturnsNoneForMissing:
    def test_get_account_returns_none_for_missing(self, tmp_path):
        conn = _conn(tmp_path)
        _seed_ron(conn)
        assert get_account(conn, 999) is None
        conn.close()

    def test_get_real_estate_returns_none_for_missing(self, tmp_path):
        conn = _conn(tmp_path)
        _seed_ron(conn)
        assert get_real_estate(conn, 999) is None
        conn.close()

    def test_get_investment_returns_none_for_missing(self, tmp_path):
        conn = _conn(tmp_path)
        _seed_ron(conn)
        assert get_investment(conn, 999) is None
        conn.close()

    def test_get_motor_vehicle_returns_none_for_missing(self, tmp_path):
        conn = _conn(tmp_path)
        _seed_ron(conn)
        assert get_motor_vehicle(conn, 999) is None
        conn.close()

    def test_get_accommodation_bond_returns_none_for_missing(self, tmp_path):
        conn = _conn(tmp_path)
        _seed_ron(conn)
        assert get_accommodation_bond(conn, 999) is None
        conn.close()

    def test_get_debt_liability_returns_none_for_missing(self, tmp_path):
        conn = _conn(tmp_path)
        _seed_ron(conn)
        assert get_debt_liability(conn, 999) is None
        conn.close()


# ---------------------------------------------------------------------------
# TestUpdateNoOpAndCrossCutting
# ---------------------------------------------------------------------------


class TestUpdateNoOpAndCrossCutting:
    def test_update_account_with_unchanged_dto_is_safe(self, tmp_path):
        """An update with the same values as the current row must not crash."""
        # Arrange
        conn = _conn(tmp_path)
        ron_id = _seed_ron(conn)
        acc_id = _seed_account(conn, ron_id)

        # Act
        original = get_account(conn, acc_id)
        update_account(conn, acc_id, original)

        # Assert — row still exists, role_label preserved
        fetched = get_account(conn, acc_id)
        assert fetched.role_label == original.role_label
        assert fetched.current_balance == original.current_balance
        conn.close()

    def test_update_account_appears_in_list_accounts(self, tmp_path):
        """End-to-end: update_account → list_accounts shows the updated value."""
        # Arrange
        conn = _conn(tmp_path)
        ron_id = _seed_ron(conn)
        acc_id = _seed_account(conn, ron_id, role_label="living", notes="before")

        # Act
        original = get_account(conn, acc_id)
        update_account(conn, acc_id, replace(original, notes="after"))

        # Assert
        accounts = list_accounts(conn, ron_id)
        assert len(accounts) == 1
        assert accounts[0].notes == "after"
        conn.close()

    def test_update_real_estate_bumps_updated_at(self, tmp_path):
        """Proves the _update timestamp behavior propagates to S3 helpers."""
        # Arrange
        conn = _conn(tmp_path)
        ron_id = _seed_ron(conn)
        re_id = insert_real_estate(
            conn,
            RealEstate(managed_person_id=ron_id, address="1 Test St"),
        )
        before = conn.execute(
            "SELECT updated_at FROM real_estate WHERE id = ?", (re_id,)
        ).fetchone()["updated_at"]
        time.sleep(1.0)  # SQLite datetime('now') resolution is 1 second

        # Act
        original = get_real_estate(conn, re_id)
        update_real_estate(conn, re_id, replace(original, postcode="2000"))

        # Assert
        after = conn.execute(
            "SELECT updated_at FROM real_estate WHERE id = ?", (re_id,)
        ).fetchone()["updated_at"]
        assert after > before
        conn.close()
