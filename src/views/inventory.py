"""Estate Inventory view — Sections B and C of the NSWTG Private Manager's Plan.

Six tabs:
  Accounts             — Section B.1 (auto-populated from parsed PDFs;
                          identity columns are read-only)
  Real Estate          — Section B.2
  Investments          — Section B.3
  Motor Vehicles       — Section B.4
  Accommodation Bonds  — Section B.5
  Debts                — Section C

Every save path goes through `dataclasses.replace(original, ...)` so hidden
DTO fields survive the round-trip — this is the codified fix for the
SP-UPDATE-FIELDS bug landed in commit 902f95c.

audit_log integration is intentionally deferred to S2.5; this view writes
directly via the queries_estate update_* helpers.
"""

from __future__ import annotations

from dataclasses import replace

import pandas as pd
import streamlit as st

from src.db.database import get_connection, init_db
from src.db.queries_estate import (
    bootstrap_managed_person_if_empty,
    get_accommodation_bond,
    get_account,
    get_debt_liability,
    get_investment,
    get_motor_vehicle,
    get_real_estate,
    insert_accommodation_bond,
    insert_debt_liability,
    insert_investment,
    insert_motor_vehicle,
    insert_real_estate,
    list_accommodation_bonds,
    list_accounts,
    list_debts_liabilities,
    list_investments,
    list_motor_vehicles,
    list_real_estate,
    update_accommodation_bond,
    update_account,
    update_debt_liability,
    update_investment,
    update_motor_vehicle,
    update_real_estate,
)
from src.models.estate import (
    AccommodationBond,
    DebtLiability,
    Investment,
    MotorVehicle,
    RealEstate,
)
from src.ui.help import page_header, section_header

_ROLE_OPTIONS = [None, "living", "spending", "savings", "other"]
_OWNERSHIP_OPTIONS = [None, "sole", "joint"]
_REAL_ESTATE_OWNERSHIP_OPTIONS = [None, "sole", "joint_tenant", "tenants_in_common"]
_REAL_ESTATE_OCCUPANCY_OPTIONS = [None, "managed_person", "tenant", "vacant"]
_PAID_UNPAID_OPTIONS = [None, "paid", "unpaid"]


def render_inventory_view() -> None:
    """Render the Estate Inventory management page."""
    page_header("Estate Inventory", "inventory")

    conn = get_connection()
    init_db(conn)

    mp_id = bootstrap_managed_person_if_empty(conn, "GENTILI", "Renato")

    (tab_acc, tab_re, tab_inv, tab_mv, tab_bond, tab_debt) = st.tabs(
        ["Accounts", "Real Estate", "Investments",
         "Motor Vehicles", "Accommodation Bonds", "Debts"]
    )

    with tab_acc:
        _render_accounts_tab(conn, mp_id)
    with tab_re:
        _render_real_estate_tab(conn, mp_id)
    with tab_inv:
        _render_investments_tab(conn, mp_id)
    with tab_mv:
        _render_motor_vehicles_tab(conn, mp_id)
    with tab_bond:
        _render_accommodation_bonds_tab(conn, mp_id)
    with tab_debt:
        _render_debts_tab(conn, mp_id)

    conn.close()


def _coerce_float(raw) -> float | None:
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def _coerce_int(raw) -> int | None:
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def _coerce_str(raw) -> str | None:
    if raw is None:
        return None
    s = str(raw).strip()
    return s or None


# ---------------------------------------------------------------------------
# Tab: Accounts (Section B.1) — identity fields read-only
# ---------------------------------------------------------------------------

