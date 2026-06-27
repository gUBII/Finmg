"""Record Ron's rent-arrears debt to Linda Jane as a Section C liability.

Ron is co-lessee with Linda Jane Travia. While NCAT rent transfers were on
hold, Linda covered Ron's $250/wk share from 1 Dec 2025 to 20 Apr 2026
(20 weeks x $250 = $5,000). That sum is a debt of Ron's estate, recoverable
by Linda — evidenced by the rental receipt issued to both Ron and Linda.

Idempotent: skips if a matching rent-arrears liability already exists.

Run: source .venv/bin/activate && python3 scripts/record_rent_arrears_debt.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.db.database import get_connection
from src.db.queries_estate import (
    bootstrap_managed_person_if_empty,
    insert_debt_liability,
    list_debts_liabilities,
)
from src.models.estate import DebtLiability

WEEKS = 20
WEEKLY = 250.0
AMOUNT = WEEKS * WEEKLY  # $5,000.00
LENDER = "Linda Jane Travia (co-lessee & private manager)"
DTYPE = "Rent arrears — recoverable by co-lessee"
TERM = "1 Dec 2025–20 Apr 2026 · 20 wks × $250 · to be legally reclaimed"


def main() -> int:
    conn = get_connection()
    mp_id = bootstrap_managed_person_if_empty(conn, "GENTILI", "Renato")

    existing = [
        d for d in list_debts_liabilities(conn, mp_id)
        if (d.lender or "").startswith("Linda Jane Travia")
        and "arrears" in (d.type or "").lower()
    ]
    if existing:
        d = existing[0]
        print(f"Already recorded: debt #{d.id} — {d.lender} ${d.amount:,.2f} ({d.type})")
        conn.close()
        return 0

    debt = DebtLiability(
        managed_person_id=mp_id,
        lender=LENDER,
        type=DTYPE,
        term=TERM,
        amount=AMOUNT,
    )
    debt_id = insert_debt_liability(conn, debt)
    conn.commit()
    print(f"Recorded Section C debt #{debt_id}:")
    print(f"  Owed by:  GENTILI, Renato (managed person)")
    print(f"  Owed to:  {LENDER}")
    print(f"  Type:     {DTYPE}")
    print(f"  Term:     {TERM}")
    print(f"  Amount:   ${AMOUNT:,.2f}")
    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
