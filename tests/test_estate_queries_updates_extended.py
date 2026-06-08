"""Extended edge-case and integration tests for queries_estate.py — S2 gates.

Covers concurrent update resilience, disability_flags round-trip,
nullable-field edge cases, multi-row get scenarios, and bootstrap idempotency.

AAA structure throughout; _conn(tmp_path) fixture mirrors test_estate_queries.py.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.db.database import get_connection, init_db
from src.db.queries_estate import (
    bootstrap_managed_person_if_empty,
    get_managed_person,
    get_significant_person,
    insert_managed_person,
    insert_significant_person,
    list_significant_people,
    update_managed_person,
    update_significant_person,
)
from src.models.estate import ManagedPerson, SignificantPerson


def _conn(tmp_path):
    conn = get_connection(tmp_path / "test.db")
    init_db(conn)
    return conn


def _seed_ron(conn) -> int:
    return insert_managed_person(
        conn, ManagedPerson(surname="GENTILI", given_names="Renato")
    )


# ---------------------------------------------------------------------------
# Concurrent Update Resilience
# ---------------------------------------------------------------------------


class TestConcurrentUpdateResilience:
    def test_sequential_updates_last_write_wins(self, tmp_path):
        """Simulate concurrent updates via sequential writes; verify last write wins."""
        # Arrange
        conn = _conn(tmp_path)
        mp_id = _seed_ron(conn)

        # Act — first update sets address
        first_update = ManagedPerson(
            surname="GENTILI",
            given_names="Renato",
            address_line1="136 MADELINE ST",
            postcode="2191",
        )
        update_managed_person(conn, mp_id, first_update)

        # Act — second update overwrites address, adds phone
        second_update = ManagedPerson(
            surname="GENTILI",
            given_names="Renato",
            address_line1="250 PITT ST",
            postcode="2000",
            phone="02 9999 9999",
        )
        update_managed_person(conn, mp_id, second_update)

        # Assert — last write wins; address is from second update, phone is set
        fetched = get_managed_person(conn, mp_id)
        assert fetched.address_line1 == "250 PITT ST"
        assert fetched.postcode == "2000"
        assert fetched.phone == "02 9999 9999"
        conn.close()

    def test_multiple_updates_with_full_object_replace(self, tmp_path):
        """Verify sequential updates that replace the full object."""
        # Arrange
        conn = _conn(tmp_path)
        mp_id = _seed_ron(conn)

        # Act — set initial data (address + dob + phone)
        first = ManagedPerson(
            surname="GENTILI",
            given_names="Renato",
            address_line1="136 MADELINE ST",
            dob="1960-01-01",
            phone="02 1111 1111",
        )
        update_managed_person(conn, mp_id, first)

        # Act — update phone with full object (must include all fields to preserve them)
        second = ManagedPerson(
            surname="GENTILI",
            given_names="Renato",
            address_line1="136 MADELINE ST",  # Must re-include to preserve
            dob="1960-01-01",  # Must re-include to preserve
            phone="02 9999 9999",  # Updated value
        )
        update_managed_person(conn, mp_id, second)

        # Assert — address, dob, and updated phone are all present
        fetched = get_managed_person(conn, mp_id)
        assert fetched.address_line1 == "136 MADELINE ST"
        assert fetched.dob == "1960-01-01"
        assert fetched.phone == "02 9999 9999"
        conn.close()


# ---------------------------------------------------------------------------
# disability_flags Round-Trip (JSON String Serialization)
# ---------------------------------------------------------------------------


class TestDisabilityFlagsRoundTrip:
    def test_disability_flags_json_array_survives_update(self, tmp_path):
        """Verify disability_flags JSON array round-trips through update cycle."""
        # Arrange
        conn = _conn(tmp_path)
        mp_id = _seed_ron(conn)
        json_flags = '["physical_disability","brain_injury","hearing_loss"]'

        # Act — set complex JSON array
        with_flags = ManagedPerson(
            surname="GENTILI",
            given_names="Renato",
            disability_flags=json_flags,
        )
        update_managed_person(conn, mp_id, with_flags)

        # Assert — JSON string is preserved bit-for-bit
        fetched = get_managed_person(conn, mp_id)
        assert fetched.disability_flags == json_flags
        conn.close()

    def test_disability_flags_empty_array_preserved(self, tmp_path):
        """Verify empty JSON array doesn't corrupt on round-trip."""
        # Arrange
        conn = _conn(tmp_path)
        mp_id = _seed_ron(conn)

        # Act — set empty JSON array
        empty_flags = ManagedPerson(
            surname="GENTILI",
            given_names="Renato",
            disability_flags="[]",
        )
        update_managed_person(conn, mp_id, empty_flags)

        # Assert — empty array preserved
        fetched = get_managed_person(conn, mp_id)
        assert fetched.disability_flags == "[]"
        conn.close()

    def test_disability_flags_null_to_populated_to_null(self, tmp_path):
        """Verify disability_flags can be set, updated, and cleared."""
        # Arrange
        conn = _conn(tmp_path)
        mp_id = _seed_ron(conn)

        # Act — set flags
        with_flags = ManagedPerson(
            surname="GENTILI",
            given_names="Renato",
            disability_flags='["physical"]',
        )
        update_managed_person(conn, mp_id, with_flags)
        assert get_managed_person(conn, mp_id).disability_flags == '["physical"]'

        # Act — clear flags (set to None)
        cleared = ManagedPerson(
            surname="GENTILI",
            given_names="Renato",
            disability_flags=None,
        )
        update_managed_person(conn, mp_id, cleared)

        # Assert — flags are now None
        fetched = get_managed_person(conn, mp_id)
        assert fetched.disability_flags is None
        conn.close()


