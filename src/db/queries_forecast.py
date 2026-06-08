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

from src.models.forecast import Forecast, ForecastCategory

# section → which transactions column to sum
_SECTION_TO_COLUMN = {
    "D_income": "deposit",
    "D_expenditure": "withdrawal",
}


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
