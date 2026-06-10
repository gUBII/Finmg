"""Tests for src/services/one_off.py — Section E candidate detection + triage."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.db.database import get_connection, init_db
from src.db.queries_compliance import list_audit
from src.db.queries_estate import insert_managed_person
from src.db.queries_forecast import list_one_off_events
from src.models.estate import ManagedPerson
from src.models.forecast import OneOffEvent
from src.services.one_off import (
    confirm_candidate,
    detect_candidates,
    dismiss_candidate,
    record_one_off_event,
)


def _insert_txn(conn, date, description, withdrawal=None, deposit=None,
                category="Miscellaneous", internal=0) -> int:
    cur = conn.execute(
        "INSERT INTO transactions "
        "(date, description, withdrawal, deposit, account_number, account_type, "
        " category, month, is_internal_transfer) "
        "VALUES (?, ?, ?, ?, '178865319', 'Spending', ?, ?, ?)",
        (date, description, withdrawal, deposit, category, date[:7], internal),
    )
    conn.commit()
    return cur.lastrowid


def _setup(tmp_path):
    conn = get_connection(tmp_path / "test.db")
    init_db(conn)
    rid = insert_managed_person(
        conn, ManagedPerson(surname="GENTILI", given_names="Renato")
    )
    return conn, rid


def test_detect_thresholds_directions_and_exclusions(tmp_path):
    conn, _rid = _setup(tmp_path)
    big_out = _insert_txn(conn, "2026-03-01", "ACCOM BOND PART", withdrawal=2500.0)
    big_in = _insert_txn(conn, "2026-03-05", "INSURANCE PAYOUT", deposit=1500.0)
    _insert_txn(conn, "2026-03-07", "GROCERIES", withdrawal=80.0)            # below
    _insert_txn(conn, "2026-03-09", "PENSION", deposit=1100.0,
                category="Disability Support Pension")                       # recurring
    _insert_txn(conn, "2026-03-11", "XFER TO SAVINGS", withdrawal=3000.0,
                internal=1)                                                  # internal

    cands = detect_candidates(conn, threshold=1000.0)
    by_id = {c.transaction_id: c for c in cands}
    assert set(by_id) == {big_out, big_in}
    assert by_id[big_out].direction == "expenditure"
    assert by_id[big_out].amount == 2500.0
    assert by_id[big_in].direction == "receipt"


def test_confirm_inserts_event_and_hides_candidate(tmp_path):
    conn, rid = _setup(tmp_path)
    _insert_txn(conn, "2026-03-01", "ACCOM BOND PART", withdrawal=2500.0)
    cand = detect_candidates(conn)[0]

    event = confirm_candidate(conn, rid, cand, recorded_by="Linda")
    assert event.id is not None
    assert event.status == "completed"
    assert event.linked_transaction_id == cand.transaction_id

    assert detect_candidates(conn) == []  # linked → no longer a candidate
    stored = list_one_off_events(conn, rid)
    assert len(stored) == 1 and stored[0].event_type == "expenditure"
    audits = list_audit(conn, "one_off_events")
    assert len(audits) == 1 and audits[0].row_id == event.id


def test_dismiss_hides_candidate_and_audits(tmp_path):
    conn, rid = _setup(tmp_path)
    tid = _insert_txn(conn, "2026-03-01", "BIG SHOP", withdrawal=1200.0)
    dismiss_candidate(conn, tid, reason="bulk grocery run, not a one-off",
                      recorded_by="Linda")
    assert detect_candidates(conn) == []
    assert list_one_off_events(conn, rid) == []
    audits = list_audit(conn, "one_off_dismissals")
    assert len(audits) == 1
    assert "bulk grocery" in audits[0].after_json


def test_record_manual_event_validates_and_audits(tmp_path):
    conn, rid = _setup(tmp_path)
    eid = record_one_off_event(
        conn,
        OneOffEvent(
            managed_person_id=rid,
            event_type="expenditure",
            event_description="Anticipated dental surgery",
            status="anticipated",
            amount=4500.0,
        ),
        recorded_by="Linda",
    )
    assert eid is not None
    events = list_one_off_events(conn, rid, status="anticipated")
    assert len(events) == 1

    with pytest.raises(ValueError):
        record_one_off_event(
            conn,
            OneOffEvent(managed_person_id=rid, event_type="receipt",
                        event_description="   ", status="anticipated"),
        )
    with pytest.raises(ValueError):
        record_one_off_event(
            conn,
            OneOffEvent(managed_person_id=rid, event_type="receipt",
                        event_description="Refund", status="anticipated",
                        amount=-5.0),
        )
