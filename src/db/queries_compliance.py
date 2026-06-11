"""CRUD wrappers for the compliance + audit tables (migrations 004 + 006).

Style mirrors `src/db/queries_estate.py` / `queries_forecast.py`: plain
functions taking a sqlite3.Connection, returning frozen DTOs from
`src/models/compliance.py`. Mutation helpers commit before returning.

Covers the compliance tables that previously had no query layer:
compliance_settings, artifact_field_rationales, submissions,
acknowledgements, submission_attachments, gifts, consultation_log, and an
append-only insert for audit_log. `notifications_log` is intentionally left
out until a notifications view needs it.

`audit_log` is append-only (UPDATE/DELETE blocked by triggers in 004), so only
`insert_audit` is exposed.
"""

from __future__ import annotations

import sqlite3
from dataclasses import asdict, fields

from src.models.compliance import (
    Acknowledgement,
    AuditEntry,
    ComplianceSetting,
    ConsultationLogEntry,
    EstateChangeDetail,
    FieldRationale,
    Gift,
    Submission,
    SubmissionAttachment,
)


def _row_to_dto(row: sqlite3.Row, dto_class):
    """Convert a Row to a dataclass, dropping columns the dataclass doesn't define."""
    valid = {f.name for f in fields(dto_class)}
    kwargs = {k: row[k] for k in row.keys() if k in valid}
    return dto_class(**kwargs)


# ---------------------------------------------------------------------------
# compliance_settings  (upsert by rule_key)
# ---------------------------------------------------------------------------

def upsert_compliance_setting(conn: sqlite3.Connection, setting: ComplianceSetting) -> None:
    """Insert or update the toggle for a rule. Keyed by rule_key (PK)."""
    conn.execute(
        """
        INSERT INTO compliance_settings (rule_key, mode, threshold_json, updated_at)
        VALUES (?, ?, ?, datetime('now'))
        ON CONFLICT(rule_key) DO UPDATE SET
            mode = excluded.mode,
            threshold_json = excluded.threshold_json,
            updated_at = datetime('now')
        """,
        (setting.rule_key, setting.mode, setting.threshold_json),
    )
    conn.commit()


def get_compliance_setting(conn: sqlite3.Connection, rule_key: str) -> ComplianceSetting | None:
    row = conn.execute(
        "SELECT * FROM compliance_settings WHERE rule_key = ?", (rule_key,)
    ).fetchone()
    return _row_to_dto(row, ComplianceSetting) if row else None


def list_compliance_settings(conn: sqlite3.Connection) -> list[ComplianceSetting]:
    rows = conn.execute(
        "SELECT * FROM compliance_settings ORDER BY rule_key"
    ).fetchall()
    return [_row_to_dto(r, ComplianceSetting) for r in rows]


# ---------------------------------------------------------------------------
# artifact_field_rationales  (upsert by artifact_key + field_key + person)
# ---------------------------------------------------------------------------

def upsert_field_rationale(conn: sqlite3.Connection, r: FieldRationale) -> int:
    """Record (or replace) the rationale for an intentionally-blank field/section.

    Returns the row id. Unique on (artifact_key, field_key, managed_person_id).
    """
    cur = conn.execute(
        """
        INSERT INTO artifact_field_rationales
            (artifact_key, field_key, managed_person_id, rationale, recorded_by)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(artifact_key, field_key, managed_person_id) DO UPDATE SET
            rationale = excluded.rationale,
            recorded_by = excluded.recorded_by,
            recorded_at = datetime('now')
        """,
        (r.artifact_key, r.field_key, r.managed_person_id, r.rationale, r.recorded_by),
    )
    conn.commit()
    row = conn.execute(
        "SELECT id FROM artifact_field_rationales "
        "WHERE artifact_key = ? AND field_key = ? AND managed_person_id = ?",
        (r.artifact_key, r.field_key, r.managed_person_id),
    ).fetchone()
    return row["id"]


def get_field_rationale(
    conn: sqlite3.Connection,
    artifact_key: str,
    field_key: str,
    managed_person_id: int,
) -> FieldRationale | None:
    row = conn.execute(
        "SELECT * FROM artifact_field_rationales "
        "WHERE artifact_key = ? AND field_key = ? AND managed_person_id = ?",
        (artifact_key, field_key, managed_person_id),
    ).fetchone()
    return _row_to_dto(row, FieldRationale) if row else None


def list_field_rationales(
    conn: sqlite3.Connection,
    artifact_key: str,
    managed_person_id: int,
) -> list[FieldRationale]:
    rows = conn.execute(
        "SELECT * FROM artifact_field_rationales "
        "WHERE artifact_key = ? AND managed_person_id = ? ORDER BY field_key",
        (artifact_key, managed_person_id),
    ).fetchall()
    return [_row_to_dto(r, FieldRationale) for r in rows]


def delete_field_rationale(
    conn: sqlite3.Connection,
    artifact_key: str,
    field_key: str,
    managed_person_id: int,
) -> None:
    conn.execute(
        "DELETE FROM artifact_field_rationales "
        "WHERE artifact_key = ? AND field_key = ? AND managed_person_id = ?",
        (artifact_key, field_key, managed_person_id),
    )
    conn.commit()


