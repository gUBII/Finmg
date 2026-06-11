"""Audit Log view (S8) — read-only window onto the immutable audit trail.

Every consequential action in the app (gift edits, one-off confirmations and
dismissals, compliance rule toggles, N/A rationales, submissions, estate-change
status moves) writes a row to audit_log, which triggers make append-only.
This view only reads; there is nothing here that can change the trail.
"""

from __future__ import annotations

import json

import pandas as pd
import streamlit as st

from src.db.database import get_connection, init_db
from src.db.queries_compliance import count_audit, list_audit, list_audit_tables
from src.ui.help import page_header, section_header, widget_help
from src.ui.status import status_label

TABLE_LABELS = {
    "submissions": "Submissions & estate changes",
    "gifts": "Gifts",
    "one_off_events": "One-off events",
    "one_off_dismissals": "One-off dismissals",
    "compliance_settings": "Compliance rule toggles",
    "artifact_field_rationales": "N/A rationales",
    "consultation_log": "Consultations",
    "category_overrides": "Category changes",
}

DEFAULT_LIMIT = 100


def _label(table: str) -> str:
    return TABLE_LABELS.get(table, table)


def _render_trail(conn) -> list:
    section_header("Trail", "audit.trail")

    tables = list_audit_tables(conn)
    f1, f2, f3 = st.columns([2, 1, 2])
    table_choice = f1.selectbox(
        "Area",
        options=["All"] + tables,
        format_func=lambda t: "All areas" if t == "All" else _label(t),
        key="audit_table",
    )
    action_choice = f2.selectbox(
        "Action",
        options=["All", "insert", "update", "delete"],
        format_func=lambda a: "All actions" if a == "All" else status_label(a),
        key="audit_action",
    )
    search = f3.text_input(
        "Search",
        key="audit_search",
        help=widget_help("audit.search"),
    )

    entries = list_audit(
        conn,
        table_name=None if table_choice == "All" else table_choice,
        action=None if action_choice == "All" else action_choice,
        search=search.strip() or None,
        limit=DEFAULT_LIMIT,
    )
    if not entries:
        st.info("No audit entries match these filters.")
        return []

    df = pd.DataFrame(
        {
            "#": e.id,
            "When": e.timestamp,
            "Who": e.actor_user or "system",
            "Action": status_label(e.action),
            "Area": _label(e.table_name),
            "Reason": e.reason or "",
        }
        for e in entries
    )
    st.dataframe(df, width="stretch", hide_index=True)
    if len(entries) == DEFAULT_LIMIT:
        st.caption(
            f"Showing the most recent {DEFAULT_LIMIT} entries — "
            "narrow the filters to see older ones."
        )
    return entries


def _render_detail(entries: list) -> None:
    section_header("Entry detail", "audit.detail")
    if not entries:
        st.caption("Nothing to inspect — adjust the filters above.")
        return
    chosen = st.selectbox(
        "Entry",
        options=[e.id for e in entries],
        format_func=lambda i: next(
            f"#{e.id} · {e.timestamp} · {e.reason or _label(e.table_name)}"
            for e in entries if e.id == i
        ),
        key="audit_detail_id",
    )
    entry = next(e for e in entries if e.id == chosen)
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**Before**")
        if entry.before_json:
            st.json(json.loads(entry.before_json))
        else:
            st.caption("— (new record, nothing before)")
    with c2:
        st.markdown("**After**")
        if entry.after_json:
            st.json(json.loads(entry.after_json))
        else:
            st.caption("—")
    st.caption(
        f"Row {entry.row_id} in `{entry.table_name}` · recorded as "
        f"{entry.actor_role or 'unknown role'}"
    )


def render_audit_view() -> None:
    page_header("Audit Log", "audit")
    st.caption(
        "The permanent record of every consequential action in this app. "
        "Entries can never be edited or deleted — by you, by Farhan, or by "
        "the app itself."
    )

    conn = get_connection()
    init_db(conn)

    total = count_audit(conn)
    latest = list_audit(conn, limit=1)
    k1, k2, k3 = st.columns(3)
    k1.metric("Total entries", str(total))
    k2.metric("Areas covered", str(len(list_audit_tables(conn))))
    k3.metric("Last activity", latest[0].timestamp if latest else "—")

    entries = _render_trail(conn)
    st.divider()
    _render_detail(entries)

    conn.close()
