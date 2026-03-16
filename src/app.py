"""
FinMg — ANZ Statement Processor
Streamlit application for parsing bank statements into budget workbooks.
"""

import sys
import tempfile
from pathlib import Path

import pandas as pd
import streamlit as st

# Ensure project root is on path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.parser.pdf_extractor import extract_transactions, validate_totals
from src.parser.header_parser import extract_account_meta
from src.pipeline.month_splitter import split_by_month
from src.pipeline.categoriser import categorise_all, load_category_rules, get_category_summary, get_all_category_names
from src.pipeline.merger import merge_accounts
from src.pipeline.excel_writer import write_budget_excel
from src.checkpoints.checkpoint_io import (
    transactions_to_dataframe,
    dataframe_to_transactions,
    save_checkpoint,
)
from src.models.transaction import Transaction

# Known expected totals for validation
EXPECTED_TOTALS = {
    "178865319": {"withdrawals": 28171.78, "deposits": 30125.60},
    "178870011": {"withdrawals": 13315.83, "deposits": 13315.79},
    "437669532": {"withdrawals": 28519.93, "deposits": 7471.46},
}

st.set_page_config(
    page_title="FinMg — ANZ Statement Processor",
    page_icon="📊",
    layout="wide",
)

st.title("FinMg — ANZ Statement Processor")

# ── Session state initialisation ──
if "parsed_accounts" not in st.session_state:
    st.session_state.parsed_accounts = {}  # acct_num → {meta, transactions}
if "monthly_split" not in st.session_state:
    st.session_state.monthly_split = {}    # acct_num → {month → [txns]}
if "categorised" not in st.session_state:
    st.session_state.categorised = False
if "merged" not in st.session_state:
    st.session_state.merged = {}           # month → [txns]
if "exported_files" not in st.session_state:
    st.session_state.exported_files = []

# ── Helper: is step complete? ──
def step_complete(n: int) -> bool:
    if n == 1:
        return len(st.session_state.parsed_accounts) > 0
    if n == 2:
        return len(st.session_state.monthly_split) > 0
    if n == 3:
        return st.session_state.categorised
    if n == 4:
        return len(st.session_state.merged) > 0
    if n == 5:
        return len(st.session_state.exported_files) > 0
    return False


# ── Tabs ──
tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "1. Parse PDFs",
    "2. Split by Month",
    "3. Categorise",
    "4. Merge Accounts",
    "5. Export Excel",
])

# ═══════════════════════════════════════════════════════════════
# TAB 1: Parse PDFs
# ═══════════════════════════════════════════════════════════════
with tab1:
    st.header("Step 1: Parse Bank Statement PDFs")

    uploaded_files = st.file_uploader(
        "Upload ANZ Transaction Report PDFs",
        type=["pdf"],
        accept_multiple_files=True,
        key="pdf_uploader",
    )

    if uploaded_files and st.button("Parse PDFs", type="primary", key="parse_btn"):
        st.session_state.parsed_accounts = {}
        st.session_state.monthly_split = {}
        st.session_state.categorised = False
        st.session_state.merged = {}
        st.session_state.exported_files = []

        for uploaded in uploaded_files:
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
                tmp.write(uploaded.read())
                tmp_path = tmp.name

            with st.spinner(f"Parsing {uploaded.name}..."):
                meta, txns = extract_transactions(tmp_path)

            # Validate
            expected = EXPECTED_TOTALS.get(meta.account_number, {})
            result = validate_totals(
                txns,
                expected.get("withdrawals"),
                expected.get("deposits"),
            )

            st.session_state.parsed_accounts[meta.account_number] = {
                "meta": meta,
                "transactions": txns,
                "validation": result,
            }

            # Show results
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Account", f"{meta.account_type}")
                st.caption(f"BSB: {meta.bsb} | Acct: {meta.account_number}")
            with col2:
                match_w = result.get("withdrawals_match", None)
                st.metric(
                    "Withdrawals",
                    f"${result['parsed_withdrawals']:,.2f}",
                    delta="Match" if match_w else ("No expected" if match_w is None else "MISMATCH"),
                    delta_color="normal" if match_w else ("off" if match_w is None else "inverse"),
                )
            with col3:
                match_d = result.get("deposits_match", None)
                st.metric(
                    "Deposits",
                    f"${result['parsed_deposits']:,.2f}",
                    delta="Match" if match_d else ("No expected" if match_d is None else "MISMATCH"),
                    delta_color="normal" if match_d else ("off" if match_d is None else "inverse"),
                )

            st.success(f"{uploaded.name}: {result['transaction_count']} transactions parsed")

    # Show parsed data preview
    if step_complete(1):
        st.divider()
        st.subheader("Parsed Transactions Preview")
        acct_select = st.selectbox(
            "Select account",
            list(st.session_state.parsed_accounts.keys()),
            format_func=lambda x: f"{st.session_state.parsed_accounts[x]['meta'].account_type} ({x})",
            key="preview_acct",
        )
        if acct_select:
            txns = st.session_state.parsed_accounts[acct_select]["transactions"]
            df = transactions_to_dataframe(txns)
            edited_df = st.data_editor(
                df,
                use_container_width=True,
                num_rows="dynamic",
                key=f"edit_raw_{acct_select}",
            )
            try:
                updated_transactions = dataframe_to_transactions(edited_df)
            except ValueError as exc:
                st.error(f"Cannot apply edits yet: {exc}")
            else:
                st.session_state.parsed_accounts[acct_select]["transactions"] = updated_transactions

            # Download checkpoint
            csv = edited_df.to_csv(index=False)
            st.download_button(
                f"Download CSV — {acct_select}",
                csv,
                f"step1_raw_{acct_select}.csv",
                "text/csv",
                key=f"dl_raw_{acct_select}",
            )

