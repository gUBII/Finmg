"""Tests for the annualized forecast generator (Section D).

Covers: annualization of partial-window actuals, benchmark overrides (DSP
fortnightly rate, rent cycle), one-off exclusion, NCAT override-reason
generation, insufficient-coverage guard, idempotency, and manual-override
preservation.

Mirrors the harness in tests/test_services_forecast.py: in-memory tmp DB,
transactions seeded via insert_pdf_and_transactions. Benchmarks are injected
per-test so assertions don't depend on the shipped config file.
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.db.database import get_connection, init_db
from src.db.queries import insert_pdf_and_transactions
from src.db.queries_estate import insert_managed_person
from src.db.queries_forecast import (
    get_forecast,
    insert_forecast_category,
    list_forecasts,
)
from src.models.estate import ManagedPerson
from src.models.forecast import ForecastCategory
from src.models.transaction import AccountMeta, Transaction
from src.services.forecast import (
    bootstrap_forecast_period,
    generate_forecast_proposals,
    save_forecast_override,
)
from src.services.forecast_generator import (
    CategoryProposal,
    generate_category_proposals,
)

PERIOD = ("2026-07-01", "2027-06-30")  # trailing window: 2025-07-01..2026-06-30
PERIOD_DAYS = 365  # inclusive length of the trailing window


# --------------------------------------------------------------------------- helpers
def _conn(tmp_path):
    conn = get_connection(tmp_path / "test.db")
    init_db(conn)
    return conn


def _seed_ron(conn) -> int:
    return insert_managed_person(
        conn,
        ManagedPerson(surname="GENTILI", given_names="Renato", dob="1955-01-01"),
    )


def _seed_categories(conn) -> None:
    insert_forecast_category(
        conn, ForecastCategory(section="D_expenditure", category_name="Groceries", display_order=0)
    )
    insert_forecast_category(
        conn, ForecastCategory(section="D_expenditure", category_name="Rent", display_order=1)
    )
    insert_forecast_category(
        conn,
        ForecastCategory(section="D_income", category_name="Disability Support Pension", display_order=0),
    )
    insert_forecast_category(
        conn, ForecastCategory(section="D_income", category_name="Other", display_order=1)
    )


def _seed_transactions(conn, rows, file_hash_suffix="0") -> None:
    """rows: (date_iso, category, description, withdrawal, deposit, internal_transfer)"""
    meta = AccountMeta(
        account_type="ACCESS ACCOUNT",
        account_name="GENTILI RENATO",
        bsb="013711",
        account_number="437669532",
        balance=0.0,
        report_start="2025-07-01",
        report_end="2026-06-30",
    )
    txns = []
    for d, cat, desc, w, dep, it in rows:
        y, m, day = (int(x) for x in d.split("-"))
        txns.append(
            Transaction(
                date=date(y, m, day),
                description=desc,
                withdrawal=w or None,
                deposit=dep or None,
                account_number="437669532",
                account_type="ACCESS ACCOUNT",
                month=f"{y}-{m:02d}",
                category=cat,
                is_internal_transfer=bool(it),
            )
        )
    fhash = ("dead" + file_hash_suffix * 60)[:64]
    insert_pdf_and_transactions(conn, meta, txns, f"test{file_hash_suffix}.pdf", fhash)


def _benchmarks(**overrides) -> dict:
    base = {
        "annualization": {"min_coverage_days": 14, "fortnights_per_year": 26.0893},
        "income_benchmarks": {
            "Disability Support Pension": {
                "type": "fortnightly_rate",
                "rate": 1420.30,
                "reason": "Benchmark from observed steady-state DSP rate.",
            }
        },
        "expenditure_benchmarks": {
            "Rent": {
                "type": "cycle_amount",
                "amount": None,
                "cycle": "weekly",
                "reason": "Rent paid via internal transfer; set amount before generating.",
            }
        },
        "one_off_categories": {
            "Other": {"reason": "Single non-recurring event; routed to Section E."}
        },
        "seasonality_flags": {},
    }
    base.update(overrides)
    return base


def _proposal_by_name(proposals, name) -> CategoryProposal:
    return next(p for p in proposals if p.category_name == name)


# --------------------------------------------------------------------------- annualization
class TestAnnualization:
    def test_annualizes_partial_window_expenditure(self, tmp_path):
        conn = _conn(tmp_path)
        mp_id = _seed_ron(conn)
        _seed_categories(conn)
        # Groceries span: 2026-02-10 .. 2026-04-10 → 60 days of coverage
        _seed_transactions(
            conn,
            [
                ("2026-02-10", "Groceries", "WOOLWORTHS", 100.0, 0, 0),
                ("2026-03-10", "Groceries", "COLES", 50.0, 0, 0),
                ("2026-04-10", "Groceries", "IGA", 30.0, 0, 0),
            ],
        )
        props = generate_category_proposals(conn, mp_id, *PERIOD, benchmarks=_benchmarks())
        g = _proposal_by_name(props, "Groceries")
        coverage_days = (date(2026, 4, 10) - date(2026, 2, 10)).days + 1  # 60
        expected = 180.0 * PERIOD_DAYS / coverage_days
        assert g.actual_value == pytest.approx(180.0)
        assert g.annualized_estimate == pytest.approx(expected, rel=1e-6)
        assert g.proposed_value == pytest.approx(expected, rel=1e-6)
        assert g.months_of_data == pytest.approx(coverage_days / 30.4375, abs=0.1)
        assert g.override_reason  # differs from actual → reason required

    def test_full_year_coverage_factor_is_one(self, tmp_path):
        conn = _conn(tmp_path)
        mp_id = _seed_ron(conn)
        _seed_categories(conn)
        # Span the entire trailing window edge-to-edge → coverage == period
        _seed_transactions(
            conn,
            [
                ("2025-07-01", "Groceries", "START", 100.0, 0, 0),
                ("2026-06-30", "Groceries", "END", 100.0, 0, 0),
            ],
        )
        props = generate_category_proposals(conn, mp_id, *PERIOD, benchmarks=_benchmarks())
        g = _proposal_by_name(props, "Groceries")
        assert g.annualized_estimate == pytest.approx(200.0, rel=1e-6)
        assert g.proposed_value == pytest.approx(200.0, rel=1e-6)
        # proposed == actual → no override reason
        assert not g.override_reason

    def test_insufficient_coverage_returns_actual(self, tmp_path):
        conn = _conn(tmp_path)
        mp_id = _seed_ron(conn)
        _seed_categories(conn)
        # Whole expenditure section has a single day of coverage (< min 14)
        _seed_transactions(conn, [("2026-03-10", "Groceries", "ONE", 80.0, 0, 0)])
        props = generate_category_proposals(conn, mp_id, *PERIOD, benchmarks=_benchmarks())
        g = _proposal_by_name(props, "Groceries")
        assert g.proposed_value == pytest.approx(80.0)
        assert g.flag and "insufficient" in g.flag.lower()


# --------------------------------------------------------------------------- benchmarks
class TestBenchmarks:
    def test_dsp_benchmark_overrides_actual(self, tmp_path):
        conn = _conn(tmp_path)
        mp_id = _seed_ron(conn)
        _seed_categories(conn)
        # Incomplete deposits — only a few, far from a full year
        _seed_transactions(
            conn,
            [
                ("2026-03-20", "Disability Support Pension", "CTRLINK", 0, 1394.10, 0),
                ("2026-04-02", "Disability Support Pension", "CTRLINK", 0, 1420.30, 0),
            ],
        )
        props = generate_category_proposals(conn, mp_id, *PERIOD, benchmarks=_benchmarks())
        dsp = _proposal_by_name(props, "Disability Support Pension")
        expected = 1420.30 * 26.0893
        assert dsp.proposed_value == pytest.approx(expected, rel=1e-6)
        # Benchmark must NOT be day-scaled on top of the fortnightly math
        assert dsp.proposed_value < 40000
        assert "benchmark" in dsp.override_reason.lower() or "fortnight" in dsp.override_reason.lower()

    def test_rent_null_benchmark_flags_not_fabricates(self, tmp_path):
        conn = _conn(tmp_path)
        mp_id = _seed_ron(conn)
        _seed_categories(conn)
        _seed_transactions(conn, [("2026-03-10", "Groceries", "X", 50.0, 0, 0)])
        props = generate_category_proposals(conn, mp_id, *PERIOD, benchmarks=_benchmarks())
        rent = _proposal_by_name(props, "Rent")
        assert rent.proposed_value == pytest.approx(0.0)
        assert rent.flag and "input" in rent.flag.lower()

    def test_rent_set_amount_annualizes_cycle(self, tmp_path):
        conn = _conn(tmp_path)
        mp_id = _seed_ron(conn)
        _seed_categories(conn)
        bm = _benchmarks()
        bm["expenditure_benchmarks"]["Rent"] = {
            "type": "cycle_amount",
            "amount": 420.0,
            "cycle": "weekly",
            "reason": "Rent benchmark $420/week.",
        }
        _seed_transactions(conn, [("2026-03-10", "Groceries", "X", 50.0, 0, 0)])
        props = generate_category_proposals(conn, mp_id, *PERIOD, benchmarks=bm)
        rent = _proposal_by_name(props, "Rent")
        assert rent.proposed_value == pytest.approx(420.0 * 52)
        assert rent.override_reason

    def test_one_off_category_excluded(self, tmp_path):
        conn = _conn(tmp_path)
        mp_id = _seed_ron(conn)
        _seed_categories(conn)
        _seed_transactions(
            conn,
            [("2026-03-13", "Other", "PAY/SALARY LACTALIS", 0, 3188.42, 0)],
        )
        props = generate_category_proposals(conn, mp_id, *PERIOD, benchmarks=_benchmarks())
        other = _proposal_by_name(props, "Other")
        assert other.proposed_value == pytest.approx(0.0)
        assert "one-off" in other.override_reason.lower() or "section e" in other.override_reason.lower()

    def test_seasonality_flag_attached(self, tmp_path):
        conn = _conn(tmp_path)
        mp_id = _seed_ron(conn)
        _seed_categories(conn)
        bm = _benchmarks(seasonality_flags={"Groceries": "Lumpy — verify."})
        _seed_transactions(
            conn,
            [
                ("2026-02-10", "Groceries", "A", 100.0, 0, 0),
                ("2026-04-10", "Groceries", "B", 100.0, 0, 0),
            ],
        )
        props = generate_category_proposals(conn, mp_id, *PERIOD, benchmarks=bm)
        g = _proposal_by_name(props, "Groceries")
        assert g.flag and "lumpy" in g.flag.lower()


# --------------------------------------------------------------------------- NCAT invariant
class TestOverrideReason:
    def test_reason_generated_when_proposed_differs(self, tmp_path):
        conn = _conn(tmp_path)
        mp_id = _seed_ron(conn)
        _seed_categories(conn)
        _seed_transactions(
            conn,
            [
                ("2026-02-10", "Groceries", "A", 100.0, 0, 0),
                ("2026-04-10", "Groceries", "B", 100.0, 0, 0),
            ],
        )
        props = generate_category_proposals(conn, mp_id, *PERIOD, benchmarks=_benchmarks())
        for p in props:
            if abs(p.proposed_value - p.actual_value) > 0.01:
                assert p.override_reason, f"{p.category_name} differs but has no reason"


# --------------------------------------------------------------------------- service orchestration
class TestServiceOrchestration:
    def _setup(self, tmp_path):
        conn = _conn(tmp_path)
        mp_id = _seed_ron(conn)
        _seed_categories(conn)
        _seed_transactions(
            conn,
            [
                ("2026-02-10", "Groceries", "A", 100.0, 0, 0),
                ("2026-04-10", "Groceries", "B", 100.0, 0, 0),
                ("2026-03-20", "Disability Support Pension", "CTRLINK", 0, 1420.30, 0),
            ],
        )
        return conn, mp_id

    def test_generate_writes_proposals(self, tmp_path):
        conn, mp_id = self._setup(tmp_path)
        summary = generate_forecast_proposals(conn, mp_id, *PERIOD, benchmarks=_benchmarks())
        assert summary["updated"] >= 1
        rows = list_forecasts(conn, mp_id, *PERIOD, section="D_income")
        dsp = next(r for r in rows if r.forecast_value and r.forecast_value > 30000)
        assert dsp.override_reason  # NCAT invariant satisfied on write

    def test_idempotent_regenerate(self, tmp_path):
        conn, mp_id = self._setup(tmp_path)
        generate_forecast_proposals(conn, mp_id, *PERIOD, benchmarks=_benchmarks())
        rows1 = list_forecasts(conn, mp_id, *PERIOD)
        generate_forecast_proposals(conn, mp_id, *PERIOD, benchmarks=_benchmarks())
        rows2 = list_forecasts(conn, mp_id, *PERIOD)
        assert len(rows1) == len(rows2)  # no duplicate rows
        v1 = {r.category_id: r.forecast_value for r in rows1}
        v2 = {r.category_id: r.forecast_value for r in rows2}
        assert v1 == v2  # stable

    def test_preserves_manual_override(self, tmp_path):
        conn, mp_id = self._setup(tmp_path)
        bootstrap_forecast_period(conn, mp_id, *PERIOD)
        g_row = next(
            r for r in list_forecasts(conn, mp_id, *PERIOD, section="D_expenditure")
        )
        save_forecast_override(conn, g_row.id, 9999.0, "Manual: known upcoming cost")
        generate_forecast_proposals(conn, mp_id, *PERIOD, benchmarks=_benchmarks())
        refreshed = get_forecast(conn, g_row.id)
        assert refreshed.forecast_value == pytest.approx(9999.0)
        assert refreshed.override_reason == "Manual: known upcoming cost"
