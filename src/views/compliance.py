"""Compliance view — toggle handbook rules and see live findings.

Each rule can be set Off / Warn / Enforce (default Warn; Enforce hard-blocks
submission). State findings show current breaches; the Forecast panel shows
forward-looking early-warnings (projected §76 gift breach, category overrun,
estate drawdown). Mode changes are written to the immutable audit_log.
"""

from __future__ import annotations

from datetime import date, timedelta

import streamlit as st

from src.db.database import get_connection, init_db
from src.db.queries_estate import bootstrap_managed_person_if_empty
from src.services.compliance.engine import (
    ENFORCE,
    OFF,
    WARN,
    effective_mode,
    evaluate_compliance,
    set_rule_mode,
)
from src.services.compliance.rules import all_rules

_MODES = [OFF, WARN, ENFORCE]


def render_compliance_view() -> None:
    st.title("Compliance")
    st.caption("Handbook-sourced rules. Toggle enforcement; review live findings.")

    conn = get_connection()
    init_db(conn)
    mp_id = bootstrap_managed_person_if_empty(conn, "GENTILI", "Renato")

    # Period for forecast rules (trailing 12 months, projecting from today).
    today = date.today()
    period_start = (today - timedelta(days=365)).isoformat()
    period_end = today.isoformat()
    result = evaluate_compliance(
        conn, mp_id, period_start=period_start, period_end=period_end, as_of=period_end
    )

    blocking = result.blocking
    if blocking:
        st.error(f"{len(blocking)} enforced rule(s) currently failing — submission blocked.")
    else:
        st.success("No enforced rules failing — submission not blocked.")

    # ---------------------------------------------------------------- toggles
    st.subheader("Rules")
    for rule in all_rules():
        current = effective_mode(conn, rule.key)
        col1, col2 = st.columns([3, 2])
        with col1:
            tag = "🔮 " if rule.kind == "forecast" else ""
            st.markdown(f"{tag}**{rule.title}**  \n`{rule.key}` · {rule.handbook_ref}")
        with col2:
            chosen = st.selectbox(
                "Mode",
                options=_MODES,
                index=_MODES.index(current),
                key=f"mode_{rule.key}",
                label_visibility="collapsed",
            )
            if chosen != current:
                set_rule_mode(conn, rule.key, chosen, recorded_by="Linda")
                st.rerun()

    # --------------------------------------------------------------- findings
    st.subheader("Current findings")
    state = result.state_findings
    if not state:
        st.info("No current state findings.")
    for g in state:
        render = st.error if g.mode == ENFORCE else st.warning
        render(f"**[{g.mode}] {g.finding.handbook_ref} — {g.finding.title}**\n\n{g.finding.detail}")

    st.subheader("🔮 Forecast — early warnings")
    forecast = result.forecast_findings
    if not forecast:
        st.info("No anomalies projected for the current period.")
    for g in forecast:
        render = st.error if g.mode == ENFORCE else st.warning
        render(f"**[{g.mode}] {g.finding.handbook_ref} — {g.finding.title}**\n\n{g.finding.detail}")

    conn.close()
