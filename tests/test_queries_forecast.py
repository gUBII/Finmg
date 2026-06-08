"""Tests for queries_forecast.py — CRUD + actual-value aggregation."""

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
    compute_actual_value,
    get_forecast,
    get_forecast_category,
    insert_forecast,
    insert_forecast_category,
    list_forecast_categories,
    list_forecasts,
    update_forecast,
    upsert_forecast,
    upsert_forecast_category,
)
from src.models.estate import ManagedPerson
from src.models.forecast import Forecast, ForecastCategory
from src.models.transaction import AccountMeta, Transaction


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


def _seed_transactions(conn, rows: list[tuple[str, str, float, float, int]]) -> None:
    """rows: (date_iso, description, withdrawal, deposit, internal_transfer)"""
    meta = AccountMeta(
        account_type="ACCESS ACCOUNT",
        account_name="GENTILI RENATO",
        bsb="013711",
        account_number="437669532",
        balance=0.0,
        report_start="2026-02-08",
        report_end="2026-06-08",
    )
    txns = []
    for d, desc, w, dep, it in rows:
        y, m, day = (int(x) for x in d.split("-"))
        # Re-derive category from description: tests pass it as the description
        # for simplicity; the test exercise sums by category column so we set
        # the category in the description's first token. Real ingestion uses
        # the categoriser; here we set it directly via the Transaction DTO.
        txns.append(
            Transaction(
                date=date(y, m, day),
                description=desc,
                withdrawal=w or None,
                deposit=dep or None,
                account_number="437669532",
                account_type="ACCESS ACCOUNT",
                month=f"{y}-{m:02d}",
                category=desc.split("|")[0],
                is_internal_transfer=bool(it),
            )
        )
    insert_pdf_and_transactions(conn, meta, txns, "test.pdf", "deadbeef" + "0" * 56)


# ---------------------------------------------------------------------------
# forecast_categories
# ---------------------------------------------------------------------------


class TestForecastCategories:
    def test_round_trip(self, tmp_path):
        conn = _conn(tmp_path)
        fc_id = insert_forecast_category(
            conn,
            ForecastCategory(section="D_income", category_name="Disability Support Pension", display_order=0),
        )
        fetched = get_forecast_category(conn, fc_id)
        assert fetched is not None
        assert fetched.section == "D_income"
        assert fetched.category_name == "Disability Support Pension"
        assert fetched.display_order == 0

    def test_upsert_inserts_when_missing(self, tmp_path):
        conn = _conn(tmp_path)
        fc_id = upsert_forecast_category(
            conn, ForecastCategory(section="D_expenditure", category_name="Groceries", display_order=1)
        )
        assert get_forecast_category(conn, fc_id).category_name == "Groceries"

    def test_upsert_returns_existing_id_and_updates_order(self, tmp_path):
        conn = _conn(tmp_path)
        a = upsert_forecast_category(
            conn, ForecastCategory(section="D_income", category_name="Bonus", display_order=5)
        )
        b = upsert_forecast_category(
            conn, ForecastCategory(section="D_income", category_name="Bonus", display_order=99)
        )
        assert a == b
        assert get_forecast_category(conn, a).display_order == 99

    def test_list_filtered_by_section_and_ordered(self, tmp_path):
        conn = _conn(tmp_path)
        insert_forecast_category(conn, ForecastCategory(section="D_expenditure", category_name="Rent", display_order=0))
        insert_forecast_category(conn, ForecastCategory(section="D_expenditure", category_name="Groceries", display_order=1))
        insert_forecast_category(conn, ForecastCategory(section="D_income", category_name="Bonus", display_order=0))
        rows = list_forecast_categories(conn, section="D_expenditure")
        assert [r.category_name for r in rows] == ["Rent", "Groceries"]

    def test_list_unfiltered_returns_all_sections(self, tmp_path):
        conn = _conn(tmp_path)
        insert_forecast_category(conn, ForecastCategory(section="D_expenditure", category_name="Rent", display_order=0))
        insert_forecast_category(conn, ForecastCategory(section="D_income", category_name="Bonus", display_order=0))
        rows = list_forecast_categories(conn)
        assert len(rows) == 2
        assert {r.section for r in rows} == {"D_expenditure", "D_income"}

    def test_get_returns_none_for_missing_id(self, tmp_path):
        conn = _conn(tmp_path)
        assert get_forecast_category(conn, 999) is None


