"""Semantic status vocabulary — one color language across every view.

The colors mirror the theme's semantic tokens in `.streamlit/config.toml`
(a test asserts they stay in sync). Views never hardcode status colors:

- `status_chip(key)`   → markdown badge (`:orange-badge[Warn]`) for labels,
  expander titles, and markdown bodies
- `status_label(key)`  → plain text for dataframe cells and selectboxes
- `cell_css(kind)`     → CSS for pandas Styler cells (month grids, ledgers)
- `PALETTE`            → hexes for plotly traces
"""

from __future__ import annotations

# status key → (badge color, default label)
_STYLES: dict[str, tuple[str, str]] = {
    # submission / estate-change lifecycle
    "draft": ("gray", "Draft"),
    "submitted": ("blue", "Submitted"),
    "approved": ("green", "Approved"),
    "rejected": ("red", "Rejected"),
    # compliance rule modes
    "off": ("gray", "Off"),
    "warn": ("orange", "Warn"),
    "enforce": ("red", "Enforce"),
    # audit actions
    "insert": ("green", "Added"),
    "update": ("blue", "Changed"),
    "delete": ("red", "Removed"),
    # one-off event lifecycle
    "anticipated": ("blue", "Anticipated"),
    "proposed": ("violet", "Proposed"),
    "completed": ("green", "Completed"),
    # generic
    "ok": ("green", "OK"),
    "missing": ("orange", "Missing"),
}

# Hexes mirror the [theme] tokens in .streamlit/config.toml.
PALETTE: dict[str, str] = {
    "green": "#1E7B4F",
    "green_bg": "#E2EFE5",
    "green_text": "#175E3D",
    "orange": "#B45309",
    "orange_bg": "#F6E9D4",
    "orange_text": "#8A3E07",
    "red": "#B3261E",
    "red_bg": "#F7E2E0",
    "red_text": "#8C1D17",
    "blue": "#1D5D8A",
    "blue_bg": "#E0EAF2",
    "blue_text": "#174A6E",
    "gray": "#6B7066",
    "gray_bg": "#ECE7DC",
    "gray_text": "#4F544B",
    "violet": "#6D5A8E",
    "violet_bg": "#EBE5F2",
    "violet_text": "#554570",
    "primary": "#2F6B60",
}


def status_color(key: str) -> str:
    """Badge color name for a status key; gray for anything unknown."""
    color, _ = _STYLES.get(key, ("gray", key))
    return color


def status_label(key: str, label: str | None = None) -> str:
    """Plain-text label for a status key (override for context-specific wording)."""
    if label is not None:
        return label
    _, default = _STYLES.get(key, ("gray", key))
    return default


def status_chip(key: str, label: str | None = None) -> str:
    """Markdown badge directive, usable in labels, expander titles, markdown."""
    return f":{status_color(key)}-badge[{status_label(key, label)}]"


def cell_css(kind: str, center: bool = False) -> str:
    """CSS for a pandas Styler cell: kind is 'ok' | 'missing' (or any color name)."""
    color = status_color(kind) if kind in _STYLES else kind
    css = f"background-color: {PALETTE[f'{color}_bg']}; color: {PALETTE[f'{color}_text']}"
    return f"{css}; text-align: center" if center else css
