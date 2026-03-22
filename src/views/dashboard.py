"""Analytics dashboard with KPIs, month status grid, and plotly charts."""

from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st

from src.db.database import get_connection, init_db
from src.db.queries import (
    get_account_types,
    get_category_totals,
    get_distinct_accounts,
    get_distinct_months,
    get_month_account_coverage,
    get_monthly_totals,
    get_transaction_count,
)

# Fiscal year months Jun 2025 → Jun 2026
FISCAL_MONTHS = [
    "2025-06", "2025-07", "2025-08", "2025-09", "2025-10", "2025-11",
    "2025-12", "2026-01", "2026-02", "2026-03", "2026-04", "2026-05",
    "2026-06",
]

EXPECTED_ACCOUNTS = ["178865319", "178870011", "437669532"]


def _short_month(month_key: str) -> str:
    """Convert '2025-11' → 'Nov25'."""
    parts = month_key.split("-")
    names = {
        "01": "Jan", "02": "Feb", "03": "Mar", "04": "Apr",
        "05": "May", "06": "Jun", "07": "Jul", "08": "Aug",
        "09": "Sep", "10": "Oct", "11": "Nov", "12": "Dec",
    }
    return f"{names.get(parts[1], parts[1])}{parts[0][2:]}"


def _render_month_status_grid(conn) -> None:
    """Render the 13-month × 3-account coverage grid."""
    coverage = get_month_account_coverage(conn)
    account_types = get_account_types(conn)

    account_labels = {}
    for acct in EXPECTED_ACCOUNTS:
        atype = account_types.get(acct, acct)
        account_labels[acct] = atype

    rows = []
    for acct in EXPECTED_ACCOUNTS:
        row = {"Account": account_labels.get(acct, acct)}
        for month in FISCAL_MONTHS:
            has_data = (acct, month) in coverage
            row[_short_month(month)] = "✓" if has_data else "⚠"
        rows.append(row)

    # Status row
    status_row = {"Account": "Status"}
    for month in FISCAL_MONTHS:
        covered = sum(1 for acct in EXPECTED_ACCOUNTS if (acct, month) in coverage)
        status_row[_short_month(month)] = (
            "Complete" if covered == len(EXPECTED_ACCOUNTS) else f"{covered}/{len(EXPECTED_ACCOUNTS)}"
        )
    rows.append(status_row)

    df = pd.DataFrame(rows)

    def _style_cell(val):
        if val == "✓" or val == "Complete":
            return "background-color: #d4edda; color: #155724; text-align: center"
        if val == "⚠" or (isinstance(val, str) and "/" in val):
            return "background-color: #fff3cd; color: #856404; text-align: center"
        return ""

    styled = df.style.map(_style_cell, subset=[c for c in df.columns if c != "Account"])
    st.dataframe(styled, use_container_width=True, hide_index=True)


