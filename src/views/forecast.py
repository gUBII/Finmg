"""Forecast view — Section D of the NSWTG Private Manager's Plan.

Two tabs: Income (D_income) and Expenditure (D_expenditure). Each tab
shows one row per forecast_category for the selected forward-looking
period, with:

  - `actual` (read-only) — sum of matching transactions over the trailing
    window of the same length, derived from the transactions table.
  - `forecast` (editable) — Linda's number, defaulted to `actual` on first
    bootstrap.
  - `override reason` (editable) — required if `forecast` differs from
    `actual` by more than 1 cent.

Save invokes `save_forecast_override` per row, surfacing the missing-reason
error inline so Linda can correct without losing other edits.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import date, timedelta

import pandas as pd
import streamlit as st

from src.db.database import get_connection, init_db
from src.db.queries_estate import bootstrap_managed_person_if_empty
from src.db.queries_forecast import (
    list_forecast_categories,
    list_forecasts,
)
from src.services.forecast import (
    ForecastOverrideError,
    bootstrap_forecast_period,
    generate_forecast_proposals,
    save_forecast_override,
    _trailing_window,
)
from src.services.forecast_generator import generate_category_proposals
from src.ui.help import page_header, section_header, widget_help


def _default_period() -> tuple[date, date]:
    """Forward 12-month window starting today."""
    today = date.today()
    return today, today.replace(year=today.year + 1) - timedelta(days=1)


def render_forecast_view() -> None:
    page_header("Forecast (Section D)", "forecast")

    conn = get_connection()
    init_db(conn)

    mp_id = bootstrap_managed_person_if_empty(conn, "GENTILI", "Renato")

    categories = list_forecast_categories(conn)
    if not categories:
        st.warning(
            "No forecast categories seeded yet. Run `python3 scripts/seed.py` "
            "to mirror the categoriser categories into `forecast_categories`."
        )
        conn.close()
        return

    # ------------------------------------------------------------------ period
    default_start, default_end = _default_period()
    col1, col2, col3, col4 = st.columns([2, 2, 1, 1])
    with col1:
        period_start = st.date_input(
            "Forecast period start",
            value=default_start,
            key="fc_start",
            help=widget_help("forecast.period"),
        )
    with col2:
        period_end = st.date_input(
            "Forecast period end",
            value=default_end,
            key="fc_end",
        )
    with col3:
        st.write("")  # vertical alignment
        st.write("")
        if st.button("Refresh actuals", help="Re-derive actuals from transactions"):
            count = bootstrap_forecast_period(
                conn, mp_id, period_start.isoformat(), period_end.isoformat()
            )
            st.success(f"Refreshed {count} forecast rows.")
            st.rerun()
    with col4:
        st.write("")
        st.write("")
        if st.button(
            "Generate proposals",
            type="primary",
            help=widget_help("forecast.generate"),
        ):
            summary = generate_forecast_proposals(
                conn, mp_id, period_start.isoformat(), period_end.isoformat()
            )
            st.success(
                f"Generated {summary['updated']} proposals "
                f"({summary['flagged']} flagged, {summary['skipped']} manual kept)."
            )
            st.rerun()

    if period_end <= period_start:
        st.error("End date must be after start date.")
        conn.close()
        return

    trailing_start, trailing_end = _trailing_window(
        period_start.isoformat(), period_end.isoformat()
    )
    st.caption(
        f"Trailing actuals window: **{trailing_start} → {trailing_end}**"
    )

    # Auto-bootstrap if no forecasts exist yet for this period.
    existing = list_forecasts(
        conn, mp_id, period_start.isoformat(), period_end.isoformat()
    )
    if not existing:
        bootstrap_forecast_period(
            conn, mp_id, period_start.isoformat(), period_end.isoformat()
        )

    # ----------------------------------------------------- coverage + net summary
    proposals = generate_category_proposals(
        conn, mp_id, period_start.isoformat(), period_end.isoformat()
    )
    proposals_by_cat = {p.category_id: p for p in proposals}
    months = max((p.months_of_data for p in proposals), default=0.0)
    flagged = sum(1 for p in proposals if p.flag)
    factor = f"x{12 / months:.1f}" if months else "n/a"
    coverage_note = (
        f"Data coverage: **{months:.1f} months** → annualization **{factor}**."
    )
    if flagged:
        coverage_note += f"  ⚠ {flagged} categor{'y' if flagged == 1 else 'ies'} flagged for review."
    st.caption(coverage_note)

    forecasts_all = list_forecasts(
        conn, mp_id, period_start.isoformat(), period_end.isoformat()
    )
    cat_section = {c.id: c.section for c in categories}
    inc_total = sum(
        (f.forecast_value or 0.0)
        for f in forecasts_all
        if cat_section.get(f.category_id) == "D_income"
    )
    exp_total = sum(
        (f.forecast_value or 0.0)
        for f in forecasts_all
        if cat_section.get(f.category_id) == "D_expenditure"
    )
    m1, m2, m3 = st.columns(3)
    m1.metric("Income — annual forecast", f"${inc_total:,.2f}")
    m2.metric("Expenditure — annual forecast", f"${exp_total:,.2f}")
    m3.metric("Net position", f"${inc_total - exp_total:,.2f}")

    # ------------------------------------------------------------------- tabs
    tab_income, tab_expenditure = st.tabs(["Income", "Expenditure"])

    with tab_income:
        section_header("Income", "forecast.income")
        _render_section_editor(
            conn,
            mp_id,
            period_start.isoformat(),
            period_end.isoformat(),
            section="D_income",
            label="Income",
            key_suffix="inc",
            proposals_by_cat=proposals_by_cat,
        )

    with tab_expenditure:
        section_header("Expenditure", "forecast.expenditure")
        _render_section_editor(
            conn,
            mp_id,
            period_start.isoformat(),
            period_end.isoformat(),
            section="D_expenditure",
            label="Expenditure",
            key_suffix="exp",
            proposals_by_cat=proposals_by_cat,
        )

    conn.close()


def _render_section_editor(
    conn,
    mp_id: int,
    period_start: str,
    period_end: str,
    section: str,
    label: str,
    key_suffix: str,
    proposals_by_cat: dict | None = None,
) -> None:
    proposals_by_cat = proposals_by_cat or {}
    categories = list_forecast_categories(conn, section=section)
    forecasts = list_forecasts(conn, mp_id, period_start, period_end, section=section)
    by_cat_id = {f.category_id: f for f in forecasts}

    rows: list[dict] = []
    for cat in categories:
        f = by_cat_id.get(cat.id)
        prop = proposals_by_cat.get(cat.id)
        rows.append(
            {
                "_forecast_id": f.id if f else None,
                "Category": cat.category_name,
                "Actual": f.actual_value if f else 0.0,
                "Months": prop.months_of_data if prop else 0.0,
                "Annualized": prop.annualized_estimate if prop else 0.0,
                "Forecast": f.forecast_value if f else 0.0,
                "Override reason": (f.override_reason if f else "") or "",
                "Flag": (prop.flag if prop and prop.flag else "") or "",
            }
        )

    df = pd.DataFrame(rows)

    edited = st.data_editor(
        df,
        column_config={
            "_forecast_id": None,  # hidden
            "Category": st.column_config.TextColumn("Category", disabled=True),
            "Actual": st.column_config.NumberColumn(
                "Actual (trailing)", disabled=True, format="$%.2f"
            ),
            "Months": st.column_config.NumberColumn(
                "Months of data",
                disabled=True,
                format="%.1f",
                help=widget_help("forecast.months_of_data"),
            ),
            "Annualized": st.column_config.NumberColumn(
                "Annualized estimate",
                disabled=True,
                format="$%.2f",
                help=widget_help("forecast.annualized"),
            ),
            "Forecast": st.column_config.NumberColumn(
                "Forecast", format="$%.2f"
            ),
            "Override reason": st.column_config.TextColumn(
                "Override reason",
                help="Required when Forecast differs from Actual.",
                max_chars=300,
            ),
            "Flag": st.column_config.TextColumn("Flag", disabled=True),
        },
        width="stretch",
        hide_index=True,
        num_rows="fixed",
        key=f"fc_editor_{key_suffix}",
    )

    totals_col1, totals_col2 = st.columns(2)
    totals_col1.metric(f"{label} — total actual",  f"${edited['Actual'].sum():,.2f}")
    totals_col2.metric(f"{label} — total forecast", f"${edited['Forecast'].sum():,.2f}")

    if st.button(f"Save {label.lower()} forecasts", type="primary", key=f"fc_save_{key_suffix}"):
        errors: list[str] = []
        saved = 0
        for _, row in edited.iterrows():
            f_id = row["_forecast_id"]
            if f_id is None:
                continue
            try:
                new_forecast = float(row["Forecast"] or 0.0)
            except (TypeError, ValueError):
                errors.append(f"{row['Category']}: forecast must be a number")
                continue
            reason = str(row["Override reason"] or "").strip() or None
            try:
                save_forecast_override(conn, int(f_id), new_forecast, reason)
                saved += 1
            except ForecastOverrideError as exc:
                errors.append(f"{row['Category']}: {exc}")
        if errors:
            for err in errors:
                st.error(err)
        if saved:
            st.success(f"Saved {saved} {label.lower()} rows.")
            st.rerun()
