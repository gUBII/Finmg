"""S8: lodgement bundle export + mark-lodged lifecycle."""

from __future__ import annotations

import io
import sys
import zipfile
from datetime import date
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.db.database import get_connection, init_db
from src.db.queries import insert_pdf_and_transactions
from src.db.queries_compliance import list_audit
from src.db.queries_estate import insert_managed_person
from src.models.estate import ManagedPerson
from src.models.transaction import AccountMeta, Transaction
from src.services.lodgement import build_lodgement_zip, mark_lodged
from src.services.submission_record import persist_submission

STATEMENT_SHA = "abc123def456" + "0" * 52
PDF_BYTES = b"%PDF-1.7 fake filled form"
STATEMENT_BYTES = b"%PDF-1.7 fake bank statement"


@pytest.fixture
def conn(tmp_path):
    conn = get_connection(tmp_path / "test.db")
    init_db(conn)
    yield conn
    conn.close()


@pytest.fixture
def mp_id(conn):
    return insert_managed_person(
        conn, ManagedPerson(surname="GENTILI", given_names="Renato")
    )


def _ingest_statement(conn, sha=STATEMENT_SHA):
    meta = AccountMeta(
        account_type="ACCESS ACCOUNT", account_name="GENTILI RENATO",
        bsb="013711", account_number="437669532", balance=0.0,
        report_start="2026-02-01", report_end="2026-06-30",
    )
    txns = [Transaction(date=date(2026, 2, 9), description="x", withdrawal=None,
                        deposit=10.0, account_number="437669532",
                        account_type="ACCESS ACCOUNT", category="Other",
                        month="2026-02")]
    insert_pdf_and_transactions(conn, meta, txns, "statement_feb.pdf", sha)


def _saved_submission(conn, mp_id, tmp_path):
    _ingest_statement(conn)
    return persist_submission(
        conn, "annual_accounts", mp_id, PDF_BYTES,
        "2026-02-01", "2026-06-30",
        attachments_root=tmp_path / "attach",
    )


def test_bundle_contains_pdf_statements_index_manifest(conn, mp_id, tmp_path):
    sub = _saved_submission(conn, mp_id, tmp_path)
    uploads = tmp_path / "uploads"
    uploads.mkdir()
    (uploads / f"{STATEMENT_SHA[:8]}_statement_feb.pdf").write_bytes(STATEMENT_BYTES)

    blob = build_lodgement_zip(conn, sub.id, repo_root=tmp_path, uploads_dir=uploads)
    zf = zipfile.ZipFile(io.BytesIO(blob))
    names = set(zf.namelist())

    assert f"annual_accounts_{sub.id}.pdf" in names
    assert "statements/statement_feb.pdf" in names
    assert "index.json" in names
    assert "MANIFEST.txt" in names
    assert zf.read(f"annual_accounts_{sub.id}.pdf") == PDF_BYTES
    assert zf.read("statements/statement_feb.pdf") == STATEMENT_BYTES

    manifest = zf.read("MANIFEST.txt").decode()
    assert "Annual Accounts" in manifest
    assert "MISSING" not in manifest


def test_bundle_flags_missing_statement_file(conn, mp_id, tmp_path):
    sub = _saved_submission(conn, mp_id, tmp_path)
    uploads = tmp_path / "uploads-empty"
    uploads.mkdir()

    blob = build_lodgement_zip(conn, sub.id, repo_root=tmp_path, uploads_dir=uploads)
    zf = zipfile.ZipFile(io.BytesIO(blob))

    assert not any(n.startswith("statements/") for n in zf.namelist())
    manifest = zf.read("MANIFEST.txt").decode()
    assert "MISSING ON DISK" in manifest
    assert "statement_feb.pdf" in manifest
    assert "Re-upload" in manifest


def test_bundle_requires_generated_pdf(conn, mp_id):
    with pytest.raises(ValueError, match="no submission"):
        build_lodgement_zip(conn, 999)


def test_mark_lodged_sets_status_and_audits(conn, mp_id, tmp_path):
    sub = _saved_submission(conn, mp_id, tmp_path)
    lodged = mark_lodged(conn, sub.id, recorded_by="Linda")
    assert lodged.status == "submitted"
    assert lodged.submitted_at is not None
    assert lodged.submitted_by == "Linda"

    audits = list_audit(conn, search="lodged with NSWTG")
    assert audits and audits[0].row_id == sub.id

    with pytest.raises(ValueError, match="not 'draft'"):
        mark_lodged(conn, sub.id)