# ---------------------------------------------------------------------------
# forecasts
# ---------------------------------------------------------------------------


class TestForecasts:
    def _setup(self, tmp_path):
        conn = _conn(tmp_path)
        mp_id = _seed_ron(conn)
        cat_id = insert_forecast_category(
            conn, ForecastCategory(section="D_expenditure", category_name="Groceries", display_order=0)
        )
        return conn, mp_id, cat_id

    def test_round_trip(self, tmp_path):
        conn, mp_id, cat_id = self._setup(tmp_path)
        f_id = insert_forecast(
            conn,
            Forecast(
                managed_person_id=mp_id,
                period_start="2026-07-01",
                period_end="2027-06-30",
                category_id=cat_id,
                actual_value=1234.56,
                forecast_value=1234.56,
                override_reason=None,
            ),
        )
        fetched = get_forecast(conn, f_id)
        assert fetched.actual_value == 1234.56
        assert fetched.forecast_value == 1234.56
        assert fetched.override_reason is None

    def test_update_persists_editable_fields(self, tmp_path):
        conn, mp_id, cat_id = self._setup(tmp_path)
        f_id = insert_forecast(
            conn,
            Forecast(
                managed_person_id=mp_id,
                period_start="2026-07-01",
                period_end="2027-06-30",
                category_id=cat_id,
                actual_value=1000.0,
                forecast_value=1000.0,
            ),
        )
        original = get_forecast(conn, f_id)
        patched = Forecast(
            managed_person_id=original.managed_person_id,
            period_start=original.period_start,
            period_end=original.period_end,
            category_id=original.category_id,
            id=original.id,
            actual_value=1000.0,
            forecast_value=1500.0,
            override_reason="Projected price rise per CPI",
        )
        update_forecast(conn, f_id, patched)
        refetched = get_forecast(conn, f_id)
        assert refetched.forecast_value == 1500.0
        assert refetched.override_reason == "Projected price rise per CPI"

    def test_upsert_inserts_when_missing(self, tmp_path):
        conn, mp_id, cat_id = self._setup(tmp_path)
        f_id = upsert_forecast(
            conn,
            Forecast(
                managed_person_id=mp_id,
                period_start="2026-07-01",
                period_end="2027-06-30",
                category_id=cat_id,
                actual_value=500.0,
                forecast_value=500.0,
            ),
        )
        assert get_forecast(conn, f_id) is not None

    def test_upsert_updates_when_present(self, tmp_path):
        conn, mp_id, cat_id = self._setup(tmp_path)
        a = upsert_forecast(
            conn,
            Forecast(
                managed_person_id=mp_id,
                period_start="2026-07-01",
                period_end="2027-06-30",
                category_id=cat_id,
                actual_value=500.0,
                forecast_value=500.0,
            ),
        )
        b = upsert_forecast(
            conn,
            Forecast(
                managed_person_id=mp_id,
                period_start="2026-07-01",
                period_end="2027-06-30",
                category_id=cat_id,
                actual_value=600.0,
                forecast_value=800.0,
                override_reason="bumped",
            ),
        )
        assert a == b
        f = get_forecast(conn, a)
        assert f.forecast_value == 800.0
        assert f.override_reason == "bumped"

    def test_list_filtered_by_section(self, tmp_path):
        conn = _conn(tmp_path)
        mp_id = _seed_ron(conn)
        inc_id = insert_forecast_category(
            conn, ForecastCategory(section="D_income", category_name="Bonus", display_order=0)
        )
        exp_id = insert_forecast_category(
            conn, ForecastCategory("D_expenditure", "Groceries", 0)
        )
        common = dict(
            managed_person_id=mp_id, period_start="2026-07-01", period_end="2027-06-30"
        )
        insert_forecast(conn, Forecast(**common, category_id=inc_id, actual_value=100.0, forecast_value=100.0))
        insert_forecast(conn, Forecast(**common, category_id=exp_id, actual_value=200.0, forecast_value=200.0))
        income = list_forecasts(conn, mp_id, "2026-07-01", "2027-06-30", section="D_income")
        assert len(income) == 1
        assert income[0].category_id == inc_id

    def test_list_unfiltered_returns_all_sections(self, tmp_path):
        conn = _conn(tmp_path)
        mp_id = _seed_ron(conn)
        inc_id = insert_forecast_category(conn, ForecastCategory(section="D_income", category_name="Bonus", display_order=0))
        exp_id = insert_forecast_category(conn, ForecastCategory("D_expenditure", "Groceries", 0))
        common = dict(
            managed_person_id=mp_id, period_start="2026-07-01", period_end="2027-06-30"
        )
        insert_forecast(conn, Forecast(**common, category_id=inc_id, actual_value=100.0, forecast_value=100.0))
        insert_forecast(conn, Forecast(**common, category_id=exp_id, actual_value=200.0, forecast_value=200.0))
        rows = list_forecasts(conn, mp_id, "2026-07-01", "2027-06-30")
        assert len(rows) == 2

    def test_get_returns_none_for_missing_id(self, tmp_path):
        conn, _, _ = self._setup(tmp_path)
        assert get_forecast(conn, 999) is None


