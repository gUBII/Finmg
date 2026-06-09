"""P3: annual_accounts.json field map — resolves Section A/B/C from DB.

Verifies the bank-account row-set, the Section C income/expenditure rollup, and
the critical invariant that the printed totals reconcile with raw transactions
EVEN WHEN individual lines under-report (unmapped personal-living spend is in the
total but not in any line — the gap the audit engine surfaces).
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.db.database import get_connection, init_db
from src.db.queries import insert_pdf_and_transactions
from src.db.queries_estate import insert_account, insert_managed_person, insert_private_manager
from src.models.estate import Account, ManagedPerson, PrivateManager
from src.models.transaction import AccountMeta, Transaction
from src.services.artifacts.fill import resolve_artifact
from src.services.artifacts.resolvers import Ctx
from src.services.artifacts.spec import load_spec

PERIOD = ("2026-02-09", "2026-06-08")


def _conn(tmp_path):
    conn = get_connection(tmp_path / "test.db")
    init_db(conn)
    return conn


def _seed(conn) -> int:
    rid = insert_managed_person(
        conn,
        ManagedPerson(
            surname="GENTILI", given_names="Renato",
            customer_reference_number="CRN123",
        ),
    )
    insert_private_manager(
        conn,
        PrivateManager(
            managed_person_id=rid, surname="TRAVIA", given_name="Linda Jane",
            relationship="Lifelong partner", mobile="0405211554", postcode="2191",
        ),
    )
    insert_account(conn, Account(managed_person_id=rid, institution="ANZ",
                                 account_number="437669532", bsb="013711",
                                 role_label="living", ownership="sole"))
    insert_account(conn, Account(managed_person_id=rid, institution="ANZ",
                                 account_number="178865319", bsb="012401",
                                 role_label="spending", ownership="sole"))
    insert_account(conn, Account(managed_person_id=rid, institution="ANZ",
                                 account_number="178870011", bsb="012401",
                                 role_label="savings", ownership="sole"))

    meta = AccountMeta(account_type="ACCESS ACCOUNT", account_name="GENTILI RENATO",
                       bsb="013711", account_number="437669532", balance=0.0,
                       report_start=PERIOD[0], report_end=PERIOD[1])
    txns = [
        Transaction(date=date(2026, 3, 1), description="CTRLINK PENSION", withdrawal=None,
                    deposit=1420.0, account_number="437669532", account_type="ACCESS ACCOUNT",
                    category="Disability Support Pension", month="2026-03"),
        Transaction(date=date(2026, 3, 10), description="LACTALIS WAGES", withdrawal=None,
                    deposit=2817.0, account_number="437669532", account_type="ACCESS ACCOUNT",
                    category="Other", month="2026-03"),
        Transaction(date=date(2026, 3, 12), description="BP PETROL", withdrawal=200.0, deposit=None,
                    account_number="437669532", account_type="ACCESS ACCOUNT",
                    category="Car & Petrol", month="2026-03"),
        Transaction(date=date(2026, 3, 14), description="GIFT SHOP", withdrawal=50.0, deposit=None,
                    account_number="437669532", account_type="ACCESS ACCOUNT",
                    category="Gifts  & Outing", month="2026-03"),
        Transaction(date=date(2026, 3, 15), description="COLES", withdrawal=300.0, deposit=None,
                    account_number="437669532", account_type="ACCESS ACCOUNT",
                    category="Groceries", month="2026-03"),
    ]
    insert_pdf_and_transactions(conn, meta, txns, "living.pdf", "hash1" + "0" * 60)
    return rid


def _resolve(conn, rid):
    spec = load_spec("annual_accounts")
    ctx = Ctx(conn=conn, managed_person_id=rid, period_start=PERIOD[0], period_end=PERIOD[1])
    return resolve_artifact(spec, ctx)


def test_section_a_person_and_manager(tmp_path):
    conn = _conn(tmp_path)
    rid = _seed(conn)
    values, _ = _resolve(conn, rid)
    assert values["SurnameRow1"] == "GENTILI"
    assert values["Given namesRow1"] == "Renato"
    assert values["Customer reference numberRow1"] == "CRN123"
    assert values["SurnameRow1_2"] == "TRAVIA"
    assert values["Given name sRow1"] == "Linda Jane"
    assert values["From"] == "2026-02-09"
    assert values["To"] == "2026-06-08"


def test_bank_accounts_all_three_rows(tmp_path):
    conn = _conn(tmp_path)
    rid = _seed(conn)
    values, _ = _resolve(conn, rid)
    accts = {values[f"Account numberRow{i}"] for i in range(1, 4)}
    assert accts == {"437669532", "178865319", "178870011"}
    assert all(values[f"Ownership SolejointRow{i}"] == "Sole" for i in range(1, 4))
    assert all(values[f"Name of financial institutionRow{i}"] == "ANZ" for i in range(1, 4))


def test_section_c_income_rollup(tmp_path):
    conn = _conn(tmp_path)
    rid = _seed(conn)
    values, _ = _resolve(conn, rid)
    # Pensions = DSP only.
    assert values["fill_8"] == "1420.00"
    # Other income = "Other" wages line.
    assert values["fill_16"] == "2817.00"
    # Total income reconciles with all deposits.
    assert values["fill_18"] == "4237.00"


def test_section_c_expenditure_rollup_and_gap(tmp_path):
    conn = _conn(tmp_path)
    rid = _seed(conn)
    values, _ = _resolve(conn, rid)
    assert values["fill_27"] == "200.00"   # motor vehicle ← Car & Petrol
    assert values["fill_41_2"] == "50.00"  # gifts
    # Total expenditure reconciles with ALL withdrawals incl. unmapped groceries.
    assert values["fill_43_2"] == "550.00"
    # The $300 groceries are in the total but in NO mapped line → the gap.
    mapped = sum(
        float(values[f]) for f in ("fill_27", "fill_41_2") if f in values
    )
    assert mapped == 250.0
    assert float(values["fill_43_2"]) - mapped == 300.0  # unallocated personal-living


def test_unmapped_lines_stay_blank(tmp_path):
    conn = _conn(tmp_path)
    rid = _seed(conn)
    values, blanks = _resolve(conn, rid)
    # No rental, super, accommodation, utilities for Ron → blank.
    for f in ("fill_10", "fill_14", "fill_21", "fill_39_2"):
        assert f in blanks
