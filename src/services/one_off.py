"""One-off events service (Plan Section E) — detect, confirm, dismiss, record.

Section E of the NSWTG Plan lists one-off receipts and expenditures. Rather
than Linda combing statements, `detect_candidates` surfaces large unusual
transactions as candidates: amount at or above a threshold, not an internal
transfer, not in a known recurring category, not already confirmed (linked to
an event) or dismissed. Linda then confirms (→ one_off_events row, audited)
or dismisses (→ one_off_dismissals, audited) each candidate.

Anticipated/proposed future events that have no transaction yet are added via
`record_one_off_event`. The compliance engine's R-CIE-ONEOFF picks events up
from the table — nothing here decides whether NSWTG approval is needed.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, replace

from src.db.queries_compliance import insert_audit
from src.db.queries_forecast import (
    dismissed_transaction_ids,
    insert_one_off_dismissal,
    insert_one_off_event,
)
from src.models.compliance import AuditEntry
from src.models.forecast import OneOffEvent

DEFAULT_THRESHOLD = 1000.0

# Categories that are large but routine — never one-off candidates.
RECURRING_CATEGORIES = frozenset(
    {"Disability Support Pension", "Rent", "Savings", "Interest"}
)


@dataclass(frozen=True)
class Candidate:
    """A transaction that looks like a Section E one-off, pending Linda's call."""
    transaction_id: int
    date: str
    description: str
    amount: float
    direction: str  # 'receipt' | 'expenditure'
    account_number: str
    category: str


def detect_candidates(
    conn: sqlite3.Connection,
    threshold: float = DEFAULT_THRESHOLD,
) -> list[Candidate]:
    """Surface unreviewed transactions >= threshold as one-off candidates."""
    linked = {
        r["linked_transaction_id"]
        for r in conn.execute(
            "SELECT linked_transaction_id FROM one_off_events "
            "WHERE linked_transaction_id IS NOT NULL"
        ).fetchall()
    }
    dismissed = dismissed_transaction_ids(conn)
    reviewed = linked | dismissed

    placeholders = ", ".join("?" for _ in RECURRING_CATEGORIES)
    rows = conn.execute(
        f"""
        SELECT id, date, description, withdrawal, deposit, account_number, category
        FROM transactions
        WHERE COALESCE(is_internal_transfer, 0) = 0
          AND category NOT IN ({placeholders})
          AND (COALESCE(withdrawal, 0) >= ? OR COALESCE(deposit, 0) >= ?)
        ORDER BY date DESC, id DESC
        """,
        (*RECURRING_CATEGORIES, threshold, threshold),
    ).fetchall()

    out: list[Candidate] = []
    for r in rows:
        if r["id"] in reviewed:
            continue
        is_receipt = (r["deposit"] or 0) >= threshold
        out.append(
            Candidate(
                transaction_id=r["id"],
                date=r["date"],
                description=r["description"],
                amount=float(r["deposit"] if is_receipt else r["withdrawal"]),
                direction="receipt" if is_receipt else "expenditure",
                account_number=r["account_number"],
                category=r["category"],
            )
        )
    return out


def confirm_candidate(
    conn: sqlite3.Connection,
    managed_person_id: int,
    candidate: Candidate,
    recorded_by: str | None = None,
) -> OneOffEvent:
    """Confirm a candidate as a real Section E event (status completed, audited)."""
    event = OneOffEvent(
        managed_person_id=managed_person_id,
        event_type=candidate.direction,
        event_description=candidate.description,
        status="completed",
        amount=candidate.amount,
        date_occurred=candidate.date,
        linked_transaction_id=candidate.transaction_id,
        notes=f"confirmed from transaction #{candidate.transaction_id} "
              f"({candidate.category}, acct {candidate.account_number})",
    )
    event_id = insert_one_off_event(conn, event)
    _audit(
        conn,
        action="insert",
        row_id=event_id,
        recorded_by=recorded_by,
        payload={
            "event_description": event.event_description,
            "amount": event.amount,
            "linked_transaction_id": candidate.transaction_id,
        },
        reason=f"confirmed one-off candidate (txn #{candidate.transaction_id})",
    )
    return replace(event, id=event_id)


def dismiss_candidate(
    conn: sqlite3.Connection,
    transaction_id: int,
    reason: str | None = None,
    recorded_by: str | None = None,
) -> None:
    """Mark a candidate as reviewed-and-not-a-one-off (audited)."""
    insert_one_off_dismissal(conn, transaction_id, reason=reason, recorded_by=recorded_by)
    _audit(
        conn,
        action="insert",
        row_id=transaction_id,
        recorded_by=recorded_by,
        payload={"transaction_id": transaction_id, "reason": reason},
        reason=f"dismissed one-off candidate (txn #{transaction_id})",
        table_name="one_off_dismissals",
    )


def record_one_off_event(
    conn: sqlite3.Connection,
    event: OneOffEvent,
    recorded_by: str | None = None,
) -> int:
    """Add a manual (typically anticipated/proposed) Section E event, audited."""
    description = (event.event_description or "").strip()
    if not description:
        raise ValueError("event_description must be non-empty")
    if event.amount is not None and event.amount < 0:
        raise ValueError("amount must be non-negative")
    event_id = insert_one_off_event(conn, event)
    _audit(
        conn,
        action="insert",
        row_id=event_id,
        recorded_by=recorded_by,
        payload={
            "event_description": description,
            "event_type": event.event_type,
            "status": event.status,
            "amount": event.amount,
        },
        reason="manually recorded one-off event",
    )
    return event_id


def _audit(
    conn: sqlite3.Connection,
    action: str,
    row_id: int,
    recorded_by: str | None,
    payload: dict,
    reason: str,
    table_name: str = "one_off_events",
) -> None:
    insert_audit(
        conn,
        AuditEntry(
            action=action,
            table_name=table_name,
            row_id=row_id,
            actor_user=recorded_by,
            actor_role="private_manager",
            after_json=json.dumps(payload),
            reason=reason,
        ),
    )
