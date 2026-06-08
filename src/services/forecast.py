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
