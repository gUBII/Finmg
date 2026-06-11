"""UAT: Changes in Estate (S8) + Audit Log views via AppTest.

Login is bypassed (session_state["authenticated"]=True + current_view setter).
Runs against the LIVE data/finmg.db read-only — no mutating button is clicked
(record/status paths are covered by the service unit tests).
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


def test_estate_changes_view_renders():
    at = _run("Changes in Estate")
    assert not at.exception
    titles = [t.value for t in at.title]
    assert any("Changes in Estate" in t for t in titles)
    labels = [m.label for m in at.metric]
    assert any("Drafts" in l for l in labels)
    assert any("Awaiting decision" in l for l in labels)
    # Subsection picker present with all 18 Appendix-A options.
    sb = at.selectbox(key="cie_subsection")
    assert sb is not None
    assert len(sb.options) == 18


def test_estate_changes_subsection_switch_shows_trigger():
    at = _run("Changes in Estate")
    # §Q (accommodation bond) is one of the 12 handbook triggers → warning shown.
    at.selectbox(key="cie_subsection").set_value("Q").run()
    assert not at.exception
    warnings = " ".join(w.value for w in at.warning)
    assert "Handbook §14 trigger" in warnings


def test_audit_view_renders():
    at = _run("Audit Log")
    assert not at.exception
    titles = [t.value for t in at.title]
    assert any("Audit Log" in t for t in titles)
    labels = [m.label for m in at.metric]
    assert any("Total entries" in l for l in labels)
    assert at.selectbox(key="audit_table") is not None
    assert at.selectbox(key="audit_action") is not None


def test_audit_view_filters_rerun():
    at = _run("Audit Log")
    at.selectbox(key="audit_action").set_value("update").run()
    assert not at.exception
    at.text_input(key="audit_search").set_value("zzz-no-such-entry").run()
    assert not at.exception
