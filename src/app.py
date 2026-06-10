"""
FinMg — Linda-Jane's personal finance dashboard.

Single-page Streamlit app with login gate and sidebar navigation.
All data is persisted in SQLite (data/finmg.db).
"""

import sys
from pathlib import Path

import streamlit as st

# Ensure project root is on path when running `streamlit run src/app.py`.
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.db.database import get_connection, init_db
from src.views.compliance import render_compliance_view
from src.views.dashboard import render_dashboard_view
from src.views.export import render_export_view
from src.views.forecast import render_forecast_view
from src.views.gifts import render_gifts_view
from src.views.identity import render_identity_view
from src.views.inventory import render_inventory_view
from src.views.login import render_login_view, resolve_profile_image
from src.views.submission import render_submission_view
from src.views.transactions import render_transactions_view
from src.views.upload import render_upload_view

VIEW_OPTIONS = [
    "Dashboard",
    "Upload",
    "Identity",
    "Inventory",
    "Forecast",
    "Gifts",
    "Submissions",
    "Compliance",
    "Transactions",
    "Export",
]


def _init_session_state() -> None:
    defaults = {
        "authenticated": False,
        "current_view": "Dashboard",
        "exported_files": [],
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def _ensure_db() -> None:
    """Initialise the SQLite database on first run."""
    conn = get_connection()
    init_db(conn)
    conn.close()


def _render_sidebar() -> str:
    current_view = st.session_state.get("current_view", VIEW_OPTIONS[0])
    if current_view not in VIEW_OPTIONS:
        current_view = VIEW_OPTIONS[0]

    # Programmatic navigation (e.g. dashboard quick-links set `pending_view`):
    # widget state must be written BEFORE the radio instantiates this run.
    pending = st.session_state.pop("pending_view", None)
    if pending in VIEW_OPTIONS:
        current_view = pending
        st.session_state.nav_radio = pending
    if "nav_radio" not in st.session_state:
        st.session_state.nav_radio = current_view

    with st.sidebar:
        profile_image = resolve_profile_image()
        if profile_image is not None:
            st.image(str(profile_image), width=150)

        st.markdown("### Hi, Linda-Jane")
        st.caption("Private household finance dashboard")
        st.divider()

        selected_view = st.radio("Navigate", VIEW_OPTIONS, key="nav_radio")

        st.divider()
        st.caption("Period: Jun 2025 – Jun 2026")

        if st.button("Log Out", use_container_width=True):
            st.session_state.authenticated = False
            st.session_state.current_view = VIEW_OPTIONS[0]
            st.session_state.pending_view = VIEW_OPTIONS[0]
            st.rerun()

    st.session_state.current_view = selected_view
    return selected_view


def main() -> None:
    st.set_page_config(
        page_title="FinMg Dashboard",
        page_icon="📊",
        layout="wide",
    )

    _init_session_state()
    _ensure_db()

    if not st.session_state.authenticated:
        render_login_view()
        return

    selected_view = _render_sidebar()
    view_map = {
        "Dashboard": render_dashboard_view,
        "Upload": render_upload_view,
        "Identity": render_identity_view,
        "Inventory": render_inventory_view,
        "Forecast": render_forecast_view,
        "Gifts": render_gifts_view,
        "Submissions": render_submission_view,
        "Compliance": render_compliance_view,
        "Transactions": render_transactions_view,
        "Export": render_export_view,
    }
    view_map[selected_view]()


if __name__ == "__main__":
    main()
