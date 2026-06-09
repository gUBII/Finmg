"""P3: plan.json field map — Section A/B + Section D forecast rollup.

Confirms the forward-looking Plan reads forecast_value (not actuals) and that
the 'Personal living expenses' line rolls up multiple granular categories.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.db.database import get_connection, init_db
from src.db.queries_estate import (
    insert_account,
    insert_managed_person,
    insert_private_manager,
)
from src.db.queries_forecast import insert_forecast, insert_forecast_category
from src.models.estate import Account, ManagedPerson, PrivateManager
from src.models.forecast import Forecast, ForecastCategory
from src.services.artifacts.fill import resolve_artifact
from src.services.artifacts.resolvers import Ctx
from src.services.artifacts.spec import load_spec

PERIOD = ("2026-07-01", "2027-06-30")


def _conn(tmp_path):
    conn = get_connection(tmp_path / "test.db")
    init_db(conn)
    return conn


def _seed(conn) -> int:
    rid = insert_managed_person(
        conn,
        ManagedPerson(
            surname="GENTILI", given_names="Renato",
            disability_flags='["physical","brain_injury"]', has_will="yes",
        ),
    )
    insert_private_manager(
        conn,
        PrivateManager(managed_person_id=rid, surname="TRAVIA",
                       given_name="Linda Jane", relationship="Lifelong partner"),
    )
    insert_account(conn, Account(managed_person_id=rid, institution="ANZ",
                                 account_number="437669532", bsb="013711", ownership="sole"))

    # Forecast categories + rows for the plan period.
    dsp = insert_forecast_category(conn, ForecastCategory(section="D_income",
                                   category_name="Disability Support Pension", display_order=0))
    groc = insert_forecast_category(conn, ForecastCategory(section="D_expenditure",
                                    category_name="Groceries", display_order=0))
    med = insert_forecast_category(conn, ForecastCategory(section="D_expenditure",
                                   category_name="Medicine (PRN & Oil)", display_order=1))
    rent = insert_forecast_category(conn, ForecastCategory(section="D_expenditure",
                                    category_name="Rent", display_order=2))
    for cat_id, fval in [(dsp, 8000.0), (groc, 3000.0), (med, 1500.0), (rent, 1200.0)]:
        insert_forecast(conn, Forecast(managed_person_id=rid, period_start=PERIOD[0],
                        period_end=PERIOD[1], category_id=cat_id, actual_value=fval,
                        forecast_value=fval))
    return rid


def _resolve(conn, rid):
    spec = load_spec("plan")
    ctx = Ctx(conn=conn, managed_person_id=rid, period_start=PERIOD[0], period_end=PERIOD[1])
    return resolve_artifact(spec, ctx)


def test_section_a_and_disability_checkboxes(tmp_path):
    conn = _conn(tmp_path)
    rid = _seed(conn)
    values, _ = _resolve(conn, rid)
    assert values["SurnameRow1"] == "GENTILI"
    assert values["Brain injury"] == "/On"
    assert values["undefined_3"] == "/On"  # physical
    assert values["Does the managed person have a Will"] == "/Yes"


def test_private_manager_row(tmp_path):
    conn = _conn(tmp_path)
    rid = _seed(conn)
    values, _ = _resolve(conn, rid)
    assert values["SurnameRow1_2"] == "TRAVIA"
    assert values["Given nameRow1"] == "Linda Jane"
    assert values["RelationshipRow1"] == "Lifelong partner"


def test_section_d_forecast_rollup(tmp_path):
    conn = _conn(tmp_path)
    rid = _seed(conn)
    values, _ = _resolve(conn, rid)
    # Pensions = DSP forecast.
    assert values["fill_19"] == "8000.00"
    # Accommodation = Rent forecast.
    assert values["fill_31"] == "1200.00"
    # Personal living = Groceries + Medicine rolled up (3000 + 1500).
    assert values["fill_32"] == "4500.00"


def test_empty_forecast_lines_blank(tmp_path):
    conn = _conn(tmp_path)
    rid = _seed(conn)
    values, blanks = _resolve(conn, rid)
    # No NDIS / super / utilities forecast → blank.
    assert "fill_28" in blanks  # NDIS
    assert "fill_36" in blanks  # utilities
