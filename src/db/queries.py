"""All SQL query functions for the FinMg dashboard."""

from __future__ import annotations

import sqlite3
from datetime import date

from src.models.estate import Account
from src.db.queries_estate import get_account_by_number, insert_account
from src.models.transaction import Transaction

# Institution is fixed for this deployment (ANZ bank statement dashboard).
# Auto-registered accounts inherit it; the field stays evidence-grade and
# user-editable in the estate view afterwards.
_DEFAULT_INSTITUTION = "ANZ"


# ---------------------------------------------------------------------------
# Insert helpers
# ---------------------------------------------------------------------------

def delete_account_transactions_in_range(
    conn: sqlite3.Connection,
    account_number: str,
    date_start: str,
    date_end: str,
) -> int:
    """
    Delete transactions for an account within [date_start, date_end].

    Called before inserting a new rolling-window statement so overlapping
    dates from a previous upload are replaced rather than duplicated.
    Returns the number of rows deleted.
    """
    cur = conn.execute(
        """
        DELETE FROM transactions
        WHERE account_number = ?
          AND date >= ?
          AND date <= ?
        """,
        (account_number, date_start, date_end),
    )
    return cur.rowcount


def insert_pdf_and_transactions(
    conn: sqlite3.Connection,
    meta,
    txns: list[Transaction],
    filename: str,
    file_hash: str,
) -> int:
    """
    Insert a parsed PDF record and its transactions.

    Before inserting, any existing transactions for the same account within
    the PDF's date range are removed to prevent double-counting from
    rolling 120-day statements. Returns the pdf_id.

    If a row exists in `accounts` matching `meta.account_number`, each
    transaction is FK-linked to it via `account_id`. If not (e.g. seed has
    not run yet, or this is a brand-new account number), `account_id` stays
    NULL and `backfill_transactions_account_id` can close the gap later.
    """
    if txns:
        dates = [t.date.isoformat() for t in txns]
        delete_account_transactions_in_range(
            conn, meta.account_number, min(dates), max(dates)
        )

    total_w = round(sum(t.withdrawal or 0 for t in txns), 2)
    total_d = round(sum(t.deposit or 0 for t in txns), 2)

    cur = conn.execute(
        """
        INSERT INTO uploaded_pdfs
            (filename, file_hash, account_number, account_type, bsb,
             report_start, report_end, transaction_count,
             parsed_withdrawals, parsed_deposits)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            filename,
            file_hash,
            meta.account_number,
            meta.account_type,
            meta.bsb,
            meta.report_start,
            meta.report_end,
            len(txns),
            total_w,
            total_d,
        ),
    )
    pdf_id = cur.lastrowid

    account_id = ensure_account_for_upload(conn, meta)

    conn.executemany(
        """
        INSERT INTO transactions
            (date, description, withdrawal, deposit, account_number,
             account_type, category, month, is_internal_transfer, pdf_id,
             account_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                t.date.isoformat(),
                t.description,
                t.withdrawal,
                t.deposit,
                t.account_number,
                t.account_type,
                t.category,
                t.month,
                int(t.is_internal_transfer),
                pdf_id,
                account_id,
            )
            for t in txns
        ],
    )
    conn.commit()
    return pdf_id


# ---------------------------------------------------------------------------
# Read helpers
# ---------------------------------------------------------------------------

def is_pdf_already_uploaded(conn: sqlite3.Connection, file_hash: str) -> bool:
    """Return True if a PDF with this SHA-256 hash is already in the DB."""
    row = conn.execute(
        "SELECT 1 FROM uploaded_pdfs WHERE file_hash = ?", (file_hash,)
    ).fetchone()
    return row is not None


def get_all_transactions(
    conn: sqlite3.Connection,
    month: str | None = None,
    account: str | None = None,
) -> list[dict]:
    """Fetch transactions with optional month/account filters."""
    query = "SELECT * FROM transactions WHERE 1=1"
    params: list = []
    if month:
        query += " AND month = ?"
        params.append(month)
    if account:
        query += " AND account_number = ?"
        params.append(account)
    query += " ORDER BY date, account_number"
    rows = conn.execute(query, params).fetchall()
    return [dict(r) for r in rows]


