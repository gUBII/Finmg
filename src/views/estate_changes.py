"""Changes in Estate view (S8) — handbook §14 / form Appendix A.

Linda proposes a change (one of the 18 Appendix-A subsections, covering the
12 handbook trigger events), sees exactly which documents NSWTG requires for
that subsection, then tracks the proposal through draft → submitted →
approved/rejected with the NCAT reference. Every step is audit-logged.
"""

from __future__ import annotations

import json

import streamlit as st

from src.db.database import get_connection, init_db
from src.db.queries_estate import bootstrap_managed_person_if_empty
from src.services.estate_changes import (
    list_changes,
    load_appendix_a,
    record_change,
    update_change_status,
)
from src.ui.help import page_header, section_header, widget_help
from src.ui.status import status_chip

# Context-specific wording on top of the shared status vocabulary.
STATUS_WORDING = {"submitted": "Submitted — awaiting NSWTG/NCAT"}


def _parse_views(text: str) -> list[dict]:
    """Parse 'Name | relationship | support-or-object' lines into view dicts."""
    views = []
    for line in text.strip().splitlines():
        parts = [p.strip() for p in line.split("|")]
        if not parts or not parts[0]:
            continue
        views.append(
            {
                "name": parts[0],
                "relationship": parts[1] if len(parts) > 1 else "",
                "view": parts[2].lower() if len(parts) > 2 else "",
            }
        )
    return views


def _subsection_brief(letter: str, entry: dict) -> None:
    """The registry context panel: what this subsection is + required documents."""
    st.markdown(f"**§{letter} — {entry['title']}.** {entry['summary']}")
    if entry["handbook_trigger"]:
        st.warning(f"**Handbook §14 trigger:** {entry['handbook_trigger']}")
    if entry["required_attachments"]:
        st.markdown(
            "**Documents NSWTG requires:**\n"
            + "\n".join(f"- {a}" for a in entry["required_attachments"])
        )
    else:
        st.markdown("**Documents NSWTG requires:** none listed for this subsection.")
    st.caption(entry["notes"])


def _render_propose(conn, mp_id: int) -> None:
    section_header("Propose a change", "estate_changes.propose")
    st.caption(
        "Pick the kind of change first — the panel shows what NSWTG will ask "
        "for. Recording a proposal here does NOT submit anything; it creates a "
        "draft you can prepare documents against."
    )
    registry = load_appendix_a()
    letter = st.selectbox(
        "Kind of change (form Appendix A)",
        options=list(registry.keys()),
        format_func=lambda k: f"{k} — {registry[k]['title']}",
        key="cie_subsection",
        help=widget_help("estate_changes.subsection"),
    )
    _subsection_brief(letter, registry[letter])

    with st.form("cie_propose_form", clear_on_submit=True):
        description = st.text_area(
            "What is being proposed?",
            key="cie_desc",
            placeholder="e.g. Sell the unit at 1 Example St to fund the accommodation bond",
        )
        c1, c2 = st.columns(2)
        amount = c1.number_input(
            "Amount involved ($, 0 if not applicable)",
            min_value=0.0, step=100.0, key="cie_amount",
        )
        affordable = c2.checkbox(
            "I am satisfied the estate can afford this",
            key="cie_affordable",
        )
        views_text = st.text_area(
            "Views of family / significant people (one per line: Name | relationship | support or object)",
            key="cie_views",
            placeholder="Linda-Jane | sister | support",
            help=widget_help("estate_changes.views"),
        )
        notes = st.text_input("Notes (optional)", key="cie_notes")
        if st.form_submit_button("Record draft proposal", type="primary"):
            if not description.strip():
                st.error("Describe what is being proposed.")
            else:
                record_change(
                    conn,
                    mp_id,
                    letter,
                    description.strip(),
                    amount=amount or None,
                    affordability_confirmed=affordable,
                    views=_parse_views(views_text) or None,
                    notes=notes.strip() or None,
                    recorded_by="Linda",
                )
                st.success(f"Draft recorded under Appendix A §{letter}.")
                st.rerun()


