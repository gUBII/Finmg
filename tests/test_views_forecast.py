"""UAT: Forecast view (Section D) via AppTest.

Mirrors tests/test_views_gifts_dashboard.py: login bypassed via session_state,
runs against the local data/finmg.db. The `Generate proposals` button is NOT
clicked here (its persistence is covered by test_forecast_generator.py /
test_services_forecast.py) — this only asserts the view renders with the new
annualization affordances present.
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


def test_forecast_view_renders_without_exception():
    at = _run("Forecast")
    assert not at.exception
    titles = [t.value for t in at.title]
    assert any("Forecast" in t for t in titles)


def test_forecast_view_has_generate_and_net():
    at = _run("Forecast")
    assert not at.exception
    # Generator affordance present (not clicked — would mutate the ledger).
    assert any(b.label == "Generate proposals" for b in at.button)
    # Net-position metric surfaced by the new summary row.
    labels = [m.label for m in at.metric]
    assert any("Net position" in l for l in labels)
    assert any("annual forecast" in l.lower() for l in labels)
