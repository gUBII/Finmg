"""One-off script to re-categorise transactions currently marked Uncategorised.

Loads updated rules from src/config/categories.json, applies them to every
Uncategorised row in the database, updates matched rows via the existing
update_transaction_category() path (which writes to category_overrides), and
prints a before/after summary plus a list of transactions that still require
Linda-Jane/user confirmation.

Run (from repo root):
    python3 scripts/recategorise_uncategorised.py [--db PATH]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from src.db.database import get_connection
from src.db.queries import update_transaction_category
from src.models.transaction import Transaction
from src.pipeline.categoriser import categorise_transaction, load_category_rules

DB_PATH = REPO_ROOT / "data" / "finmg.db"


def _load_uncategorised(conn) -> list[dict]:
    cur = conn.execute(
        """
        SELECT id, date, description, withdrawal, deposit, account_type, category
        FROM transactions
        WHERE category = 'Uncategorised'
        ORDER BY date, id
        """
    )
    return [dict(r) for r in cur.fetchall()]


def _row_to_transaction(row: dict) -> Transaction:
    from datetime import date as _date
    return Transaction(
        date=_date.fromisoformat(row["date"]),
        description=row["description"],
        withdrawal=row["withdrawal"],
        deposit=row["deposit"],
        account_number="",
        account_type=row["account_type"] or "",
        category=row["category"],
        month="",
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default=str(DB_PATH))
    args = parser.parse_args()

    conn = get_connection(args.db)
    config = load_category_rules()

    rows = _load_uncategorised(conn)
    before_count = len(rows)
    print(f"\nBefore: {before_count} Uncategorised transactions\n")

    updated: list[dict] = []
    still_uncategorised: list[dict] = []

    for row in rows:
        txn = _row_to_transaction(row)
        new_cat = categorise_transaction(txn, config)
        if new_cat != "Uncategorised":
            update_transaction_category(conn, row["id"], new_cat, "Uncategorised")
            updated.append({**row, "new_category": new_cat})
        else:
            still_uncategorised.append(row)

    print(f"Auto-categorised: {len(updated)} transactions")
    print(f"Still Uncategorised: {len(still_uncategorised)} transactions\n")

    if updated:
        print("=== AUTO-CATEGORISED ===")
        by_cat: dict[str, list[dict]] = {}
        for u in updated:
            by_cat.setdefault(u["new_category"], []).append(u)
        for cat, txns in sorted(by_cat.items()):
            total = sum(t["withdrawal"] or 0 for t in txns)
            print(f"  {cat} ({len(txns)} txns, ${total:.2f})")
            for t in txns:
                direction = f"OUT={t['withdrawal']:.2f}" if t["withdrawal"] else f"IN={t['deposit']:.2f}"
                print(f"    [{t['id']:4}] {t['date']}  {direction:12}  {t['description'][:70]}")

    if still_uncategorised:
        print("\n=== NEEDS USER CONFIRMATION ===")
        print("These transactions require Linda-Jane's input to categorise correctly:\n")
        for t in still_uncategorised:
            direction = f"OUT={t['withdrawal']:.2f}" if t["withdrawal"] else f"IN={t['deposit']:.2f}"
            print(f"  [{t['id']:4}] {t['date']}  {direction:12}  {t['description'][:80]}")

    conn.close()
    print(f"\nDone. Remaining Uncategorised: {len(still_uncategorised)}")


if __name__ == "__main__":
    main()
