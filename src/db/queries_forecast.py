"""CRUD wrappers for forecast_categories and forecasts (NSWTG Plan Section D).

Style mirrors `src/db/queries_estate.py`: plain functions taking a
sqlite3.Connection, returning DTOs from `src/models/forecast.py`. The
mutation helpers commit before returning so callers don't have to remember.

`compute_actual_value` derives an aggregate from the `transactions` table for
a given category over a date window. It is read-only and does not write
to the DB — service-layer code is responsible for persisting the result
into `forecasts.actual_value`.
"""

from __future__ import annotations

import sqlite3
from dataclasses import asdict, fields, replace
from datetime import date

from src.models.forecast import Forecast, ForecastCategory, OneOffEvent

# section → which transactions column to sum
_SECTION_TO_COLUMN = {
    "D_income": "deposit",
    "D_expenditure": "withdrawal",
}

# Average days per month (365.25 / 12) for converting a coverage span to months.
_DAYS_PER_MONTH = 30.4375


def _row_to_dto(row: sqlite3.Row, dto_class):
    valid = {f.name for f in fields(dto_class)}
    kwargs = {k: row[k] for k in row.keys() if k in valid}
    return dto_class(**kwargs)


# ---------------------------------------------------------------------------
# forecast_categories
# ---------------------------------------------------------------------------

def insert_forecast_category(conn: sqlite3.Connection, fc: ForecastCategory) -> int:
    cur = conn.execute(
        "INSERT INTO forecast_categories (section, category_name, display_order) "
        "VALUES (?, ?, ?)",
        (fc.section, fc.category_name, fc.display_order),
    )
    conn.commit()
    return cur.lastrowid


def upsert_forecast_category(
    conn: sqlite3.Connection, fc: ForecastCategory
) -> int:
    """Idempotent insert — returns the existing id if (section, category_name)
    already exists, otherwise inserts and returns the new id. display_order
    is updated on hit so reseeding can fix ordering drift.
    """
    existing = conn.execute(
        "SELECT id FROM forecast_categories WHERE section = ? AND category_name = ?",
        (fc.section, fc.category_name),
    ).fetchone()
    if existing:
        conn.execute(
            "UPDATE forecast_categories SET display_order = ? WHERE id = ?",
            (fc.display_order, existing["id"]),
        )
        conn.commit()
        return int(existing["id"])
    return insert_forecast_category(conn, fc)


def get_forecast_category(
    conn: sqlite3.Connection, fc_id: int
) -> ForecastCategory | None:
    row = conn.execute(
        "SELECT * FROM forecast_categories WHERE id = ?", (fc_id,)
    ).fetchone()
    return _row_to_dto(row, ForecastCategory) if row else None


def list_forecast_categories(
    conn: sqlite3.Connection, section: str | None = None
) -> list[ForecastCategory]:
    if section:
        rows = conn.execute(
            "SELECT * FROM forecast_categories WHERE section = ? "
            "ORDER BY display_order, category_name",
            (section,),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM forecast_categories "
            "ORDER BY section, display_order, category_name"
        ).fetchall()
    return [_row_to_dto(r, ForecastCategory) for r in rows]


# ---------------------------------------------------------------------------
# forecasts
# ---------------------------------------------------------------------------

def insert_forecast(conn: sqlite3.Connection, f: Forecast) -> int:
    data = asdict(f)
    data.pop("id", None)
    data.pop("last_updated_at", None)
    cols = ", ".join(data.keys())
    placeholders = ", ".join("?" for _ in data)
    cur = conn.execute(
        f"INSERT INTO forecasts ({cols}) VALUES ({placeholders})",
        tuple(data.values()),
    )
    conn.commit()
    return cur.lastrowid


