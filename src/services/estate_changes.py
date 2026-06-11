"""Change-in-Estate workflow service (S8, handbook §14 / form Appendix A).

A proposed change is a `submissions` row (type 'change_in_estate',
trigger_subsection = Appendix-A letter A..R) paired 1:1 with an
`estate_change_details` row. The subsection registry — titles, the handbook
§14 trigger text, required attachments, and compliance notes — lives in
`src/config/appendix_a.json` (JSON owns structure, Python owns logic).

Status lifecycle on submissions.status:
    draft → submitted → approved | rejected;  rejected → submitted (resubmit).
Every mutation writes an immutable audit_log entry.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

from src.db.queries_compliance import (
    get_estate_change_detail,
    get_submission,
    insert_audit,
    insert_estate_change_detail,
    insert_submission,
    list_submissions,
    update_submission,
)
from src.models.compliance import AuditEntry, EstateChangeDetail, Submission

APPENDIX_A_PATH = Path(__file__).parent.parent / "config" / "appendix_a.json"

_VALID_TRANSITIONS: dict[str, set[str]] = {
    "draft": {"submitted"},
    "submitted": {"approved", "rejected"},
    "approved": set(),
    "rejected": {"submitted"},
}


@dataclass(frozen=True)
class EstateChange:
    """A submission + its detail, as the views consume them together."""
    submission: Submission
    detail: EstateChangeDetail | None


@lru_cache(maxsize=1)
def load_appendix_a() -> dict[str, dict]:
    """The Appendix-A subsection registry, keyed by letter A..R."""
    with APPENDIX_A_PATH.open(encoding="utf-8") as f:
        return json.load(f)


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def record_change(
    conn: sqlite3.Connection,
    managed_person_id: int,
    subsection: str,
    description: str,
    amount: float | None = None,
    affordability_confirmed: bool = False,
    views: list[dict] | None = None,
    notes: str | None = None,
    recorded_by: str | None = None,
) -> EstateChange:
    """Create a draft Change-in-Estate proposal. Audited."""
    registry = load_appendix_a()
    if subsection not in registry:
        raise ValueError(f"unknown Appendix-A subsection {subsection!r} (expected A..R)")
    if not description or not description.strip():
        raise ValueError("description must be non-empty")
    if amount is not None and amount < 0:
        raise ValueError("amount must be non-negative")

    sub_id = insert_submission(
        conn,
        Submission(
            managed_person_id=managed_person_id,
            type="change_in_estate",
            trigger_subsection=subsection,
            status="draft",
        ),
    )
    detail = EstateChangeDetail(
        submission_id=sub_id,
        description=description.strip(),
        amount=amount,
        affordability_confirmed=affordability_confirmed,
        views_json=json.dumps(views) if views else None,
        notes=notes,
    )
    detail_id = insert_estate_change_detail(conn, detail)

    insert_audit(
        conn,
        AuditEntry(
            action="insert",
            table_name="submissions",
            row_id=sub_id,
            actor_user=recorded_by,
            actor_role="private_manager",
            after_json=json.dumps(
                {
                    "type": "change_in_estate",
                    "subsection": subsection,
                    "title": registry[subsection]["title"],
                    "amount": amount,
                }
            ),
            reason=f"proposed change in estate — Appendix A §{subsection}",
        ),
    )

    return EstateChange(
        submission=get_submission(conn, sub_id),
        detail=replace(detail, id=detail_id),
    )


def update_change_status(
    conn: sqlite3.Connection,
    submission_id: int,
    new_status: str,
    ncat_reference: str | None = None,
    recorded_by: str | None = None,
) -> Submission:
    """Move a proposal through draft → submitted → approved/rejected. Audited."""
    sub = get_submission(conn, submission_id)
    if sub is None:
        raise ValueError(f"no submission with id {submission_id}")
    if sub.type != "change_in_estate":
        raise ValueError(f"submission {submission_id} is not a change_in_estate")
    allowed = _VALID_TRANSITIONS.get(sub.status, set())
    if new_status not in allowed:
        raise ValueError(
            f"cannot move from {sub.status!r} to {new_status!r} "
            f"(allowed: {sorted(allowed) or 'none'})"
        )

    now = _now_iso()
    updated = replace(
        sub,
        status=new_status,
        submitted_at=now if new_status == "submitted" else sub.submitted_at,
        submitted_by=recorded_by if new_status == "submitted" else sub.submitted_by,
        ncat_reference=ncat_reference or sub.ncat_reference,
        ncat_decision_at=now
        if new_status in ("approved", "rejected")
        else sub.ncat_decision_at,
    )
    update_submission(conn, submission_id, updated)

    insert_audit(
        conn,
        AuditEntry(
            action="update",
            table_name="submissions",
            row_id=submission_id,
            actor_user=recorded_by,
            actor_role="private_manager",
            before_json=json.dumps({"status": sub.status}),
            after_json=json.dumps(
                {"status": new_status, "ncat_reference": updated.ncat_reference}
            ),
            reason=f"change-in-estate §{sub.trigger_subsection} status → {new_status}",
        ),
    )

    return get_submission(conn, submission_id)


def list_changes(conn: sqlite3.Connection, managed_person_id: int) -> list[EstateChange]:
    """All Change-in-Estate proposals, newest first, with details attached."""
    subs = list_submissions(conn, managed_person_id, type_="change_in_estate")
    return [
        EstateChange(submission=s, detail=get_estate_change_detail(conn, s.id))
        for s in subs
    ]
