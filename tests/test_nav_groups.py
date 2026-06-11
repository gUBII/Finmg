"""UI-2: grouped sidebar navigation — one selection across four group radios."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from streamlit.testing.v1 import AppTest

from src.app import NAV_GROUPS, VIEW_OPTIONS

APP = str(Path(__file__).parent.parent / "src" / "app.py")


def _run(view: str = "Dashboard") -> AppTest:
    at = AppTest.from_file(APP, default_timeout=30)
    at.session_state["authenticated"] = True
    at.session_state["current_view"] = view
    at.run()
    return at


def test_groups_cover_all_views_exactly_once():
    flat = [v for views in NAV_GROUPS.values() for v in views]
    assert flat == VIEW_OPTIONS
    assert len(set(flat)) == len(flat)


def test_only_current_group_has_a_selection():
    at = _run("Compliance")
    assert not at.exception
    assert at.session_state["nav_radio_nswtg"] == "Compliance"
    assert at.session_state["nav_radio_day_to_day"] is None
    assert at.session_state["nav_radio_rons_estate"] is None
    assert at.session_state["nav_radio_records"] is None


def test_picking_in_another_group_switches_view_and_clears_old_group():
    at = _run("Dashboard")
    at.radio(key="nav_radio_nswtg").set_value("Compliance").run()
    assert not at.exception
    assert at.session_state["current_view"] == "Compliance"
    assert at.session_state["nav_radio_day_to_day"] is None
    # The Compliance page actually rendered.
    titles = [t.value for t in at.title]
    assert any("Compliance" in t for t in titles)
