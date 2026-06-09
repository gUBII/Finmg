"""Submission view — produce an NSWTG artifact, audit its gaps, download it.

Flow: pick a form (Annual Accounts / Plan) + period → see per-section
completeness and the remaining gaps → fill the data elsewhere or record a
section-level N/A rationale → check the compliance readiness gate (only rules
Linda has set to `enforce` hard-block) → generate and download the filled PDF.
"""

from __future__ import annotations

from datetime import date, timedelta

import streamlit as st

from src.db.database import get_connection, init_db
from src.db.queries_estate import bootstrap_managed_person_if_empty
from src.services.artifacts.fill import fill_artifact
from src.services.artifacts.resolvers import Ctx
from src.services.artifacts.spec import load_spec
from src.services.audit import audit_artifact, record_rationale
from src.services.compliance.engine import evaluate_compliance
from src.services.submission_record import persist_submission

ARTIFACTS = {
    "annual_accounts": "Annual Accounts — past-year actuals",
    "plan": "Private Manager's Plan — forward forecast",
}


def _default_period(artifact_key: str) -> tuple[date, date]:
    today = date.today()
    if artifact_key == "plan":
        return today, today.replace(year=today.year + 1) - timedelta(days=1)
    # Annual Accounts: the trailing 12 months.
    return today.replace(year=today.year - 1), today


def render_submission_view() -> None:
    st.title("Submissions")
    st.caption("Generate, audit, and download NSWTG submission artifacts.")

    conn = get_connection()
    init_db(conn)
    mp_id = bootstrap_managed_person_if_empty(conn, "GENTILI", "Renato")

    artifact_key = st.selectbox(
        "Artifact",
        options=list(ARTIFACTS.keys()),
        format_func=lambda k: ARTIFACTS[k],
        key="sub_artifact",
    )
    default_start, default_end = _default_period(artifact_key)
    col1, col2 = st.columns(2)
    period_start = col1.date_input("Period start", value=default_start, key="sub_start")
    period_end = col2.date_input("Period end", value=default_end, key="sub_end")

    if period_end <= period_start:
        st.error("End date must be after start date.")
        conn.close()
        return

    spec = load_spec(artifact_key)
    ctx = Ctx(
        conn=conn,
        managed_person_id=mp_id,
        period_start=period_start.isoformat(),
        period_end=period_end.isoformat(),
    )

    report = audit_artifact(conn, spec, ctx)

    # --------------------------------------------------------------- readiness
    st.subheader("Readiness")
    m1, m2, m3 = st.columns(3)
    m1.metric("Completeness", f"{report.completeness * 100:.0f}%")
    m2.metric("Open gaps", str(len(report.gaps)))

    compliance = evaluate_compliance(
        conn, mp_id, period_start.isoformat(), period_end.isoformat()
    )
    m3.metric("Compliance blocks", str(len(compliance.blocking)))

    if compliance.is_blocked:
        st.error(
            "Submission is blocked by enforced compliance rules:\n\n"
            + "\n".join(f"- {g.finding.handbook_ref} {g.finding.title}" for g in compliance.blocking)
        )
    if compliance.warnings:
        with st.expander(f"Compliance warnings ({len(compliance.warnings)})"):
            for g in compliance.warnings:
                st.warning(f"**{g.finding.handbook_ref} — {g.finding.title}**\n\n{g.finding.detail}")

    # ------------------------------------------------------------------ gaps
    st.subheader("Section completeness & gaps")
    for section in report.sections:
        pct = section.completeness * 100
        title = f"{section.title} — {pct:.0f}% ({section.filled}/{section.total})"
        if not section.gaps:
            st.markdown(f"✅ {title}")
            continue
        with st.expander(f"⚠️ {title} — {len(section.gaps)} gap(s)"):
            st.write("Blank fields:", ", ".join(section.gaps))
            st.caption(
                "Fill these in the Identity / Inventory / Forecast views, or record "
                "why they are intentionally N/A below (a section-level rationale clears "
                "the whole section)."
            )
            reason = st.text_input(
                "N/A rationale for this section",
                key=f"rat_{artifact_key}_{section.key}",
            )
            if st.button("Record N/A rationale", key=f"ratbtn_{artifact_key}_{section.key}"):
                if reason.strip():
                    record_rationale(
                        conn, artifact_key, section.key, mp_id, reason, recorded_by="Linda"
                    )
                    st.success("Rationale recorded.")
                    st.rerun()
                else:
                    st.error("Rationale cannot be empty.")

    # -------------------------------------------------------------- generate
    st.subheader("Generate")
    filled = fill_artifact(spec, ctx)
    st.caption(f"{len(filled.resolved)} fields filled · {len(filled.blanks)} blank.")
    dl_col, save_col = st.columns(2)
    with dl_col:
        st.download_button(
            "Download filled PDF",
            data=filled.pdf_bytes,
            file_name=f"{artifact_key}_{period_start.isoformat()}_{period_end.isoformat()}.pdf",
            mime="application/pdf",
            type="primary",
            disabled=compliance.is_blocked,
            help="Blocked while enforced compliance rules are failing." if compliance.is_blocked else None,
        )
    with save_col:
        if st.button(
            "Save to submissions register",
            disabled=compliance.is_blocked,
            help="Records the PDF + auto-attaches the ANZ statements covering the period.",
        ):
            sub = persist_submission(
                conn, artifact_key, mp_id, filled.pdf_bytes,
                period_start.isoformat(), period_end.isoformat(), recorded_by="Linda",
            )
            st.success(
                f"Saved submission #{sub.id} → `{sub.generated_pdf_path}` "
                f"(sha {sub.generated_pdf_sha[:12]}…)."
            )

    conn.close()
