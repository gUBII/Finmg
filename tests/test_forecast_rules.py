"""P6: forecast/anomaly rules — projected §76 gift breach, category overrun,
estate drawdown. Uses synthetic mid-period trajectories + tunable thresholds."""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.db.database import get_connection, init_db
from src.db.queries import insert_pdf_and_transactions
from src.db.queries_compliance import insert_gift
from src.db.queries_forecast import insert_forecast, insert_forecast_category
from src.db.queries_estate import insert_managed_person
from src.models.compliance import Gift
from src.models.estate import ManagedPerson
from src.models.forecast import Forecast, ForecastCategory
from src.models.transaction import AccountMeta, Transaction
from src.services.compliance.engine import evaluate_compliance, set_rule_mode
from src.services.compliance.rules import RuleContext, _eval_fc_gift_section76

# A full-year period; "as_of" a quarter in so projection multiplies ~4x.
PERIOD = ("2026-01-01", "2026-12-31")
AS_OF = "2026-03-31"  # ~90 days elapsed of 365


def _conn(tmp_path):
    conn = get_connection(tmp_path / "test.db")
    init_db(conn)
    return conn


def _ron(conn) -> int:
    return insert_managed_person(conn, ManagedPerson(surname="GENTILI", given_names="Renato"))


def _add_txns(conn, rows):
    """rows: (date, withdrawal, deposit, category)"""
    meta = AccountMeta(account_type="ACCESS ACCOUNT", account_name="GENTILI RENATO",
                       bsb="013711", account_number="437669532", balance=0.0,
                       report_start=PERIOD[0], report_end=PERIOD[1])
    txns = [
        Transaction(date=date.fromisoformat(d), description="x", withdrawal=w, deposit=dep,
                    account_number="437669532", account_type="ACCESS ACCOUNT",
                    category=cat, month=d[:7])
        for (d, w, dep, cat) in rows
    ]
    insert_pdf_and_transactions(conn, meta, txns, "f.pdf", "h" + "0" * 63)


def _forecast_only_rules(conn, rid, **kw):
    res = evaluate_compliance(conn, rid, period_start=PERIOD[0], period_end=PERIOD[1],
                              as_of=AS_OF, **kw)
    return res.forecast_findings


def test_gift_projection_breaches_limit(tmp_path):
    conn = _conn(tmp_path)
    rid = _ron(conn)
    # $500 of gifts in Q1 → projects to ~$2027/yr, over the $1500 default limit.
    insert_gift(conn, Gift(managed_person_id=rid, occasion="birthday",
                           occasion_date="2026-02-14", actual_amount=500.0))
    findings = _forecast_only_rules(conn, rid)
    assert any(f.finding.rule_key == "R-FC-GIFT-76" for f in findings)


def test_gift_projection_under_limit_silent(tmp_path):
    conn = _conn(tmp_path)
    rid = _ron(conn)
    # $100 in Q1 → ~$405/yr, under $1500 → no finding.
    insert_gift(conn, Gift(managed_person_id=rid, occasion="birthday",
                           occasion_date="2026-02-14", actual_amount=100.0))
    findings = _forecast_only_rules(conn, rid)
    assert not any(f.finding.rule_key == "R-FC-GIFT-76" for f in findings)


def test_gift_threshold_is_tunable(tmp_path):
    conn = _conn(tmp_path)
    rid = _ron(conn)
    insert_gift(conn, Gift(managed_person_id=rid, occasion="birthday",
                           occasion_date="2026-02-14", actual_amount=500.0))
    # Raise the annual limit well above the projection → no finding.
    set_rule_mode(conn, "R-FC-GIFT-76", "warn", threshold_json='{"annual_limit": 5000}')
    findings = _forecast_only_rules(conn, rid)
    assert not any(f.finding.rule_key == "R-FC-GIFT-76" for f in findings)


def test_category_overrun_flagged(tmp_path):
    conn = _conn(tmp_path)
    rid = _ron(conn)
    cat = insert_forecast_category(conn, ForecastCategory(section="D_expenditure",
                                   category_name="Groceries", display_order=0))
    # Forecast $4000/yr; but $3000 spent in Q1 → projects to ~$12000 → way over.
    insert_forecast(conn, Forecast(managed_person_id=rid, period_start=PERIOD[0],
                    period_end=PERIOD[1], category_id=cat, forecast_value=4000.0,
                    actual_value=4000.0))
    _add_txns(conn, [("2026-02-10", 3000.0, None, "Groceries")])
    findings = _forecast_only_rules(conn, rid)
    assert any(f.finding.rule_key == "R-FC-OVERRUN" for f in findings)


def test_category_on_track_silent(tmp_path):
    conn = _conn(tmp_path)
    rid = _ron(conn)
    cat = insert_forecast_category(conn, ForecastCategory(section="D_expenditure",
                                   category_name="Groceries", display_order=0))
    # Forecast $4000/yr; $900 in Q1 → projects to ~$3650 → under → silent.
    insert_forecast(conn, Forecast(managed_person_id=rid, period_start=PERIOD[0],
                    period_end=PERIOD[1], category_id=cat, forecast_value=4000.0,
                    actual_value=4000.0))
    _add_txns(conn, [("2026-02-10", 900.0, None, "Groceries")])
    findings = _forecast_only_rules(conn, rid)
    assert not any(f.finding.rule_key == "R-FC-OVERRUN" for f in findings)


def test_drawdown_projection_flagged(tmp_path):
    conn = _conn(tmp_path)
    rid = _ron(conn)
    # Spending far exceeds income in Q1 → projected net strongly negative.
    _add_txns(conn, [
        ("2026-02-01", None, 1000.0, "Disability Support Pension"),
        ("2026-02-15", 4000.0, None, "Groceries"),
    ])
    findings = _forecast_only_rules(conn, rid)
    assert any(f.finding.rule_key == "R-FC-DRAWDOWN" for f in findings)


def test_positive_cashflow_no_drawdown(tmp_path):
    conn = _conn(tmp_path)
    rid = _ron(conn)
    _add_txns(conn, [
        ("2026-02-01", None, 4000.0, "Disability Support Pension"),
        ("2026-02-15", 1000.0, None, "Groceries"),
    ])
    findings = _forecast_only_rules(conn, rid)
    assert not any(f.finding.rule_key == "R-FC-DRAWDOWN" for f in findings)


def test_forecast_findings_separated_from_state(tmp_path):
    conn = _conn(tmp_path)
    rid = _ron(conn)  # no FMO etc → state findings exist
    insert_gift(conn, Gift(managed_person_id=rid, occasion="birthday",
                           occasion_date="2026-02-14", actual_amount=500.0))
    res = evaluate_compliance(conn, rid, period_start=PERIOD[0], period_end=PERIOD[1], as_of=AS_OF)
    assert res.state_findings           # FMO/Will warnings
    assert res.forecast_findings        # gift projection
    # The two sets are disjoint.
    state_keys = {g.finding.rule_key for g in res.state_findings}
    fc_keys = {g.finding.rule_key for g in res.forecast_findings}
    assert state_keys.isdisjoint(fc_keys)


def test_projection_helper_quarter_scales_4x():
    # Direct unit check of the projection math.
    val = _eval_fc_gift_section76.__globals__["_project_to_period"](
        100.0, "2026-01-01", "2026-03-31", "2026-12-31"
    )
    assert 380 < val < 420  # ~365/90 * 100
