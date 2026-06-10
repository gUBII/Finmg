"""Tests for src/services/consultations.py — audited consultation logging."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.db.database import get_connection, init_db
from src.db.queries_compliance import list_audit, list_consultations
from src.db.queries_estate import insert_managed_person, insert_significant_person
from src.models.compliance import ConsultationLogEntry
from src.models.estate import ManagedPerson, SignificantPerson
from src.services.consultations import record_consultation


def _setup(tmp_path):
    conn = get_connection(tmp_path / "test.db")
    init_db(conn)
    rid = insert_managed_person(
        conn, ManagedPerson(surname="GENTILI", given_names="Renato")
    )
    sid = insert_significant_person(
        conn,
        SignificantPerson(managed_person_id=rid, surname="GENTILI",
                          given_name="Sebastian", relationship="Son"),
    )
    return conn, rid, sid


def test_record_consultation_persists_and_audits(tmp_path):
    conn, rid, sid = _setup(tmp_path)
    cid = record_consultation(
        conn,
        ConsultationLogEntry(
            managed_person_id=rid,
            date="2026-06-01",
            consulted_person_id=sid,
            decision_topic="Accommodation bond top-up",
            summary="Sebastian agrees the bond increase is in Ron's interest.",
        ),
        recorded_by="Linda",
    )
    entries = list_consultations(conn, rid)
    assert len(entries) == 1 and entries[0].id == cid
    assert entries[0].consulted_person_id == sid
    audits = list_audit(conn, "consultation_log")
    assert len(audits) == 1 and audits[0].row_id == cid
    assert "Accommodation bond" in audits[0].after_json


def test_record_consultation_validates(tmp_path):
    conn, rid, _sid = _setup(tmp_path)
    with pytest.raises(ValueError):
        record_consultation(
            conn,
            ConsultationLogEntry(managed_person_id=rid, date="2026-06-01",
                                 decision_topic="  "),
        )
    with pytest.raises(ValueError):
        record_consultation(
            conn,
            ConsultationLogEntry(managed_person_id=rid, date="",
                                 decision_topic="Bond"),
        )
    assert list_audit(conn, "consultation_log") == []
