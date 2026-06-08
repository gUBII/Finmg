"""Tests for src/services/forecast.py — bootstrap + override validation."""

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
    ForecastOverrideError,
    bootstrap_forecast_period,
    save_forecast_override,
    _trailing_window,
)


def _conn(tmp_path):
    conn = get_connection(tmp_path / "test.db")
    init_db(conn)
    return conn


def _seed_ron(conn) -> int:
    return insert_managed_person(
        conn,
        ManagedPerson(
            surname="GENTILI",
            given_names="Renato",
            dob="1955-01-01",
            disability_flags='["physical","brain_injury"]',
        ),
    )


def _seed_transactions(
    conn,
    rows: list[tuple[str, str, str, float, float, int]],
    file_hash_suffix: str = "0",
) -> None:
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


# ---------------------------------------------------------------------------
# _trailing_window
# ---------------------------------------------------------------------------


class TestTrailingWindow:
    def test_twelve_month_forecast_pulls_prior_twelve_months(self):
        start, end = _trailing_window("2026-07-01", "2027-06-30")
        assert start == "2025-07-01"
        assert end == "2026-06-30"

    def test_six_month_window(self):
        start, end = _trailing_window("2026-07-01", "2026-12-31")
        assert end == "2026-06-30"
        # 6mo from 2026-12-31 to 2026-07-01 = 183 days; trailing starts 183 days before 2026-06-30
        # Just check the length is preserved
        from datetime import date as _date
        f_len = (_date(2026, 12, 31) - _date(2026, 7, 1)).days
        t_len = (_date.fromisoformat(end) - _date.fromisoformat(start)).days
        assert t_len == f_len


# ---------------------------------------------------------------------------
# bootstrap_forecast_period
# ---------------------------------------------------------------------------


class TestBootstrap:
    def _setup(self, tmp_path):
        conn = _conn(tmp_path)
        mp_id = _seed_ron(conn)
        insert_forecast_category(
            conn, ForecastCategory(section="D_expenditure", category_name="Groceries", display_order=0)
        )
        insert_forecast_category(
            conn,
            ForecastCategory(section="D_income", category_name="Disability Support Pension", display_order=0),
        )
        return conn, mp_id

    def test_materialises_one_row_per_category(self, tmp_path):
        conn, mp_id = self._setup(tmp_path)
        count = bootstrap_forecast_period(conn, mp_id, "2026-07-01", "2027-06-30")
        assert count == 2
        rows = list_forecasts(conn, mp_id, "2026-07-01", "2027-06-30")
        assert len(rows) == 2

    def test_actual_value_sums_trailing_window(self, tmp_path):
        conn, mp_id = self._setup(tmp_path)
        # Trailing window is 2025-07-01..2026-06-30
        _seed_transactions(
            conn,
            [
                ("2026-02-10", "Groceries", "WOOLWORTHS", 100.0, 0, 0),
                ("2026-03-10", "Groceries", "COLES", 50.0, 0, 0),
                ("2026-04-10", "Groceries", "IGA", 25.0, 0, 0),
                # Outside trailing window — should not count
                ("2027-01-10", "Groceries", "OUTSIDE", 999.0, 0, 0),
            ],
        )
        bootstrap_forecast_period(conn, mp_id, "2026-07-01", "2027-06-30")
        rows = list_forecasts(conn, mp_id, "2026-07-01", "2027-06-30", section="D_expenditure")
        assert len(rows) == 1
        assert rows[0].actual_value == 175.0

    def test_forecast_value_defaults_to_actual_on_first_bootstrap(self, tmp_path):
        conn, mp_id = self._setup(tmp_path)
        _seed_transactions(
            conn,
            [("2026-02-10", "Groceries", "WOOLWORTHS", 200.0, 0, 0)],
        )
        bootstrap_forecast_period(conn, mp_id, "2026-07-01", "2027-06-30")
        rows = list_forecasts(conn, mp_id, "2026-07-01", "2027-06-30", section="D_expenditure")
        assert rows[0].forecast_value == 200.0
        assert rows[0].override_reason is None

    def test_rebootstrap_refreshes_actual_but_preserves_override(self, tmp_path):
        conn, mp_id = self._setup(tmp_path)
        _seed_transactions(
            conn,
            [("2026-02-10", "Groceries", "WOOLWORTHS", 100.0, 0, 0)],
            file_hash_suffix="1",
        )
        bootstrap_forecast_period(conn, mp_id, "2026-07-01", "2027-06-30")
        rows = list_forecasts(conn, mp_id, "2026-07-01", "2027-06-30", section="D_expenditure")
        groceries_id = rows[0].id

        # Linda overrides
        save_forecast_override(conn, groceries_id, 5000.0, "Projected price rise per CPI")

        # New transactions land
        _seed_transactions(
            conn,
            [("2026-05-10", "Groceries", "COLES", 50.0, 0, 0)],
            file_hash_suffix="2",
        )
        # Re-bootstrap
        bootstrap_forecast_period(conn, mp_id, "2026-07-01", "2027-06-30")

        refreshed = get_forecast(conn, groceries_id)
        assert refreshed.actual_value == 150.0  # actual refreshed
        assert refreshed.forecast_value == 5000.0  # Linda's override preserved
        assert refreshed.override_reason == "Projected price rise per CPI"

    def test_excludes_internal_transfers_from_actual(self, tmp_path):
        conn, mp_id = self._setup(tmp_path)
        _seed_transactions(
            conn,
            [
                ("2026-02-10", "Groceries", "WOOLWORTHS", 100.0, 0, 0),
                ("2026-02-20", "Groceries", "FUNDS TFER", 999.0, 0, 1),
            ],
        )
        bootstrap_forecast_period(conn, mp_id, "2026-07-01", "2027-06-30")
        rows = list_forecasts(conn, mp_id, "2026-07-01", "2027-06-30", section="D_expenditure")
        assert rows[0].actual_value == 100.0


