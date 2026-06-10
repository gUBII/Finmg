"""Consultations view (S7, Plan Section F) — log and review consultations.

Handbook §4.2: Linda must consult Ron and the significant people on major
decisions. Each entry is keyed to a significant person (or recorded as
Ron / external) and written to the immutable audit log via the service.
"""

from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st

from src.db.database import get_connection, init_db
from src.db.queries_compliance import list_consultations
from src.db.queries_estate import (
    bootstrap_managed_person_if_empty,
    list_significant_people,
)
from src.models.compliance import ConsultationLogEntry
from src.services.consultations import record_consultation

RON_OPTION = "Ron (managed person) / external party"


def _people_options(conn, mp_id: int) -> dict[str, int | None]:
    """Display label → significant_people id (None for Ron/external)."""
    options: dict[str, int | None] = {RON_OPTION: None}
    for p in list_significant_people(conn, mp_id, include_deceased=True):
        label = f"{p.given_name} {p.surname}".strip()
        if p.relationship:
            label += f" ({p.relationship})"
        options[label] = p.id
    return options


def _render_log_form(conn, mp_id: int, options: dict[str, int | None]) -> None:
    st.subheader("Log a consultation")
    with st.form("consult_form", clear_on_submit=True):
        c1, c2 = st.columns(2)
        consult_date = c1.date_input(
            "Date", value=date.today(), key="consult_date"
        )
        person_label = c2.selectbox(
            "Consulted with", options=list(options.keys()), key="consult_person"
        )
        topic = st.text_input(
            "Decision topic (e.g. accommodation bond top-up)", key="consult_topic"
        )
        summary = st.text_area(
            "Summary — what was discussed, their view", key="consult_summary"
        )
        if st.form_submit_button("Log consultation", type="primary"):
            if not topic.strip():
                st.error("Decision topic is required.")
            else:
                record_consultation(
                    conn,
                    ConsultationLogEntry(
                        managed_person_id=mp_id,
                        date=consult_date.isoformat(),
                        consulted_person_id=options[person_label],
                        decision_topic=topic.strip(),
                        summary=summary.strip() or None,
                    ),
                    recorded_by="Linda",
                )
                st.success("Consultation logged (audited).")
                st.rerun()


def _render_history(entries, id_to_label: dict[int | None, str]) -> None:
    st.subheader("History")
    if not entries:
        st.info("No consultations logged yet.")
        return
    df = pd.DataFrame(
        {
            "Date": e.date,
            "With": id_to_label.get(e.consulted_person_id, RON_OPTION),
            "Topic": e.decision_topic,
            "Summary": e.summary or "—",
        }
        for e in entries
    )
    st.dataframe(df, use_container_width=True, hide_index=True)


def render_consultation_view() -> None:
    st.title("Consultations")
    st.caption(
        "Plan Section F — the consultation trail with Ron and the significant "
        "people (handbook §4.2). Every entry is written to the immutable audit log."
    )

    conn = get_connection()
    init_db(conn)
    mp_id = bootstrap_managed_person_if_empty(conn, "GENTILI", "Renato")

    options = _people_options(conn, mp_id)
    id_to_label = {pid: label for label, pid in options.items()}
    entries = list_consultations(conn, mp_id)

    k1, k2, k3 = st.columns(3)
    k1.metric("Consultations logged", str(len(entries)))
    k2.metric("Last consultation", entries[0].date if entries else "—")
    consulted_ids = {e.consulted_person_id for e in entries if e.consulted_person_id}
    people_total = len(options) - 1  # minus the Ron/external option
    k3.metric("People consulted", f"{len(consulted_ids)} of {people_total}")

    _render_log_form(conn, mp_id, options)
    st.divider()
    _render_history(entries, id_to_label)

    conn.close()