# ---------------------------------------------------------------------------
# Nullable Fields Edge Cases
# ---------------------------------------------------------------------------


class TestUpdateSignificantPersonNullableFields:
    def test_significant_person_clear_all_nullable_fields(self, tmp_path):
        """Verify update_significant_person can clear all optional fields."""
        # Arrange
        conn = _conn(tmp_path)
        ron_id = _seed_ron(conn)
        sp_id = insert_significant_person(
            conn,
            SignificantPerson(
                managed_person_id=ron_id,
                surname="GENTILI",
                given_name="Sebastian",
                relationship="Son",
                address_line1="10 TEST STREET",
                address_line2="SUITE 2",
                postcode="2191",
                home_phone="02 9999 9999",
                mobile="0411 111 111",
                email="sebastian@example.com",
                notes="Original notes",
            ),
        )

        # Act — update to clear all optional fields except required (surname, given_name)
        cleared = SignificantPerson(
            managed_person_id=ron_id,
            surname="GENTILI",
            given_name="Sebastian",
            relationship=None,
            address_line1=None,
            address_line2=None,
            postcode=None,
            home_phone=None,
            mobile=None,
            email=None,
            notes=None,
        )
        update_significant_person(conn, sp_id, cleared)

        # Assert — all optional fields are None
        fetched = get_significant_person(conn, sp_id)
        assert fetched is not None
        assert fetched.surname == "GENTILI"
        assert fetched.given_name == "Sebastian"
        assert fetched.relationship is None
        assert fetched.address_line1 is None
        assert fetched.address_line2 is None
        assert fetched.postcode is None
        assert fetched.home_phone is None
        assert fetched.mobile is None
        assert fetched.email is None
        assert fetched.notes is None
        conn.close()

    def test_significant_person_mixed_null_and_populated_update(self, tmp_path):
        """Verify selective field nullification."""
        # Arrange
        conn = _conn(tmp_path)
        ron_id = _seed_ron(conn)
        sp_id = insert_significant_person(
            conn,
            SignificantPerson(
                managed_person_id=ron_id,
                surname="GENTILI",
                given_name="Sebastian",
                relationship="Son",
                mobile="0411 111 111",
                email="sebastian@example.com",
            ),
        )

        # Act — clear mobile but keep email
        partial_clear = SignificantPerson(
            managed_person_id=ron_id,
            surname="GENTILI",
            given_name="Sebastian",
            relationship="Son",
            mobile=None,
            email="sebastian@example.com",
        )
        update_significant_person(conn, sp_id, partial_clear)

        # Assert — mobile is None, email persists
        fetched = get_significant_person(conn, sp_id)
        assert fetched.mobile is None
        assert fetched.email == "sebastian@example.com"
        conn.close()


# ---------------------------------------------------------------------------
# Multi-Row get_significant_person Correctness
# ---------------------------------------------------------------------------


