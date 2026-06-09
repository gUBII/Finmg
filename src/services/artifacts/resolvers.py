"""Resolver registry for the artifact engine.

A resolver is a small Python function `(ctx, **args) -> value` registered under a
string key. The JSON field map names the resolver + args; the engine looks it up
here. A dozen parameterised generics cover hundreds of PDF fields — logic lives
here, the per-field map stays declarative JSON.

`value` conventions:
- scalar bindings: return a str (or anything str()-able), or None/"" for blank.
- checkbox bindings: return a truthy/falsy value; the engine ticks the box's
  `on_state` when truthy.
- source resolvers (repeat-group `source`): return a list of row objects; the
  engine sets `ctx.row` to each in turn for the column resolvers.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, replace
from functools import lru_cache
from pathlib import Path
from typing import Callable

from src.db.queries_estate import (
    get_managed_person,
    list_accommodation_bonds,
    list_accounts,
    list_debts_liabilities,
    list_investments,
    list_motor_vehicles,
    list_private_managers,
    list_real_estate,
    list_significant_people,
)
from src.db.queries_forecast import list_forecast_categories, list_forecasts

_CONFIG_DIR = Path(__file__).resolve().parent.parent.parent / "config" / "artifacts"


@lru_cache(maxsize=1)
def _rollup_config() -> dict:
    """Load the granular-category → NSWTG-line rollup map (JSON, cached)."""
    path = _CONFIG_DIR / "nswtg_rollup.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _rollup_line(line: str) -> dict | None:
    """Find a line's {direction, categories} across all rollup groups.

    Groups whose key starts with '_' (metadata) are skipped. Supports both the
    Accounts taxonomy (income/expenditure) and the Plan taxonomy
    (plan_income/plan_expenditure) in one config.
    """
    cfg = _rollup_config()
    for key, group in cfg.items():
        if key.startswith("_") or not isinstance(group, dict):
            continue
        if line in group:
            return group[line]
    return None


@dataclass(frozen=True)
class Ctx:
    """Resolution context handed to every resolver.

    `row` is set by the engine when resolving repeat-group columns. Use
    `replace(ctx, row=...)` (frozen) to inject it.
    """
    conn: sqlite3.Connection
    managed_person_id: int
    period_start: str | None = None
    period_end: str | None = None
    row: object | None = None

    def with_row(self, row: object) -> "Ctx":
        return replace(self, row=row)


_REGISTRY: dict[str, Callable] = {}


def resolver(name: str) -> Callable:
    """Decorator registering a resolver under `name`."""
    def deco(fn: Callable) -> Callable:
        if name in _REGISTRY:
            raise ValueError(f"duplicate resolver: {name}")
        _REGISTRY[name] = fn
        return fn
    return deco


def get_resolver(name: str) -> Callable:
    try:
        return _REGISTRY[name]
    except KeyError:
        raise KeyError(f"unknown resolver: {name!r}") from None


def _money(value) -> str | None:
    """Format a number as a plain 2dp string (form has its own '$' label)."""
    if value is None:
        return None
    try:
        return f"{float(value):.2f}"
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Primitive / repeat-row resolvers
# ---------------------------------------------------------------------------

@resolver("static")
def _static(ctx: Ctx, value=None):
    return value


@resolver("attr")
def _attr(ctx: Ctx, name: str):
    return getattr(ctx.row, name, None) if ctx.row is not None else None


@resolver("attr_money")
def _attr_money(ctx: Ctx, name: str):
    return _money(getattr(ctx.row, name, None)) if ctx.row is not None else None


@resolver("attr_truthy")
def _attr_truthy(ctx: Ctx, name: str):
    return bool(getattr(ctx.row, name, None)) if ctx.row is not None else False


@resolver("attr_map")
def _attr_map(ctx: Ctx, name: str, mapping: dict, default=None):
    """Map a row attr through a value→label dict (e.g. 'sole'→'Sole')."""
    if ctx.row is None:
        return default
    return (mapping or {}).get(getattr(ctx.row, name, None), default)


# ---------------------------------------------------------------------------
# managed_persons scalar resolvers
# ---------------------------------------------------------------------------

@resolver("managed_person")
def _managed_person(ctx: Ctx, column: str):
    mp = get_managed_person(ctx.conn, ctx.managed_person_id)
    return getattr(mp, column, None) if mp is not None else None


@resolver("managed_person_money")
def _managed_person_money(ctx: Ctx, column: str):
    mp = get_managed_person(ctx.conn, ctx.managed_person_id)
    return _money(getattr(mp, column, None)) if mp is not None else None


@resolver("managed_person_truthy")
def _managed_person_truthy(ctx: Ctx, column: str):
    mp = get_managed_person(ctx.conn, ctx.managed_person_id)
    return bool(getattr(mp, column, None)) if mp is not None else False


@resolver("managed_person_eq")
def _managed_person_eq(ctx: Ctx, column: str, equals=None):
    mp = get_managed_person(ctx.conn, ctx.managed_person_id)
    return getattr(mp, column, None) == equals if mp is not None else False


@resolver("disability_flag")
def _disability_flag(ctx: Ctx, flag: str):
    """True if `flag` is present in the managed person's disability_flags JSON."""
    mp = get_managed_person(ctx.conn, ctx.managed_person_id)
    if mp is None or not mp.disability_flags:
        return False
    try:
        flags = json.loads(mp.disability_flags)
    except (TypeError, ValueError, json.JSONDecodeError):
        return False
    return flag in flags


