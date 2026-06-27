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
from src.db.queries_estate import bootstrap_managed_person_if_empty
from src.models.compliance import Gift
from src.pipeline.gift_forecast_excel import write_gift_forecast_xlsx
from src.services.gift_forecast import OCC_LABEL, OCC_ORDER, TITLE, build_matrix
from src.services.gifts import record_gift_actual, revamp_gift_recipient
from src.ui.help import page_header, section_header, widget_help
from src.ui.status import PALETTE, cell_css

# Reproducible export path for the gift-forecast matrix (gitignored data/).
FORECAST_XLSX = "data/exports/Gift_Forecast_RenatoGentili.xlsx"

OCCASION_LABELS = {
    "birthday": "Birthday",
    "christmas": "Christmas",
    "easter": "Easter",
    "mothers_day": "Mother's Day",
    "fathers_day": "Father's Day",
    "valentines": "Valentine's Day",
    "wedding": "Wedding",
}


def _display_name(gift: Gift) -> str:
    return (gift.recipient_name or "").strip() or "(unattributed)"


def _flag_reason(gift: Gift) -> str | None:
    notes = gift.notes or ""
    return notes.split(" — ", 1)[1].strip() if " — " in notes else None


def _ledger_frame(gifts: list[Gift]) -> pd.DataFrame:
    rows = []
    for g in gifts:
        rows.append(
            {
                "Recipient": _display_name(g),
                "Relation": g.recipient_relation or "—",
                "Occasion": OCCASION_LABELS.get(g.occasion, g.occasion or "—"),
                "Date": g.occasion_date or "—",
                "Planned": g.planned_amount or 0.0,
                "Actual": g.actual_amount,
                "§76": "🚩 flagged" if g.section_76_assessment != "compliant" else "✓",
            }
        )
    return pd.DataFrame(rows)


def _money(v: float) -> str:
    return f"${v:,.0f}" if v else "·"


def _render_forecast_matrix(conn, mp_id: int) -> None:
    """The §76 gift-forecast matrix (recipients × occasions) — the digital twin
    of the handwritten doc, styled to the FinMg theme. Reproducible: the same
    build_matrix feeds the Excel export."""
    rows, col_totals, grand = build_matrix(conn, mp_id)
    if not rows:
        return

    head = "".join(f"<th>{OCC_LABEL[o]}</th>" for o in OCC_ORDER)
    body = []
    for r in rows:
        tint = ' style="background:#FCE8E6"' if r.flagged else ""
        flag = " 🚩" if r.flagged else ""
        cells = "".join(f"<td>{_money(r.amounts.get(o, 0.0))}</td>" for o in OCC_ORDER)
        body.append(
            f'<tr{tint}><td class="nm">{r.name}{flag}</td><td class="rel">{r.relation}</td>'
            f'{cells}<td class="tot">${r.total:,.0f}</td></tr>'
        )
    foot_cells = "".join(f"<td>${col_totals[o]:,.0f}</td>" for o in OCC_ORDER)
    table = f"""
    <div class="gf-wrap">
      <div class="gf-title">{TITLE}</div>
      <table class="gf">
        <thead><tr><th class="nm">Person's Name</th><th class="rel">Relation</th>{head}<th>Row Total</th></tr></thead>
        <tbody>{''.join(body)}</tbody>
        <tfoot><tr><td class="nm">Column total</td><td></td>{foot_cells}<td class="grand">${grand:,.0f}</td></tr></tfoot>
      </table>
    </div>
    <style>
      .gf-wrap {{ font-family: Georgia, 'Times New Roman', serif; overflow-x:auto; }}
      .gf-title {{ color:#1F4E5F; font-weight:700; font-size:1.05rem; margin:.2rem 0 .5rem; }}
      table.gf {{ border-collapse:collapse; width:100%; font-size:.82rem; }}
      table.gf th, table.gf td {{ border:1px solid #C9D6D9; padding:5px 8px; text-align:center; white-space:nowrap; }}
      table.gf thead th {{ background:#1F4E5F; color:#fff; font-weight:700; }}
      table.gf td.nm {{ text-align:left; font-weight:600; }}
      table.gf td.rel {{ text-align:left; color:#4a5a5e; }}
      table.gf td.tot {{ font-weight:700; }}
      table.gf tfoot td {{ background:#EDF3F4; font-weight:700; border-top:2px solid #1F4E5F; }}
      table.gf tfoot td.grand {{ color:#1F4E5F; }}
    </style>
    """
    st.markdown(table, unsafe_allow_html=True)

    flagged = [r for r in rows if r.flagged]
    if flagged:
        names = ", ".join(r.name for r in flagged)
        st.warning(f"🚩 §76 review: {names}. A gift from the managed estate to the "
                   "private manager (or related parties) is a conflict of interest — "
                   "disclose and confirm NCAT authorisation before lodging.")

    try:
        path, _ = write_gift_forecast_xlsx(conn, mp_id, FORECAST_XLSX)
        with open(path, "rb") as fh:
            st.download_button(
                "⬇ Download gift-forecast table (Excel)", fh.read(),
                file_name="Gift_Forecast_RenatoGentili.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="gift_forecast_xlsx",
            )
    except Exception as exc:  # never let the export break the page
        st.caption(f"Excel export unavailable: {exc}")


