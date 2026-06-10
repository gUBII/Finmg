"""Gifts ledger service — record actual spend against planned gifts.

The ledger rows come from the doc-03 loader (planned_amount only); as gifts
are actually given, Linda records the real amount (optionally linked to the
bank transaction). Every actual recorded writes an immutable audit_log entry,
so the planned→actual trail is NCAT-traceable. Section 76 assessment is NOT
touched here — that stays with the compliance engine (R-GIFT-76 / R-FC-GIFT-76).
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import replace

from src.db.queries_compliance import get_gift, insert_audit, update_gift
from src.models.compliance import AuditEntry, Gift


def record_gift_actual(
    conn: sqlite3.Connection,
    gift_id: int,
    actual_amount: float,
    actual_transaction_id: int | None = None,
    recorded_by: str | None = None,
) -> Gift:
    """Record what was actually spent on a planned gift. Returns the updated row."""
    gift = get_gift(conn, gift_id)
    if gift is None:
        raise ValueError(f"no gift with id {gift_id}")
    if actual_amount is None or actual_amount < 0:
        raise ValueError("actual_amount must be a non-negative number")

    updated = replace(
        gift,
        actual_amount=float(actual_amount),
        actual_transaction_id=actual_transaction_id,
    )
    update_gift(conn, updated)
    insert_audit(
        conn,
        AuditEntry(
            action="update",
            table_name="gifts",
            row_id=gift_id,
            actor_user=recorded_by,
            actor_role="private_manager",
            before_json=json.dumps({"actual_amount": gift.actual_amount}),
            after_json=json.dumps(
                {
                    "actual_amount": updated.actual_amount,
                    "actual_transaction_id": actual_transaction_id,
                }
            ),
            reason=f"recorded actual gift spend for gift #{gift_id} ({gift.occasion})",
        ),
    )
    return updated
