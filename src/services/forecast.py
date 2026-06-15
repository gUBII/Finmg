"""Forecast service layer.

Two operations:

- `bootstrap_forecast_period` — for a given person + forecast period
  [period_start, period_end] (forward-looking window, typically the next 12
  months), upserts one forecast row per forecast_category, with
  `actual_value` derived from the matching trailing-12m window of
  transactions and `forecast_value` defaulted to `actual_value`. Pure
  idempotent: re-running refreshes `actual_value` without clobbering
  Linda-edited `forecast_value` or `override_reason`.

- `save_forecast_override` — validates the NCAT invariant that any
  `forecast_value` differing from `actual_value` requires a non-empty
  `override_reason`, then persists.

Conventions:
- Periods are ISO date strings (YYYY-MM-DD), inclusive both ends.
- Trailing window matches the forecast window length, ending the day
  before `period_start` — i.e. for a forecast 2026-07-01..2027-06-30 the
  actuals window is 2025-07-01..2026-06-30.
"""

from __future__ import annotations

import sqlite3
from dataclasses import replace
from datetime import date, timedelta

from src.db.queries_forecast import (
    compute_actual_value,
    get_forecast,
    list_forecast_categories,
    list_forecasts,
    update_forecast,
    upsert_forecast,
)
from src.models.forecast import Forecast

# Provenance marker appended to generator-authored override reasons. Lets a
# re-run refresh its own prior proposals while leaving Linda's manual edits
# (which never carry this tag) untouched.
_AUTO_TAG = " [auto]"
_MONEY_TOLERANCE = 0.01


def _trailing_window(period_start: str, period_end: str) -> tuple[str, str]:
    """Return the trailing-actuals window aligned to the forecast window length.

    For a 12-month forecast 2026-07-01..2027-06-30, the trailing window is
    2025-07-01..2026-06-30. Length is preserved (in days, inclusive of both
    ends) so a 6-month forecast pulls a 6-month actuals window.
    """
    start = date.fromisoformat(period_start)
    end = date.fromisoformat(period_end)
    length_days = (end - start).days
    trailing_end = start - timedelta(days=1)
    trailing_start = trailing_end - timedelta(days=length_days)
    return trailing_start.isoformat(), trailing_end.isoformat()


def bootstrap_forecast_period(
    conn: sqlite3.Connection,
    managed_person_id: int,
    period_start: str,
    period_end: str,
) -> int:
    """Materialise one forecast row per forecast_category for this period.

    Refreshes `actual_value` on every call. Preserves existing
    `forecast_value` and `override_reason` so Linda's overrides survive
    re-bootstrapping (e.g. after new transactions land).

    Returns the count of rows materialised.
    """
    categories = list_forecast_categories(conn)
    trailing_start, trailing_end = _trailing_window(period_start, period_end)

    materialised = 0
    for cat in categories:
        actual = compute_actual_value(
            conn, cat.category_name, cat.section, trailing_start, trailing_end
        )
        # Look up any existing row to preserve Linda's edits.
        existing_rows = list_forecasts(
            conn,
            managed_person_id,
            period_start,
            period_end,
            section=cat.section,
        )
        existing = next((r for r in existing_rows if r.category_id == cat.id), None)

        if existing is None:
            forecast_value = actual
            override_reason = None
        else:
            forecast_value = (
                existing.forecast_value
                if existing.forecast_value is not None
                else actual
            )
            override_reason = existing.override_reason

        upsert_forecast(
            conn,
            Forecast(
                managed_person_id=managed_person_id,
                period_start=period_start,
                period_end=period_end,
                category_id=cat.id,
                actual_value=actual,
                forecast_value=forecast_value,
                override_reason=override_reason,
            ),
        )
        materialised += 1
    return materialised


def _is_manual_override(row: Forecast) -> bool:
    """True if this row carries a Linda-authored override the generator must keep.

    A manual override has a non-empty reason that does NOT end with the
    generator's provenance tag. Rows still at their bootstrap default
    (forecast == actual, no reason) or previously written by the generator
    (reason tagged `[auto]`) are eligible for refresh.
    """
    reason = (row.override_reason or "").strip()
    if not reason:
        return False
    return not reason.endswith(_AUTO_TAG.strip())


def generate_forecast_proposals(
    conn: sqlite3.Connection,
    managed_person_id: int,
    period_start: str,
    period_end: str,
    benchmarks: dict | None = None,
) -> dict:
    """Fill annualized, benchmark-corrected proposals for every Section D row.

    Bootstraps the period first (refreshing raw `actual_value` and keying the
    rows), then writes each proposal's `forecast_value` + `override_reason`,
    skipping rows Linda has manually overridden. Idempotent: re-running with
    the same data reproduces the same proposals.

    Returns `{updated, skipped, flagged}`.
    """
    from src.services.forecast_generator import generate_category_proposals

    bootstrap_forecast_period(conn, managed_person_id, period_start, period_end)
    existing = list_forecasts(conn, managed_person_id, period_start, period_end)
    by_cat = {r.category_id: r for r in existing}

    proposals = generate_category_proposals(
        conn, managed_person_id, period_start, period_end, benchmarks=benchmarks
    )

    updated = skipped = flagged = 0
    for p in proposals:
        if p.flag:
            flagged += 1
        row = by_cat.get(p.category_id)
        if row is not None and _is_manual_override(row):
            skipped += 1
            continue

        if p.override_reason and abs(p.proposed_value - p.actual_value) > _MONEY_TOLERANCE:
            reason = f"{p.override_reason}{_AUTO_TAG}"
        else:
            reason = None

        upsert_forecast(
            conn,
            Forecast(
                managed_person_id=managed_person_id,
                period_start=period_start,
                period_end=period_end,
                category_id=p.category_id,
                actual_value=p.actual_value,
                forecast_value=p.proposed_value,
                override_reason=reason,
            ),
        )
        updated += 1

    return {"updated": updated, "skipped": skipped, "flagged": flagged}


class ForecastOverrideError(ValueError):
    """Raised when a forecast_value differs from actual without a reason."""


def save_forecast_override(
    conn: sqlite3.Connection,
    forecast_id: int,
    new_forecast_value: float,
    override_reason: str | None,
) -> Forecast:
    """Persist Linda's forecast_value + override_reason on an existing row.

    Invariant: if `new_forecast_value` differs from `actual_value` by more than
    1 cent, `override_reason` must be a non-empty string. The view should
    surface this as an inline error rather than rely on the exception.
    """
    current = get_forecast(conn, forecast_id)
    if current is None:
        raise ForecastOverrideError(f"forecast {forecast_id} not found")

    actual = current.actual_value or 0.0
    diff = abs(new_forecast_value - actual)
    reason = (override_reason or "").strip()
    if diff > 0.01 and not reason:
        raise ForecastOverrideError(
            "override_reason is required when forecast_value differs from actual_value"
        )

    patched = replace(
        current,
        forecast_value=new_forecast_value,
        override_reason=reason or None,
    )
    update_forecast(conn, forecast_id, patched)
    refetched = get_forecast(conn, forecast_id)
    assert refetched is not None  # we just updated it
    return refetched
