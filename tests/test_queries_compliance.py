"""Tests for queries_compliance.py — settings, rationales, audit, submissions,
acknowledgements, attachments, gifts, consultation."""

from __future__ import annotations

import sys
from dataclasses import replace
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.db.database import get_connection, init_db
from src.db.queries_compliance import (
    delete_field_rationale,
    get_compliance_setting,
    get_field_rationale,
    get_submission,
    insert_attachment,
    insert_audit,
    insert_consultation,
    insert_gift,
    insert_submission,
    list_acknowledgements,
    list_attachments,
    list_audit,
    list_compliance_settings,
    list_consultations,
    list_field_rationales,
    list_gifts,
    list_submissions,
    update_gift,
    update_submission,
    upsert_acknowledgement,
    upsert_compliance_setting,
    upsert_field_rationale,
)
from src.db.queries_estate import insert_managed_person
from src.models.compliance import (
    Acknowledgement,
    AuditEntry,
    ComplianceSetting,
    ConsultationLogEntry,
    FieldRationale,
    Gift,
    Submission,
    SubmissionAttachment,
)
from src.models.estate import ManagedPerson


def _conn(tmp_path):
    conn = get_connection(tmp_path / "test.db")
    init_db(conn)
    return conn


def _ron(conn) -> int:
    return insert_managed_person(
        conn, ManagedPerson(surname="GENTILI", given_names="Renato")
    )


# --- migration 006 applied -------------------------------------------------