# ---------------------------------------------------------------------------
# audit_log  (append-only)
# ---------------------------------------------------------------------------

def insert_audit(conn: sqlite3.Connection, entry: AuditEntry) -> int:
    """Append one immutable audit row. UPDATE/DELETE are blocked by triggers."""
    data = asdict(entry)
    data.pop("id", None)
    data.pop("timestamp", None)  # DB default datetime('now')
    cols = ", ".join(data.keys())
    placeholders = ", ".join("?" for _ in data)
    cur = conn.execute(
        f"INSERT INTO audit_log ({cols}) VALUES ({placeholders})",
        tuple(data.values()),
    )
    conn.commit()
    return cur.lastrowid


def list_audit(
    conn: sqlite3.Connection,
    table_name: str | None = None,
    limit: int = 200,
    action: str | None = None,
    search: str | None = None,
) -> list[AuditEntry]:
    """Newest-first audit entries, optionally filtered.

    `search` matches case-insensitively against reason, actor, and the
    before/after JSON payloads.
    """
    clauses, params = [], []
    if table_name:
        clauses.append("table_name = ?")
        params.append(table_name)
    if action:
        clauses.append("action = ?")
        params.append(action)
    if search:
        like = f"%{search}%"
        clauses.append(
            "(reason LIKE ? OR actor_user LIKE ? OR before_json LIKE ? OR after_json LIKE ?)"
        )
        params.extend([like, like, like, like])
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    rows = conn.execute(
        f"SELECT * FROM audit_log {where} ORDER BY id DESC LIMIT ?",
        (*params, limit),
    ).fetchall()
    return [_row_to_dto(r, AuditEntry) for r in rows]


def list_audit_tables(conn: sqlite3.Connection) -> list[str]:
    """Distinct table names appearing in the audit log (for filter pickers)."""
    rows = conn.execute(
        "SELECT DISTINCT table_name FROM audit_log ORDER BY table_name"
    ).fetchall()
    return [r["table_name"] for r in rows]


def count_audit(conn: sqlite3.Connection) -> int:
    return conn.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0]


# ---------------------------------------------------------------------------
# submissions
# ---------------------------------------------------------------------------

def insert_submission(conn: sqlite3.Connection, sub: Submission) -> int:
    data = asdict(sub)
    data.pop("id", None)
    cols = ", ".join(data.keys())
    placeholders = ", ".join("?" for _ in data)
    cur = conn.execute(
        f"INSERT INTO submissions ({cols}) VALUES ({placeholders})",
        tuple(data.values()),
    )
    conn.commit()
    return cur.lastrowid


def update_submission(conn: sqlite3.Connection, sub_id: int, sub: Submission) -> None:
    data = asdict(sub)
    data.pop("id", None)
    set_clauses = ", ".join(f"{c} = ?" for c in data)
    conn.execute(
        f"UPDATE submissions SET {set_clauses}, updated_at = datetime('now') WHERE id = ?",
        (*data.values(), sub_id),
    )
    conn.commit()


def get_submission(conn: sqlite3.Connection, sub_id: int) -> Submission | None:
    row = conn.execute("SELECT * FROM submissions WHERE id = ?", (sub_id,)).fetchone()
    return _row_to_dto(row, Submission) if row else None


def list_submissions(
    conn: sqlite3.Connection,
    managed_person_id: int,
    type_: str | None = None,
) -> list[Submission]:
    if type_:
        rows = conn.execute(
            "SELECT * FROM submissions WHERE managed_person_id = ? AND type = ? "
            "ORDER BY id DESC",
            (managed_person_id, type_),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM submissions WHERE managed_person_id = ? ORDER BY id DESC",
            (managed_person_id,),
        ).fetchall()
    return [_row_to_dto(r, Submission) for r in rows]


# ---------------------------------------------------------------------------
# estate_change_details (1:1 with a change_in_estate submission)
# ---------------------------------------------------------------------------

def _detail_from_row(row: sqlite3.Row) -> EstateChangeDetail:
    dto = _row_to_dto(row, EstateChangeDetail)
    # SQLite stores the flag as INTEGER 0/1.
    return EstateChangeDetail(
        **{**asdict(dto), "affordability_confirmed": bool(row["affordability_confirmed"])}
    )


def insert_estate_change_detail(conn: sqlite3.Connection, detail: EstateChangeDetail) -> int:
    cur = conn.execute(
        "INSERT INTO estate_change_details "
        "(submission_id, description, amount, affordability_confirmed, views_json, notes) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (
            detail.submission_id,
            detail.description,
            detail.amount,
            int(detail.affordability_confirmed),
            detail.views_json,
            detail.notes,
        ),
    )
    conn.commit()
    return cur.lastrowid


def get_estate_change_detail(
    conn: sqlite3.Connection, submission_id: int
) -> EstateChangeDetail | None:
    row = conn.execute(
        "SELECT * FROM estate_change_details WHERE submission_id = ?", (submission_id,)
    ).fetchone()
    return _detail_from_row(row) if row else None


