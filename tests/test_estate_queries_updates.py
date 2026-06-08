"""Update-path tests for queries_estate.py — S2 acceptance gate.

Covers: update_managed_person, update_private_manager,
update_significant_person, get_significant_person,
bootstrap_managed_person_if_empty.

AAA structure throughout; _conn(tmp_path) fixture mirrors test_estate_queries.py.
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
    bootstrap_managed_person_if_empty,
    get_managed_person,
    get_significant_person,
    insert_managed_person,
    insert_private_manager,
    insert_significant_person,
    list_private_managers,
    list_significant_people,
    update_managed_person,
    update_private_manager,
    update_significant_person,
)
from src.models.estate import ManagedPerson, PrivateManager, SignificantPerson


def _conn(tmp_path):
    conn = get_connection(tmp_path / "test.db")
    init_db(conn)
    return conn


def _seed_ron(conn) -> int:
    return insert_managed_person(
        conn, ManagedPerson(surname="GENTILI", given_names="Renato")
    )


# ---------------------------------------------------------------------------
# TestUpdateManagedPerson
# ---------------------------------------------------------------------------


class TestUpdateManagedPerson:
    def test_round_trip_updates_fields(self, tmp_path):
        # Arrange
        conn = _conn(tmp_path)
        mp_id = _seed_ron(conn)

        # Act
        updated = ManagedPerson(
            surname="GENTILI",
            given_names="Renato",
            address_line1="136 MADELINE ST",
            postcode="2191",
            has_will="yes",
        )
        update_managed_person(conn, mp_id, updated)

        # Assert
        fetched = get_managed_person(conn, mp_id)
        assert fetched.address_line1 == "136 MADELINE ST"
        assert fetched.postcode == "2191"
        assert fetched.has_will == "yes"
        conn.close()

    def test_interpreter_bool_stored_as_int(self, tmp_path):
        # Arrange
        conn = _conn(tmp_path)
        mp_id = _seed_ron(conn)

        # Act — set interpreter_required=True
        updated = ManagedPerson(
            surname="GENTILI",
            given_names="Renato",
            interpreter_required=True,
            interpreter_language="Italian",
        )
        update_managed_person(conn, mp_id, updated)

        # Assert — raw DB value is 1, DTO coerces back
        raw = conn.execute(
            "SELECT interpreter_required FROM managed_persons WHERE id = ?", (mp_id,)
        ).fetchone()
        assert raw["interpreter_required"] == 1
        fetched = get_managed_person(conn, mp_id)
        assert fetched.interpreter_language == "Italian"
        conn.close()

    def test_updated_at_advances(self, tmp_path):
        # Arrange
        conn = _conn(tmp_path)
        mp_id = _seed_ron(conn)
        before_ts = conn.execute(
            "SELECT updated_at FROM managed_persons WHERE id = ?", (mp_id,)
        ).fetchone()["updated_at"]

        # Act — small sleep so datetime('now') differs
        time.sleep(1)
        update_managed_person(
            conn, mp_id, ManagedPerson(surname="GENTILI", given_names="Renato")
        )

        # Assert
        after_ts = conn.execute(
            "SELECT updated_at FROM managed_persons WHERE id = ?", (mp_id,)
        ).fetchone()["updated_at"]
        assert after_ts > before_ts
        conn.close()

    def test_none_id_row_is_rejected_gracefully(self, tmp_path):
        # Arrange
        conn = _conn(tmp_path)
        ron_id = _seed_ron(conn)

        # Act + Assert — id=999 doesn't exist; no row modified but no crash either
        update_managed_person(
            conn,
            999,
            ManagedPerson(surname="GHOST", given_names="Nobody"),
        )
        # The original Ron row is untouched
        fetched = get_managed_person(conn, ron_id)
        assert fetched.surname == "GENTILI"
        conn.close()


# ---------------------------------------------------------------------------
# TestUpdatePrivateManager
# ---------------------------------------------------------------------------


class TestUpdatePrivateManager:
    def test_round_trip_updates_fields(self, tmp_path):
        # Arrange
        conn = _conn(tmp_path)
        ron_id = _seed_ron(conn)
        pm_id = insert_private_manager(
            conn,
            PrivateManager(
                managed_person_id=ron_id,
                surname="TRAVIA",
                given_name="Linda",
            ),
        )

        # Act
        updated = PrivateManager(
            managed_person_id=ron_id,
            surname="TRAVIA",
            given_name="Linda Jane",
            mobile="0400 000 000",
            appointment_type="sole",
        )
        update_private_manager(conn, pm_id, updated)

        # Assert
        results = list_private_managers(conn, ron_id)
        assert results[0].given_name == "Linda Jane"
        assert results[0].mobile == "0400 000 000"
        assert results[0].appointment_type == "sole"
        conn.close()


# ---------------------------------------------------------------------------
# TestUpdateSignificantPerson
# ---------------------------------------------------------------------------


class TestUpdateSignificantPerson:
    def test_round_trip_updates_fields(self, tmp_path):
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
            ),
        )

        # Act — update mobile and notes
        updated = SignificantPerson(
            managed_person_id=ron_id,
            surname="GENTILI",
            given_name="Sebastian",
            relationship="Son",
            mobile="0411 111 111",
            notes="Confirmed to consult on large purchases",
        )
        update_significant_person(conn, sp_id, updated)

        # Assert
        fetched = get_significant_person(conn, sp_id)
        assert fetched is not None
        assert fetched.mobile == "0411 111 111"
        assert fetched.notes == "Confirmed to consult on large purchases"
        conn.close()

    def test_soft_delete_via_status(self, tmp_path):
        # Arrange
        conn = _conn(tmp_path)
        ron_id = _seed_ron(conn)
        sp_id = insert_significant_person(
            conn,
            SignificantPerson(
                managed_person_id=ron_id,
                surname="GHOST",
                given_name="Old",
                consultation_status="active",
            ),
        )

        # Act — mark deceased (soft delete)
        deceased = SignificantPerson(
            managed_person_id=ron_id,
            surname="GHOST",
            given_name="Old",
            consultation_status="deceased",
        )
        update_significant_person(conn, sp_id, deceased)

        # Assert — not in default list, present when include_deceased=True
        active_list = list_significant_people(conn, ron_id)
        assert sp_id not in {sp.id for sp in active_list}
        all_list = list_significant_people(conn, ron_id, include_deceased=True)
        assert sp_id in {sp.id for sp in all_list}
        conn.close()

    def test_get_significant_person_returns_none_for_missing_id(self, tmp_path):
        # Arrange
        conn = _conn(tmp_path)
        _seed_ron(conn)

        # Act + Assert
        result = get_significant_person(conn, 999)
        assert result is None
        conn.close()

    def test_replace_pattern_preserves_hidden_address_fields(self, tmp_path):
        """Regression: SP-UPDATE-FIELDS — the data_editor only exposes a subset
        of columns, so the view must use `dataclasses.replace(original, ...)`
        to patch visible fields without nulling address_line1, address_line2,
        postcode, and home_phone. This mirrors what the Identity view does on
        Save Changes (src/views/identity.py:_render_significant_people_tab).
        """
        # Arrange
        conn = _conn(tmp_path)
        ron_id = _seed_ron(conn)
        sp_id = insert_significant_person(
            conn,
            SignificantPerson(
                managed_person_id=ron_id,
                given_name="Anna",
                surname="DELUCA",
                address_line1="42 Some Street",
                address_line2="Unit 7",
                postcode="2204",
                home_phone="02 9999 0000",
                mobile="0400 000 000",
            ),
        )
        original = get_significant_person(conn, sp_id)
        assert original is not None

        # Act — patch ONLY a visible column (mobile), like the data_editor does
        patched = replace(original, mobile="0411 111 111")
        update_significant_person(conn, sp_id, patched)

        # Assert — hidden address columns survive the round-trip
        refetched = get_significant_person(conn, sp_id)
        assert refetched.mobile == "0411 111 111"
        assert refetched.address_line1 == "42 Some Street"
        assert refetched.address_line2 == "Unit 7"
        assert refetched.postcode == "2204"
        assert refetched.home_phone == "02 9999 0000"
        conn.close()


# ---------------------------------------------------------------------------
# TestBootstrapManagedPersonIfEmpty
# ---------------------------------------------------------------------------


class TestBootstrapManagedPersonIfEmpty:
    def test_inserts_when_table_empty(self, tmp_path):
        # Arrange
        conn = _conn(tmp_path)

        # Act
        mp_id = bootstrap_managed_person_if_empty(conn, "GENTILI", "Renato")

        # Assert
        assert mp_id == 1
        fetched = get_managed_person(conn, mp_id)
        assert fetched.surname == "GENTILI"
        assert fetched.given_names == "Renato"
        conn.close()

    def test_returns_existing_id_when_row_present(self, tmp_path):
        # Arrange
        conn = _conn(tmp_path)
        existing_id = insert_managed_person(
            conn, ManagedPerson(surname="EXISTING", given_names="Person")
        )

        # Act — try to bootstrap with different name
        returned_id = bootstrap_managed_person_if_empty(conn, "GENTILI", "Renato")

        # Assert — returns the existing row, no new row inserted
        assert returned_id == existing_id
        all_persons = conn.execute(
            "SELECT COUNT(*) AS cnt FROM managed_persons"
        ).fetchone()["cnt"]
        assert all_persons == 1
        conn.close()
