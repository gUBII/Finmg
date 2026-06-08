"""Seed the v3 estate tables for the live FinMg installation.

Populates:
- Ron's `managed_persons` row
- Linda's `private_managers` row
- Significant people derived from the gift table on pages 16-17 of the
  submitted Plan (`data/reference_docs/03_PFM_ron_submitted_plan.md`)
- The three ANZ accounts (mapping confirmed by Linda on 2026-06-08)
- Backfills `transactions.account_id` from `accounts.account_number`

Idempotent: every insert is gated by an existence check, so running this
script twice is safe and never produces duplicates.

Run:
    python3 scripts/seed.py [--db PATH]
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from src.db.database import get_connection, init_db
from src.db.queries_estate import (
    backfill_transactions_account_id,
    find_significant_person_by_name,
    get_account_by_number,
    insert_account,
    insert_managed_person,
    insert_private_manager,
    insert_significant_person,
    list_managed_persons,
    list_private_managers,
)
from src.models.estate import (
    Account,
    ManagedPerson,
    PrivateManager,
    SignificantPerson,
)

# ---------------------------------------------------------------------------
# Seed data — all values traceable to a reference doc or memory file.
# Where a value is INFERRED rather than directly stated, note it inline.
# ---------------------------------------------------------------------------

RON = ManagedPerson(
    surname="GENTILI",
    given_names="Renato",
    address_line1="136 MADELINE ST",            # from ANZ statement headers
    address_line2="BELFIELD NSW",
    postcode="2191",
    disability_flags='["physical","brain_injury"]',  # form Section A
    has_will=None,                              # blank on submitted plan
)

# Linda — placeholder until she confirms. address mirrors Ron's per docs.
LINDA = PrivateManager(
    managed_person_id=0,                        # filled at insert time
    surname="TRAVIA",
    given_name="Linda Jane",
    relationship="Lifelong partner",
    address_line1="136 MADELINE ST",            # INFERRED — Linda to confirm
    address_line2="BELFIELD NSW",
    postcode="2191",
    appointment_type="sole",                    # NCAT FMO is sole-manager
)

# Three ANZ accounts (mapping confirmed by Linda on 2026-06-08).
# Inception dates per finmg-account-inception-dates memory.
ACCOUNTS = [
    Account(
        managed_person_id=0,
        institution="ANZ",
        account_number="437669532",
        bsb="013711",
        account_type="ACCESS ACCOUNT",
        role_label="living",
        inception_date="2025-05-01",
        notes="Wages (LACTALIS), Centrelink pension, source of rent transfers",
    ),
    Account(
        managed_person_id=0,
        institution="ANZ",
        account_number="178865319",
        bsb="012401",
        account_type="ACCESS ACCOUNT",
        role_label="spending",
        inception_date="2025-09-01",
        notes="Visa Debit card daily purchases; card issued ~Aug 2025",
    ),
    Account(
        managed_person_id=0,
        institution="ANZ",
        account_number="178870011",
        bsb="012401",
        account_type="PROGRESS SAVER",
        role_label="savings",
        inception_date="2025-09-01",
        notes="Weekly $200 sweeps from Living + interest credits",
    ),
]

# Significant people — derived from the gift table on submitted-plan pages 16-17.
# Each entry uses `(surname, given_name, relationship)`. Status defaults to
# 'active'; Linda will refine.
SIGNIFICANT_PEOPLE: list[tuple[str, str, str]] = [
    ("GENTILI",  "Sebastian",       "Son"),
    ("GENTILI",  "Nathan",          "Son"),
    ("GENTILI",  "Katherine",       "Daughter-in-law"),
    ("GENTILI",  "Cherina",         "Daughter-in-law"),
    # Step-children with surname initial "A." on the gift table:
    ("A.",       "Chantal",         "Step-child"),
    ("A.",       "Cartier",         "Step-child"),
    ("A.",       "Armani",          "Step-child"),
    ("A.",       "Diesel",          "Step-child"),
    ("A.",       "Hugo",            "Step-child"),
    # Linda's niece Gilda's children:
    ("(Gilda)",  "Allegna",         "Niece's child"),
    ("(Gilda)",  "Thomas",          "Niece's child"),
    ("(Gilda)",  "Gabriel",         "Niece's child"),
    # In-laws via Linda:
    ("TRAVIA",   "Margaret",        "Mother-in-law"),
    ("TRAVIA",   "Robert",          "Father-in-law"),
    # Tentative — needs Linda confirmation:
    ("?",        "Mikayla",         "Possibly a cousin"),
]


def _ensure_managed_person(conn: sqlite3.Connection) -> int:
    existing = list_managed_persons(conn)
    for mp in existing:
        if mp.surname == RON.surname and mp.given_names == RON.given_names:
            return mp.id  # type: ignore[return-value]
    return insert_managed_person(conn, RON)


def _ensure_private_manager(conn: sqlite3.Connection, managed_person_id: int) -> int:
    existing = list_private_managers(conn, managed_person_id)
    for pm in existing:
        if pm.surname == LINDA.surname and pm.given_name == LINDA.given_name:
            return pm.id  # type: ignore[return-value]
    from dataclasses import replace
    linda = replace(LINDA, managed_person_id=managed_person_id)
    return insert_private_manager(conn, linda)


def _ensure_significant_people(
    conn: sqlite3.Connection, managed_person_id: int
) -> int:
    inserted = 0
    for surname, given, relationship in SIGNIFICANT_PEOPLE:
        existing = find_significant_person_by_name(
            conn, managed_person_id, given, surname
        )
        if existing is not None:
            continue
        insert_significant_person(
            conn,
            SignificantPerson(
                managed_person_id=managed_person_id,
                surname=surname,
                given_name=given,
                relationship=relationship,
            ),
        )
        inserted += 1
    return inserted


def _ensure_accounts(conn: sqlite3.Connection, managed_person_id: int) -> int:
    from dataclasses import replace
    inserted = 0
    for acc in ACCOUNTS:
        if get_account_by_number(conn, acc.account_number) is not None:
            continue
        insert_account(conn, replace(acc, managed_person_id=managed_person_id))
        inserted += 1
    return inserted


def seed(conn: sqlite3.Connection) -> dict:
    """Run the whole seed; return a summary dict."""
    mp_id = _ensure_managed_person(conn)
    pm_id = _ensure_private_manager(conn, mp_id)
    sp_count = _ensure_significant_people(conn, mp_id)
    acc_count = _ensure_accounts(conn, mp_id)
    backfilled = backfill_transactions_account_id(conn)
    return {
        "managed_person_id": mp_id,
        "private_manager_id": pm_id,
        "significant_people_added": sp_count,
        "accounts_added": acc_count,
        "transactions_backfilled": backfilled,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--db",
        default=str(REPO_ROOT / "data" / "finmg.db"),
        help="Path to the SQLite DB (default: data/finmg.db)",
    )
    args = parser.parse_args()

    conn = get_connection(args.db)
    try:
        init_db(conn)                            # ensure migrations applied
        summary = seed(conn)
        for k, v in summary.items():
            print(f"{k}: {v}")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
