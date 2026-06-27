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
from src.ui.help import render_nav_help
from src.views.audit import render_audit_view
from src.views.compliance import render_compliance_view
from src.views.consultation import render_consultation_view
from src.views.dashboard import render_dashboard_view
from src.views.estate_changes import render_estate_changes_view
from src.views.export import render_export_view
from src.views.forecast import render_forecast_view
from src.views.gifts import render_gifts_view
from src.views.identity import render_identity_view
from src.views.inventory import render_inventory_view
from src.views.login import render_login_view
from src.views.one_off import render_one_off_view
from src.views.submission import render_submission_view
from src.views.transactions import render_transactions_view
from src.views.upload import render_upload_view

# Sidebar navigation, grouped by how Linda actually works: the everyday
# loop, Ron's estate records, the NSWTG approval/submission surfaces, and
# the reference material. VIEW_OPTIONS stays the flat source of truth for
# routing, login redirects, and the help-registry completeness test.
NAV_GROUPS = {
    "Day to day": ["Dashboard", "Upload", "Transactions"],
    "Ron's estate": [
        "Identity",
        "Inventory",
        "Forecast",
        "Gifts",
        "One-off Events",
        "Consultations",
    ],
    "NSWTG": ["Changes in Estate", "Submissions", "Compliance"],
    "Records": ["Audit Log", "Export"],
}

VIEW_OPTIONS = [view for views in NAV_GROUPS.values() for view in views]


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


def _nav_key(group_title: str) -> str:
    slug = group_title.lower().replace(" ", "_").replace("'", "")
    return f"nav_radio_{slug}"


def _on_nav_change(changed_title: str) -> None:
    """One selection across all group radios: picking in one clears the rest."""
    chosen = st.session_state.get(_nav_key(changed_title))
    if chosen is None:
        return
    st.session_state.current_view = chosen
    for title in NAV_GROUPS:
        if title != changed_title:
            st.session_state[_nav_key(title)] = None


def _render_sidebar() -> str:
    current_view = st.session_state.get("current_view", VIEW_OPTIONS[0])
    if current_view not in VIEW_OPTIONS:
        current_view = VIEW_OPTIONS[0]

    # Programmatic navigation (e.g. dashboard quick-links set `pending_view`):
    # widget state must be written BEFORE the radios instantiate this run.
    pending = st.session_state.pop("pending_view", None)
    if pending in VIEW_OPTIONS:
        current_view = pending
    for title, views in NAV_GROUPS.items():
        st.session_state[_nav_key(title)] = (
            current_view if current_view in views else None
        )

    with st.sidebar:
        st.markdown(
            "<div style=\"font-family:Georgia,'Times New Roman',serif;font-size:1.15rem;"
            "font-weight:600;color:#2F6B60;line-height:1.25;\">Financial Manager<br>Dashboard</div>",
            unsafe_allow_html=True,
        )
        st.caption("Private Financial Management · NSW")
        st.divider()

        for title, views in NAV_GROUPS.items():
            st.radio(
                title,
                views,
                index=None,
                key=_nav_key(title),
                on_change=_on_nav_change,
                args=(title,),
            )
        render_nav_help(VIEW_OPTIONS)
        selected_view = current_view

        st.divider()
        st.caption("Period: Jun 2025 – Jun 2026")

        if st.button("Log Out", width="stretch"):
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
        "One-off Events": render_one_off_view,
        "Consultations": render_consultation_view,
        "Changes in Estate": render_estate_changes_view,
        "Submissions": render_submission_view,
        "Compliance": render_compliance_view,
        "Audit Log": render_audit_view,
        "Transactions": render_transactions_view,
        "Export": render_export_view,
    }
    view_map[selected_view]()


if __name__ == "__main__":
    main()
