"""Load the handwritten gift forecast (doc 03 pages 16-17) into the gifts ledger.

The ledger DATA lives in gitignored `data/gift_ledger_doc03.json` (PII — names
and amounts); this script holds only the loading logic. One `gifts` row per
recipient x occasion, planned_amount only (these are estimates — actuals get
linked to transactions later).

Section 76 assessment policy applied here:
- $100 seasonal gift to a confirmed relative      -> 'compliant' (within §76 on
  its face per the doc-03 forensic read; reasonableness vs estate size is the
  compliance engine's ongoing job)
- any row carrying a `flag_reason` in the JSON    -> 'flagged' (COI to the
  manager herself, uncertain relationship, or illegible recipient)

Idempotent: rows carry a `[doc03 p16-17]` source tag in notes; re-running
deletes and reloads only its own rows. The batch is recorded in audit_log.

Run:  python3 scripts/load_gift_ledger.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from src.db.database import get_connection, init_db
from src.db.queries_compliance import insert_audit, insert_gift
from src.models.compliance import AuditEntry, Gift

SOURCE_TAG = "[doc03 p16-17]"
LEDGER_PATH = REPO_ROOT / "data" / "gift_ledger_doc03.json"


def load_gift_ledger(conn, ledger: dict, managed_person_id: int) -> dict:
    """Replace this source's gift rows from the parsed ledger. Returns a summary."""
    deleted = conn.execute(
        "DELETE FROM gifts WHERE managed_person_id = ? AND notes LIKE ?",
        (managed_person_id, f"%{SOURCE_TAG}%"),
    ).rowcount
    conn.commit()

    occasion_dates = ledger.get("occasion_dates", {})
    inserted = 0
    flagged = 0
    total_planned = 0.0

    for row in ledger["rows"]:
        # Recipient identity is gift-owned — no lookup into significant_people.
        given = (row.get("given_name") or "").strip()
        surname = (row.get("surname") or "").strip()
        recipient_name = f"{given} {surname}".strip() or "(unattributed)"
        recipient_relation = row.get("relationship")

        flag_reason = row.get("flag_reason")
        assessment = "flagged" if flag_reason else "compliant"

        for occasion, amount in row["occasions"].items():
            notes = f"{SOURCE_TAG} planned for {recipient_name}"
            if flag_reason:
                notes += f" — {flag_reason}"
            insert_gift(
                conn,
                Gift(
                    managed_person_id=managed_person_id,
                    recipient_name=recipient_name,
                    recipient_relation=recipient_relation,
                    occasion=occasion,
                    occasion_date=occasion_dates.get(occasion),
                    planned_amount=float(amount),
                    section_76_assessment=assessment,
                    notes=notes,
                ),
            )
            inserted += 1
            total_planned += float(amount)
            if flag_reason:
                flagged += 1

    insert_audit(
        conn,
        AuditEntry(
            action="insert",
            table_name="gifts",
            actor_role="system",
            after_json=json.dumps(
                {"source": SOURCE_TAG, "inserted": inserted, "replaced": deleted,
                 "flagged": flagged, "total_planned": total_planned}
            ),
            reason="loaded handwritten gift forecast from submitted Plan attachment (doc 03)",
        ),
    )

    return {
        "inserted": inserted,
        "replaced": deleted,
        "flagged": flagged,
        "total_planned": total_planned,
    }


def main() -> int:
    if not LEDGER_PATH.exists():
        print(f"ledger data not found: {LEDGER_PATH} (PII file, lives only in data/)")
        return 1
    ledger = json.loads(LEDGER_PATH.read_text(encoding="utf-8"))

    conn = get_connection()
    init_db(conn)
    mp_row = conn.execute("SELECT id FROM managed_persons ORDER BY id LIMIT 1").fetchone()
    if mp_row is None:
        print("no managed person — run scripts/seed.py first")
        return 1

    summary = load_gift_ledger(conn, ledger, mp_row["id"])
    print(f"gifts loaded: {summary['inserted']} rows "
          f"(replaced {summary['replaced']}, flagged {summary['flagged']}) "
          f"— total planned ${summary['total_planned']:,.2f}")
    for note in ledger.get("_discrepancies", []):
        print(f"NOTE: {note}")
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
