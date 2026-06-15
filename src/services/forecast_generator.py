"""Annualized forecast generator (NSWTG Plan Section D).

Produces a realistic full-year proposal for each forecast category, instead of
copying an incomplete trailing-actual sum. For each category:

  1. Coverage — how many days/months of real data exist (section-wide).
  2. Annualize — scale the trailing actual to the forecast-window length,
     mirroring the linear extrapolation in services/compliance/rules.py
     (`_project_to_period`), but with the DATA-COVERAGE span as the
     denominator so edge/mid-window gaps don't deflate the estimate.
  3. Benchmark / one-off override — domain knowledge from
     config/forecast_benchmarks.json takes precedence over annualization
     (e.g. DSP from a published fortnightly rate; one-off salary excluded;
     rent from a stated cycle amount). A null benchmark amount FLAGS for
     input; it never fabricates a number.
  4. Override reason — set whenever the proposal differs from the raw actual,
     satisfying the NCAT invariant up front so a later Save won't trip
     `ForecastOverrideError`.

This module is pure (no DB writes). Persistence lives in services/forecast.py.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from src.db.queries_forecast import (
    compute_actual_with_coverage,
    list_forecast_categories,
)

_BENCHMARKS_PATH = (
    Path(__file__).resolve().parent.parent / "config" / "forecast_benchmarks.json"
)

# Cycle → multiplier to reach a 12-month equivalent.
_CYCLE_PER_YEAR = {
    "weekly": 52.0,
    "fortnightly": 26.0893,
    "monthly": 12.0,
    "quarterly": 4.0,
    "annual": 1.0,
}

_MONEY_TOLERANCE = 0.01


@dataclass(frozen=True)
class CategoryProposal:
    """One generated Section D proposal, before it is written to `forecasts`."""

    category_id: int
    category_name: str
    section: str
    actual_value: float
    months_of_data: float
    annualized_estimate: float
    proposed_value: float
    override_reason: str | None = None
    flag: str | None = None


@lru_cache(maxsize=1)
def load_forecast_benchmarks() -> dict:
    """Load and cache the benchmark config. Pure data; safe to cache."""
    with open(_BENCHMARKS_PATH, encoding="utf-8") as fh:
        return json.load(fh)


def _annualize(actual: float, period_days: int, coverage_days: int) -> float:
    """Scale `actual` accrued over `coverage_days` to a `period_days` window."""
    if coverage_days <= 0 or period_days <= 0:
        return actual
    return actual * period_days / coverage_days


def _propose_one(
    *,
    category_id: int,
    category_name: str,
    section: str,
    actual: float,
    coverage_days: int,
    months: float,
    period_days: int,
    benchmarks: dict,
) -> CategoryProposal:
    ann_cfg = benchmarks.get("annualization", {})
    min_cov = int(ann_cfg.get("min_coverage_days", 14))
    fortnights = float(ann_cfg.get("fortnights_per_year", 26.0893))

    # --- annualized estimate (informational + default proposal) ---------------
    if coverage_days >= min_cov:
        annualized = _annualize(actual, period_days, coverage_days)
        base_flag: str | None = None
    else:
        annualized = actual
        base_flag = "Insufficient data coverage — shown unscaled; verify."

    proposed = annualized
    reason: str | None = None
    flag = base_flag

    # --- benchmark / one-off precedence (overrides annualization) -------------
    one_off = benchmarks.get("one_off_categories", {})
    income_bm = benchmarks.get("income_benchmarks", {})
    exp_bm = benchmarks.get("expenditure_benchmarks", {})

    if category_name in one_off:
        proposed = 0.0
        reason = one_off[category_name].get("reason")
    elif section == "D_income" and category_name in income_bm:
        bm = income_bm[category_name]
        if bm.get("type") == "fortnightly_rate" and bm.get("rate") is not None:
            proposed = float(bm["rate"]) * fortnights
            reason = bm.get("reason")
    elif section == "D_expenditure" and category_name in exp_bm:
        bm = exp_bm[category_name]
        if bm.get("type") == "cycle_amount":
            amount = bm.get("amount")
            if amount is None:
                proposed = 0.0
                flag = "Benchmark needs input — set the amount before relying on this."
            else:
                proposed = float(amount) * _CYCLE_PER_YEAR.get(bm.get("cycle", "weekly"), 52.0)
                reason = bm.get("reason")

    # --- seasonality flag (advisory; does not change the number) --------------
    seasonal = benchmarks.get("seasonality_flags", {})
    if category_name in seasonal and flag is None:
        flag = seasonal[category_name]

    # --- NCAT invariant: any divergence from raw actual needs a reason --------
    if abs(proposed - actual) > _MONEY_TOLERANCE and not reason:
        reason = (
            f"Annualized from {months} months of data "
            f"(x{period_days / coverage_days:.2f}) to a full-year equivalent."
            if coverage_days >= min_cov
            else "Adjusted from incomplete trailing actuals; verify."
        )
    if abs(proposed - actual) <= _MONEY_TOLERANCE:
        reason = None

    return CategoryProposal(
        category_id=category_id,
        category_name=category_name,
        section=section,
        actual_value=actual,
        months_of_data=months,
        annualized_estimate=annualized,
        proposed_value=proposed,
        override_reason=reason,
        flag=flag,
    )


def generate_category_proposals(
    conn,
    managed_person_id: int,
    period_start: str,
    period_end: str,
    benchmarks: dict | None = None,
) -> list[CategoryProposal]:
    """Build a proposal for every Section D forecast_category over the period.

    `benchmarks` defaults to the shipped config; tests inject their own. Pure —
    reads transactions, writes nothing. The trailing-actuals window is computed
    by the caller's convention; here we sum over [trailing_start, trailing_end]
    derived the same way the service does.
    """
    from src.services.forecast import _trailing_window  # local import avoids cycle

    if benchmarks is None:
        benchmarks = load_forecast_benchmarks()

    trailing_start, trailing_end = _trailing_window(period_start, period_end)
    from datetime import date as _date

    period_days = (
        _date.fromisoformat(trailing_end) - _date.fromisoformat(trailing_start)
    ).days + 1

    proposals: list[CategoryProposal] = []
    for cat in list_forecast_categories(conn):
        if cat.section not in ("D_income", "D_expenditure"):
            continue
        actual, cov_days, months = compute_actual_with_coverage(
            conn, cat.category_name, cat.section, trailing_start, trailing_end
        )
        proposals.append(
            _propose_one(
                category_id=cat.id,
                category_name=cat.category_name,
                section=cat.section,
                actual=actual,
                coverage_days=cov_days,
                months=months,
                period_days=period_days,
                benchmarks=benchmarks,
            )
        )
    return proposals
