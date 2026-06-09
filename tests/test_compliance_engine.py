"""P5: compliance rule engine — handbook rules, mode toggles, enforce gating."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.db.database import get_connection, init_db
from src.db.queries_compliance import insert_gift, list_audit
from src.db.queries_estate import (
    insert_account,
    insert_investment,
    insert_managed_person,
)
from src.models.compliance import Gift
from src.models.estate import Account, Investment, ManagedPerson
from src.services.compliance.engine import (
    DEFAULT_MODE,
    effective_mode,
    evaluate_compliance,
    set_rule_mode,
)
from src.services.compliance.rules import all_rules


def _conn(tmp_path):
    conn = get_connection(tmp_path / "test.db")
    init_db(conn)
    return conn


def _ron(conn, **kw) -> int:
    return insert_managed_person(
        conn, ManagedPerson(surname="GENTILI", given_names="Renato", **kw)
    )


def test_registry_has_handbook_rules():
    keys = {r.key for r in all_rules()}
    assert {"R-SEP-01", "R-GIFT-76", "R-WILL-01", "R-INVEST-REVIEW", "R-FMO-01"} <= keys
    # Every rule cites the handbook.
    assert all(r.handbook_ref for r in all_rules())


def test_default_mode_is_warn(tmp_path):
    conn = _conn(tmp_path)
    assert effective_mode(conn, "R-SEP-01") == DEFAULT_MODE == "warn"


def test_account_separation_flags_joint(tmp_path):
    conn = _conn(tmp_path)
    rid = _ron(conn, fmo_date="2026-01-01", d_and_a_reference="DA-1", has_will="no")
    insert_account(conn, Account(managed_person_id=rid, institution="ANZ",
                                 account_number="111", bsb="012", ownership="sole"))
    insert_account(conn, Account(managed_person_id=rid, institution="ANZ",
                                 account_number="222", bsb="012", ownership="joint"))
    result = evaluate_compliance(conn, rid)
    sep = [g for g in result.graded if g.finding.rule_key == "R-SEP-01"]
    assert len(sep) == 1
    assert sep[0].finding.subject == "222"


def test_gift_over_limit_flagged(tmp_path):
    conn = _conn(tmp_path)
    rid = _ron(conn, fmo_date="2026-01-01", d_and_a_reference="DA-1", has_will="no")
    insert_gift(conn, Gift(managed_person_id=rid, occasion="other",
                           planned_amount=5000.0, section_76_assessment="over_limit"))
    insert_gift(conn, Gift(managed_person_id=rid, occasion="birthday",
                           planned_amount=50.0, section_76_assessment="compliant"))
    result = evaluate_compliance(conn, rid)
    gifts = [g for g in result.graded if g.finding.rule_key == "R-GIFT-76"]
    assert len(gifts) == 1  # only the over_limit one


def test_fmo_and_will_gaps_flagged(tmp_path):
    conn = _conn(tmp_path)
    rid = _ron(conn)  # no fmo_date, d_and_a, or will
    result = evaluate_compliance(conn, rid)
    keys = {g.finding.rule_key for g in result.graded}
    assert "R-FMO-01" in keys
    assert "R-WILL-01" in keys


def test_off_mode_skips_rule(tmp_path):
    conn = _conn(tmp_path)
    rid = _ron(conn)
    set_rule_mode(conn, "R-FMO-01", "off")
    result = evaluate_compliance(conn, rid)
    assert all(g.finding.rule_key != "R-FMO-01" for g in result.graded)


def test_enforce_mode_blocks(tmp_path):
    conn = _conn(tmp_path)
    rid = _ron(conn, fmo_date="2026-01-01", d_and_a_reference="DA-1", has_will="no")
    insert_account(conn, Account(managed_person_id=rid, institution="ANZ",
                                 account_number="222", bsb="012", ownership="joint"))
    # Warn by default → not blocking.
    assert not evaluate_compliance(conn, rid).is_blocked
    # Opt into enforce → now blocking.
    set_rule_mode(conn, "R-SEP-01", "enforce", recorded_by="Linda")
    result = evaluate_compliance(conn, rid)
    assert result.is_blocked
    assert len(result.blocking) == 1


def test_set_rule_mode_writes_audit(tmp_path):
    conn = _conn(tmp_path)
    set_rule_mode(conn, "R-SEP-01", "enforce", recorded_by="Linda")
    audits = list_audit(conn, "compliance_settings")
    assert len(audits) == 1
    assert "enforce" in (audits[0].after_json or "")


def test_set_rule_mode_rejects_bad_inputs(tmp_path):
    conn = _conn(tmp_path)
    with pytest.raises(ValueError):
        set_rule_mode(conn, "R-SEP-01", "nuke")
    with pytest.raises(ValueError):
        set_rule_mode(conn, "NO-SUCH-RULE", "warn")


def test_investment_review_flags_stale(tmp_path):
    conn = _conn(tmp_path)
    rid = _ron(conn, fmo_date="2026-01-01", d_and_a_reference="DA-1", has_will="no")
    insert_investment(conn, Investment(managed_person_id=rid, type="shares",
                                       description="ASX200 ETF", last_review_date=None))
    result = evaluate_compliance(conn, rid, period_end="2026-06-30")
    assert any(g.finding.rule_key == "R-INVEST-REVIEW" for g in result.graded)
