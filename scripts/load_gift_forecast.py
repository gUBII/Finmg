"""Seed the §76 gift ledger from the gift-forecast doc (ginseng pp16-17),
mapped onto the CORRECTED FinMg recipient names.

One gifts row per recipient x occasion (a person may receive several gifts).
"Christening" maps to occasion 'other' (not in the occasion enum). Linda — the
private manager — is flagged §76 (a gift from the managed estate to the manager
is a conflict of interest). The ledger is the source of truth; the Gifts view
and the Excel export pivot it via src/services/gift_forecast.py.

Idempotent: wipes this managed person's gifts and reloads. Audited.
Run:  source .venv/bin/activate && python3 scripts/load_gift_forecast.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.db.database import get_connection, init_db
from src.db.queries_compliance import insert_audit, insert_gift
from src.models.compliance import AuditEntry, Gift
from src.services.gift_forecast import OCC_LABEL

SOURCE = "[ginseng forecast p16-17]"

# Row order mirrors the doc; names are the CORRECTED FinMg names.
ORDER = ["Sebastian Gentili", "Katherine", "Nathan Gentili", "Carolina", "Chanel M. A",
         "Cartier R. A", "Armani J. A", "Diesel J. A", "Hugo D. A", "Linda J. Travia",
         "Allegra", "Thomas", "Gabriel", "Margaret Travia", "Robert Travia",
         "Mikayla & Jared", "Goran", "Anthony"]
RELATION = {
    "Sebastian Gentili": "Son", "Nathan Gentili": "Son", "Katherine": "Daughter-in-law",
    "Carolina": "Daughter-in-law", "Chanel M. A": "S. daughter", "Cartier R. A": "S. daughter",
    "Armani J. A": "S. son", "Diesel J. A": "S. son", "Hugo D. A": "S. son",
    "Linda J. Travia": "Partner", "Allegra": "Niece", "Thomas": "Nephew", "Gabriel": "Nephew",
    "Margaret Travia": "Mother-in-law", "Robert Travia": "Father-in-law",
    "Mikayla & Jared": "Niece (& Jared, marrying)", "Goran": None, "Anthony": None,
}
GIFTS = {
    "Sebastian Gentili": {"birthday": 100, "christmas": 100, "easter": 100},
    "Nathan Gentili": {"birthday": 100, "christmas": 100, "easter": 100},
    "Katherine": {"birthday": 100, "christmas": 100, "easter": 100},
    "Carolina": {"birthday": 100, "christmas": 100, "easter": 100},
    "Chanel M. A": {"birthday": 100, "christmas": 100, "easter": 100},
    "Cartier R. A": {"birthday": 100, "christmas": 100, "easter": 100},
    "Armani J. A": {"birthday": 100, "christmas": 100, "easter": 100},
    "Diesel J. A": {"birthday": 100, "christmas": 100, "easter": 100},
    "Hugo D. A": {"birthday": 100, "christmas": 100, "easter": 100},
    "Linda J. Travia": {"birthday": 100, "christmas": 100, "easter": 100, "mothers_day": 100, "valentines": 100},
    "Allegra": {"birthday": 100, "christmas": 100, "easter": 100},
    "Thomas": {"birthday": 100, "christmas": 100, "easter": 100},
    "Gabriel": {"birthday": 100, "christmas": 100, "easter": 100, "other": 100},  # other = Christening
    "Margaret Travia": {"birthday": 100, "christmas": 100, "easter": 100, "mothers_day": 100},
    "Robert Travia": {"birthday": 100, "christmas": 100, "easter": 100, "fathers_day": 100},
    "Mikayla & Jared": {"wedding": 300},
    "Goran": {"birthday": 100, "christmas": 100, "easter": 100},
    "Anthony": {"birthday": 100, "christmas": 100, "easter": 100},
}
# §76 flags (recipient -> reason). The manager gifting herself is a COI.
FLAG = {
    "Linda J. Travia": "§76 FLAG: gift from the managed estate to the private manager (Linda) — conflict of interest.",
}


def load(conn, managed_person_id: int) -> dict:
    conn.execute("DELETE FROM gifts WHERE managed_person_id = ?", (managed_person_id,))
    inserted = flagged = 0
    total = 0.0
    for name in ORDER:
        rel = RELATION[name]
        flag = FLAG.get(name)
        assessment = "flagged" if flag else "compliant"
        for occasion, amount in GIFTS[name].items():
            note = f"{SOURCE} {OCC_LABEL[occasion]}" + (f" — {flag}" if flag else "")
            insert_gift(conn, Gift(
                managed_person_id=managed_person_id, recipient_name=name,
                recipient_relation=rel, occasion=occasion, planned_amount=float(amount),
                section_76_assessment=assessment, notes=note))
            inserted += 1
            total += amount
            if flag:
                flagged += 1
    insert_audit(conn, AuditEntry(
        action="insert", table_name="gifts", actor_role="system",
        after_json=json.dumps({"source": SOURCE, "rows": inserted, "flagged": flagged, "total": total}),
        reason="seeded §76 gift forecast (ginseng pp16-17) onto corrected recipient names"))
    conn.commit()
    return {"inserted": inserted, "flagged": flagged, "total": total}


def main() -> int:
    conn = get_connection()
    init_db(conn)
    mp = conn.execute("SELECT id FROM managed_persons ORDER BY id LIMIT 1").fetchone()
    if mp is None:
        print("no managed person — run scripts/seed.py first")
        return 1
    s = load(conn, mp["id"])
    print(f"gift forecast loaded: {s['inserted']} rows ({s['flagged']} flagged) — total ${s['total']:,.0f}")
    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
