"""P8: submission persistence + attachments index."""

from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.db.database import get_connection, init_db
from src.db.queries import insert_pdf_and_transactions
from src.db.queries_compliance import get_submission, list_attachments, list_audit
from src.db.queries_estate import insert_managed_person
from src.models.estate import ManagedPerson
from src.models.transaction import AccountMeta, Transaction
from src.services.submission_record import persist_submission


def _conn(tmp_path):
    conn = get_connection(tmp_path / "test.db")
    init_db(conn)
    return conn


def _ron(conn) -> int:
    return insert_managed_person(conn, ManagedPerson(surname="GENTILI", given_names="Renato"))


def _ingest_statement(conn, acct, rs, re_):
    meta = AccountMeta(account_type="ACCESS ACCOUNT", account_name="GENTILI RENATO",
                       bsb="013711", account_number=acct, balance=0.0,
                       report_start=rs, report_end=re_)
    txns = [Transaction(date=date.fromisoformat(rs), description="x", withdrawal=None,
                        deposit=10.0, account_number=acct, account_type="ACCESS ACCOUNT",
                        category="Other", month=rs[:7])]
    insert_pdf_and_transactions(conn, meta, txns, f"{acct}.pdf", acct + "0" * (64 - len(acct)))


def test_persist_writes_submission_and_pdf(tmp_path):
    conn = _conn(tmp_path)
    rid = _ron(conn)
    root = tmp_path / "attach"
    sub = persist_submission(conn, "annual_accounts", rid, b"%PDF-1.7 fake",
                             "2026-02-01", "2026-06-30", attachments_root=root)
    assert sub.id is not None
    assert sub.type == "annual_accounts"
    assert sub.generated_pdf_sha
    # File written under <root>/<id>/<sha>.pdf
    pdf_path = root / str(sub.id) / f"{sub.generated_pdf_sha}.pdf"
    assert pdf_path.exists()
    assert pdf_path.read_bytes() == b"%PDF-1.7 fake"
    # Submission row reflects path + sha.
    stored = get_submission(conn, sub.id)
    assert stored.generated_pdf_sha == sub.generated_pdf_sha
    assert stored.generated_pdf_path.endswith(".pdf")


def test_plan_maps_to_initial_plan_type(tmp_path):
    conn = _conn(tmp_path)
    rid = _ron(conn)
    sub = persist_submission(conn, "plan", rid, b"x", attachments_root=tmp_path / "a")
    assert sub.type == "initial_plan"


def test_attachments_index_includes_statements_in_period(tmp_path):
    conn = _conn(tmp_path)
    rid = _ron(conn)
    _ingest_statement(conn, "437669532", "2026-02-09", "2026-06-08")   # in period
    _ingest_statement(conn, "999999999", "2025-01-01", "2025-03-31")   # out of period
    root = tmp_path / "a"
    sub = persist_submission(conn, "annual_accounts", rid, b"x",
                             "2026-02-01", "2026-06-30", attachments_root=root)
    atts = list_attachments(conn, sub.id)
    filenames = {a.filename for a in atts}
    assert "437669532.pdf" in filenames
    assert "999999999.pdf" not in filenames  # outside the period
    # index.json sidecar written + lists the in-period statement.
    index = json.loads((root / str(sub.id) / "index.json").read_text())
    assert index["generated_pdf_sha"] == sub.generated_pdf_sha
    assert len(index["attachments"]) == 1


def test_persist_writes_audit(tmp_path):
    conn = _conn(tmp_path)
    rid = _ron(conn)
    persist_submission(conn, "annual_accounts", rid, b"x", attachments_root=tmp_path / "a")
    audits = list_audit(conn, "submissions")
    assert len(audits) == 1
    assert "annual_accounts" in (audits[0].after_json or "")


def test_unknown_artifact_rejected(tmp_path):
    conn = _conn(tmp_path)
    rid = _ron(conn)
    with pytest.raises(ValueError):
        persist_submission(conn, "bogus", rid, b"x", attachments_root=tmp_path / "a")
