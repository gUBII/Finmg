"""Tests for the Change-in-Estate workflow (S8): registry, recording, lifecycle."""

from __future__ import annotations

import json
import sys
from dataclasses import replace
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.db.database import get_connection, init_db
from src.db.queries_compliance import (
    get_estate_change_detail,
    list_audit,
    update_estate_change_detail,
)
from src.db.queries_estate import insert_managed_person
from src.models.estate import ManagedPerson
from src.services.estate_changes import (
    list_changes,
    load_appendix_a,
    record_change,
    update_change_status,
)

HANDBOOK_TRIGGER_COUNT = 12  # handbook §14 / Appendix 2 list
SUBSECTION_LETTERS = [chr(c) for c in range(ord("A"), ord("R") + 1)]


@pytest.fixture
def conn(tmp_path):
    conn = get_connection(tmp_path / "test.db")
    init_db(conn)
    yield conn
    conn.close()


@pytest.fixture
def mp_id(conn):
    return insert_managed_person(
        conn, ManagedPerson(surname="GENTILI", given_names="Renato")
    )


# ---------------------------------------------------------------- registry

def test_registry_has_all_18_subsections():
    registry = load_appendix_a()
    assert sorted(registry.keys()) == SUBSECTION_LETTERS


def test_registry_entries_are_complete():
    for letter, entry in load_appendix_a().items():
        assert entry["title"].strip(), f"§{letter} missing title"
        assert entry["summary"].strip(), f"§{letter} missing summary"
        assert isinstance(entry["required_attachments"], list), f"§{letter} attachments"
        assert entry["notes"].strip(), f"§{letter} missing notes"


def test_registry_covers_the_12_handbook_triggers():
    triggers = [
        e["handbook_trigger"]
        for e in load_appendix_a().values()
        if e["handbook_trigger"]
    ]
    assert len(triggers) == HANDBOOK_TRIGGER_COUNT
    assert len(set(triggers)) == HANDBOOK_TRIGGER_COUNT  # no duplicates


def test_past_gratuitous_care_requires_all_ten_documents():
    assert len(load_appendix_a()["I"]["required_attachments"]) == 10


# ------------------------------------------------------------ record_change

def test_record_change_creates_submission_detail_and_audit(conn, mp_id):
    change = record_change(
        conn,
        mp_id,
        "M",
        "Sell the unit at 1 Example St",
        amount=450_000.0,
        affordability_confirmed=True,
        views=[{"name": "Linda", "relationship": "sister", "view": "support"}],
        recorded_by="Linda",
    )
    sub = change.submission
    assert sub.type == "change_in_estate"
    assert sub.trigger_subsection == "M"
    assert sub.status == "draft"

    detail = get_estate_change_detail(conn, sub.id)
    assert detail.description == "Sell the unit at 1 Example St"
    assert detail.amount == 450_000.0
    assert detail.affordability_confirmed is True
    assert json.loads(detail.views_json)[0]["view"] == "support"

    audits = list_audit(conn, table_name="submissions")
    assert any("Appendix A §M" in (a.reason or "") for a in audits)


def test_record_change_rejects_bad_input(conn, mp_id):
    with pytest.raises(ValueError, match="unknown Appendix-A subsection"):
        record_change(conn, mp_id, "Z", "something")
    with pytest.raises(ValueError, match="non-empty"):
        record_change(conn, mp_id, "B", "   ")
    with pytest.raises(ValueError, match="non-negative"):
        record_change(conn, mp_id, "B", "gift", amount=-5.0)


def test_update_detail_round_trip(conn, mp_id):
    change = record_change(conn, mp_id, "G", "Buy a wheelchair-accessible van")
    detail = get_estate_change_detail(conn, change.submission.id)
    update_estate_change_detail(conn, replace(detail, amount=38_000.0))
    assert get_estate_change_detail(conn, change.submission.id).amount == 38_000.0


# ------------------------------------------------------- status lifecycle

def test_status_lifecycle_draft_submitted_approved(conn, mp_id):
    change = record_change(conn, mp_id, "Q", "Pay accommodation bond", recorded_by="Linda")
    sub_id = change.submission.id

    submitted = update_change_status(conn, sub_id, "submitted", recorded_by="Linda")
    assert submitted.status == "submitted"
    assert submitted.submitted_at is not None
    assert submitted.submitted_by == "Linda"

    approved = update_change_status(
        conn, sub_id, "approved", ncat_reference="NCAT-2026-0042"
    )
    assert approved.status == "approved"
    assert approved.ncat_reference == "NCAT-2026-0042"
    assert approved.ncat_decision_at is not None


def test_rejected_can_be_resubmitted(conn, mp_id):
    change = record_change(conn, mp_id, "D", "Move funds to a term deposit")
    update_change_status(conn, change.submission.id, "submitted")
    update_change_status(conn, change.submission.id, "rejected")
    resubmitted = update_change_status(conn, change.submission.id, "submitted")
    assert resubmitted.status == "submitted"


def test_invalid_transitions_raise(conn, mp_id):
    change = record_change(conn, mp_id, "C", "Trip to the coast")
    with pytest.raises(ValueError, match="cannot move"):
        update_change_status(conn, change.submission.id, "approved")  # draft → approved
    update_change_status(conn, change.submission.id, "submitted")
    update_change_status(conn, change.submission.id, "approved")
    with pytest.raises(ValueError, match="cannot move"):
        update_change_status(conn, change.submission.id, "rejected")  # approved is final


def test_status_change_is_audited(conn, mp_id):
    change = record_change(conn, mp_id, "N", "Bathroom rail installation")
    update_change_status(conn, change.submission.id, "submitted", recorded_by="Linda")
    audits = list_audit(conn, table_name="submissions")
    status_entries = [a for a in audits if "status → submitted" in (a.reason or "")]
    assert status_entries
    assert json.loads(status_entries[0].before_json)["status"] == "draft"
    assert json.loads(status_entries[0].after_json)["status"] == "submitted"


# ------------------------------------------------------------ list_changes

def test_list_changes_returns_composites_newest_first(conn, mp_id):
    record_change(conn, mp_id, "A", "Hire a weekday carer")
    record_change(conn, mp_id, "R", "Replace hearing aids")
    changes = list_changes(conn, mp_id)
    assert [c.submission.trigger_subsection for c in changes] == ["R", "A"]
    assert all(c.detail is not None for c in changes)