def render_dashboard_view() -> None:
    """Render the analytics dashboard backed by SQLite."""
    st.title("Dashboard")

    conn = get_connection()
    init_db(conn)

    txn_count = get_transaction_count(conn)
    if txn_count == 0:
        st.info("Upload PDFs in the **Upload** view to start populating the dashboard.")
        conn.close()
        return

    months = get_distinct_months(conn)
    month_options = ["All (YTD)"] + months
    selected = st.selectbox("View", month_options)
    filter_month = None if selected == "All (YTD)" else selected

    # Monthly totals for KPIs
    monthly_data = get_monthly_totals(conn)
    if filter_month:
        monthly_data = [m for m in monthly_data if m["month"] == filter_month]

    total_expenses = sum(m["expenses"] for m in monthly_data)
    total_income = sum(m["income"] for m in monthly_data)
    net_position = total_income - total_expenses
    months_complete = sum(
        1 for m in FISCAL_MONTHS
        if all(
            (acct, m) in get_month_account_coverage(conn)
            for acct in EXPECTED_ACCOUNTS
        )
    )

    # KPI row
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Total Expenses", f"${total_expenses:,.2f}")
    with col2:
        st.metric("Total Income", f"${total_income:,.2f}")
    with col3:
        color = "normal" if net_position >= 0 else "inverse"
        st.metric("Net Position", f"${net_position:+,.2f}")
    with col4:
        st.metric("Months Complete", f"{months_complete}/13")

    # Month status grid
    st.subheader("Month Status")
    _render_month_status_grid(conn)

    # Charts (2×2)
    # Trend/cumulative charts always show all months (filtering to one month
    # makes them meaningless as time-series). Category charts respect the filter.
    all_monthly = get_monthly_totals(conn)
    cat_data = get_category_totals(conn, month=filter_month)

    chart_col1, chart_col2 = st.columns(2)

    with chart_col1:
        # Monthly spending trends - grouped bar (always shows all months)
        if all_monthly:
            chart_df = pd.DataFrame(all_monthly)
            chart_df["month_label"] = chart_df["month"].apply(_short_month)
            trend_title = "Monthly Spending Trends"
            if filter_month:
                # Highlight the selected month by giving the others muted opacity
                chart_df["selected"] = chart_df["month"] == filter_month
                trend_title += f" (highlighted: {_short_month(filter_month)})"
            fig = px.bar(
                chart_df,
                x="month_label",
                y=["expenses", "income"],
                barmode="group",
                title=trend_title,
                labels={"value": "Amount ($)", "month_label": "Month", "variable": "Type"},
                color_discrete_map={"expenses": "#e74c3c", "income": "#2ecc71"},
            )
            if filter_month:
                selected_label = _short_month(filter_month)
                for trace in fig.data:
                    opacities = [
                        1.0 if x == selected_label else 0.35
                        for x in chart_df["month_label"]
                    ]
                    trace.marker.opacity = opacities
            fig.update_layout(height=350, margin=dict(t=40, b=20))
            st.plotly_chart(fig, use_container_width=True)

    with chart_col2:
        # Category breakdown - donut (respects filter)
        expense_cats = [c for c in cat_data if c["total_withdrawals"] > 0 and c["category"] != "Uncategorised"]
        if expense_cats:
            cat_df = pd.DataFrame(expense_cats)
            pie_title = "Category Breakdown (Expenses)"
            if filter_month:
                pie_title += f" — {_short_month(filter_month)}"
            fig = px.pie(
                cat_df,
                values="total_withdrawals",
                names="category",
                title=pie_title,
                hole=0.4,
            )
            fig.update_layout(height=350, margin=dict(t=40, b=20))
            st.plotly_chart(fig, use_container_width=True)

    chart_col3, chart_col4 = st.columns(2)

    with chart_col3:
        # Cumulative net position (always all months — cumulative needs full history)
        if all_monthly:
            chart_df = pd.DataFrame(all_monthly)
            chart_df["net"] = chart_df["income"] - chart_df["expenses"]
            chart_df["cumulative_net"] = chart_df["net"].cumsum()
            chart_df["month_label"] = chart_df["month"].apply(_short_month)
            fig = px.line(
                chart_df,
                x="month_label",
                y="cumulative_net",
                title="Net Position Over Time (cumulative)",
                labels={"cumulative_net": "Cumulative ($)", "month_label": "Month"},
                markers=True,
            )
            if filter_month:
                selected_label = _short_month(filter_month)
                selected_row = chart_df[chart_df["month"] == filter_month]
                if not selected_row.empty:
                    fig.add_scatter(
                        x=selected_row["month_label"],
                        y=selected_row["cumulative_net"],
                        mode="markers",
                        marker=dict(size=14, color="#f39c12", symbol="star"),
                        name="selected",
                        showlegend=False,
                    )
            fig.update_layout(height=350, margin=dict(t=40, b=20))
            st.plotly_chart(fig, use_container_width=True)

    with chart_col4:
        # Top 5 spending categories - horizontal bar
        expense_cats = [c for c in cat_data if c["total_withdrawals"] > 0]
        if expense_cats:
            top5 = sorted(expense_cats, key=lambda x: x["total_withdrawals"], reverse=True)[:5]
            top5_df = pd.DataFrame(top5)
            fig = px.bar(
                top5_df,
                x="total_withdrawals",
                y="category",
                orientation="h",
                title=f"Top 5 Spending Categories" + (f" — {_short_month(filter_month)}" if filter_month else ""),
                labels={"total_withdrawals": "Amount ($)", "category": ""},
                color_discrete_sequence=["#e74c3c"],
            )
            fig.update_layout(height=350, margin=dict(t=40, b=20), yaxis=dict(autorange="reversed"))
            st.plotly_chart(fig, use_container_width=True)

    conn.close()