def get_month_account_coverage(conn: sqlite3.Connection) -> set[tuple[str, str]]:
    """Return set of (account_number, month) pairs that have data."""
    rows = conn.execute(
        "SELECT DISTINCT account_number, month FROM transactions"
    ).fetchall()
    return {(r["account_number"], r["month"]) for r in rows}


def get_distinct_months(conn: sqlite3.Connection) -> list[str]:
    """Return sorted list of distinct months in the DB."""
    rows = conn.execute(
        "SELECT DISTINCT month FROM transactions ORDER BY month"
    ).fetchall()
    return [r["month"] for r in rows]


def get_distinct_accounts(conn: sqlite3.Connection) -> list[str]:
    """Return sorted list of distinct account numbers."""
    rows = conn.execute(
        "SELECT DISTINCT account_number FROM transactions ORDER BY account_number"
    ).fetchall()
    return [r["account_number"] for r in rows]


# Fallback friendly names keyed by full account number, used only when the
# `accounts` table can't supply one (e.g. a brand-new account that hasn't been
# role-labelled yet). The DB `accounts.role_label` is the source of truth.
ACCOUNT_NAMES: dict[str, str] = {
    "437669532": "Living Account",
    "178865319": "Spending Account",
    "178870011": "Savings Account",
}

# accounts.role_label → friendly display name.
_ROLE_DISPLAY: dict[str, str] = {
    "living": "Living Account",
    "spending": "Spending Account",
    "savings": "Savings Account",
}


def _role_from_account_type(account_type: str | None) -> str | None:
    """Best-effort role guess from the raw PDF account type.

    Only "PROGRESS SAVER" is unambiguous (→ savings). The two ACCESS ACCOUNTs
    (Living vs Spending) cannot be told apart by type, so they stay unlabelled
    for the user to set in the estate view.
    """
    if account_type and "SAVER" in account_type.upper():
        return "savings"
    return None


def account_display_name(account_number: str) -> str:
    """Friendly name for an account number, conn-free.

    Pure fallback (static dict → raw number) for callers without a DB handle.
    Prefer `get_account_display_names(conn)` where a connection is available,
    as that consults `accounts.role_label` first.
    """
    return ACCOUNT_NAMES.get(account_number, account_number)


def get_account_display_names(conn: sqlite3.Connection) -> dict[str, str]:
    """Map every known account_number → friendly display name, DB-first.

    Resolution order per number: accounts.role_label → static ACCOUNT_NAMES →
    accounts.account_type → the raw number. Covers numbers seen in either the
    `accounts` table or the `transactions` table so nothing renders blank.
    """
    names: dict[str, str] = {}

    for r in conn.execute(
        "SELECT account_number, account_type, role_label FROM accounts"
    ).fetchall():
        num = r["account_number"]
        names[num] = (
            _ROLE_DISPLAY.get(r["role_label"])
            or ACCOUNT_NAMES.get(num)
            or r["account_type"]
            or num
        )

    # Any transaction account not (yet) registered falls back to dict → number.
    for r in conn.execute(
        "SELECT DISTINCT account_number FROM transactions"
    ).fetchall():
        names.setdefault(r["account_number"], account_display_name(r["account_number"]))

    return names


def get_account_types(conn: sqlite3.Connection) -> dict[str, str]:
    """Return mapping of account_number → friendly display name (DB-first)."""
    return get_account_display_names(conn)


