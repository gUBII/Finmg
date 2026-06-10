"""UAT: One-off Events (Section E) + Consultations (Section F) views via AppTest.

Login is bypassed (session_state["authenticated"]=True + current_view setter).
Runs against the LIVE data/finmg.db read-only — no mutating button is clicked
(confirm/dismiss/record paths are covered by the service unit tests).
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


def test_one_off_view_renders():
    at = _run("One-off Events")
    assert not at.exception
    titles = [t.value for t in at.title]
    assert any("One-off" in t for t in titles)
    labels = [m.label for m in at.metric]
    assert any("Awaiting review" in l for l in labels)
    assert any("Completed events" in l for l in labels)
    # Threshold control + manual-add form present.
    assert at.number_input(key="oneoff_threshold") is not None


def test_one_off_threshold_change_reruns():
    at = _run("One-off Events")
    assert not at.exception
    at.number_input(key="oneoff_threshold").set_value(5000.0).run()
    assert not at.exception


def test_consultation_view_renders():
    at = _run("Consultations")
    assert not at.exception
    titles = [t.value for t in at.title]
    assert any("Consultations" in t for t in titles)
    labels = [m.label for m in at.metric]
    assert any("Consultations logged" in l for l in labels)
    # Person picker includes the Ron/external option plus significant people.
    sb = at.selectbox(key="consult_person")
    assert sb is not None
    assert any("Ron" in str(opt) for opt in sb.options)