def render_gifts_view() -> None:
    page_header("Gifts", "gifts")
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

    planned_total = sum(g.planned_amount or 0.0 for g in gifts)
    actual_total = sum(g.actual_amount or 0.0 for g in gifts)
    flagged = [g for g in gifts if g.section_76_assessment != "compliant"]

    # ------------------------------------------------------------------- KPIs
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Planned (year)", f"${planned_total:,.2f}")
    k2.metric("Actual to date", f"${actual_total:,.2f}")
    k3.metric("Remaining budget", f"${planned_total - actual_total:,.2f}")
    k4.metric("§76 flagged", f"{len(flagged)} of {len(gifts)}")

    # ------------------------------------------------ §76 gift-forecast matrix
    section_header("Gift forecast (§76) — planned matrix", "gifts.forecast")
    _render_forecast_matrix(conn, mp_id)

    # ----------------------------------------------------------------- ledger
    section_header("Ledger", "gifts.ledger")
    df = _ledger_frame(gifts)

    def _style_flag(val):
        if isinstance(val, str) and val.startswith("🚩"):
            return cell_css("missing")
        return ""

    styled = df.style.map(_style_flag, subset=["§76"]).format(
        {"Planned": "${:,.2f}", "Actual": lambda v: "—" if pd.isna(v) else f"${v:,.2f}"}
    )
    st.dataframe(styled, width="stretch", hide_index=True)

    # ------------------------------------------------------------ flag detail
    if flagged:
        with st.expander(f"🚩 Flagged rows ({len(flagged)}) — why"):
            for g in flagged:
                reason = _flag_reason(g) or "Flagged by the compliance engine."
                label = OCCASION_LABELS.get(g.occasion, g.occasion or "—")
                st.warning(
                    f"**{_display_name(g)} — {label} "
                    f"(${g.planned_amount or 0.0:,.2f})**\n\n{reason}"
                )

    # ----------------------------------------------- revamp recipients/relation
    section_header("Recipients & relations", "gifts.recipients")
    st.caption(
        "Edit each gift's recipient name and relationship to Ron. These are "
        "gift-owned — independent of Significant People. Changes are audited."
    )
    editor_df = pd.DataFrame(
        [
            {
                "id": g.id,
                "Recipient": g.recipient_name or "",
                "Relation": g.recipient_relation or "",
                "Occasion": OCCASION_LABELS.get(g.occasion, g.occasion or "—"),
            }
            for g in gifts
        ]
    )
    edited = st.data_editor(
        editor_df,
        width="stretch",
        hide_index=True,
        key="gift_recipients_editor",
        column_config={
            "id": st.column_config.NumberColumn("id", disabled=True),
            "Recipient": st.column_config.TextColumn("Recipient"),
            "Relation": st.column_config.TextColumn("Relation"),
            "Occasion": st.column_config.TextColumn("Occasion", disabled=True),
        },
    )
    if st.button("Save recipient changes", key="gift_recipients_save"):
        current = {g.id: g for g in gifts}
        changes = 0
        for _, r in edited.iterrows():
            g = current.get(int(r["id"]))
            if g is None:
                continue
            new_name = (str(r["Recipient"]) or "").strip() or None
            new_rel = (str(r["Relation"]) or "").strip() or None
            if new_name != (g.recipient_name or None) or new_rel != (g.recipient_relation or None):
                revamp_gift_recipient(conn, g.id, new_name, new_rel, recorded_by="Linda")
                changes += 1
        if changes:
            st.success(f"Saved {changes} recipient change(s).")
            st.rerun()
        else:
            st.info("No changes to save.")

    # ---------------------------------------------------------- record actual
    section_header("Record an actual", "gifts.record_actual")
    st.caption(
        "When a planned gift is actually given, record the real amount here — "
        "the change is written to the immutable audit log."
    )

    def _gift_label(g: Gift) -> str:
        label = OCCASION_LABELS.get(g.occasion, g.occasion or "—")
        actual = "" if g.actual_amount is None else f" · actual ${g.actual_amount:,.2f}"
        return f"{_display_name(g)} — {label} (planned ${g.planned_amount or 0.0:,.2f}){actual}"

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
    section_header("Planned vs actual by recipient", "gifts.chart")
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
        color_discrete_map={"Planned": PALETTE["gray"], "Actual": PALETTE["green"]},
    )
    fig.update_layout(
        height=max(350, 28 * by_recipient["Recipient"].nunique()),
        margin=dict(t=20, b=20),
    )
    st.plotly_chart(fig, width="stretch")

    conn.close()