# ---------------------------------------------------------------------------
# save_forecast_override
# ---------------------------------------------------------------------------


class TestOverrideValidation:
    def _setup_with_one_forecast(self, tmp_path) -> tuple:
        conn = _conn(tmp_path)
        mp_id = _seed_ron(conn)
        insert_forecast_category(
            conn, ForecastCategory(section="D_expenditure", category_name="Groceries", display_order=0)
        )
        _seed_transactions(
            conn,
            [("2026-02-10", "Groceries", "WOOLWORTHS", 100.0, 0, 0)],
        )
        bootstrap_forecast_period(conn, mp_id, "2026-07-01", "2027-06-30")
        f_id = list_forecasts(conn, mp_id, "2026-07-01", "2027-06-30")[0].id
        return conn, f_id

    def test_no_change_no_reason_required(self, tmp_path):
        conn, f_id = self._setup_with_one_forecast(tmp_path)
        # Setting forecast_value = actual_value (100) without reason is fine
        result = save_forecast_override(conn, f_id, 100.0, None)
        assert result.forecast_value == 100.0
        assert result.override_reason is None

    def test_change_requires_reason(self, tmp_path):
        conn, f_id = self._setup_with_one_forecast(tmp_path)
        with pytest.raises(ForecastOverrideError):
            save_forecast_override(conn, f_id, 500.0, None)
        with pytest.raises(ForecastOverrideError):
            save_forecast_override(conn, f_id, 500.0, "")
        with pytest.raises(ForecastOverrideError):
            save_forecast_override(conn, f_id, 500.0, "   ")

    def test_change_with_reason_persists(self, tmp_path):
        conn, f_id = self._setup_with_one_forecast(tmp_path)
        result = save_forecast_override(conn, f_id, 500.0, "CPI projection")
        assert result.forecast_value == 500.0
        assert result.override_reason == "CPI projection"

    def test_unknown_forecast_id_raises(self, tmp_path):
        conn = _conn(tmp_path)
        with pytest.raises(ForecastOverrideError):
            save_forecast_override(conn, 999, 100.0, "x")

    def test_one_cent_diff_is_treated_as_no_change(self, tmp_path):
        conn, f_id = self._setup_with_one_forecast(tmp_path)
        # 100.005 rounds within tolerance of 100.0 actual
        result = save_forecast_override(conn, f_id, 100.005, None)
        assert result.forecast_value == 100.005
