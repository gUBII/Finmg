"""P7 UAT: submission + compliance views via streamlit.testing.AppTest.

Login is bypassed (session_state["authenticated"]=True + current_view setter) —
the established in-process testing path; the user declines to enter a password.
These exercise the views against the LIVE data/finmg.db (read-only here).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from streamlit.testing.v1 import AppTest

APP = str(Path(__file__).parent.parent / "src" / "app.py")


def _run(view: str) -> AppTest:
    at = AppTest.from_file(APP, default_timeout=30)
    at.session_state["authenticated"] = True
    at.session_state["current_view"] = view
    at.run()
    return at


def test_submission_view_renders():
    at = _run("Submissions")
    assert not at.exception
    titles = [t.value for t in at.title]
    assert any("Submission" in t for t in titles)
    # Readiness metrics present (Completeness, Open gaps, Compliance blocks).
    labels = [m.label for m in at.metric]
    assert any("Completeness" in l for l in labels)
    assert any("gaps" in l.lower() for l in labels)


def test_submission_view_generates():
    at = _run("Submissions")
    assert not at.exception
    # The generate step renders a "N fields filled / M blank" caption.
    captions = [c.value for c in at.caption]
    assert any("fields filled" in c for c in captions)


def test_submission_artifact_switch_to_plan():
    at = _run("Submissions")
    assert not at.exception
    # Select the Plan artifact and re-run.
    at.selectbox(key="sub_artifact").set_value("plan").run()
    assert not at.exception
    titles = [t.value for t in at.title]
    assert any("Submission" in t for t in titles)


def test_compliance_view_renders_rules_and_findings():
    at = _run("Compliance")
    assert not at.exception
    titles = [t.value for t in at.title]
    assert any("Compliance" in t for t in titles)
    # One mode selectbox per registered rule.
    from src.services.compliance.rules import all_rules
    mode_selects = [sb for sb in at.selectbox if sb.key and sb.key.startswith("mode_")]
    assert len(mode_selects) == len(all_rules())


def test_compliance_toggle_to_enforce_blocks():
    at = _run("Compliance")
    assert not at.exception
    # Flip the account-separation rule to enforce; the app should re-run cleanly.
    sb = at.selectbox(key="mode_R-SEP-01")
    sb.set_value("enforce").run()
    assert not at.exception
    # Reset back to warn so we don't leave the live DB in enforce.
    at.selectbox(key="mode_R-SEP-01").set_value("warn").run()
    assert not at.exception
