"""P4: gap/audit engine — classification, rationale clearing, audit_log wiring."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.db.database import get_connection, init_db
from src.db.queries_compliance import list_audit
from src.db.queries_estate import insert_account, insert_managed_person
from src.models.estate import Account, ManagedPerson
from src.services.audit import GAP, audit_artifact, record_rationale
from src.services.artifacts.resolvers import Ctx
from src.services.artifacts.spec import parse_spec

TEMPLATE = "templates/nswtg/plan.pdf"


def _conn(tmp_path):
    conn = get_connection(tmp_path / "test.db")
    init_db(conn)
    return conn


def _spec():
    # Small artifact: Section A with two scalar fields + a checkbox; Section B
    # with an accounts repeat group (value column will be a gap when balance null).
    return parse_spec(
        {
            "key": "audit_test",
            "title": "Audit test",
            "template": TEMPLATE,
            "sections": [
                {
                    "key": "A",
                    "title": "Section A",
                    "bindings": [
                        {"field": "SurnameRow1", "resolver": "managed_person", "args": {"column": "surname"}},
                        {"field": "Date of birthRow1", "resolver": "managed_person", "args": {"column": "dob"}},
                        {"field": "Brain injury", "type": "checkbox", "on_state": "/On",
                         "resolver": "disability_flag", "args": {"flag": "brain_injury"}},
                    ],
                },
                {
                    "key": "B",
                    "title": "Section B",
                    "repeat_groups": [
                        {
                            "source": "accounts",
                            "max_rows": 5,
                            "columns": [
                                {"field_template": "Account numberRow{i}", "resolver": "attr", "args": {"name": "account_number"}},
                                {"fields": ["fill_73", "fill_74", "fill_75", "fill_76", "fill_77"],
                                 "resolver": "attr_money", "args": {"name": "current_balance"}},
                            ],
                        }
                    ],
                },
            ],
        }
    )


def _seed(conn, *, dob=None) -> int:
    rid = insert_managed_person(
        conn, ManagedPerson(surname="GENTILI", given_names="Renato", dob=dob)
    )
    # One account with no balance → the balance column is a gap; account_number filled.
    insert_account(conn, Account(managed_person_id=rid, institution="ANZ",
                                 account_number="437669532", bsb="013711"))
    return rid


def test_filled_and_gap_classification(tmp_path):
    conn = _conn(tmp_path)
    rid = _seed(conn, dob=None)
    report = audit_artifact(conn, _spec(), Ctx(conn=conn, managed_person_id=rid))
    sec_a = next(s for s in report.sections if s.key == "A")
    # surname filled, dob blank → gap. Checkbox excluded entirely.
    assert "SurnameRow1" not in sec_a.gaps
    assert "Date of birthRow1" in sec_a.gaps
    assert sec_a.total == 2  # checkbox not counted


def test_empty_repeat_rows_not_gaps(tmp_path):
    conn = _conn(tmp_path)
    rid = _seed(conn)  # only 1 account
    report = audit_artifact(conn, _spec(), Ctx(conn=conn, managed_person_id=rid))
    sec_b = next(s for s in report.sections if s.key == "B")
    # Present row (1): account_number filled, balance is a gap. Rows 2-5 ignored.
    assert "Account numberRow1" not in sec_b.gaps
    assert "fill_73" in sec_b.gaps
    assert "Account numberRow2" not in sec_b.gaps  # empty row ignored
    assert sec_b.total == 2  # only the one present row's two columns


def test_field_level_rationale_clears_gap(tmp_path):
    conn = _conn(tmp_path)
    rid = _seed(conn)
    record_rationale(conn, "audit_test", "fill_73", rid,
                     "Balance not yet captured; statements pending.", recorded_by="Linda")
    report = audit_artifact(conn, _spec(), Ctx(conn=conn, managed_person_id=rid))
    sec_b = next(s for s in report.sections if s.key == "B")
    assert "fill_73" not in sec_b.gaps
    assert "fill_73" in sec_b.rationalised


def test_section_level_rationale_clears_all_section_gaps(tmp_path):
    conn = _conn(tmp_path)
    rid = _seed(conn, dob=None)
    # Rationalise the whole of Section A.
    record_rationale(conn, "audit_test", "A", rid, "Personal details verified offline.")
    report = audit_artifact(conn, _spec(), Ctx(conn=conn, managed_person_id=rid))
    sec_a = next(s for s in report.sections if s.key == "A")
    assert sec_a.gaps == ()
    assert "Date of birthRow1" in sec_a.rationalised


def test_rationale_writes_audit_log(tmp_path):
    conn = _conn(tmp_path)
    rid = _seed(conn)
    record_rationale(conn, "audit_test", "fill_73", rid, "n/a", recorded_by="Linda")
    audits = list_audit(conn, "artifact_field_rationales")
    assert len(audits) == 1
    assert audits[0].actor_user == "Linda"
    assert "audit_test" in (audits[0].after_json or "")


def test_empty_rationale_rejected(tmp_path):
    conn = _conn(tmp_path)
    rid = _seed(conn)
    with pytest.raises(ValueError):
        record_rationale(conn, "audit_test", "fill_73", rid, "   ")


def test_completeness_increases_with_rationale(tmp_path):
    conn = _conn(tmp_path)
    rid = _seed(conn, dob=None)
    spec = _spec()
    before = audit_artifact(conn, spec, Ctx(conn=conn, managed_person_id=rid)).completeness
    record_rationale(conn, "audit_test", "Date of birthRow1", rid, "DOB on file offline.")
    record_rationale(conn, "audit_test", "fill_73", rid, "balance pending")
    after = audit_artifact(conn, spec, Ctx(conn=conn, managed_person_id=rid)).completeness
    assert after > before