def _render_accounts_tab(conn, mp_id: int) -> None:
    section_header("Bank & credit-union accounts — Section B.1", "inventory.accounts")
    st.caption(
        "Institution, account number, and BSB come from parsed bank statements "
        "and are evidence-grade — they cannot be edited here. Use the editable "
        "columns to set the role label, ownership, balance, and notes."
    )

    accounts = list_accounts(conn, mp_id)
    if not accounts:
        st.info("No accounts found. Run `python3 scripts/seed.py` to seed Ron's three ANZ accounts.")
        return

    rows = [
        {
            "id": acc.id,
            "Institution": acc.institution or "",
            "Account number": acc.account_number or "",
            "BSB": acc.bsb or "",
            "Type": acc.account_type or "",
            "Role": acc.role_label,
            "Ownership": acc.ownership or "sole",
            "Inception date": acc.inception_date or "",
            "Current balance": acc.current_balance,
            "Balance as-of": acc.balance_as_of_date or "",
            "Notes": acc.notes or "",
        }
        for acc in accounts
    ]
    df = pd.DataFrame(rows)

    edited = st.data_editor(
        df,
        column_config={
            "id": st.column_config.NumberColumn("ID", disabled=True),
            "Institution": st.column_config.TextColumn("Institution", disabled=True),
            "Account number": st.column_config.TextColumn("Account number", disabled=True),
            "BSB": st.column_config.TextColumn("BSB", disabled=True),
            "Type": st.column_config.TextColumn("Type", disabled=True),
            "Role": st.column_config.SelectboxColumn("Role", options=_ROLE_OPTIONS),
            "Ownership": st.column_config.SelectboxColumn("Ownership", options=["sole", "joint"]),
            "Current balance": st.column_config.NumberColumn("Current balance", format="%.2f"),
        },
        width="stretch",
        hide_index=True,
        num_rows="fixed",
        key="acc_editor",
    )

    if st.button("Save accounts", type="primary", key="acc_save"):
        changes = 0
        for _, row in edited.iterrows():
            acc_id = int(row["id"])
            original = get_account(conn, acc_id)
            if original is None:
                continue
            patched = replace(
                original,
                role_label=_coerce_str(row["Role"]),
                ownership=_coerce_str(row["Ownership"]) or "sole",
                inception_date=_coerce_str(row["Inception date"]),
                current_balance=_coerce_float(row["Current balance"]),
                balance_as_of_date=_coerce_str(row["Balance as-of"]),
                notes=_coerce_str(row["Notes"]),
            )
            if patched != original:
                update_account(conn, acc_id, patched)
                changes += 1
        if changes:
            st.success(f"Updated {changes} account(s).")
            st.rerun()
        else:
            st.info("No changes to save.")


# ---------------------------------------------------------------------------
# Tab: Real Estate (Section B.2)
# ---------------------------------------------------------------------------

def _render_real_estate_tab(conn, mp_id: int) -> None:
    section_header("Real estate — Section B.2", "inventory.real_estate")
    items = list_real_estate(conn, mp_id)

    if items:
        rows = [
            {
                "id": it.id,
                "Address": it.address or "",
                "Postcode": it.postcode or "",
                "Ownership": it.ownership,
                "Occupancy": it.occupancy,
                "Value": it.value,
                "Valuation date": it.valuation_date or "",
            }
            for it in items
        ]
        df = pd.DataFrame(rows)
        edited = st.data_editor(
            df,
            column_config={
                "id": st.column_config.NumberColumn("ID", disabled=True),
                "Ownership": st.column_config.SelectboxColumn("Ownership", options=_REAL_ESTATE_OWNERSHIP_OPTIONS),
                "Occupancy": st.column_config.SelectboxColumn("Occupancy", options=_REAL_ESTATE_OCCUPANCY_OPTIONS),
                "Value": st.column_config.NumberColumn("Value", format="%.2f"),
            },
            width="stretch",
            hide_index=True,
            num_rows="fixed",
            key="re_editor",
        )

        if st.button("Save real estate", type="primary", key="re_save"):
            changes = 0
            for _, row in edited.iterrows():
                re_id = int(row["id"])
                original = get_real_estate(conn, re_id)
                if original is None:
                    continue
                patched = replace(
                    original,
                    address=_coerce_str(row["Address"]) or "",
                    postcode=_coerce_str(row["Postcode"]),
                    ownership=_coerce_str(row["Ownership"]),
                    occupancy=_coerce_str(row["Occupancy"]),
                    value=_coerce_float(row["Value"]),
                    valuation_date=_coerce_str(row["Valuation date"]),
                )
                if patched != original:
                    update_real_estate(conn, re_id, patched)
                    changes += 1
            if changes:
                st.success(f"Updated {changes} property/properties.")
                st.rerun()
            else:
                st.info("No changes to save.")
    else:
        st.info("No real estate recorded.")

    st.divider()
    _render_add_real_estate_form(conn, mp_id)


