"""Surgically append PDF transactions missing from the DB (no wipe).

The DB was loaded from CSVs that stopped in early June; the newer ANZ PDFs run
to 15 June. This re-syncs only the rows present in the PDFs but absent from the
DB (anti-join on date+amount+description), categorises them with the current
rules (including learned patterns), flags internal transfers, and inserts them.
Existing reviewed rows and manual overrides are left untouched.

Idempotent: re-running finds nothing new. Run:
  source .venv/bin/activate && python3 scripts/sync_missing_from_pdf.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.db.database import get_connection
from src.db.queries import ensure_account_for_upload
from src.parser.pdf_extractor import extract_transactions
from src.pipeline.categoriser import categorise_all, load_category_rules
from src.pipeline.merger import detect_internal_transfers

PDFS = ["living.pdf", "spending.pdf", "savings.pdf"]


def _key(date_s, w, d, desc):
    return (date_s, round(w or 0, 2), round(d or 0, 2), desc.strip())


def main() -> int:
    conn = get_connection()
    config = load_category_rules()
    total_added = 0
    uncategorised = []

    for name in PDFS:
        meta, txns = extract_transactions(f"data/raw_pdf/{name}")
        acct = meta.account_number
        db = conn.execute(
            "SELECT date, withdrawal, deposit, description FROM transactions WHERE account_number=?",
            (acct,),
        ).fetchall()
        dbkeys = {_key(r["date"], r["withdrawal"], r["deposit"], r["description"]) for r in db}
        missing = [t for t in txns if _key(t.date.isoformat(), t.withdrawal, t.deposit, t.description) not in dbkeys]
        if not missing:
            print(f"{name} ({acct}): nothing to add")
            continue

        for t in missing:
            t.month = t.date.isoformat()[:7]
        categorise_all(missing, config)
        detect_internal_transfers(missing)

        account_id = ensure_account_for_upload(conn, meta)
        pdf_row = conn.execute(
            "SELECT id FROM uploaded_pdfs WHERE account_number=? ORDER BY id DESC LIMIT 1",
            (acct,),
        ).fetchone()
        pdf_id = pdf_row["id"] if pdf_row else None

        conn.executemany(
            """
            INSERT INTO transactions
                (date, description, withdrawal, deposit, account_number,
                 account_type, category, month, is_internal_transfer, pdf_id, account_id)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)
            """,
            [
                (
                    t.date.isoformat(), t.description, t.withdrawal, t.deposit,
                    t.account_number, t.account_type, t.category, t.month,
                    int(t.is_internal_transfer), pdf_id, account_id,
                )
                for t in missing
            ],
        )
        conn.commit()
        total_added += len(missing)
        print(f"\n{name} ({acct}): added {len(missing)} rows")
        for t in sorted(missing, key=lambda x: x.date):
            amt = f"-{t.withdrawal:.2f}" if t.withdrawal else f"+{t.deposit:.2f}"
            print(f"   {t.date}  {amt:>10}  {t.category:<22} {t.description[:42]}")
            if t.category == "Uncategorised":
                uncategorised.append((t.date.isoformat(), amt, t.description))

    print(f"\n=== Added {total_added} transactions ===")
    if uncategorised:
        print(f"\n{len(uncategorised)} NEW rows are Uncategorised — need a decision:")
        for d, a, desc in uncategorised:
            print(f"   {d}  {a:>10}  {desc[:60]}")
    new_total = conn.execute("SELECT COUNT(*) c, MAX(date) m FROM transactions").fetchone()
    print(f"\nDB now: {new_total['c']} txns, latest {new_total['m']}")
    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
