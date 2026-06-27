"""Gift forecast (§76) matrix — pivots the gift ledger into a recipients ×
occasions table shared by the Gifts view (on-screen) and the Excel export.

The ledger (`gifts` table) is the single source of truth; this module only
reads and reshapes it, so the dashboard and the exported workbook can never
drift apart. Seed the ledger with scripts/load_gift_forecast.py.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from src.db.queries_compliance import list_gifts

# Column order + display labels for the matrix. 'other' carries Christening
# (not a first-class occasion in the gifts CHECK enum).
OCC_ORDER = ["birthday", "christmas", "easter", "fathers_day",
             "mothers_day", "valentines", "other", "wedding"]
OCC_LABEL = {
    "birthday": "Birthday", "christmas": "Christmas", "easter": "Easter",
    "fathers_day": "Father's Day", "mothers_day": "Mother's Day",
    "valentines": "Valentine's Day", "other": "Christening", "wedding": "Wedding",
}

TITLE = "Gift (cashout / equivalent) for Renato Gentili — Estimation for this year"


@dataclass(frozen=True)
class ForecastRow:
    name: str
    relation: str
    amounts: dict[str, float]   # occasion -> planned amount
    total: float
    flagged: bool


def build_matrix(
    conn: sqlite3.Connection, managed_person_id: int
) -> tuple[list[ForecastRow], dict[str, float], float]:
    """Return (rows, column_totals, grand_total).

    Recipients keep first-seen order from the ledger; each row aggregates that
    recipient's planned gifts by occasion. A recipient is flagged if any of
    their gift rows is not §76-compliant.
    """
    order: list[str] = []
    by_name: dict[str, dict] = {}
    for g in list_gifts(conn, managed_person_id):
        name = (g.recipient_name or "(unattributed)").strip()
        rec = by_name.get(name)
        if rec is None:
            rec = {"relation": g.recipient_relation or "—", "amounts": {}, "total": 0.0, "flagged": False}
            by_name[name] = rec
            order.append(name)
        if g.occasion:
            rec["amounts"][g.occasion] = rec["amounts"].get(g.occasion, 0.0) + (g.planned_amount or 0.0)
        rec["total"] += g.planned_amount or 0.0
        if g.section_76_assessment and g.section_76_assessment != "compliant":
            rec["flagged"] = True

    rows = [
        ForecastRow(name=n, relation=by_name[n]["relation"], amounts=by_name[n]["amounts"],
                    total=by_name[n]["total"], flagged=by_name[n]["flagged"])
        for n in order
    ]
    col_totals = {o: sum(r.amounts.get(o, 0.0) for r in rows) for o in OCC_ORDER}
    grand_total = sum(r.total for r in rows)
    return rows, col_totals, grand_total
