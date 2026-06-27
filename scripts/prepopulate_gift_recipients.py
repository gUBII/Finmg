"""Prepopulate gift recipient names + relations from the operator's 27 Jun 2026
revamp instruction. Every change is written through the audited
`revamp_gift_recipient` service (immutable audit_log).

Per the operator:
  - Allegra = niece; Thomas, Gabriel = nephews (drop the "(Gilda)" tag)
  - Caroline -> Carolina (name correction)
  - Sebastian/Nathan Gentili = sons
  - Mikayla is a niece marrying Jared -> one collective gift "Mikayla & Jared"
  - Goran and Anthony are HELD for now -> left untouched
  - relations not yet supplied (Katherine, the A-family, the Travias, Linda)
    are left blank and reported so they can be filled in the Gifts view.

Idempotent: re-running is a no-op once a row already matches its target.

Run:  python3 scripts/prepopulate_gift_recipients.py
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from src.db.database import get_connection, init_db
from src.db.queries_compliance import list_gifts
from src.services.gifts import revamp_gift_recipient

# current recipient_name -> (new recipient_name, relation)
REVAMP = {
    "Sebastian G.": ("Sebastian Gentili", "Son"),
    "Nathan Gentili": ("Nathan Gentili", "Son"),
    "Caroline": ("Carolina", None),
    "Allegra (Gilda)": ("Allegra", "Niece"),
    "Thomas (Gilda)": ("Thomas", "Nephew"),
    "Gabriel (Gilda)": ("Gabriel", "Nephew"),
    "Mikayla & Jared": ("Mikayla & Jared", "Niece (& Jared, marrying)"),
}
HELD = {"Goran", "Anthony"}  # left untouched per operator ("hold for now")


def main() -> int:
    conn = get_connection()
    init_db(conn)
    mp = conn.execute("SELECT id FROM managed_persons ORDER BY id LIMIT 1").fetchone()
    if mp is None:
        print("no managed person — run scripts/seed.py first")
        return 1

    changed = 0
    for g in list_gifts(conn, mp["id"]):
        cur = (g.recipient_name or "").strip()
        if cur not in REVAMP:
            continue
        new_name, relation = REVAMP[cur]
        already = g.recipient_name == new_name and (g.recipient_relation or None) == (relation or None)
        if already:
            continue
        revamp_gift_recipient(conn, g.id, new_name, relation, recorded_by="Linda")
        print(f"  #{g.id}: {cur!r} -> {new_name!r} [{relation or '—'}]")
        changed += 1

    print(f"\nprepopulated {changed} recipient(s); held (untouched): {', '.join(sorted(HELD))}")
    print("\nstill need a relation:")
    for g in list_gifts(conn, mp["id"]):
        name = (g.recipient_name or "").strip()
        if name in HELD:
            continue
        if not (g.recipient_relation or "").strip():
            print(f"  #{g.id}  {name}")
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