def ensure_account_for_upload(conn: sqlite3.Connection, meta) -> int | None:
    """Return the `accounts.id` for `meta.account_number`, auto-registering it.

    On upload of a statement for an account that isn't in `accounts` yet, a row
    is created from the parsed header (institution, number, BSB, type) and a
    best-effort role guess, attached to the single managed person. This keeps
    transaction→account FK linkage and friendly naming working for new accounts
    without a manual seed step.

    Returns None (leaving account_id NULL, as before) only when no managed
    person exists yet — the caller must not fail in that bootstrap-less case.
    """
    existing = get_account_by_number(conn, meta.account_number)
    if existing is not None:
        return existing.id

    mp_row = conn.execute(
        "SELECT id FROM managed_persons ORDER BY id LIMIT 1"
    ).fetchone()
    if mp_row is None:
        return None

    return insert_account(
        conn,
        Account(
            managed_person_id=int(mp_row["id"]),
            institution=_DEFAULT_INSTITUTION,
            account_number=meta.account_number,
            bsb=getattr(meta, "bsb", None),
            account_type=getattr(meta, "account_type", None),
            role_label=_role_from_account_type(getattr(meta, "account_type", None)),
        ),
    )


def get_monthly_totals(conn: sqlite3.Connection) -> list[dict]:
    """Monthly expense/income totals for charts."""
    rows = conn.execute(
        """
        SELECT month,
               COALESCE(SUM(CASE WHEN is_internal_transfer = 0 THEN withdrawal END), 0) AS expenses,
               COALESCE(SUM(CASE WHEN is_internal_transfer = 0 THEN deposit END), 0) AS income
        FROM transactions
        GROUP BY month
        ORDER BY month
        """
    ).fetchall()
    return [dict(r) for r in rows]


def get_category_totals(
    conn: sqlite3.Connection, month: str | None = None
) -> list[dict]:
    """Category breakdown for pie/bar charts."""
    query = """
        SELECT category,
               COUNT(*) AS count,
               COALESCE(SUM(withdrawal), 0) AS total_withdrawals,
               COALESCE(SUM(deposit), 0) AS total_deposits
        FROM transactions
        WHERE is_internal_transfer = 0
    """
    params: list = []
    if month:
        query += " AND month = ?"
        params.append(month)
    query += " GROUP BY category ORDER BY total_withdrawals DESC"
    rows = conn.execute(query, params).fetchall()
    return [dict(r) for r in rows]


def get_transaction_count(conn: sqlite3.Connection) -> int:
    """Total number of transactions in the DB."""
    row = conn.execute("SELECT COUNT(*) AS cnt FROM transactions").fetchone()
    return row["cnt"]


def get_uploaded_pdfs(conn: sqlite3.Connection) -> list[dict]:
    """Return all uploaded PDF records."""
    rows = conn.execute(
        "SELECT * FROM uploaded_pdfs ORDER BY uploaded_at DESC"
    ).fetchall()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Update helpers
# ---------------------------------------------------------------------------

def update_transaction_category(
    conn: sqlite3.Connection,
    txn_id: int,
    new_cat: str,
    old_cat: str,
) -> None:
    """Update a transaction's category and log the override."""
    conn.execute(
        "UPDATE transactions SET category = ?, is_internal_transfer = ? WHERE id = ?",
        (new_cat, int(new_cat == "Internal Transfer"), txn_id),
    )
    conn.execute(
        """
        INSERT INTO category_overrides (transaction_id, old_category, new_category)
        VALUES (?, ?, ?)
        """,
        (txn_id, old_cat, new_cat),
    )
    conn.commit()


# ---------------------------------------------------------------------------
# Conversion helpers
# ---------------------------------------------------------------------------

def rows_to_transactions(rows: list[dict]) -> list[Transaction]:
    """Convert DB row dicts back to Transaction objects for excel_writer/merger."""
    txns = []
    for r in rows:
        txns.append(
            Transaction(
                date=date.fromisoformat(r["date"]),
                description=r["description"],
                withdrawal=r["withdrawal"],
                deposit=r["deposit"],
                account_number=r["account_number"],
                account_type=r["account_type"],
                category=r["category"],
                month=r["month"],
                is_internal_transfer=bool(r["is_internal_transfer"]),
            )
        )
    return txns