# ═══════════════════════════════════════════════════════════════
# TAB 2: Split by Month
# ═══════════════════════════════════════════════════════════════
with tab2:
    st.header("Step 2: Split by Calendar Month")

    if not step_complete(1):
        st.info("Complete Step 1 (Parse PDFs) first.")
    else:
        if st.button("Split by Month", type="primary", key="split_btn"):
            st.session_state.monthly_split = {}
            st.session_state.categorised = False
            st.session_state.merged = {}
            st.session_state.exported_files = []

            for acct_num, data in st.session_state.parsed_accounts.items():
                monthly = split_by_month(data["transactions"])
                st.session_state.monthly_split[acct_num] = monthly

            st.success("Transactions split by month.")

        if step_complete(2):
            # Show month distribution
            all_months = set()
            for acct_months in st.session_state.monthly_split.values():
                all_months.update(acct_months.keys())

            st.subheader("Transaction Count by Month & Account")
            summary_data = []
            for month in sorted(all_months):
                row = {"Month": month}
                for acct_num in st.session_state.monthly_split:
                    acct_type = st.session_state.parsed_accounts[acct_num]["meta"].account_type
                    txns = st.session_state.monthly_split[acct_num].get(month, [])
                    row[f"{acct_type} ({acct_num})"] = len(txns)
                summary_data.append(row)

            st.dataframe(pd.DataFrame(summary_data), use_container_width=True)

            # Preview per month
            month_select = st.selectbox("Select month to preview", sorted(all_months), key="month_preview")
            if month_select:
                for acct_num, monthly in st.session_state.monthly_split.items():
                    if month_select in monthly:
                        acct_type = st.session_state.parsed_accounts[acct_num]["meta"].account_type
                        with st.expander(f"{acct_type} ({acct_num}) — {len(monthly[month_select])} transactions"):
                            df = transactions_to_dataframe(monthly[month_select])
                            st.dataframe(df, use_container_width=True)