def upsert_forecast(conn: sqlite3.Connection, f: Forecast) -> int:
    """Insert or update by (managed_person_id, period_start, period_end, category_id).

    Returns the row id. Bumps `last_updated_at` to now on every call.
    """
    existing = conn.execute(
        "SELECT id FROM forecasts "
        "WHERE managed_person_id = ? AND period_start = ? "
        "  AND period_end = ? AND category_id = ?",
        (f.managed_person_id, f.period_start, f.period_end, f.category_id),
    ).fetchone()
    if existing:
        update_forecast(conn, int(existing["id"]), f)
        return int(existing["id"])
    return insert_forecast(conn, f)


def get_forecast(conn: sqlite3.Connection, f_id: int) -> Forecast | None:
    row = conn.execute(
        "SELECT * FROM forecasts WHERE id = ?", (f_id,)
    ).fetchone()
    return _row_to_dto(row, Forecast) if row else None


def update_forecast(conn: sqlite3.Connection, f_id: int, f: Forecast) -> None:
    """Update the editable fields on a forecast row.

    Identity columns (managed_person_id, period_start/end, category_id) are
    NOT updated — a forecast row's keying tuple is immutable. Bumps
    `last_updated_at` to now.
    """
    conn.execute(
        "UPDATE forecasts SET "
        "  actual_value = ?, forecast_value = ?, override_reason = ?, "
        "  last_updated_at = datetime('now') "
        "WHERE id = ?",
        (f.actual_value, f.forecast_value, f.override_reason, f_id),
    )
    conn.commit()


def list_forecasts(
    conn: sqlite3.Connection,
    managed_person_id: int,
    period_start: str,
    period_end: str,
    section: str | None = None,
) -> list[Forecast]:
    """Return forecasts for the given person + period, optionally filtered by section.

    Ordered by forecast_categories.display_order then category_name so the UI
    can render directly without resorting.
    """
    if section:
        rows = conn.execute(
            "SELECT f.* FROM forecasts f "
            "JOIN forecast_categories fc ON fc.id = f.category_id "
            "WHERE f.managed_person_id = ? AND f.period_start = ? "
            "  AND f.period_end = ? AND fc.section = ? "
            "ORDER BY fc.display_order, fc.category_name",
            (managed_person_id, period_start, period_end, section),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT f.* FROM forecasts f "
            "JOIN forecast_categories fc ON fc.id = f.category_id "
            "WHERE f.managed_person_id = ? AND f.period_start = ? "
            "  AND f.period_end = ? "
            "ORDER BY fc.section, fc.display_order, fc.category_name",
            (managed_person_id, period_start, period_end),
        ).fetchall()
    return [_row_to_dto(r, Forecast) for r in rows]


# ---------------------------------------------------------------------------
# Aggregate helper
# ---------------------------------------------------------------------------

def compute_actual_value(
    conn: sqlite3.Connection,
    category_name: str,
    section: str,
    date_from: str,
    date_to: str,
) -> float:
    """Sum the relevant transactions column for `category_name` over [date_from, date_to].

    Internal transfers are always excluded so they don't double-count
    deposits/withdrawals between Linda's own accounts. Returns 0.0 when no
    rows match (rather than None) so the UI never gets a NULL.

    Caller is responsible for mapping a forecast section to the same
    `category` strings used at parse time — for S4 the two name spaces are
    aligned (see `src/config/categories.json`).
    """
    column = _SECTION_TO_COLUMN.get(section)
    if column is None:
        return 0.0
    row = conn.execute(
        f"SELECT COALESCE(SUM({column}), 0) AS total "
        "FROM transactions "
        "WHERE category = ? "
        "  AND date >= ? AND date <= ? "
        "  AND COALESCE(is_internal_transfer, 0) = 0",
        (category_name, date_from, date_to),
    ).fetchone()
    return float(row["total"] or 0.0)