class TestGetSignificantPersonMultipleRows:
    def test_get_significant_person_with_multiple_people_in_table(self, tmp_path):
        """Verify get_significant_person returns the correct row when multiple exist."""
        # Arrange
        conn = _conn(tmp_path)
        ron_id = _seed_ron(conn)

        # Act — insert three significant people
        sp1_id = insert_significant_person(
            conn,
            SignificantPerson(
                managed_person_id=ron_id,
                surname="GENTILI",
                given_name="Sebastian",
                relationship="Son",
                mobile="0411 111 111",
            ),
        )
        sp2_id = insert_significant_person(
            conn,
            SignificantPerson(
                managed_person_id=ron_id,
                surname="GENTILI",
                given_name="Daniela",
                relationship="Daughter",
                mobile="0422 222 222",
            ),
        )
        sp3_id = insert_significant_person(
            conn,
            SignificantPerson(
                managed_person_id=ron_id,
                surname="TRAVIA",
                given_name="Linda",
                relationship="Spouse",
                mobile="0433 333 333",
            ),
        )

        # Assert — each get returns the correct row
        fetched1 = get_significant_person(conn, sp1_id)
        assert fetched1.id == sp1_id
        assert fetched1.given_name == "Sebastian"
        assert fetched1.mobile == "0411 111 111"

        fetched2 = get_significant_person(conn, sp2_id)
        assert fetched2.id == sp2_id
        assert fetched2.given_name == "Daniela"
        assert fetched2.mobile == "0422 222 222"

        fetched3 = get_significant_person(conn, sp3_id)
        assert fetched3.id == sp3_id
        assert fetched3.given_name == "Linda"
        assert fetched3.mobile == "0433 333 333"
        conn.close()

    def test_get_significant_person_after_update_multirow_table(self, tmp_path):
        """Verify get_significant_person still works correctly after updating one row in a multi-row table."""
        # Arrange
        conn = _conn(tmp_path)
        ron_id = _seed_ron(conn)

        sp1_id = insert_significant_person(
            conn,
            SignificantPerson(
                managed_person_id=ron_id,
                surname="GENTILI",
                given_name="Sebastian",
                relationship="Son",
            ),
        )
        sp2_id = insert_significant_person(
            conn,
            SignificantPerson(
                managed_person_id=ron_id,
                surname="GENTILI",
                given_name="Daniela",
                relationship="Daughter",
            ),
        )

        # Act — update sp1
        updated = SignificantPerson(
            managed_person_id=ron_id,
            surname="GENTILI",
            given_name="Sebastian",
            relationship="Son",
            mobile="0411 999 999",
        )
        update_significant_person(conn, sp1_id, updated)

        # Assert — get sp1 and sp2; sp1 has new mobile, sp2 unchanged
        fetched1 = get_significant_person(conn, sp1_id)
        assert fetched1.mobile == "0411 999 999"

        fetched2 = get_significant_person(conn, sp2_id)
        assert fetched2.mobile is None
        conn.close()


# ---------------------------------------------------------------------------
# bootstrap_managed_person_if_empty Idempotency
# ---------------------------------------------------------------------------


class TestBootstrapManagedPersonIdempotency:
    def test_bootstrap_with_two_existing_rows_returns_first_by_id(self, tmp_path):
        """Verify bootstrap returns the first row by id when two rows exist."""
        # Arrange
        conn = _conn(tmp_path)

        # Act — insert two rows
        first_id = insert_managed_person(
            conn, ManagedPerson(surname="FIRST", given_names="Person")
        )
        second_id = insert_managed_person(
            conn, ManagedPerson(surname="SECOND", given_names="Person")
        )

        # Act — bootstrap with different name
        returned_id = bootstrap_managed_person_if_empty(conn, "GENTILI", "Renato")

        # Assert — returns the first row (id=1), not the second
        assert returned_id == first_id
        assert returned_id < second_id
        fetched = get_managed_person(conn, returned_id)
        assert fetched.surname == "FIRST"
        # No new row inserted
        all_count = conn.execute(
            "SELECT COUNT(*) AS cnt FROM managed_persons"
        ).fetchone()["cnt"]
        assert all_count == 2
        conn.close()

    def test_bootstrap_idempotent_across_multiple_calls(self, tmp_path):
        """Verify bootstrap always returns the same id on repeated calls."""
        # Arrange
        conn = _conn(tmp_path)

        # Act — call bootstrap three times
        id1 = bootstrap_managed_person_if_empty(conn, "FIRST", "Call")
        id2 = bootstrap_managed_person_if_empty(conn, "SECOND", "Call")
        id3 = bootstrap_managed_person_if_empty(conn, "THIRD", "Call")

        # Assert — all return the same id
        assert id1 == id2 == id3
        # Only one row in table
        count = conn.execute(
            "SELECT COUNT(*) AS cnt FROM managed_persons"
        ).fetchone()["cnt"]
        assert count == 1
        conn.close()
