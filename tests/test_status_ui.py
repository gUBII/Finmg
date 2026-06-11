"""UI-3: semantic status vocabulary stays valid and in sync with the theme."""

from __future__ import annotations

import sys
import tomllib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.ui.status import PALETTE, _STYLES, cell_css, status_chip, status_color, status_label

CONFIG = Path(__file__).parent.parent / ".streamlit" / "config.toml"

# st.badge / markdown badge directive colors Streamlit accepts.
VALID_BADGE_COLORS = {"blue", "green", "orange", "red", "violet", "gray", "primary"}


def test_every_status_uses_a_valid_badge_color():
    for key, (color, label) in _STYLES.items():
        assert color in VALID_BADGE_COLORS, key
        assert label.strip(), key


def test_palette_mirrors_theme_tokens():
    theme = tomllib.loads(CONFIG.read_text(encoding="utf-8"))["theme"]
    pairs = {
        "green": "greenColor", "green_bg": "greenBackgroundColor",
        "green_text": "greenTextColor",
        "orange": "orangeColor", "orange_bg": "orangeBackgroundColor",
        "orange_text": "orangeTextColor",
        "red": "redColor", "red_bg": "redBackgroundColor", "red_text": "redTextColor",
        "blue": "blueColor", "blue_bg": "blueBackgroundColor", "blue_text": "blueTextColor",
        "gray": "grayColor", "gray_bg": "grayBackgroundColor", "gray_text": "grayTextColor",
        "violet": "violetColor", "violet_bg": "violetBackgroundColor",
        "violet_text": "violetTextColor",
        "primary": "primaryColor",
    }
    for palette_key, theme_key in pairs.items():
        assert PALETTE[palette_key].lower() == theme[theme_key].lower(), palette_key


def test_chip_and_label_formats():
    assert status_chip("warn") == ":orange-badge[Warn]"
    assert status_chip("submitted", "Lodged") == ":blue-badge[Lodged]"
    assert status_label("approved") == "Approved"


def test_unknown_key_falls_back_to_gray_raw():
    assert status_color("no-such-status") == "gray"
    assert status_label("no-such-status") == "no-such-status"
    assert status_chip("no-such-status") == ":gray-badge[no-such-status]"


def test_cell_css_uses_palette():
    ok = cell_css("ok", center=True)
    assert PALETTE["green_bg"] in ok and PALETTE["green_text"] in ok
    assert "text-align: center" in ok
    warn = cell_css("missing")
    assert PALETTE["orange_bg"] in warn
    assert "text-align" not in warn
