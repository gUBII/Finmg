"""Login view for the FinMg dashboard."""

from __future__ import annotations

import streamlit as st

from src.auth.auth import check_credentials

# Professional banner — matches the app's "calm ledger" theme
# (deep teal primary, warm paper text, serif headings).
_BANNER_HTML = """
<div style="background:linear-gradient(135deg,#2F6B60 0%,#1F4A42 100%);
            border-radius:14px;padding:2.6rem 1.5rem;text-align:center;
            box-shadow:0 10px 30px rgba(47,107,96,.22);margin-bottom:1.5rem;">
  <div style="font-family:Georgia,'Times New Roman',serif;font-size:1.95rem;
              font-weight:600;color:#F7F3EB;letter-spacing:.4px;line-height:1.2;">
    Financial Manager Dashboard
  </div>
  <div style="font-family:sans-serif;font-size:.72rem;color:#CFE0DA;
              margin-top:.65rem;letter-spacing:2px;text-transform:uppercase;">
    Private Financial Management &middot; NSW
  </div>
</div>
"""


def render_login_view() -> None:
    """Render the login gate."""
    left, center, right = st.columns([1, 1.25, 1])
    with center:
        st.markdown(_BANNER_HTML, unsafe_allow_html=True)
        st.caption("Sign in to access the finance workspace.")

        with st.form("login_form", clear_on_submit=False):
            username = st.text_input("Username")
            password = st.text_input("Password", type="password")
            submitted = st.form_submit_button("Log In", width="stretch")

        if submitted:
            if check_credentials(username, password):
                st.session_state.authenticated = True
                st.session_state.current_view = "Dashboard"
                st.rerun()
            st.error("Incorrect username or password.")