# ---------------------------------------------------------------------------
# compute_actual_value
# ---------------------------------------------------------------------------


class TestComputeActualValue:
    def test_sums_withdrawals_for_expenditure_section(self, tmp_path):
        conn = _conn(tmp_path)
        _seed_transactions(
            conn,
            [
                ("2026-02-10", "Groceries|WOOLWORTHS", 100.0, 0, 0),
                ("2026-03-15", "Groceries|COLES", 50.0, 0, 0),
                ("2026-04-20", "Groceries|IGA", 25.0, 0, 0),
                ("2026-05-01", "Fast food & Restaurant|MCDONALDS", 30.0, 0, 0),  # not Groceries
            ],
        )
        total = compute_actual_value(
            conn, "Groceries", "D_expenditure", "2026-01-01", "2026-06-30"
        )
        assert total == 175.0

    def test_sums_deposits_for_income_section(self, tmp_path):
        conn = _conn(tmp_path)
        _seed_transactions(
            conn,
            [
                ("2026-02-15", "Disability Support Pension|CTRLINK PENS", 0, 1500.0, 0),
                ("2026-03-15", "Disability Support Pension|CTRLINK PENS", 0, 1500.0, 0),
                ("2026-04-15", "Disability Support Pension|CTRLINK PENS", 0, 1500.0, 0),
                ("2026-05-01", "Bonus|XMAS BONUS", 0, 500.0, 0),  # not DSP
            ],
        )
        total = compute_actual_value(
            conn, "Disability Support Pension", "D_income", "2026-01-01", "2026-06-30"
        )
        assert total == 4500.0

    def test_excludes_internal_transfers(self, tmp_path):
        conn = _conn(tmp_path)
        _seed_transactions(
            conn,
            [
                ("2026-02-10", "Groceries|WOOLWORTHS", 100.0, 0, 0),
                ("2026-02-20", "Groceries|FUNDS TFER", 999.0, 0, 1),  # internal transfer
            ],
        )
        total = compute_actual_value(
            conn, "Groceries", "D_expenditure", "2026-01-01", "2026-12-31"
        )
        assert total == 100.0

    def test_respects_date_window(self, tmp_path):
        conn = _conn(tmp_path)
        _seed_transactions(
            conn,
            [
                ("2026-01-10", "Groceries|JAN", 100.0, 0, 0),
                ("2026-02-10", "Groceries|FEB", 200.0, 0, 0),
                ("2026-03-10", "Groceries|MAR", 300.0, 0, 0),
            ],
        )
        total = compute_actual_value(
            conn, "Groceries", "D_expenditure", "2026-02-01", "2026-02-28"
        )
        assert total == 200.0

    def test_returns_zero_when_no_matching_rows(self, tmp_path):
        conn = _conn(tmp_path)
        _seed_transactions(
            conn,
            [("2026-02-10", "Groceries|WOOLWORTHS", 100.0, 0, 0)],
        )
        total = compute_actual_value(
            conn, "Nonexistent", "D_expenditure", "2026-01-01", "2026-12-31"
        )
        assert total == 0.0

    def test_returns_zero_for_unknown_section(self, tmp_path):
        conn = _conn(tmp_path)
        _seed_transactions(
            conn,
            [("2026-02-10", "Groceries|WOOLWORTHS", 100.0, 0, 0)],
        )
        total = compute_actual_value(
            conn, "Groceries", "D_NOT_A_SECTION", "2026-01-01", "2026-12-31"
        )
        assert total == 0.0
