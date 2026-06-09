"""Persist a generated artifact to the submissions register (P8).

`persist_submission` writes the filled PDF to a SHA-addressed path under
`data/attachments/<submission_id>/` (gitignored — contains PII), records a
`submissions` row with the path + SHA, auto-attaches the ingested ANZ
statements that overlap the period as `submission_attachments`, and drops an
`index.json` sidecar listing everything. Every write is audited.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import replace
from pathlib import Path

from src.db.queries import get_uploaded_pdfs
from src.db.queries_compliance import (
    insert_attachment,
    insert_audit,
    insert_submission,
    update_submission,
)
from src.models.compliance import AuditEntry, Submission, SubmissionAttachment

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
ATTACHMENTS_ROOT = REPO_ROOT / "data" / "attachments"

# Artifact key → submissions.type (the table's CHECK enum).
_ARTIFACT_TO_TYPE = {
    "annual_accounts": "annual_accounts",
    "plan": "initial_plan",
}


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _statements_in_period(conn, period_start: str | None, period_end: str | None) -> list[dict]:
    """Ingested ANZ statements whose reporting window overlaps the period."""
    out = []
    for pdf in get_uploaded_pdfs(conn):
        rs, re_ = pdf.get("report_start"), pdf.get("report_end")
        if period_start and period_end and rs and re_:
            if re_ < period_start or rs > period_end:
                continue
        out.append(pdf)
    return out


def persist_submission(
    conn: sqlite3.Connection,
    artifact_key: str,
    managed_person_id: int,
    pdf_bytes: bytes,
    period_start: str | None = None,
    period_end: str | None = None,
    recorded_by: str | None = None,
    attachments_root: Path = ATTACHMENTS_ROOT,
) -> Submission:
    """Write the filled PDF to disk and register the submission + attachments."""
    sub_type = _ARTIFACT_TO_TYPE.get(artifact_key)
    if sub_type is None:
        raise ValueError(f"unknown artifact_key {artifact_key!r}")

    sub_id = insert_submission(
        conn, Submission(managed_person_id=managed_person_id, type=sub_type, status="draft")
    )

    sha = _sha256(pdf_bytes)
    out_dir = attachments_root / str(sub_id)
    out_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = out_dir / f"{sha}.pdf"
    pdf_path.write_bytes(pdf_bytes)

    # Store a repo-relative path when the file lives under the repo; else absolute.
    try:
        stored_path = str(pdf_path.relative_to(REPO_ROOT))
    except ValueError:
        stored_path = str(pdf_path)

    update_submission(
        conn,
        sub_id,
        Submission(
            id=sub_id,
            managed_person_id=managed_person_id,
            type=sub_type,
            status="draft",
            generated_pdf_path=stored_path,
            generated_pdf_sha=sha,
        ),
    )

    # Auto-attach the source bank statements that cover the period.
    attachments_index = []
    for pdf in _statements_in_period(conn, period_start, period_end):
        insert_attachment(
            conn,
            SubmissionAttachment(
                submission_id=sub_id,
                filename=pdf["filename"],
                sha=pdf["file_hash"],
                description=f"ANZ statement {pdf.get('account_number', '')} "
                            f"{pdf.get('report_start', '')}–{pdf.get('report_end', '')}".strip(),
            ),
        )
        attachments_index.append(
            {"filename": pdf["filename"], "sha": pdf["file_hash"],
             "account_number": pdf.get("account_number")}
        )

    # index.json sidecar.
    index = {
        "submission_id": sub_id,
        "artifact": artifact_key,
        "type": sub_type,
        "generated_pdf": pdf_path.name,
        "generated_pdf_sha": sha,
        "period": {"start": period_start, "end": period_end},
        "attachments": attachments_index,
    }
    (out_dir / "index.json").write_text(json.dumps(index, indent=2), encoding="utf-8")

    insert_audit(
        conn,
        AuditEntry(
            action="insert",
            table_name="submissions",
            row_id=sub_id,
            actor_user=recorded_by,
            actor_role="private_manager",
            after_json=json.dumps({"artifact": artifact_key, "sha": sha,
                                   "attachments": len(attachments_index)}),
            reason=f"generated {artifact_key} submission",
        ),
    )

    return Submission(
        id=sub_id, managed_person_id=managed_person_id, type=sub_type, status="draft",
        generated_pdf_path=stored_path, generated_pdf_sha=sha,
    )
