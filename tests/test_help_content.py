"""Help-layer registry tests.

Guards the "(?)" help system: the registry must parse, every entry must carry
real copy, every key referenced by a view via page_header/section_header/
widget_help must exist, and every nav option must have a one-liner. A new
section added without help copy fails here — that is the point.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.app import VIEW_OPTIONS
from src.ui.help import HELP_PATH, help_markdown, widget_help

ROOT = Path(__file__).parent.parent
VIEW_FILES = sorted((ROOT / "src" / "views").glob("*.py")) + [ROOT / "src" / "app.py"]

# page_header("Title", "key") / section_header(...) / widget_help("key")
_HEADER_RE = re.compile(r"(?:page_header|section_header)\(\s*[^,]+,\s*\"([^\"]+)\"")
_WIDGET_RE = re.compile(r"widget_help\(\s*\"([^\"]+)\"\s*\)")


def _registry() -> dict:
    return json.loads(HELP_PATH.read_text(encoding="utf-8"))


def _referenced_keys() -> set[str]:
    keys: set[str] = set()
    for path in VIEW_FILES:
        text = path.read_text(encoding="utf-8")
        keys.update(_HEADER_RE.findall(text))
        keys.update(_WIDGET_RE.findall(text))
    return keys


def test_registry_parses_and_entries_have_copy():
    registry = _registry()
    assert registry, "help_content.json is empty"
    for key, entry in registry.items():
        assert isinstance(entry, dict), f"{key} is not an object"
        assert entry.get("what", "").strip(), f"{key} has no 'what' copy"


def test_every_referenced_key_exists_in_registry():
    registry = _registry()
    missing = sorted(k for k in _referenced_keys() if k not in registry)
    assert not missing, f"views reference help keys with no copy: {missing}"


def test_every_nav_option_has_a_one_liner():
    registry = _registry()
    missing = [v for v in VIEW_OPTIONS if f"nav.{v}" not in registry]
    assert not missing, f"nav entries missing help one-liners: {missing}"


def test_help_markdown_renders_fields_in_order():
    md = help_markdown("dashboard.ncat_readiness")
    assert md is not None
    assert "**What this is:**" in md
    assert md.index("**What this is:**") < md.index("**What to do:**")
    assert "§" in md  # handbook ref preserved


def test_missing_key_degrades_gracefully():
    assert help_markdown("no.such.key") is None
    assert widget_help("no.such.key") is None
