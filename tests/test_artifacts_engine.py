"""P2: artifact engine core — resolvers, repeat groups, checkbox fill.

Exercised against the real plan.pdf template using field names verified during
the field-map spike (SurnameRow1, the disability checkboxes, and the bank-account
repeat group).
"""

from __future__ import annotations

import io
import sys
from pathlib import Path

import pypdf
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.db.database import get_connection, init_db
from src.db.queries_estate import insert_account, insert_managed_person
from src.models.estate import Account, ManagedPerson
from src.services.artifacts.fill import fill_artifact, resolve_artifact
from src.services.artifacts.resolvers import Ctx, get_resolver
from src.services.artifacts.spec import parse_spec

TEMPLATE = "templates/nswtg/plan.pdf"


def _conn(tmp_path):
    conn = get_connection(tmp_path / "test.db")
    init_db(conn)
    return conn


def _seed(conn) -> int:
    rid = insert_managed_person(
        conn,
        ManagedPerson(
            surname="GENTILI",
            given_names="Renato",
            disability_flags='["brain_injury"]',
        ),
    )
    insert_account(
        conn,
        Account(
            managed_person_id=rid,
            institution="ANZ",
            account_number="437669532",
            bsb="013711",
        ),
    )
    insert_account(
        conn,
        Account(
            managed_person_id=rid,
            institution="ANZ",
            account_number="178865319",
            bsb="012401",
        ),
    )
    return rid


def _spec():
    return parse_spec(
        {
            "key": "plan_test",
            "title": "Plan (engine test subset)",
            "template": TEMPLATE,
            "sections": [
                {
                    "key": "A",
                    "title": "A",
                    "bindings": [
                        {"field": "SurnameRow1", "resolver": "managed_person",
                         "args": {"column": "surname"}},
                        {"field": "Other namesRow1", "resolver": "managed_person",
                         "args": {"column": "other_names"}},
                        {"field": "Brain injury", "type": "checkbox", "on_state": "/On",
                         "resolver": "disability_flag", "args": {"flag": "brain_injury"}},
                        {"field": "Age related", "type": "checkbox", "on_state": "/On",
                         "resolver": "disability_flag", "args": {"flag": "age_related"}},
                    ],
                    "repeat_groups": [
                        {
                            "source": "accounts",
                            "max_rows": 5,
                            "columns": [
                                {"field_template": "Name of financial institutionRow{i}",
                                 "resolver": "attr", "args": {"name": "institution"}},
                                {"field_template": "BSBRow{i}",
                                 "resolver": "attr", "args": {"name": "bsb"}},
                                {"field_template": "Account numberRow{i}",
                                 "resolver": "attr", "args": {"name": "account_number"}},
                            ],
                        }
                    ],
                }
            ],
        }
    )


def test_resolve_scalar_and_blank(tmp_path):
    conn = _conn(tmp_path)
    rid = _seed(conn)
    values, blanks = resolve_artifact(_spec(), Ctx(conn=conn, managed_person_id=rid))
    assert values["SurnameRow1"] == "GENTILI"
    # other_names is None on the seeded person → blank.
    assert "Other namesRow1" in blanks


def test_checkbox_ticks_only_present_flag(tmp_path):
    conn = _conn(tmp_path)
    rid = _seed(conn)
    values, blanks = resolve_artifact(_spec(), Ctx(conn=conn, managed_person_id=rid))
    assert values["Brain injury"] == "/On"
    assert "Age related" in blanks  # not a flag Ron has


def test_repeat_group_fills_present_rows_blanks_rest(tmp_path):
    conn = _conn(tmp_path)
    rid = _seed(conn)
    values, blanks = resolve_artifact(_spec(), Ctx(conn=conn, managed_person_id=rid))
    # Two accounts seeded → rows 1-2 filled (order is list_accounts'), 3-5 blank.
    filled_accts = {values["Account numberRow1"], values["Account numberRow2"]}
    assert filled_accts == {"437669532", "178865319"}
    filled_bsbs = {values["BSBRow1"], values["BSBRow2"]}
    assert filled_bsbs == {"013711", "012401"}
    assert "Account numberRow3" in blanks
    assert "Account numberRow5" in blanks


def test_fill_artifact_values_persist_in_pdf(tmp_path):
    conn = _conn(tmp_path)
    rid = _seed(conn)
    filled = fill_artifact(_spec(), Ctx(conn=conn, managed_person_id=rid))
    assert isinstance(filled.pdf_bytes, bytes) and len(filled.pdf_bytes) > 1000
    fields = pypdf.PdfReader(io.BytesIO(filled.pdf_bytes)).get_fields() or {}
    assert fields["SurnameRow1"]["/V"] == "GENTILI"
    # Both account BSBs landed somewhere in the row-set.
    bsbs = {fields[f"BSBRow{i}"].get("/V") for i in range(1, 6)}
    assert {"013711", "012401"} <= bsbs
    # Checkbox state survives the round-trip.
    assert fields["Brain injury"]["/V"] == "/On"


def test_unknown_resolver_raises():
    with pytest.raises(KeyError):
        get_resolver("does_not_exist")