def _render_status_actions(conn, sub) -> None:
    """The allowed next steps for one proposal, as buttons."""
    ncat_ref = st.text_input(
        "NCAT / NSWTG reference (optional until a decision)",
        value=sub.ncat_reference or "",
        key=f"cie_ref_{sub.id}",
    )
    ref = ncat_ref.strip() or None
    c1, c2 = st.columns(2)
    if sub.status == "draft":
        if c1.button("Mark as submitted to NSWTG", key=f"cie_submit_{sub.id}", type="primary"):
            update_change_status(conn, sub.id, "submitted", ncat_reference=ref, recorded_by="Linda")
            st.rerun()
    elif sub.status == "submitted":
        if c1.button("Record approval", key=f"cie_approve_{sub.id}", type="primary"):
            update_change_status(conn, sub.id, "approved", ncat_reference=ref, recorded_by="Linda")
            st.rerun()
        if c2.button("Record rejection", key=f"cie_reject_{sub.id}"):
            update_change_status(conn, sub.id, "rejected", ncat_reference=ref, recorded_by="Linda")
            st.rerun()
    elif sub.status == "rejected":
        if c1.button("Resubmit to NSWTG", key=f"cie_resubmit_{sub.id}", type="primary"):
            update_change_status(conn, sub.id, "submitted", ncat_reference=ref, recorded_by="Linda")
            st.rerun()
    else:  # approved — final
        st.caption("Approved — no further action. Keep the NCAT decision letter with your records.")


def _render_register(conn, mp_id: int) -> None:
    section_header("Register", "estate_changes.register")
    registry = load_appendix_a()
    changes = list_changes(conn, mp_id)
    if not changes:
        st.info("No changes proposed yet.")
        return

    for change in changes:
        sub, detail = change.submission, change.detail
        entry = registry.get(sub.trigger_subsection, {})
        title = entry.get("title", sub.trigger_subsection)
        badge = status_chip(sub.status, STATUS_WORDING.get(sub.status))
        desc = detail.description if detail else ""
        with st.expander(f"§{sub.trigger_subsection} {title} — {desc[:60]} {badge}"):
            if detail:
                st.write(desc)
                meta = []
                if detail.amount:
                    meta.append(f"Amount: ${detail.amount:,.2f}")
                meta.append(
                    status_chip("ok", "Affordability confirmed")
                    if detail.affordability_confirmed
                    else status_chip("missing", "Affordability not yet confirmed")
                )
                st.markdown(" · ".join(meta))
                if detail.views_json:
                    views = json.loads(detail.views_json)
                    st.markdown(
                        "**Views recorded:**\n"
                        + "\n".join(
                            f"- {v.get('name', '?')} ({v.get('relationship', '')}): "
                            f"{v.get('view', '—')}"
                            for v in views
                        )
                    )
                if detail.notes:
                    st.caption(f"Notes: {detail.notes}")
            if entry.get("required_attachments"):
                st.markdown(
                    "**Documents to gather before submitting:**\n"
                    + "\n".join(f"- {a}" for a in entry["required_attachments"])
                )
            dates = []
            if sub.submitted_at:
                dates.append(f"submitted {sub.submitted_at}")
            if sub.ncat_decision_at:
                dates.append(f"decision {sub.ncat_decision_at}")
            if dates:
                st.caption(" · ".join(dates))
            _render_status_actions(conn, sub)


def render_estate_changes_view() -> None:
    page_header("Changes in Estate", "estate_changes")
    st.caption(
        "Handbook §14 — significant changes to Ron's estate need NSWTG approval "
        "BEFORE they happen. Record the proposal here, gather the listed "
        "documents, then track the decision."
    )

    conn = get_connection()
    init_db(conn)
    mp_id = bootstrap_managed_person_if_empty(conn, "GENTILI", "Renato")

    changes = list_changes(conn, mp_id)
    by_status = {s: sum(1 for c in changes if c.submission.status == s)
                 for s in ("draft", "submitted", "approved", "rejected")}
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Drafts", str(by_status["draft"]))
    k2.metric("Awaiting decision", str(by_status["submitted"]))
    k3.metric("Approved", str(by_status["approved"]))
    k4.metric("Rejected", str(by_status["rejected"]))

    _render_propose(conn, mp_id)
    st.divider()
    _render_register(conn, mp_id)

    conn.close()
