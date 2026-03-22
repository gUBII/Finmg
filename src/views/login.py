"""Login view for the FinMg dashboard."""

from __future__ import annotations

from pathlib import Path

import streamlit as st

from src.auth.auth import check_credentials


def resolve_profile_image() -> Path | None:
    """Return the best available local profile image for Linda-Jane."""
    repo_root = Path(__file__).resolve().parents[2]
    candidates = [
        repo_root / "src" / "assets" / "linda_web.png",
        repo_root / "linda.png",
    ]
    for path in candidates:
        if path.exists():
            return path
    return None


def render_login_view() -> None:
    """Render the login gate."""
    left, center, right = st.columns([1, 1.25, 1])
    with center:
        profile_image = resolve_profile_image()
        if profile_image is not None:
            st.image(str(profile_image), use_container_width=True)
        else:
            st.markdown("## FinMg")

        st.markdown("### Linda-Jane Dashboard")
        st.caption("Sign in to access the household finance workspace.")

        with st.form("login_form", clear_on_submit=False):
            username = st.text_input("Username")
            password = st.text_input("Password", type="password")
            submitted = st.form_submit_button("Log In", use_container_width=True)

        if submitted:
            if check_credentials(username, password):
                st.session_state.authenticated = True
                st.session_state.current_view = "Dashboard"
                st.rerun()
            st.error("Incorrect username or password.")