def _render_add_real_estate_form(conn, mp_id: int) -> None:
    st.markdown("**Add property**")
    with st.form("form_add_re", clear_on_submit=True):
        col1, col2 = st.columns(2)
        with col1:
            address = st.text_input("Address")
            postcode = st.text_input("Postcode")
            ownership = st.selectbox("Ownership", options=_REAL_ESTATE_OWNERSHIP_OPTIONS)
        with col2:
            occupancy = st.selectbox("Occupancy", options=_REAL_ESTATE_OCCUPANCY_OPTIONS)
            value = st.number_input("Value", min_value=0.0, step=1000.0, value=0.0)
            valuation_date = st.text_input("Valuation date (YYYY-MM-DD)")
        submitted = st.form_submit_button("Add", type="secondary")

    if submitted:
        if not address.strip():
            st.error("Address is required.")
            return
        insert_real_estate(
            conn,
            RealEstate(
                managed_person_id=mp_id,
                address=address.strip(),
                postcode=_coerce_str(postcode),
                ownership=ownership,
                occupancy=occupancy,
                value=value if value > 0 else None,
                valuation_date=_coerce_str(valuation_date),
            ),
        )
        st.success(f"Added {address.strip()}.")
        st.rerun()


# ---------------------------------------------------------------------------
# Tab: Investments (Section B.3)
# ---------------------------------------------------------------------------

def _render_investments_tab(conn, mp_id: int) -> None:
    section_header("Investments — Section B.3", "inventory.investments")
    items = list_investments(conn, mp_id)

    if items:
        rows = [
            {
                "id": it.id,
                "Type": it.type or "",
                "Description": it.description or "",
                "Ownership": it.ownership,
                "Units": it.units,
                "Amount": it.amount,
                "Last review": it.last_review_date or "",
            }
            for it in items
        ]
        df = pd.DataFrame(rows)
        edited = st.data_editor(
            df,
            column_config={
                "id": st.column_config.NumberColumn("ID", disabled=True),
                "Ownership": st.column_config.SelectboxColumn("Ownership", options=_OWNERSHIP_OPTIONS),
                "Units": st.column_config.NumberColumn("Units", format="%.4f"),
                "Amount": st.column_config.NumberColumn("Amount", format="%.2f"),
            },
            width="stretch",
            hide_index=True,
            num_rows="fixed",
            key="inv_editor",
        )

        if st.button("Save investments", type="primary", key="inv_save"):
            changes = 0
            for _, row in edited.iterrows():
                inv_id = int(row["id"])
                original = get_investment(conn, inv_id)
                if original is None:
                    continue
                patched = replace(
                    original,
                    type=_coerce_str(row["Type"]),
                    description=_coerce_str(row["Description"]),
                    ownership=_coerce_str(row["Ownership"]),
                    units=_coerce_float(row["Units"]),
                    amount=_coerce_float(row["Amount"]),
                    last_review_date=_coerce_str(row["Last review"]),
                )
                if patched != original:
                    update_investment(conn, inv_id, patched)
                    changes += 1
            if changes:
                st.success(f"Updated {changes} investment(s).")
                st.rerun()
            else:
                st.info("No changes to save.")
    else:
        st.info("No investments recorded.")

    st.divider()
    _render_add_investment_form(conn, mp_id)


def _render_add_investment_form(conn, mp_id: int) -> None:
    st.markdown("**Add investment**")
    with st.form("form_add_inv", clear_on_submit=True):
        col1, col2 = st.columns(2)
        with col1:
            inv_type = st.text_input("Type (e.g. term_deposit, shares)")
            description = st.text_input("Description")
            ownership = st.selectbox("Ownership", options=_OWNERSHIP_OPTIONS)
        with col2:
            units = st.number_input("Units", min_value=0.0, step=1.0, value=0.0)
            amount = st.number_input("Amount", min_value=0.0, step=100.0, value=0.0)
            last_review = st.text_input("Last review (YYYY-MM-DD)")
        submitted = st.form_submit_button("Add", type="secondary")

    if submitted:
        if not (inv_type.strip() or description.strip()):
            st.error("Type or description is required.")
            return
        from src.db.queries_estate import insert_investment as _insert_inv
        _insert_inv(
            conn,
            Investment(
                managed_person_id=mp_id,
                type=_coerce_str(inv_type),
                description=_coerce_str(description),
                ownership=ownership,
                units=units if units > 0 else None,
                amount=amount if amount > 0 else None,
                last_review_date=_coerce_str(last_review),
            ),
        )
        st.success("Added investment.")
        st.rerun()


# ---------------------------------------------------------------------------
# Tab: Motor Vehicles (Section B.4)
# ---------------------------------------------------------------------------