def update_estate_change_detail(conn: sqlite3.Connection, detail: EstateChangeDetail) -> None:
    if detail.id is None:
        raise ValueError("detail.id is required for update")
    conn.execute(
        "UPDATE estate_change_details SET description = ?, amount = ?, "
        "affordability_confirmed = ?, views_json = ?, notes = ?, "
        "updated_at = datetime('now') WHERE id = ?",
        (
            detail.description,
            detail.amount,
            int(detail.affordability_confirmed),
            detail.views_json,
            detail.notes,
            detail.id,
        ),
    )
    conn.commit()


# ---------------------------------------------------------------------------
# acknowledgements (Section G — 7 boxes per submission)
# ---------------------------------------------------------------------------

def upsert_acknowledgement(conn: sqlite3.Connection, ack: Acknowledgement) -> None:
    """Tick (or update) one of the 7 Section-G boxes for a submission."""
    conn.execute(
        """
        INSERT INTO acknowledgements (submission_id, ack_number, ticked_at, ticked_by)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(submission_id, ack_number) DO UPDATE SET
            ticked_at = excluded.ticked_at,
            ticked_by = excluded.ticked_by
        """,
        (ack.submission_id, ack.ack_number, ack.ticked_at, ack.ticked_by),
    )
    conn.commit()


def list_acknowledgements(conn: sqlite3.Connection, submission_id: int) -> list[Acknowledgement]:
    rows = conn.execute(
        "SELECT * FROM acknowledgements WHERE submission_id = ? ORDER BY ack_number",
        (submission_id,),
    ).fetchall()
    return [_row_to_dto(r, Acknowledgement) for r in rows]


# ---------------------------------------------------------------------------
# submission_attachments (SHA-tracked)
# ---------------------------------------------------------------------------

def insert_attachment(conn: sqlite3.Connection, att: SubmissionAttachment) -> int:
    cur = conn.execute(
        "INSERT INTO submission_attachments (submission_id, filename, sha, description) "
        "VALUES (?, ?, ?, ?)",
        (att.submission_id, att.filename, att.sha, att.description),
    )
    conn.commit()
    return cur.lastrowid


def list_attachments(conn: sqlite3.Connection, submission_id: int) -> list[SubmissionAttachment]:
    rows = conn.execute(
        "SELECT * FROM submission_attachments WHERE submission_id = ? ORDER BY id",
        (submission_id,),
    ).fetchall()
    return [_row_to_dto(r, SubmissionAttachment) for r in rows]


# ---------------------------------------------------------------------------
# gifts (Appendix A B + ongoing ledger; §76 assessment set at service layer)
# ---------------------------------------------------------------------------

def insert_gift(conn: sqlite3.Connection, gift: Gift) -> int:
    data = asdict(gift)
    data.pop("id", None)
    cols = ", ".join(data.keys())
    placeholders = ", ".join("?" for _ in data)
    cur = conn.execute(
        f"INSERT INTO gifts ({cols}) VALUES ({placeholders})",
        tuple(data.values()),
    )
    conn.commit()
    return cur.lastrowid


def update_gift(conn: sqlite3.Connection, gift: Gift) -> None:
    """Update a gift row in full from its DTO (e.g. recording the actual spend)."""
    if gift.id is None:
        raise ValueError("gift.id is required for update")
    data = asdict(gift)
    gift_id = data.pop("id")
    assignments = ", ".join(f"{col} = ?" for col in data)
    conn.execute(
        f"UPDATE gifts SET {assignments} WHERE id = ?",
        (*data.values(), gift_id),
    )
    conn.commit()


def get_gift(conn: sqlite3.Connection, gift_id: int) -> Gift | None:
    row = conn.execute("SELECT * FROM gifts WHERE id = ?", (gift_id,)).fetchone()
    return _row_to_dto(row, Gift) if row else None


def list_gifts(conn: sqlite3.Connection, managed_person_id: int) -> list[Gift]:
    rows = conn.execute(
        "SELECT * FROM gifts WHERE managed_person_id = ? ORDER BY occasion_date",
        (managed_person_id,),
    ).fetchall()
    return [_row_to_dto(r, Gift) for r in rows]


# ---------------------------------------------------------------------------
# consultation_log (Section F + ongoing)
# ---------------------------------------------------------------------------

def insert_consultation(conn: sqlite3.Connection, entry: ConsultationLogEntry) -> int:
    cur = conn.execute(
        "INSERT INTO consultation_log "
        "(managed_person_id, date, consulted_person_id, decision_topic, summary, attachments_json) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (
            entry.managed_person_id,
            entry.date,
            entry.consulted_person_id,
            entry.decision_topic,
            entry.summary,
            entry.attachments_json,
        ),
    )
    conn.commit()
    return cur.lastrowid


def list_consultations(
    conn: sqlite3.Connection, managed_person_id: int
) -> list[ConsultationLogEntry]:
    rows = conn.execute(
        "SELECT * FROM consultation_log WHERE managed_person_id = ? ORDER BY date DESC",
        (managed_person_id,),
    ).fetchall()
    return [_row_to_dto(r, ConsultationLogEntry) for r in rows]