# ---------------------------------------------------------------------------
# private_manager scalar resolver (fixed slots, e.g. PM1 on the form)
# ---------------------------------------------------------------------------

@resolver("private_manager")
def _private_manager(ctx: Ctx, column: str, index: int = 0):
    managers = list_private_managers(ctx.conn, ctx.managed_person_id)
    if index >= len(managers):
        return None
    return getattr(managers[index], column, None)


# ---------------------------------------------------------------------------
# Accounting / forecast period
# ---------------------------------------------------------------------------

@resolver("period")
def _period(ctx: Ctx, which: str = "start"):
    return ctx.period_start if which == "start" else ctx.period_end


# ---------------------------------------------------------------------------
# Rollups: granular categories → NSWTG super-lines
# ---------------------------------------------------------------------------

@resolver("actuals_rollup")
def _actuals_rollup(ctx: Ctx, line: str):
    """Sum transactions (deposit or withdrawal) for the categories mapped to a
    NSWTG income/expenditure `line`, over the accounting period [start, end].

    Returns a money string, or None when the line maps to no categories (so the
    field stays blank and the audit engine can flag the gap).
    """
    spec = _rollup_line(line)
    if not spec or not spec.get("categories"):
        return None
    column = "deposit" if spec.get("direction") == "deposit" else "withdrawal"
    placeholders = ", ".join("?" for _ in spec["categories"])
    params = list(spec["categories"])
    where = [
        f"category IN ({placeholders})",
        "COALESCE(is_internal_transfer, 0) = 0",
    ]
    if ctx.period_start:
        where.append("date >= ?")
        params.append(ctx.period_start)
    if ctx.period_end:
        where.append("date <= ?")
        params.append(ctx.period_end)
    row = ctx.conn.execute(
        f"SELECT COALESCE(SUM({column}), 0) AS total FROM transactions WHERE "
        + " AND ".join(where),
        params,
    ).fetchone()
    total = float(row["total"] or 0.0)
    return _money(total) if total else None


@resolver("actuals_period_total")
def _actuals_period_total(ctx: Ctx, direction: str = "withdrawal"):
    """Sum ALL deposits or withdrawals over the period (excl. internal transfers).

    This is the honest Section-C total — it includes spend not yet allocated to
    a NSWTG line, so the printed total reconciles with the bank statements even
    while individual lines under-report. The audit engine reports the gap.
    """
    column = "deposit" if direction == "deposit" else "withdrawal"
    where = ["COALESCE(is_internal_transfer, 0) = 0"]
    params: list = []
    if ctx.period_start:
        where.append("date >= ?")
        params.append(ctx.period_start)
    if ctx.period_end:
        where.append("date <= ?")
        params.append(ctx.period_end)
    row = ctx.conn.execute(
        f"SELECT COALESCE(SUM({column}), 0) AS total FROM transactions WHERE "
        + " AND ".join(where),
        params,
    ).fetchone()
    total = float(row["total"] or 0.0)
    return _money(total) if total else None


@resolver("forecast_rollup")
def _forecast_rollup(ctx: Ctx, line: str):
    """Sum forecast_value across forecast rows whose category maps to a NSWTG
    `line`, for the ctx period. Used by the Plan's Section D.
    """
    spec = _rollup_line(line)
    if not spec or not spec.get("categories"):
        return None
    section = "D_income" if spec.get("direction") == "deposit" else "D_expenditure"
    cats = {c.category_name: c.id for c in list_forecast_categories(ctx.conn)}
    wanted_ids = {cats[name] for name in spec["categories"] if name in cats}
    if not wanted_ids:
        return None
    rows = list_forecasts(
        ctx.conn, ctx.managed_person_id, ctx.period_start, ctx.period_end, section=section
    )
    total = sum(
        (r.forecast_value or 0.0) for r in rows if r.category_id in wanted_ids
    )
    return _money(total) if total else None


# ---------------------------------------------------------------------------
# Source resolvers (return lists for repeat groups)
# ---------------------------------------------------------------------------

@resolver("accounts")
def _accounts(ctx: Ctx):
    return list_accounts(ctx.conn, ctx.managed_person_id)


@resolver("private_managers")
def _private_managers(ctx: Ctx):
    return list_private_managers(ctx.conn, ctx.managed_person_id)


@resolver("significant_people")
def _significant_people(ctx: Ctx):
    return list_significant_people(ctx.conn, ctx.managed_person_id)


@resolver("real_estate")
def _real_estate(ctx: Ctx):
    return list_real_estate(ctx.conn, ctx.managed_person_id)


@resolver("investments")
def _investments(ctx: Ctx):
    return list_investments(ctx.conn, ctx.managed_person_id)


@resolver("motor_vehicles")
def _motor_vehicles(ctx: Ctx):
    return list_motor_vehicles(ctx.conn, ctx.managed_person_id)


@resolver("accommodation_bonds")
def _accommodation_bonds(ctx: Ctx):
    return list_accommodation_bonds(ctx.conn, ctx.managed_person_id)


@resolver("debts")
def _debts(ctx: Ctx):
    return list_debts_liabilities(ctx.conn, ctx.managed_person_id)