def _render_motor_vehicles_tab(conn, mp_id: int) -> None:
    section_header("Motor vehicles — Section B.4", "inventory.vehicles")
    items = list_motor_vehicles(conn, mp_id)

    if items:
        rows = [
            {
                "id": it.id,
                "Type": it.type or "",
                "Model": it.model or "",
                "Year": it.year,
                "Ownership": it.ownership,
                "Value": it.value,
            }
            for it in items
        ]
        df = pd.DataFrame(rows)
        edited = st.data_editor(
            df,
            column_config={
                "id": st.column_config.NumberColumn("ID", disabled=True),
                "Ownership": st.column_config.SelectboxColumn("Ownership", options=_OWNERSHIP_OPTIONS),
                "Year": st.column_config.NumberColumn("Year", format="%d"),
                "Value": st.column_config.NumberColumn("Value", format="%.2f"),
            },
            width="stretch",
            hide_index=True,
            num_rows="fixed",
            key="mv_editor",
        )

        if st.button("Save vehicles", type="primary", key="mv_save"):
            changes = 0
            for _, row in edited.iterrows():
                mv_id = int(row["id"])
                original = get_motor_vehicle(conn, mv_id)
                if original is None:
                    continue
                patched = replace(
                    original,
                    type=_coerce_str(row["Type"]),
                    model=_coerce_str(row["Model"]),
                    year=_coerce_int(row["Year"]),
                    ownership=_coerce_str(row["Ownership"]),
                    value=_coerce_float(row["Value"]),
                )
                if patched != original:
                    update_motor_vehicle(conn, mv_id, patched)
                    changes += 1
            if changes:
                st.success(f"Updated {changes} vehicle(s).")
                st.rerun()
            else:
                st.info("No changes to save.")
    else:
        st.info("No motor vehicles recorded.")

    st.divider()
    _render_add_motor_vehicle_form(conn, mp_id)


def _render_add_motor_vehicle_form(conn, mp_id: int) -> None:
    st.markdown("**Add vehicle**")
    with st.form("form_add_mv", clear_on_submit=True):
        col1, col2 = st.columns(2)
        with col1:
            mv_type = st.text_input("Type (e.g. sedan, suv)")
            model = st.text_input("Model")
            year = st.number_input("Year", min_value=1900, max_value=2100, value=2020, step=1)
        with col2:
            ownership = st.selectbox("Ownership", options=_OWNERSHIP_OPTIONS)
            value = st.number_input("Value", min_value=0.0, step=1000.0, value=0.0)
        submitted = st.form_submit_button("Add", type="secondary")

    if submitted:
        if not (model.strip() or mv_type.strip()):
            st.error("Type or model is required.")
            return
        insert_motor_vehicle(
            conn,
            MotorVehicle(
                managed_person_id=mp_id,
                type=_coerce_str(mv_type),
                model=_coerce_str(model),
                year=int(year) if year else None,
                ownership=ownership,
                value=value if value > 0 else None,
            ),
        )
        st.success("Added vehicle.")
        st.rerun()


# ---------------------------------------------------------------------------
# Tab: Accommodation Bonds (Section B.5)
# ---------------------------------------------------------------------------

def _render_accommodation_bonds_tab(conn, mp_id: int) -> None:
    section_header("Accommodation bonds — Section B.5", "inventory.bonds")
    items = list_accommodation_bonds(conn, mp_id)

    if items:
        rows = [
            {
                "id": it.id,
                "Facility": it.facility_name or "",
                "Address": it.facility_address or "",
                "Date of entry": it.date_of_entry or "",
                "Paid/unpaid": it.paid_unpaid,
                "Amount": it.amount,
            }
            for it in items
        ]
        df = pd.DataFrame(rows)
        edited = st.data_editor(
            df,
            column_config={
                "id": st.column_config.NumberColumn("ID", disabled=True),
                "Paid/unpaid": st.column_config.SelectboxColumn("Paid/unpaid", options=_PAID_UNPAID_OPTIONS),
                "Amount": st.column_config.NumberColumn("Amount", format="%.2f"),
            },
            width="stretch",
            hide_index=True,
            num_rows="fixed",
            key="bond_editor",
        )

        if st.button("Save bonds", type="primary", key="bond_save"):
            changes = 0
            for _, row in edited.iterrows():
                bond_id = int(row["id"])
                original = get_accommodation_bond(conn, bond_id)
                if original is None:
                    continue
                patched = replace(
                    original,
                    facility_name=_coerce_str(row["Facility"]),
                    facility_address=_coerce_str(row["Address"]),
                    date_of_entry=_coerce_str(row["Date of entry"]),
                    paid_unpaid=_coerce_str(row["Paid/unpaid"]),
                    amount=_coerce_float(row["Amount"]),
                )
                if patched != original:
                    update_accommodation_bond(conn, bond_id, patched)
                    changes += 1
            if changes:
                st.success(f"Updated {changes} bond(s).")
                st.rerun()
            else:
                st.info("No changes to save.")
    else:
        st.info("No accommodation bonds recorded.")

    st.divider()
    _render_add_accommodation_bond_form(conn, mp_id)


