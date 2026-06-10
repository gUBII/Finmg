"""UAT: Gifts view (S6) + Dashboard NCAT readiness strip via AppTest.

Login is bypassed (session_state["authenticated"]=True + current_view setter) —
the established in-process testing path. These run against the LIVE
data/finmg.db read-only: no mutating button is clicked (record-actual is
covered by unit tests in test_gifts_service.py).
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from streamlit.testing.v1 import AppTest

APP = str(Path(__file__).parent.parent / "src" / "app.py")


def _run(view: str) -> AppTest:
    at = AppTest.from_file(APP, default_timeout=30)
    at.session_state["authenticated"] = True
    at.session_state["current_view"] = view
    at.run()
    return at


def test_gifts_view_renders_ledger():
    at = _run("Gifts")
    assert not at.exception
    titles = [t.value for t in at.title]
    assert any("Gifts" in t for t in titles)
    labels = [m.label for m in at.metric]
    assert any("Planned" in l for l in labels)
    assert any("flagged" in l.lower() for l in labels)


def test_gifts_view_has_record_actual_controls():
    at = _run("Gifts")
    assert not at.exception
    # Gift picker + amount input + record button present (button NOT clicked —
    # that would mutate the live ledger).
    assert at.selectbox(key="gift_select") is not None
    assert at.number_input(key="gift_actual_amount") is not None
    assert any(b.key == "gift_record_btn" for b in at.button)


def test_dashboard_renders_ncat_strip():
    at = _run("Dashboard")
    assert not at.exception
    labels = [m.label for m in at.metric]
    assert any("Compliance blocks" in l for l in labels)
    assert any("Plan ready" in l for l in labels)
    assert any("Gift flags" in l for l in labels)


def test_dashboard_quick_nav_to_gifts():
    at = _run("Dashboard")
    assert not at.exception
    at.button(key="dash_nav_gifts").click().run()
    assert not at.exception
    assert at.session_state["current_view"] == "Gifts"
    titles = [t.value for t in at.title]
    assert any("Gifts" in t for t in titles)
