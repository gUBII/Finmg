"""Transaction browser with DB-backed filtering and category editing."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from src.db.database import get_connection, init_db
from src.db.queries import (
    account_display_name,
    get_account_display_names,
    get_all_transactions,
    get_distinct_accounts,
    get_distinct_months,
    get_account_types,
    update_transaction_category,
)
from src.pipeline.categoriser import get_all_category_names, load_category_rules
from src.ui.help import page_header, section_header, widget_help


def render_transactions_view() -> None:
    """Render a filterable, editable transactions table backed by SQLite."""
    page_header("Transactions", "transactions")

    conn = get_connection()
    init_db(conn)

    months = get_distinct_months(conn)
    accounts = get_distinct_accounts(conn)
    account_types = get_account_types(conn)

    if not months:
        st.info("No transactions loaded yet. Use the **Upload** view first.")
        conn.close()
        return

    # Filters
    fcol1, fcol2, fcol3 = st.columns(3)
    with fcol1:
        month_options = ["All"] + months
        selected_month = st.selectbox("Month", month_options)
    with fcol2:
        acct_options = ["All"] + [
            f"{account_types.get(a, a)} ({a})" for a in accounts
        ]
        selected_account_label = st.selectbox("Account", acct_options)
    with fcol3:
        # Get all categories present in the data
        all_rows = get_all_transactions(conn)
        all_cats = sorted({r["category"] for r in all_rows})
        cat_options = ["All"] + all_cats
        selected_category = st.selectbox("Category", cat_options)

    search = st.text_input(
        "Description search", help=widget_help("transactions.search")
    )

    # Resolve account number from label
    filter_month = None if selected_month == "All" else selected_month
    filter_account = None
    if selected_account_label != "All":
        # Extract account number from "TYPE (NUMBER)" format
        filter_account = selected_account_label.split("(")[-1].rstrip(")")

    # Fetch filtered data
    rows = get_all_transactions(conn, month=filter_month, account=filter_account)

    # Apply category and search filters in-memory
    if selected_category != "All":
        rows = [r for r in rows if r["category"] == selected_category]
    if search.strip():
        term = search.strip().upper()
        rows = [r for r in rows if term in r["description"].upper()]

    # KPI row
    total = len(rows)
    categorised = sum(1 for r in rows if r["category"] != "Uncategorised")
    uncategorised = total - categorised

    kcol1, kcol2, kcol3 = st.columns(3)
    with kcol1:
        st.metric("Total", total)
    with kcol2:
        st.metric("Categorised", categorised)
    with kcol3:
        st.metric("Uncategorised", uncategorised)

    if not rows:
        st.info("No transactions match the current filters.")
        conn.close()
        return

    # Build editable dataframe
    config = load_category_rules()
    expense_cats, income_cats = get_all_category_names(config)
    category_options = expense_cats + income_cats + ["Internal Transfer", "Uncategorised"]

    df = pd.DataFrame(rows)
    account_names = get_account_display_names(conn)
    df["account_name"] = df["account_number"].map(
        lambda n: account_names.get(n) or account_display_name(n)
    )
    display_df = df[["id", "date", "description", "withdrawal", "deposit",
                      "account_name", "category", "month"]].copy()
    display_df.columns = ["ID", "Date", "Description", "Withdrawal", "Deposit",
                          "Account", "Category", "Month"]

    section_header("Edit categories", "transactions.editor")
    edited_df = st.data_editor(
        display_df,
        column_config={
            "ID": st.column_config.NumberColumn("ID", disabled=True),
            "Date": st.column_config.TextColumn("Date", disabled=True),
            "Description": st.column_config.TextColumn("Description", disabled=True),
            "Withdrawal": st.column_config.NumberColumn("Withdrawal", format="$%.2f", disabled=True),
            "Deposit": st.column_config.NumberColumn("Deposit", format="$%.2f", disabled=True),
            "Account": st.column_config.TextColumn("Account", disabled=True),
            "Category": st.column_config.SelectboxColumn(
                "Category",
                options=category_options,
            ),
            "Month": st.column_config.TextColumn("Month", disabled=True),
        },
        width="stretch",
        hide_index=True,
        key="txn_editor",
    )

    if st.button("Save Changes", type="primary", width="stretch"):
        changes = 0
        for idx, row in edited_df.iterrows():
            original_cat = display_df.loc[idx, "Category"]
            new_cat = row["Category"]
            if new_cat != original_cat:
                update_transaction_category(
                    conn, int(row["ID"]), new_cat, original_cat
                )
                changes += 1
        if changes:
            st.success(f"Updated {changes} transaction(s).")
            st.rerun()
        else:
            st.info("No changes to save.")

    conn.close()
