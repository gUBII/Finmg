"""Gifts view (S6) — §76 gift ledger: planned vs actual, flags, record actuals.

The ledger is pre-populated from the doc-03 handwritten gift forecast
(planned_amount per recipient x occasion). This view tracks actual spend
against the estimate, surfaces every §76-flagged row with its reason, and
lets Linda record an actual (audited via the gifts service). Section 76
assessments themselves belong to the compliance engine, not this view.
"""

from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st

from src.db.database import get_connection, init_db
from src.db.queries_compliance import list_gifts
from src.db.queries_estate import bootstrap_managed_person_if_empty, list_significant_people
from src.models.compliance import Gift
from src.services.gifts import record_gift_actual

OCCASION_LABELS = {
    "birthday": "Birthday",
    "christmas": "Christmas",
    "easter": "Easter",
    "mothers_day": "Mother's Day",
    "fathers_day": "Father's Day",
    "valentines": "Valentine's Day",
    "wedding": "Wedding",
}


def _recipient_names(conn, mp_id: int) -> dict[int, str]:
    people = list_significant_people(conn, mp_id, include_deceased=True)
    return {p.id: f"{p.given_name} {p.surname}".strip() for p in people}


def _display_name(gift: Gift, names: dict[int, str]) -> str:
    if gift.recipient_id is not None and gift.recipient_id in names:
        return names[gift.recipient_id]
    # Loader rows without an FK carry "planned for <name>" in notes.
    notes = gift.notes or ""
    marker = "planned for "
    if marker in notes:
        tail = notes.split(marker, 1)[1]
        return tail.split(" — ", 1)[0].strip()
    return "(unattributed)"


def _flag_reason(gift: Gift) -> str | None:
    notes = gift.notes or ""
    return notes.split(" — ", 1)[1].strip() if " — " in notes else None


def _ledger_frame(gifts: list[Gift], names: dict[int, str]) -> pd.DataFrame:
    rows = []
    for g in gifts:
        rows.append(
            {
                "Recipient": _display_name(g, names),
                "Occasion": OCCASION_LABELS.get(g.occasion, g.occasion or "—"),
                "Date": g.occasion_date or "—",
                "Planned": g.planned_amount or 0.0,
                "Actual": g.actual_amount,
                "§76": "🚩 flagged" if g.section_76_assessment != "compliant" else "✓",
            }
        )
    return pd.DataFrame(rows)


def render_gifts_view() -> None:
    st.title("Gifts")
    st.caption(
        "Section 76 gift ledger — planned estimates from the submitted Plan, "
        "actuals recorded as gifts are given. Flags come from the compliance engine."
    )

    conn = get_connection()
    init_db(conn)
    mp_id = bootstrap_managed_person_if_empty(conn, "GENTILI", "Renato")

    gifts = list_gifts(conn, mp_id)
    if not gifts:
        st.info(
            "No gifts on the ledger yet. Load the doc-03 forecast with "
            "`python3 scripts/load_gift_ledger.py`, or add gifts as they occur."
        )
        conn.close()
        return

    names = _recipient_names(conn, mp_id)
    planned_total = sum(g.planned_amount or 0.0 for g in gifts)
    actual_total = sum(g.actual_amount or 0.0 for g in gifts)
    flagged = [g for g in gifts if g.section_76_assessment != "compliant"]

    # ------------------------------------------------------------------- KPIs
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Planned (year)", f"${planned_total:,.2f}")
    k2.metric("Actual to date", f"${actual_total:,.2f}")
    k3.metric("Remaining budget", f"${planned_total - actual_total:,.2f}")
    k4.metric("§76 flagged", f"{len(flagged)} of {len(gifts)}")

    # ----------------------------------------------------------------- ledger
    st.subheader("Ledger")
    df = _ledger_frame(gifts, names)

    def _style_flag(val):
        if isinstance(val, str) and val.startswith("🚩"):
            return "background-color: #fff3cd; color: #856404"
        return ""

    styled = df.style.map(_style_flag, subset=["§76"]).format(
        {"Planned": "${:,.2f}", "Actual": lambda v: "—" if pd.isna(v) else f"${v:,.2f}"}
    )
    st.dataframe(styled, use_container_width=True, hide_index=True)

    # ------------------------------------------------------------ flag detail
    if flagged:
        with st.expander(f"🚩 Flagged rows ({len(flagged)}) — why"):
            for g in flagged:
                reason = _flag_reason(g) or "Flagged by the compliance engine."
                label = OCCASION_LABELS.get(g.occasion, g.occasion or "—")
                st.warning(
                    f"**{_display_name(g, names)} — {label} "
                    f"(${g.planned_amount or 0.0:,.2f})**\n\n{reason}"
                )

    # ---------------------------------------------------------- record actual
    st.subheader("Record an actual")
    st.caption(
        "When a planned gift is actually given, record the real amount here — "
        "the change is written to the immutable audit log."
    )

    def _gift_label(g: Gift) -> str:
        label = OCCASION_LABELS.get(g.occasion, g.occasion or "—")
        actual = "" if g.actual_amount is None else f" · actual ${g.actual_amount:,.2f}"
        return f"{_display_name(g, names)} — {label} (planned ${g.planned_amount or 0.0:,.2f}){actual}"

    chosen = st.selectbox(
        "Planned gift",
        options=gifts,
        format_func=_gift_label,
        key="gift_select",
    )
    amount = st.number_input(
        "Actual amount ($)",
        min_value=0.0,
        step=10.0,
        value=float(chosen.planned_amount or 0.0),
        key="gift_actual_amount",
    )
    if st.button("Record actual", key="gift_record_btn", type="primary"):
        record_gift_actual(conn, chosen.id, amount, recorded_by="Linda")
        st.success(f"Recorded ${amount:,.2f} for {_gift_label(chosen)}.")
        st.rerun()

    # ------------------------------------------------------------------ chart
    st.subheader("Planned vs actual by recipient")
    by_recipient = (
        df.assign(Actual=df["Actual"].fillna(0.0).astype(float))
        .groupby("Recipient", as_index=False)[["Planned", "Actual"]]
        .sum()
        .sort_values("Planned", ascending=True)
        .melt(id_vars="Recipient", value_vars=["Planned", "Actual"],
              var_name="Type", value_name="Amount")
    )
    fig = px.bar(
        by_recipient,
        x="Amount",
        y="Recipient",
        color="Type",
        orientation="h",
        barmode="group",
        labels={"Amount": "Amount ($)", "Type": ""},
        color_discrete_map={"Planned": "#aab7c4", "Actual": "#2ecc71"},
    )
    fig.update_layout(
        height=max(350, 28 * by_recipient["Recipient"].nunique()),
        margin=dict(t=20, b=20),
    )
    st.plotly_chart(fig, use_container_width=True)

    conn.close()