# ═══════════════════════════════════════════════════════════════
# TAB 3: Categorise
# ═══════════════════════════════════════════════════════════════
with tab3:
    st.header("Step 3: Categorise Transactions")

    if not step_complete(2):
        st.info("Complete Step 2 (Split by Month) first.")
    else:
        # Load and show current rules
        config = load_category_rules()
        with st.expander("Category Rules (from categories.json)"):
            st.write("**Expense Categories:**")
            for rule in config.get("expense_categories", []):
                if rule["patterns"]:
                    st.write(f"- **{rule['name']}**: {', '.join(rule['patterns'])}")
                else:
                    st.write(f"- **{rule['name']}**: *(manual assignment)*")
            st.write("**Income Categories:**")
            for rule in config.get("income_categories", []):
                if rule["patterns"]:
                    st.write(f"- **{rule['name']}**: {', '.join(rule['patterns'])}")
                else:
                    st.write(f"- **{rule['name']}**: *(manual assignment)*")

        if st.button("Categorise All", type="primary", key="cat_btn"):
            st.session_state.categorised = False
            st.session_state.merged = {}
            st.session_state.exported_files = []

            for acct_num in st.session_state.monthly_split:
                for month in st.session_state.monthly_split[acct_num]:
                    txns = st.session_state.monthly_split[acct_num][month]
                    categorise_all(txns, config)

            st.session_state.categorised = True
            st.success("All transactions categorised.")

        if step_complete(3):
            # Show uncategorised count
            all_txns = []
            for acct_months in st.session_state.monthly_split.values():
                for txns in acct_months.values():
                    all_txns.extend(txns)

            uncategorised = [t for t in all_txns if t.category == "Uncategorised"]
            total = len(all_txns)

            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Total Transactions", total)
            with col2:
                st.metric("Categorised", total - len(uncategorised))
            with col3:
                st.metric("Uncategorised", len(uncategorised))

            # Category distribution chart
            summary = get_category_summary(all_txns)
            chart_data = pd.DataFrame([
                {"Category": cat, "Count": data["count"], "Expenses": data["total_withdrawals"]}
                for cat, data in summary.items()
            ])
            st.bar_chart(chart_data.set_index("Category")["Count"])

            # Editable table for uncategorised
            if uncategorised:
                st.subheader("Uncategorised Transactions — Edit Categories")
                uncat_df = transactions_to_dataframe(uncategorised)

                # Get all category options from config
                expense_cats, income_cats = get_all_category_names(config)
                category_options = expense_cats + income_cats + ["Internal Transfer", "Uncategorised"]

                edited_uncat = st.data_editor(
                    uncat_df,
                    column_config={
                        "Category": st.column_config.SelectboxColumn(
                            "Category",
                            options=category_options,
                        ),
                    },
                    use_container_width=True,
                    key="edit_uncat",
                )

                if st.button("Apply Manual Categories", key="apply_cat"):
                    # Map back edited categories to transactions
                    edited_cats = dict(zip(
                        zip(edited_uncat["Date"], edited_uncat["Description"], edited_uncat["Account"]),
                        edited_uncat["Category"],
                    ))
                    for acct_months in st.session_state.monthly_split.values():
                        for txns in acct_months.values():
                            for txn in txns:
                                key = (txn.date.isoformat(), txn.description, txn.account_number)
                                if key in edited_cats:
                                    txn.category = edited_cats[key]
                                    txn.is_internal_transfer = txn.category == "Internal Transfer"
                    st.success("Manual categories applied.")
                    st.rerun()

# ═══════════════════════════════════════════════════════════════
# TAB 4: Merge Accounts
# ═══════════════════════════════════════════════════════════════
with tab4:
    st.header("Step 4: Merge All Accounts")

    if not step_complete(3):
        st.info("Complete Step 3 (Categorise) first.")
    else:
        if st.button("Merge Accounts", type="primary", key="merge_btn"):
            st.session_state.merged = {}
            st.session_state.exported_files = []

            merged = merge_accounts(st.session_state.monthly_split)
            st.session_state.merged = merged
            st.success("Accounts merged per month.")

        if step_complete(4):
            # Summary
            for month in sorted(st.session_state.merged.keys()):
                txns = st.session_state.merged[month]
                internal = sum(1 for t in txns if t.is_internal_transfer)
                total_w = sum(t.withdrawal or 0 for t in txns if not t.is_internal_transfer)
                total_d = sum(t.deposit or 0 for t in txns if not t.is_internal_transfer)

                with st.expander(f"{month} — {len(txns)} transactions ({internal} internal transfers)"):
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        st.metric("Expenses (excl. transfers)", f"${total_w:,.2f}")
                    with col2:
                        st.metric("Income (excl. transfers)", f"${total_d:,.2f}")
                    with col3:
                        st.metric("Net", f"${total_d - total_w:,.2f}")

                    df = transactions_to_dataframe(txns)
                    st.dataframe(df, use_container_width=True)

                    # Download merged checkpoint
                    csv = df.to_csv(index=False)
                    st.download_button(
                        f"Download CSV — {month}",
                        csv,
                        f"step4_merged_{month}.csv",
                        "text/csv",
                        key=f"dl_merged_{month}",
                    )

# ═══════════════════════════════════════════════════════════════
# TAB 5: Export Excel
# ═══════════════════════════════════════════════════════════════
with tab5:
    st.header("Step 5: Export Budget Excel Workbooks")

    if not step_complete(4):
        st.info("Complete Step 4 (Merge Accounts) first.")
    else:
        output_dir = st.text_input(
            "Output directory",
            value="monthly_output(raw)",
            key="output_dir",
        )

        if st.button("Generate Excel Workbooks", type="primary", key="export_btn"):
            st.session_state.exported_files = []

            for month, txns in sorted(st.session_state.merged.items()):
                with st.spinner(f"Writing {month}..."):
                    filepath = write_budget_excel(txns, month, output_dir)
                    st.session_state.exported_files.append(filepath)

            st.success(f"Generated {len(st.session_state.exported_files)} Excel workbooks.")

        if step_complete(5):
            st.subheader("Generated Files")
            for fp in st.session_state.exported_files:
                col1, col2 = st.columns([3, 1])
                with col1:
                    st.write(f"`{fp}`")
                with col2:
                    with open(fp, "rb") as f:
                        st.download_button(
                            "Download",
                            f.read(),
                            Path(fp).name,
                            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            key=f"dl_{fp}",
                        )
