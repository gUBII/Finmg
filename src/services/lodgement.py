"""Lodgement bundle export (S8, handbook §5.4 annual accounts lodgement).

Turns a saved submission into a single ZIP Linda can lodge with NSWTG:
the filled PDF, the source ANZ statements that were auto-attached when it was
generated, the machine index.json sidecar, and a human-readable MANIFEST.txt
cover sheet. A statement listed in the register but missing from disk is
called out in the manifest rather than silently dropped — an incomplete
bundle must say it is incomplete.

`mark_lodged` records the moment the bundle actually went to NSWTG.
"""

from __future__ import annotations

import io
import json
import sqlite3
import zipfile
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

from src.db.queries_compliance import (
    get_submission,
    insert_audit,
    list_attachments,
    update_submission,
)
from src.models.compliance import AuditEntry, Submission

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
UPLOADS_DIR = REPO_ROOT / "data" / "uploads"

TYPE_LABELS = {
    "annual_accounts": "Annual Accounts",
    "initial_plan": "Private Manager's Plan",
    "change_in_estate": "Change in Estate",
}


def _resolve(path_str: str, repo_root: Path) -> Path:
    path = Path(path_str)
    return path if path.is_absolute() else repo_root / path


def _find_statement_file(sha: str, uploads_dir: Path) -> Path | None:
    """Uploaded statements are saved as `<sha[:8]>_<original name>`."""
    if not uploads_dir.exists():
        return None
    matches = sorted(uploads_dir.glob(f"{sha[:8]}_*"))
    return matches[0] if matches else None


def build_lodgement_zip(
    conn: sqlite3.Connection,
    submission_id: int,
    repo_root: Path = REPO_ROOT,
    uploads_dir: Path = UPLOADS_DIR,
) -> bytes:
    """Assemble the lodgement ZIP for a saved submission. Read-only."""
    sub = get_submission(conn, submission_id)
    if sub is None:
        raise ValueError(f"no submission with id {submission_id}")
    if not sub.generated_pdf_path:
        raise ValueError(
            f"submission {submission_id} has no generated PDF — "
            "generate and save it in the Submissions view first"
        )
    pdf_path = _resolve(sub.generated_pdf_path, repo_root)
    if not pdf_path.exists():
        raise ValueError(f"generated PDF missing on disk: {pdf_path}")

    attachments = list_attachments(conn, submission_id)
    label = TYPE_LABELS.get(sub.type, sub.type)

    manifest_lines = [
        "FinMg lodgement bundle",
        "======================",
        f"Submission #{submission_id} — {label}",
        f"Status: {sub.status}",
    ]
    if sub.trigger_subsection:
        manifest_lines.append(f"Appendix A subsection: {sub.trigger_subsection}")
    if sub.ncat_reference:
        manifest_lines.append(f"NCAT/NSWTG reference: {sub.ncat_reference}")
    manifest_lines += [
        f"Generated PDF SHA-256: {sub.generated_pdf_sha}",
        "",
        "Contents",
        "--------",
        f"1. {sub.type}_{submission_id}.pdf — the filled NSWTG form",
    ]

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(f"{sub.type}_{submission_id}.pdf", pdf_path.read_bytes())

        index_path = pdf_path.parent / "index.json"
        if index_path.exists():
            zf.writestr("index.json", index_path.read_text(encoding="utf-8"))
            manifest_lines.append("2. index.json — machine-readable index")

        missing: list[str] = []
        for i, att in enumerate(attachments, start=1):
            src = _find_statement_file(att.sha, uploads_dir)
            entry = f"statements/{att.filename} — {att.description or 'attachment'}"
            if src is None:
                missing.append(att.filename)
                manifest_lines.append(f"   [MISSING ON DISK] {entry} (sha {att.sha[:12]}…)")
                continue
            zf.writestr(f"statements/{att.filename}", src.read_bytes())
            manifest_lines.append(f"   {entry} (sha {att.sha[:12]}…)")

        if missing:
            manifest_lines += [
                "",
                f"WARNING: {len(missing)} attachment(s) listed in the register were "
                "not found on disk and are NOT in this bundle:",
                *(f"  - {name}" for name in missing),
                "Re-upload the statement PDFs before lodging.",
            ]

        zf.writestr("MANIFEST.txt", "\n".join(manifest_lines) + "\n")

    return buffer.getvalue()


def mark_lodged(
    conn: sqlite3.Connection,
    submission_id: int,
    recorded_by: str | None = None,
) -> Submission:
    """Record that a draft submission has been lodged with NSWTG. Audited."""
    sub = get_submission(conn, submission_id)
    if sub is None:
        raise ValueError(f"no submission with id {submission_id}")
    if sub.status != "draft":
        raise ValueError(f"submission {submission_id} is {sub.status!r}, not 'draft'")

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    update_submission(
        conn, submission_id,
        replace(sub, status="submitted", submitted_at=now, submitted_by=recorded_by),
    )
    insert_audit(
        conn,
        AuditEntry(
            action="update",
            table_name="submissions",
            row_id=submission_id,
            actor_user=recorded_by,
            actor_role="private_manager",
            before_json=json.dumps({"status": "draft"}),
            after_json=json.dumps({"status": "submitted", "submitted_at": now}),
            reason=f"{sub.type} lodged with NSWTG",
        ),
    )
    return get_submission(conn, submission_id)
