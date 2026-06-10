"""Tests for src/services/gifts.py — recording actuals against planned gifts."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.db.database import get_connection, init_db
from src.db.queries_compliance import insert_gift, list_audit, list_gifts
from src.db.queries_estate import insert_managed_person
from src.models.compliance import Gift
from src.models.estate import ManagedPerson
from src.services.gifts import record_gift_actual


def _setup(tmp_path):
    conn = get_connection(tmp_path / "test.db")
    init_db(conn)
    rid = insert_managed_person(
        conn, ManagedPerson(surname="GENTILI", given_names="Renato")
    )
    gid = insert_gift(
        conn,
        Gift(
            managed_person_id=rid,
            occasion="christmas",
            occasion_date="2026-12-25",
            planned_amount=100.0,
            section_76_assessment="compliant",
        ),
    )
    return conn, rid, gid


def test_record_actual_updates_row_and_audits(tmp_path):
    conn, rid, gid = _setup(tmp_path)
    updated = record_gift_actual(conn, gid, 85.0, recorded_by="Linda")
    assert updated.actual_amount == 85.0
    assert updated.planned_amount == 100.0
    stored = list_gifts(conn, rid)[0]
    assert stored.actual_amount == 85.0
    # Assessment untouched — the compliance engine owns it.
    assert stored.section_76_assessment == "compliant"
    audits = list_audit(conn, "gifts")
    assert len(audits) == 1
    assert audits[0].action == "update"
    assert audits[0].row_id == gid
    assert "85.0" in audits[0].after_json


def test_record_actual_rejects_bad_input(tmp_path):
    conn, _rid, gid = _setup(tmp_path)
    with pytest.raises(ValueError):
        record_gift_actual(conn, gid, -5.0)
    with pytest.raises(ValueError):
        record_gift_actual(conn, 99999, 10.0)
    # Nothing written on failure.
    assert list_audit(conn, "gifts") == []
