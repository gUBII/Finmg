"""Upload view with one-click pipeline: PDF → parse → categorise → DB."""

from __future__ import annotations

import hashlib
import shutil
import tempfile
from pathlib import Path

import pandas as pd
import streamlit as st

from src.db.database import get_connection, init_db
from src.db.queries import (
    get_account_types,
    get_month_account_coverage,
    get_uploaded_pdfs,
    insert_pdf_and_transactions,
    is_pdf_already_uploaded,
)
from src.parser.pdf_extractor import extract_transactions, validate_totals
from src.pipeline.categoriser import categorise_all, load_category_rules
from src.pipeline.merger import detect_internal_transfers
from src.pipeline.month_splitter import split_by_month

EXPECTED_TOTALS = {
    "178865319": {"withdrawals": 28171.78, "deposits": 30125.60},
    "178870011": {"withdrawals": 13315.83, "deposits": 13315.79},
    "437669532": {"withdrawals": 28519.93, "deposits": 7471.46},
}

FISCAL_MONTHS = [
    "2025-06", "2025-07", "2025-08", "2025-09", "2025-10", "2025-11",
    "2025-12", "2026-01", "2026-02", "2026-03", "2026-04", "2026-05",
    "2026-06",
]

EXPECTED_ACCOUNTS = ["178865319", "178870011", "437669532"]

UPLOADS_DIR = Path(__file__).parent.parent.parent / "data" / "uploads"


def _short_month(month_key: str) -> str:
    parts = month_key.split("-")
    names = {
        "01": "Jan", "02": "Feb", "03": "Mar", "04": "Apr",
        "05": "May", "06": "Jun", "07": "Jul", "08": "Aug",
        "09": "Sep", "10": "Oct", "11": "Nov", "12": "Dec",
    }
    return f"{names.get(parts[1], parts[1])}{parts[0][2:]}"


def _file_hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _render_month_status_grid(conn) -> None:
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


def render_upload_view() -> None:
    """Render one-click upload → full pipeline → DB persistence."""
    st.title("Upload")
    st.caption("Upload ANZ bank statement PDFs. Processing is automatic.")

    conn = get_connection()
    init_db(conn)

    # File uploader
    uploaded_files = st.file_uploader(
        "Upload ANZ Transaction Report PDFs",
        type=["pdf"],
        accept_multiple_files=True,
        key="pdf_uploader",
    )

    if uploaded_files and st.button("Process", type="primary", use_container_width=True):
        config = load_category_rules()
        results = []

        for uploaded in uploaded_files:
            file_bytes = uploaded.getbuffer()
            fhash = _file_hash(bytes(file_bytes))

            # Duplicate check
            if is_pdf_already_uploaded(conn, fhash):
                st.warning(f"**{uploaded.name}** has already been uploaded — skipping.")
                continue

            # Write to temp file for parsing
            tmp_path = ""
            try:
                with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
                    tmp.write(file_bytes)
                    tmp_path = tmp.name

                with st.spinner(f"Processing {uploaded.name}..."):
                    meta, transactions = extract_transactions(tmp_path)

                    # Split, categorise, then detect internal transfers
                    monthly = split_by_month(transactions)
                    all_txns = []
                    for month_txns in monthly.values():
                        categorise_all(month_txns, config)
                        all_txns.extend(month_txns)
                    # Run cross-description transfer detection (catches
                    # account-number references in descriptions that the
                    # categoriser's pattern list may miss)
                    detect_internal_transfers(all_txns)

                    # Validate totals
                    expected = EXPECTED_TOTALS.get(meta.account_number, {})
                    validation = validate_totals(
                        all_txns,
                        expected.get("withdrawals"),
                        expected.get("deposits"),
                    )

                    # Save PDF to uploads dir; prefix with 8-char hash to
                    # prevent silent overwrite if two PDFs share a filename.
                    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
                    safe_name = f"{fhash[:8]}_{uploaded.name}"
                    dest = UPLOADS_DIR / safe_name
                    shutil.copy2(tmp_path, str(dest))

                    # Insert into DB
                    pdf_id = insert_pdf_and_transactions(
                        conn, meta, all_txns, uploaded.name, fhash
                    )

                    results.append((uploaded.name, meta, validation))

            finally:
                if tmp_path:
                    Path(tmp_path).unlink(missing_ok=True)

        # Show results
        for name, meta, validation in results:
            st.divider()
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Account", meta.account_type)
                st.caption(f"BSB: {meta.bsb} | Acct: {meta.account_number}")
            with col2:
                match_w = validation.get("withdrawals_match")
                st.metric(
                    "Withdrawals",
                    f"${validation['parsed_withdrawals']:,.2f}",
                    delta="Match" if match_w else ("No expected" if match_w is None else "MISMATCH"),
                    delta_color="normal" if match_w else ("off" if match_w is None else "inverse"),
                )
            with col3:
                match_d = validation.get("deposits_match")
                st.metric(
                    "Deposits",
                    f"${validation['parsed_deposits']:,.2f}",
                    delta="Match" if match_d else ("No expected" if match_d is None else "MISMATCH"),
                    delta_color="normal" if match_d else ("off" if match_d is None else "inverse"),
                )
            st.success(f"{name}: {validation['transaction_count']} transactions processed")

    # Month status grid
    st.subheader("Month Status")
    _render_month_status_grid(conn)

    # Previously uploaded PDFs
    pdfs = get_uploaded_pdfs(conn)
    if pdfs:
        st.subheader("Uploaded Files")
        pdf_df = pd.DataFrame(pdfs)[
            ["filename", "account_type", "account_number", "transaction_count",
             "parsed_withdrawals", "parsed_deposits", "uploaded_at"]
        ]
        pdf_df.columns = ["File", "Account Type", "Account #", "Txns",
                          "Withdrawals", "Deposits", "Uploaded"]
        st.dataframe(pdf_df, use_container_width=True, hide_index=True)

    conn.close()
