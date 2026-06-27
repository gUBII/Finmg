"""One-off: apply best-guess operator categories to the 24 flagged txns.

These are MANUAL operator overrides (audit-logged to category_overrides via
update_transaction_category), NOT categoriser-rule changes — so the existing
test policy (e.g. 7-Eleven left ambiguous in categories.json) stays intact.
Every assignment here is a best-guess for Linda-Jane to confirm in the UI.

Idempotent: only touches rows still sitting at 'Uncategorised'.

Run:  source .venv/bin/activate && python3 scripts/bucket_flagged_24.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.db.database import get_connection
from src.db.queries import update_transaction_category

# txn_id -> (category, short rationale shown in the run summary)
ASSIGNMENTS: dict[int, tuple[str, str]] = {
    # --- Personal transfers OUT to individuals (neutral bucket; CONFIRM) ---
    541: ("Miscellaneous", "transfer to B LIMO — payee unknown"),
    393: ("Miscellaneous", "transfer to FARHAN RASHID — payee unknown"),
    556: ("Miscellaneous", "transfer to D ALAFACI — payee unknown"),
    # --- ATM cash deposits IN (unknown source) -> Other income ---
    402: ("Other", "ANZ ATM cash deposit $400 — source unknown"),
    554: ("Other", "ANZ ATM cash deposit $400 — source unknown"),
    417: ("Other", "ANZ ATM cash deposit $400 — source unknown"),
    597: ("Other", "ANZ ATM cash deposit $300 — source unknown"),
    598: ("Other", "ANZ ATM cash deposit $100 — source unknown"),
    # --- Refunds / bank credits IN -> Other income ---
    405: ("Other", "ANZ fee refund $88.60"),
    448: ("Other", "Coles VISA deposit/refund $23.90"),
    # --- 7-Eleven (most-common use = fuel) ---
    546: ("Car & Petrol", "7-Eleven Lakemba — fuel (best guess)"),
    588: ("Car & Petrol", "7-Eleven Bexley — fuel (best guess)"),
    682: ("Car & Petrol", "7-Eleven Lakemba — fuel (best guess)"),
    # --- Likely food vendors (small, Punchbowl) ---
    575: ("Fast food & Restaurant", "Kheizaran Panahi Punchbowl — food vendor"),
    582: ("Fast food & Restaurant", "Kheizaran Panahi Punchbowl — food vendor"),
    # --- Likely groceries / fresh markets ---
    414: ("Groceries", "SydHmeshwNuts Rosebery — nuts/produce vendor"),
    702: ("Groceries", "Chullora Marketplace — market"),
    # --- Unknown merchants OUT (neutral bucket; CONFIRM) ---
    394: ("Miscellaneous", "DFS Online — merchant unclear"),
    605: ("Miscellaneous", "Global Faith Pty Ltd Chiswick — merchant unclear"),
    643: ("Miscellaneous", "Global Faith Pty Ltd Chiswick — merchant unclear"),
    649: ("Miscellaneous", "Siya Investment Pty Ltd Belmore — merchant unclear"),
    466: ("Miscellaneous", "Carmel Dyer Concession Olympic Park — merchant unclear"),
    694: ("Miscellaneous", "EK Hola Pty Ltd Roselands — merchant unclear"),
    736: ("Miscellaneous", "U And A Pty Ltd Roselands — merchant unclear"),
}


def main() -> int:
    conn = get_connection()
    rows = conn.execute(
        "SELECT id, category FROM transactions WHERE id IN (%s)"
        % ",".join("?" * len(ASSIGNMENTS)),
        tuple(ASSIGNMENTS),
    ).fetchall()
    current = {r["id"]: r["category"] for r in rows}

    applied, skipped = 0, []
    for txn_id, (new_cat, why) in ASSIGNMENTS.items():
        old = current.get(txn_id)
        if old is None:
            skipped.append((txn_id, "id not found"))
            continue
        if old != "Uncategorised":
            skipped.append((txn_id, f"already '{old}' — left as-is"))
            continue
        update_transaction_category(conn, txn_id, new_cat, old)
        applied += 1
        print(f"  [{txn_id}] -> {new_cat:<24} ({why})")

    remaining = conn.execute(
        "SELECT COUNT(*) c FROM transactions WHERE category='Uncategorised'"
    ).fetchone()["c"]
    conn.close()

    print(f"\nApplied {applied} overrides; skipped {len(skipped)}.")
    for tid, reason in skipped:
        print(f"  skip [{tid}]: {reason}")
    print(f"Uncategorised remaining in DB: {remaining}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
