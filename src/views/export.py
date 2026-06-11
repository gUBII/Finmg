"""Excel export view with DB-backed data and ZIP download."""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

import streamlit as st

from src.db.database import get_connection, init_db
from src.db.queries import (
    get_all_transactions,
    get_distinct_months,
    rows_to_transactions,
)
from src.pipeline.merger import merge_accounts
from src.pipeline.month_splitter import split_by_month
from src.pipeline.excel_writer import write_budget_excel
from src.ui.help import page_header, section_header


def render_export_view() -> None:
    """Render export controls backed by SQLite."""
    page_header("Export", "export")
    st.caption("Generate monthly budget workbooks from your stored transactions.")

    conn = get_connection()
    init_db(conn)

    months = get_distinct_months(conn)
    if not months:
        st.info("No data available. Use the **Upload** view first.")
        conn.close()
        return

    # Month checkboxes
    section_header("Select Months", "export.select_months")
    selected_months = []
    cols = st.columns(min(len(months), 6))
    for i, month in enumerate(months):
        with cols[i % len(cols)]:
            if st.checkbox(month, value=True, key=f"export_{month}"):
                selected_months.append(month)

    output_dir = st.text_input("Output directory", value="data/exports", key="export_dir")

    if not selected_months:
        st.warning("Select at least one month to export.")
        conn.close()
        return

    if st.button("Generate Excel Workbooks", type="primary", width="stretch"):
        exported_files = []

        for month in sorted(selected_months):
            rows = get_all_transactions(conn, month=month)
            if not rows:
                continue
            txns = rows_to_transactions(rows)

            # Group by account for merger
            by_account: dict[str, dict[str, list]] = {}
            for txn in txns:
                acct = txn.account_number
                if acct not in by_account:
                    by_account[acct] = {}
                if month not in by_account[acct]:
                    by_account[acct][month] = []
                by_account[acct][month].append(txn)

            merged = merge_accounts(by_account)
            if month in merged:
                filepath = write_budget_excel(merged[month], month, output_dir)
                exported_files.append(filepath)

        if exported_files:
            st.session_state["exported_files"] = exported_files
            st.success(f"Generated {len(exported_files)} workbook(s).")

    # Show downloads
    exported_files = st.session_state.get("exported_files", [])
    if exported_files:
        section_header("Downloads", "export.downloads")

        for filepath in exported_files:
            path = Path(filepath)
            if not path.exists():
                continue
            col1, col2 = st.columns([3, 1])
            with col1:
                st.write(f"`{path.name}`")
            with col2:
                with path.open("rb") as f:
                    st.download_button(
                        "Download",
                        f.read(),
                        path.name,
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        key=f"dl_{path.name}",
                    )

        # ZIP all
        if len(exported_files) > 1:
            st.divider()
            zip_buffer = io.BytesIO()
            with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
                for filepath in exported_files:
                    path = Path(filepath)
                    if path.exists():
                        zf.write(path, path.name)
            zip_buffer.seek(0)

            st.download_button(
                "Download All as ZIP",
                zip_buffer.getvalue(),
                "FinMg_Exports.zip",
                "application/zip",
                width="stretch",
                key="dl_zip",
            )

    conn.close()
