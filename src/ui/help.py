"""(?) help affordances — click popovers fed by src/config/help_content.json.

Every page title and section heading gets a small "?" popover beside it that
explains, in plain English for Linda: what the section is, where its data
comes from, what to do with it, and the NSWTG handbook reference if relevant.

Copy lives in one registry (help_content.json) so it can be reviewed and
edited without touching view code — same pattern as categories.json.
tests/test_help_content.py enforces that every key referenced by a view
exists in the registry.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Callable

import streamlit as st

HELP_PATH = Path(__file__).parent.parent / "config" / "help_content.json"

# Field → display label, in render order.
_FIELD_LABELS = (
    ("what", "**What this is:**"),
    ("source", "**Where it comes from:**"),
    ("do", "**What to do:**"),
)


@lru_cache(maxsize=1)
def load_help() -> dict[str, dict[str, str]]:
    """Load the help registry once per process."""
    with open(HELP_PATH, encoding="utf-8") as f:
        return json.load(f)


def help_markdown(key: str) -> str | None:
    """Full markdown body for a popover, or None if the key has no copy."""
    entry = load_help().get(key)
    if not entry:
        return None
    parts = [
        f"{label} {entry[field]}"
        for field, label in _FIELD_LABELS
        if entry.get(field)
    ]
    if entry.get("ref"):
        parts.append(f"*{entry['ref']}*")
    return "\n\n".join(parts) or None


def widget_help(key: str) -> str | None:
    """Compact plain-text help for a widget's hover tooltip (help=)."""
    entry = load_help().get(key)
    if not entry:
        return None
    return " ".join(
        entry[field] for field in ("what", "do") if entry.get(field)
    ) or None


def _heading_with_help(
    render_heading: Callable[[str], None], title: str, key: str
) -> None:
    md = help_markdown(key)
    if md is None:
        # Graceful at runtime; the completeness test catches missing copy.
        render_heading(title)
        return
    with st.container(horizontal=True, vertical_alignment="bottom"):
        render_heading(title)
        with st.popover("?", help="Tap to see what this section does"):
            st.markdown(md)


def page_header(title: str, key: str) -> None:
    """Page title with a click-to-open "(?)" explainer."""
    _heading_with_help(st.title, title, key)


def section_header(title: str, key: str) -> None:
    """Section heading with a click-to-open "(?)" explainer."""
    _heading_with_help(st.subheader, title, key)


def render_nav_help(view_options: list[str]) -> None:
    """Sidebar "(?)" — one-line explanation of every page in the nav."""
    registry = load_help()
    with st.popover("？ What does each page do?", width="stretch"):
        for view in view_options:
            entry = registry.get(f"nav.{view}")
            if entry and entry.get("what"):
                st.markdown(f"**{view}** — {entry['what']}")