def test_migration_006_tables_exist(tmp_path):
    conn = _conn(tmp_path)
    names = {
        r["name"]
        for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    assert "compliance_settings" in names
    assert "artifact_field_rationales" in names


# --- compliance_settings ---------------------------------------------------

def test_compliance_setting_defaults_warn(tmp_path):
    conn = _conn(tmp_path)
    upsert_compliance_setting(conn, ComplianceSetting(rule_key="R-SEP-01"))
    got = get_compliance_setting(conn, "R-SEP-01")
    assert got is not None
    assert got.mode == "warn"


def test_compliance_setting_upsert_replaces_mode(tmp_path):
    conn = _conn(tmp_path)
    upsert_compliance_setting(conn, ComplianceSetting(rule_key="R-GIFT-76", mode="warn"))
    upsert_compliance_setting(
        conn,
        ComplianceSetting(rule_key="R-GIFT-76", mode="enforce", threshold_json='{"limit": 500}'),
    )
    got = get_compliance_setting(conn, "R-GIFT-76")
    assert got.mode == "enforce"
    assert got.threshold_json == '{"limit": 500}'
    # No duplicate row created.
    assert len([s for s in list_compliance_settings(conn) if s.rule_key == "R-GIFT-76"]) == 1


def test_compliance_setting_rejects_bad_mode(tmp_path):
    conn = _conn(tmp_path)
    with pytest.raises(Exception):
        upsert_compliance_setting(conn, ComplianceSetting(rule_key="R-X", mode="nuke"))


# --- artifact_field_rationales --------------------------------------------

def test_field_rationale_upsert_and_get(tmp_path):
    conn = _conn(tmp_path)
    rid = _ron(conn)
    upsert_field_rationale(
        conn,
        FieldRationale(
            artifact_key="annual_accounts",
            field_key="Section_B_investments",
            managed_person_id=rid,
            rationale="Ron holds no investments.",
            recorded_by="Linda",
        ),
    )
    got = get_field_rationale(conn, "annual_accounts", "Section_B_investments", rid)
    assert got is not None
    assert got.rationale == "Ron holds no investments."


def test_field_rationale_upsert_replaces(tmp_path):
    conn = _conn(tmp_path)
    rid = _ron(conn)
    key = dict(artifact_key="plan", field_key="Section_E_oneoff", managed_person_id=rid)
    upsert_field_rationale(conn, FieldRationale(**key, rationale="none"))
    upsert_field_rationale(conn, FieldRationale(**key, rationale="none anticipated"))
    rows = list_field_rationales(conn, "plan", rid)
    assert len(rows) == 1
    assert rows[0].rationale == "none anticipated"


def test_field_rationale_delete(tmp_path):
    conn = _conn(tmp_path)
    rid = _ron(conn)
    upsert_field_rationale(
        conn, FieldRationale("plan", "x", rid, "tmp")
    )
    delete_field_rationale(conn, "plan", "x", rid)
    assert get_field_rationale(conn, "plan", "x", rid) is None


# --- audit_log -------------------------------------------------------------

def test_audit_insert_and_immutability(tmp_path):
    conn = _conn(tmp_path)
    aid = insert_audit(
        conn,
        AuditEntry(
            action="update",
            table_name="forecasts",
            row_id=1,
            actor_role="private_manager",
            reason="CPI projection",
        ),
    )
    rows = list_audit(conn, "forecasts")
    assert len(rows) == 1
    assert rows[0].reason == "CPI projection"
    # Triggers block UPDATE and DELETE.
    with pytest.raises(Exception):
        conn.execute("UPDATE audit_log SET reason = 'x' WHERE id = ?", (aid,))
    with pytest.raises(Exception):
        conn.execute("DELETE FROM audit_log WHERE id = ?", (aid,))


# --- submissions -----------------------------------------------------------

def test_submission_lifecycle(tmp_path):
    conn = _conn(tmp_path)
    rid = _ron(conn)
    sid = insert_submission(
        conn, Submission(managed_person_id=rid, type="annual_accounts")
    )
    sub = get_submission(conn, sid)
    assert sub.status == "draft"
    update_submission(
        conn,
        sid,
        Submission(
            managed_person_id=rid,
            type="annual_accounts",
            status="submitted",
            generated_pdf_sha="abc123",
        ),
    )
    sub2 = get_submission(conn, sid)
    assert sub2.status == "submitted"
    assert sub2.generated_pdf_sha == "abc123"
    assert len(list_submissions(conn, rid, "annual_accounts")) == 1


def test_submission_rejects_bad_type(tmp_path):
    conn = _conn(tmp_path)
    rid = _ron(conn)
    with pytest.raises(Exception):
        insert_submission(conn, Submission(managed_person_id=rid, type="bogus"))


# --- acknowledgements ------------------------------------------------------

def test_acknowledgement_upsert(tmp_path):
    conn = _conn(tmp_path)
    rid = _ron(conn)
    sid = insert_submission(conn, Submission(managed_person_id=rid, type="initial_plan"))
    for n in range(1, 8):
        upsert_acknowledgement(
            conn, Acknowledgement(submission_id=sid, ack_number=n, ticked_by="Linda")
        )
    acks = list_acknowledgements(conn, sid)
    assert len(acks) == 7
    # Re-ticking the same box doesn't duplicate.
    upsert_acknowledgement(conn, Acknowledgement(submission_id=sid, ack_number=1, ticked_by="Linda"))
    assert len(list_acknowledgements(conn, sid)) == 7


def test_acknowledgement_rejects_out_of_range(tmp_path):
    conn = _conn(tmp_path)
    rid = _ron(conn)
    sid = insert_submission(conn, Submission(managed_person_id=rid, type="initial_plan"))
    with pytest.raises(Exception):
        upsert_acknowledgement(conn, Acknowledgement(submission_id=sid, ack_number=8))


# --- attachments -----------------------------------------------------------

def test_attachment_insert_list(tmp_path):
    conn = _conn(tmp_path)
    rid = _ron(conn)
    sid = insert_submission(conn, Submission(managed_person_id=rid, type="annual_accounts"))
    insert_attachment(
        conn,
        SubmissionAttachment(
            submission_id=sid, filename="anz_living.pdf", sha="deadbeef", description="bank statement"
        ),
    )
    atts = list_attachments(conn, sid)
    assert len(atts) == 1
    assert atts[0].sha == "deadbeef"


# --- gifts -----------------------------------------------------------------

def test_gift_insert_list(tmp_path):
    conn = _conn(tmp_path)
    rid = _ron(conn)
    insert_gift(
        conn,
        Gift(
            managed_person_id=rid,
            occasion="christmas",
            occasion_date="2026-12-25",
            planned_amount=200.0,
            section_76_assessment="compliant",
        ),
    )
    gifts = list_gifts(conn, rid)
    assert len(gifts) == 1
    assert gifts[0].section_76_assessment == "compliant"


def test_gift_update_records_actual(tmp_path):
    conn = _conn(tmp_path)
    rid = _ron(conn)
    gid = insert_gift(
        conn,
        Gift(
            managed_person_id=rid,
            occasion="christmas",
            occasion_date="2026-12-25",
            planned_amount=200.0,
            section_76_assessment="compliant",
        ),
    )
    original = list_gifts(conn, rid)[0]
    update_gift(conn, replace(original, actual_amount=185.5, actual_transaction_id=None))
    updated = list_gifts(conn, rid)[0]
    assert updated.id == gid
    assert updated.actual_amount == 185.5
    assert updated.planned_amount == 200.0  # untouched


def test_gift_update_requires_id(tmp_path):
    conn = _conn(tmp_path)
    rid = _ron(conn)
    with pytest.raises(ValueError):
        update_gift(conn, Gift(managed_person_id=rid, planned_amount=10.0))


# --- consultation ----------------------------------------------------------

def test_consultation_insert_list(tmp_path):
    conn = _conn(tmp_path)
    rid = _ron(conn)
    insert_consultation(
        conn,
        ConsultationLogEntry(
            managed_person_id=rid,
            date="2026-06-01",
            decision_topic="annual plan",
            summary="Discussed with Ron and family.",
        ),
    )
    rows = list_consultations(conn, rid)
    assert len(rows) == 1
    assert rows[0].decision_topic == "annual plan"
