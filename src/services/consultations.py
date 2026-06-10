"""Consultation log service (Plan Section F) — record consultations, audited.

Linda must consult Ron and the significant people on major decisions
(handbook §4.2). Each logged consultation writes the consultation_log row
plus an immutable audit_log entry so the consultation trail is NCAT-traceable.
"""

from __future__ import annotations

import json
import sqlite3

from src.db.queries_compliance import insert_audit, insert_consultation
from src.models.compliance import AuditEntry, ConsultationLogEntry


def record_consultation(
    conn: sqlite3.Connection,
    entry: ConsultationLogEntry,
    recorded_by: str | None = None,
) -> int:
    """Persist a consultation and its audit entry. Returns the new row id."""
    topic = (entry.decision_topic or "").strip()
    if not topic:
        raise ValueError("decision_topic must be non-empty")
    if not (entry.date or "").strip():
        raise ValueError("date must be non-empty")

    entry_id = insert_consultation(conn, entry)
    insert_audit(
        conn,
        AuditEntry(
            action="insert",
            table_name="consultation_log",
            row_id=entry_id,
            actor_user=recorded_by,
            actor_role="private_manager",
            after_json=json.dumps(
                {
                    "date": entry.date,
                    "consulted_person_id": entry.consulted_person_id,
                    "decision_topic": topic,
                }
            ),
            reason="logged consultation with significant person",
        ),
    )
    return entry_id
