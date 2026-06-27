"""Tests for scripts/load_gift_ledger.py — loads doc-03 gift forecast into gifts.

Uses a synthetic ledger dict (no PII file dependency) against a temp DB.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.load_gift_ledger import SOURCE_TAG, load_gift_ledger
from src.db.database import get_connection, init_db
from src.db.queries_compliance import list_audit, list_gifts
from src.db.queries_estate import insert_managed_person, insert_significant_person
from src.models.estate import ManagedPerson, SignificantPerson


def _conn(tmp_path):
    conn = get_connection(tmp_path / "test.db")
    init_db(conn)
    return conn


def _seed(conn) -> int:
    rid = insert_managed_person(conn, ManagedPerson(surname="GENTILI", given_names="Renato"))
    insert_significant_person(conn, SignificantPerson(
        managed_person_id=rid, surname="GENTILI", given_name="Sebastian", relationship="Son"))
    insert_significant_person(conn, SignificantPerson(
        managed_person_id=rid, surname="?", given_name="Mikayla", relationship="Possibly a cousin"))
    return rid


LEDGER = {
    "occasion_dates": {"christmas": "2026-12-25", "easter": "2026-04-05",
                       "birthday": None, "wedding": None},
    "rows": [
        {"surname": "GENTILI", "given_name": "Sebastian",
         "occasions": {"birthday": 100, "christmas": 100, "easter": 100}},
        {"surname": "?", "given_name": "Mikayla", "occasions": {"wedding": 300},
         "flag_reason": "Relationship uncertain."},
        {"surname": None, "given_name": "Linda Jane Travia", "not_significant_person": True,
         "occasions": {"birthday": 100}, "flag_reason": "Recipient is the private manager."},
        {"surname": "NOBODY", "given_name": "Ghost", "occasions": {"birthday": 50}},
    ],
}


def test_load_inserts_rows_and_reports(tmp_path):
    conn = _conn(tmp_path)
    rid = _seed(conn)
    summary = load_gift_ledger(conn, LEDGER, rid)
    # Recipients are gift-owned now — every row loads (no significant_people
    # match required). Sebastian 3 + Mikayla 1 + Linda 1 + Ghost 1 = 6.
    assert summary["inserted"] == 6
    assert summary["flagged"] == 2
    assert "unmatched" not in summary
    # Sebastian 3x$100 + Mikayla $300 + Linda $100 + Ghost $50 = $750.
    assert summary["total_planned"] == 750.0
    gifts = list_gifts(conn, rid)
    assert len(gifts) == 6
    assert all(SOURCE_TAG in (g.notes or "") for g in gifts)
    # Recipient identity lives on the gift, not via an FK.
    assert all(g.recipient_name for g in gifts)


def test_flag_policy_and_dates(tmp_path):
    conn = _conn(tmp_path)
    rid = _seed(conn)
    load_gift_ledger(conn, LEDGER, rid)
    gifts = list_gifts(conn, rid)
    by_occasion = {}
    for g in gifts:
        by_occasion.setdefault(g.occasion, []).append(g)
    # Matched relative seasonal rows are compliant; flag_reason rows are flagged.
    assert all(g.section_76_assessment == "compliant"
               for g in by_occasion["christmas"] + by_occasion["easter"])
    assert by_occasion["wedding"][0].section_76_assessment == "flagged"
    # Dated occasions get the nominal date; birthdays stay undated.
    assert by_occasion["christmas"][0].occasion_date == "2026-12-25"
    assert all(g.occasion_date is None for g in by_occasion["birthday"])
    # Recipient name is gift-owned (no FK into significant_people).
    linda = [g for g in by_occasion["birthday"]
             if "Linda" in (g.recipient_name or "")]
    assert len(linda) == 1 and "Linda" in (linda[0].notes or "")


def test_reload_is_idempotent(tmp_path):
    conn = _conn(tmp_path)
    rid = _seed(conn)
    load_gift_ledger(conn, LEDGER, rid)
    summary2 = load_gift_ledger(conn, LEDGER, rid)
    assert summary2["replaced"] == 6
    assert len(list_gifts(conn, rid)) == 6  # no duplicates


def test_load_writes_audit(tmp_path):
    conn = _conn(tmp_path)
    rid = _seed(conn)
    load_gift_ledger(conn, LEDGER, rid)
    audits = list_audit(conn, "gifts")
    assert len(audits) == 1
    assert SOURCE_TAG in (audits[0].after_json or "")
