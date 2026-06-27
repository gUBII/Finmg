"""Record the anticipated repayment of Ron's rent arrears as a Section E one-off.

Mirrors the Section C liability (debt #2): Ron is expected to repay Linda Jane
the $5,000 she covered for his $250/wk share (1 Dec 2025–20 Apr 2026), to be
legally reclaimed. Recorded as an 'anticipated' expenditure so the plan shows
the planned cash movement. Idempotent on the description.

Run: source .venv/bin/activate && python3 scripts/record_arrears_oneoff.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.db.database import get_connection
from src.db.queries_estate import bootstrap_managed_person_if_empty
from src.db.queries_forecast import list_one_off_events
from src.models.forecast import OneOffEvent
from src.services.one_off import record_one_off_event

AMOUNT = 5000.0
DESCRIPTION = "Repay Linda Jane Travia — Ron's $250/wk rent-share arrears (1 Dec 2025–20 Apr 2026, 20 wks)"
NOTES = (
    "Ron is co-lessee with Linda Jane Travia; Linda covered Ron's $250/wk share "
    "while NCAT rent transfers were on hold. Debt to be legally reclaimed. "
    "Evidence: rental receipt issued to both Ron and Linda. Mirrors Section C debt #2."
)


def main() -> int:
    conn = get_connection()
    mp_id = bootstrap_managed_person_if_empty(conn, "GENTILI", "Renato")

    for e in list_one_off_events(conn, mp_id):
        if "rent-share arrears" in (e.event_description or ""):
            print(f"Already recorded: one-off #{e.id} — {e.event_type} ${e.amount:,.2f} ({e.status})")
            conn.close()
            return 0

    event = OneOffEvent(
        managed_person_id=mp_id,
        event_type="expenditure",
        event_description=DESCRIPTION,
        status="anticipated",
        amount=AMOUNT,
        notes=NOTES,
    )
    event_id = record_one_off_event(conn, event, recorded_by="Linda")
    conn.commit()
    print(f"Recorded Section E one-off #{event_id}: anticipated expenditure ${AMOUNT:,.2f}")
    print(f"  {DESCRIPTION}")
    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