def section_coverage_days(
    conn: sqlite3.Connection,
    section: str,
    date_from: str,
    date_to: str,
) -> int:
    """Span (in inclusive days) of dates carrying real data for `section` in the window.

    Coverage is computed section-wide (any non-internal transaction whose
    relevant column is non-null), not per-category: a category with a single
    transaction must not read as "1 day of data" and annualize to absurdity.
    Returns 0 when the section has no data in the window.
    """
    column = _SECTION_TO_COLUMN.get(section)
    if column is None:
        return 0
    row = conn.execute(
        f"SELECT MIN(date) AS lo, MAX(date) AS hi "
        "FROM transactions "
        f"WHERE {column} IS NOT NULL "
        "  AND date >= ? AND date <= ? "
        "  AND COALESCE(is_internal_transfer, 0) = 0",
        (date_from, date_to),
    ).fetchone()
    if not row or row["lo"] is None:
        return 0
    return (date.fromisoformat(row["hi"]) - date.fromisoformat(row["lo"])).days + 1


def compute_actual_with_coverage(
    conn: sqlite3.Connection,
    category_name: str,
    section: str,
    date_from: str,
    date_to: str,
) -> tuple[float, int, float]:
    """Return (raw_total, section_coverage_days, months_with_data) for a category.

    `raw_total` reuses `compute_actual_value`. Coverage is section-wide so all
    categories in a section share one annualization basis. `months_with_data`
    is the coverage span expressed in average months for display.
    """
    total = compute_actual_value(conn, category_name, section, date_from, date_to)
    cov_days = section_coverage_days(conn, section, date_from, date_to)
    months = round(cov_days / _DAYS_PER_MONTH, 1) if cov_days else 0.0
    return total, cov_days, months


# ---------------------------------------------------------------------------
# one_off_events (Section E) + one_off_dismissals (candidate triage, 007)
# ---------------------------------------------------------------------------

def insert_one_off_event(conn: sqlite3.Connection, event: OneOffEvent) -> int:
    data = asdict(event)
    data.pop("id", None)
    cols = ", ".join(data.keys())
    placeholders = ", ".join("?" for _ in data)
    cur = conn.execute(
        f"INSERT INTO one_off_events ({cols}) VALUES ({placeholders})",
        tuple(data.values()),
    )
    conn.commit()
    return cur.lastrowid


def update_one_off_event(conn: sqlite3.Connection, event: OneOffEvent) -> None:
    if event.id is None:
        raise ValueError("event.id is required for update")
    data = asdict(event)
    event_id = data.pop("id")
    assignments = ", ".join(f"{col} = ?" for col in data)
    conn.execute(
        f"UPDATE one_off_events SET {assignments}, updated_at = datetime('now') "
        "WHERE id = ?",
        (*data.values(), event_id),
    )
    conn.commit()


def list_one_off_events(
    conn: sqlite3.Connection,
    managed_person_id: int,
    status: str | None = None,
) -> list[OneOffEvent]:
    sql = "SELECT * FROM one_off_events WHERE managed_person_id = ?"
    params: list = [managed_person_id]
    if status is not None:
        sql += " AND status = ?"
        params.append(status)
    sql += " ORDER BY date_occurred IS NULL, date_occurred, id"
    rows = conn.execute(sql, params).fetchall()
    return [_row_to_dto(r, OneOffEvent) for r in rows]


def insert_one_off_dismissal(
    conn: sqlite3.Connection,
    transaction_id: int,
    reason: str | None = None,
    recorded_by: str | None = None,
) -> None:
    """Mark a candidate transaction as reviewed-and-not-a-one-off (idempotent)."""
    conn.execute(
        "INSERT INTO one_off_dismissals (transaction_id, reason, recorded_by) "
        "VALUES (?, ?, ?) "
        "ON CONFLICT(transaction_id) DO UPDATE SET "
        "  reason = excluded.reason, recorded_by = excluded.recorded_by, "
        "  recorded_at = datetime('now')",
        (transaction_id, reason, recorded_by),
    )
    conn.commit()


def dismissed_transaction_ids(conn: sqlite3.Connection) -> set[int]:
    rows = conn.execute("SELECT transaction_id FROM one_off_dismissals").fetchall()
    return {r["transaction_id"] for r in rows}