def _render_add_accommodation_bond_form(conn, mp_id: int) -> None:
    st.markdown("**Add bond**")
    with st.form("form_add_bond", clear_on_submit=True):
        col1, col2 = st.columns(2)
        with col1:
            facility_name = st.text_input("Facility name")
            facility_address = st.text_input("Facility address")
            date_of_entry = st.text_input("Date of entry (YYYY-MM-DD)")
        with col2:
            paid_unpaid = st.selectbox("Paid/unpaid", options=_PAID_UNPAID_OPTIONS)
            amount = st.number_input("Amount", min_value=0.0, step=1000.0, value=0.0)
        submitted = st.form_submit_button("Add", type="secondary")

    if submitted:
        if not facility_name.strip():
            st.error("Facility name is required.")
            return
        insert_accommodation_bond(
            conn,
            AccommodationBond(
                managed_person_id=mp_id,
                facility_name=facility_name.strip(),
                facility_address=_coerce_str(facility_address),
                date_of_entry=_coerce_str(date_of_entry),
                paid_unpaid=paid_unpaid,
                amount=amount if amount > 0 else None,
            ),
        )
        st.success("Added bond.")
        st.rerun()


# ---------------------------------------------------------------------------
# Tab: Debts & Liabilities (Section C)
# ---------------------------------------------------------------------------

def _render_debts_tab(conn, mp_id: int) -> None:
    section_header("Debts and liabilities — Section C", "inventory.debts")
    items = list_debts_liabilities(conn, mp_id)

    if items:
        rows = [
            {
                "id": it.id,
                "Lender": it.lender or "",
                "Type": it.type or "",
                "Term": it.term or "",
                "Amount": it.amount,
            }
            for it in items
        ]
        df = pd.DataFrame(rows)
        edited = st.data_editor(
            df,
            column_config={
                "id": st.column_config.NumberColumn("ID", disabled=True),
                "Amount": st.column_config.NumberColumn("Amount", format="%.2f"),
            },
            width="stretch",
            hide_index=True,
            num_rows="fixed",
            key="debt_editor",
        )

        if st.button("Save debts", type="primary", key="debt_save"):
            changes = 0
            for _, row in edited.iterrows():
                debt_id = int(row["id"])
                original = get_debt_liability(conn, debt_id)
                if original is None:
                    continue
                patched = replace(
                    original,
                    lender=_coerce_str(row["Lender"]),
                    type=_coerce_str(row["Type"]),
                    term=_coerce_str(row["Term"]),
                    amount=_coerce_float(row["Amount"]),
                )
                if patched != original:
                    update_debt_liability(conn, debt_id, patched)
                    changes += 1
            if changes:
                st.success(f"Updated {changes} debt(s).")
                st.rerun()
            else:
                st.info("No changes to save.")
    else:
        st.info("No debts recorded.")

    st.divider()
    _render_add_debt_form(conn, mp_id)


def _render_add_debt_form(conn, mp_id: int) -> None:
    st.markdown("**Add debt**")
    with st.form("form_add_debt", clear_on_submit=True):
        col1, col2 = st.columns(2)
        with col1:
            lender = st.text_input("Lender")
            debt_type = st.text_input("Type (e.g. credit_card, tax_debt)")
        with col2:
            term = st.text_input("Term")
            amount = st.number_input("Amount", min_value=0.0, step=100.0, value=0.0)
        submitted = st.form_submit_button("Add", type="secondary")

    if submitted:
        if not lender.strip():
            st.error("Lender is required.")
            return
        insert_debt_liability(
            conn,
            DebtLiability(
                managed_person_id=mp_id,
                lender=lender.strip(),
                type=_coerce_str(debt_type),
                term=_coerce_str(term),
                amount=amount if amount > 0 else None,
            ),
        )
        st.success("Added debt.")
        st.rerun()
