"""One-off Events view (S7, Plan Section E) — review candidates, manage events.

The detector surfaces large unusual transactions (threshold adjustable below);
Linda confirms each as a real Section E one-off or dismisses it with a reason.
Anticipated / proposed future events are added manually. Confirmed and manual
events feed the Plan artifact and the R-CIE-ONEOFF compliance rule (§14).
"""

from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st

from src.db.database import get_connection, init_db
from src.db.queries_estate import bootstrap_managed_person_if_empty
from src.db.queries_forecast import list_one_off_events
from src.models.forecast import OneOffEvent
from src.services.one_off import (
    DEFAULT_THRESHOLD,
    confirm_candidate,
    detect_candidates,
    dismiss_candidate,
    record_one_off_event,
)
from src.ui.help import page_header, section_header, widget_help

STATUS_LABELS = {
    "anticipated": "Anticipated",
    "proposed": "Proposed",
    "completed": "Completed",
}


def _render_candidates(conn, mp_id: int) -> None:
    section_header("Candidates for review", "one_off.candidates")
    st.caption(
        "Large unusual transactions (internal transfers and routine categories "
        "like the pension and rent are excluded). Confirm what belongs in "
        "Section E; dismiss the rest — both decisions are audit-logged."
    )
    threshold = st.number_input(
        "Detection threshold ($)",
        min_value=100.0,
        step=100.0,
        value=DEFAULT_THRESHOLD,
        key="oneoff_threshold",
        help=widget_help("one_off.threshold"),
    )
    candidates = detect_candidates(conn, threshold=threshold)
    if not candidates:
        st.success("No unreviewed transactions at this threshold.")
        return

    st.info(f"{len(candidates)} candidate(s) awaiting review.")
    for cand in candidates:
        arrow = "↓ received" if cand.direction == "receipt" else "↑ paid"
        header = (
            f"{cand.date} · {cand.description} — ${cand.amount:,.2f} {arrow}"
        )
        with st.expander(header):
            st.write(
                f"Account `{cand.account_number}` · category *{cand.category}* · "
                f"transaction #{cand.transaction_id}"
            )
            reason = st.text_input(
                "Dismissal reason (used only if you dismiss)",
                key=f"oneoff_reason_{cand.transaction_id}",
            )
            confirm_col, dismiss_col = st.columns(2)
            if confirm_col.button(
                "Confirm as one-off event",
                key=f"oneoff_confirm_{cand.transaction_id}",
                type="primary",
            ):
                confirm_candidate(conn, mp_id, cand, recorded_by="Linda")
                st.success("Confirmed — added to Section E events.")
                st.rerun()
            if dismiss_col.button(
                "Dismiss (not a one-off)",
                key=f"oneoff_dismiss_{cand.transaction_id}",
            ):
                dismiss_candidate(
                    conn, cand.transaction_id,
                    reason=reason.strip() or None, recorded_by="Linda",
                )
                st.success("Dismissed — it won't be surfaced again.")
                st.rerun()


def _render_events(conn, mp_id: int) -> None:
    section_header("Section E events", "one_off.events")
    events = list_one_off_events(conn, mp_id)
    if not events:
        st.info("No one-off events recorded yet.")
        return
    df = pd.DataFrame(
        {
            "Date": e.date_occurred or "—",
            "Type": "Receipt" if e.event_type == "receipt" else "Expenditure",
            "Description": e.event_description,
            "Status": STATUS_LABELS.get(e.status, e.status),
            "Amount": e.amount,
        }
        for e in events
    )
    styled = df.style.format(
        {"Amount": lambda v: "—" if pd.isna(v) else f"${v:,.2f}"}
    )
    st.dataframe(styled, width="stretch", hide_index=True)


def _render_add_form(conn, mp_id: int) -> None:
    section_header("Add an anticipated / proposed event", "one_off.add")
    st.caption(
        "Future one-offs with no bank transaction yet (e.g. planned surgery, "
        "expected refund). §14 events may need NSWTG approval before proceeding "
        "— the Compliance view flags them."
    )
    with st.form("oneoff_add_form", clear_on_submit=True):
        c1, c2, c3 = st.columns(3)
        event_type = c1.selectbox(
            "Type", ["expenditure", "receipt"],
            format_func=str.capitalize, key="oneoff_add_type",
        )
        status = c2.selectbox(
            "Status", ["anticipated", "proposed", "completed"],
            format_func=lambda s: STATUS_LABELS[s], key="oneoff_add_status",
        )
        amount = c3.number_input(
            "Amount ($)", min_value=0.0, step=100.0, key="oneoff_add_amount"
        )
        description = st.text_input("Description", key="oneoff_add_desc")
        event_date = st.date_input(
            "Expected / occurred date", value=date.today(), key="oneoff_add_date"
        )
        notes = st.text_input("Notes (optional)", key="oneoff_add_notes")
        if st.form_submit_button("Add event", type="primary"):
            if not description.strip():
                st.error("Description is required.")
            else:
                record_one_off_event(
                    conn,
                    OneOffEvent(
                        managed_person_id=mp_id,
                        event_type=event_type,
                        event_description=description.strip(),
                        status=status,
                        amount=amount or None,
                        date_occurred=event_date.isoformat(),
                        notes=notes.strip() or None,
                    ),
                    recorded_by="Linda",
                )
                st.success("Event recorded.")
                st.rerun()


def render_one_off_view() -> None:
    page_header("One-off Events", "one_off")
    st.caption(
        "Plan Section E — one-off receipts and expenditures, detected from the "
        "bank ledger or added ahead of time."
    )

    conn = get_connection()
    init_db(conn)
    mp_id = bootstrap_managed_person_if_empty(conn, "GENTILI", "Renato")

    events = list_one_off_events(conn, mp_id)
    completed = [e for e in events if e.status == "completed"]
    pending = [e for e in events if e.status != "completed"]
    candidates = detect_candidates(conn)

    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Awaiting review", str(len(candidates)))
    k2.metric("Completed events", str(len(completed)))
    k3.metric("Anticipated / proposed", str(len(pending)))
    k4.metric(
        "Completed total",
        f"${sum(e.amount or 0.0 for e in completed):,.2f}",
    )

    _render_candidates(conn, mp_id)
    st.divider()
    _render_events(conn, mp_id)
    st.divider()
    _render_add_form(conn, mp_id)

    conn.close()
