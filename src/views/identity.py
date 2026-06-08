"""Identity & Contacts view — Section A of the NSWTG Private Manager's Plan.

Three tabs:
  Managed Person  — Ron's biographical and legal identity (Section A.1)
  Private Manager — Linda's details and appointment (Section A.2)
  Significant People — consultation contacts and gift recipients (Section A.3)

All writes use the update_* helpers in queries_estate.py (never raw SQL here).
audit_log integration is intentionally deferred to S2.5.
"""

from __future__ import annotations

import json

import pandas as pd
import streamlit as st

from src.db.database import get_connection, init_db
from src.db.queries_estate import (
    bootstrap_managed_person_if_empty,
    get_managed_person,
    get_significant_person,
    insert_significant_person,
    list_private_managers,
    list_significant_people,
    update_managed_person,
    update_private_manager,
    update_significant_person,
)
from src.models.estate import ManagedPerson, PrivateManager, SignificantPerson

_HAS_WILL_OPTIONS = [None, "yes", "no", "unsure"]
_HAS_WILL_LABELS = {None: "— unset —", "yes": "yes", "no": "no", "unsure": "unsure"}
_APPOINTMENT_OPTIONS = [None, "sole", "jointly", "jointly_severally"]
_STATUS_OPTIONS = ["active", "estranged", "deceased"]


def render_identity_view() -> None:
    """Render the Identity & Contacts management page."""
    st.title("Identity & Contacts")

    conn = get_connection()
    init_db(conn)

    mp_id = bootstrap_managed_person_if_empty(conn, "GENTILI", "Renato")

    tab_mp, tab_pm, tab_sp = st.tabs(
        ["Managed Person", "Private Manager", "Significant People"]
    )

    with tab_mp:
        _render_managed_person_tab(conn, mp_id)

    with tab_pm:
        _render_private_manager_tab(conn, mp_id)

    with tab_sp:
        _render_significant_people_tab(conn, mp_id)

    conn.close()


# ---------------------------------------------------------------------------
# Tab: Managed Person (Section A.1)
# ---------------------------------------------------------------------------

def _render_managed_person_tab(conn, mp_id: int) -> None:
    st.subheader("Managed Person — Section A.1")
    mp = get_managed_person(conn, mp_id)
    if mp is None:
        st.error("No managed person record found.")
        return

    # Parse disability_flags JSON; fall back gracefully on corrupt data.
    try:
        disability_list: list[str] = json.loads(mp.disability_flags or "[]")
    except (json.JSONDecodeError, TypeError):
        disability_list = []

    with st.form("form_managed_person"):
        col1, col2 = st.columns(2)
        with col1:
            surname = st.text_input("Surname", value=mp.surname or "")
            given_names = st.text_input("Given names", value=mp.given_names or "")
            other_names = st.text_input("Other names", value=mp.other_names or "")
            dob = st.text_input("Date of birth (YYYY-MM-DD)", value=mp.dob or "")
        with col2:
            address_line1 = st.text_input("Address line 1", value=mp.address_line1 or "")
            address_line2 = st.text_input("Address line 2", value=mp.address_line2 or "")
            postcode = st.text_input("Postcode", value=mp.postcode or "")
            phone = st.text_input("Phone", value=mp.phone or "")
            email = st.text_input("Email", value=mp.email or "")

        st.divider()
        col3, col4 = st.columns(2)
        with col3:
            interpreter_required = st.checkbox(
                "Interpreter required", value=bool(mp.interpreter_required)
            )
            interpreter_language = st.text_input(
                "Interpreter language", value=mp.interpreter_language or ""
            )
            disability_flags_raw = st.text_input(
                "Disability flags (JSON array)",
                value=mp.disability_flags or "[]",
                help='e.g. ["physical","brain_injury"]',
            )
        with col4:
            has_will_idx = _HAS_WILL_OPTIONS.index(mp.has_will) if mp.has_will in _HAS_WILL_OPTIONS else 0
            has_will = st.selectbox(
                "Has will",
                options=_HAS_WILL_OPTIONS,
                index=has_will_idx,
                format_func=lambda v: _HAS_WILL_LABELS.get(v, str(v)),
            )
            will_location = st.text_input("Will location", value=mp.will_location or "")
            fmo_date = st.text_input("FMO date (YYYY-MM-DD)", value=mp.fmo_date or "")
            fmo_authority = st.text_input("FMO authority", value=mp.fmo_authority or "")

        col5, col6 = st.columns(2)
        with col5:
            d_and_a_reference = st.text_input(
                "D&A reference", value=mp.d_and_a_reference or ""
            )
        with col6:
            customer_reference_number = st.text_input(
                "Customer reference number",
                value=mp.customer_reference_number or "",
            )

        submitted = st.form_submit_button("Save", type="primary", use_container_width=True)

    if submitted:
        # Validate and normalise disability_flags at the form boundary.
        try:
            parsed_flags = json.loads(disability_flags_raw or "[]")
            clean_flags = json.dumps(parsed_flags)
        except (json.JSONDecodeError, TypeError):
            st.error("Disability flags must be a valid JSON array, e.g. [\"physical\"]")
            return

        updated = ManagedPerson(
            id=mp_id,
            surname=surname.strip(),
            given_names=given_names.strip(),
            other_names=other_names.strip() or None,
            dob=dob.strip() or None,
            address_line1=address_line1.strip() or None,
            address_line2=address_line2.strip() or None,
            postcode=postcode.strip() or None,
            phone=phone.strip() or None,
            email=email.strip() or None,
            interpreter_required=interpreter_required,
            interpreter_language=interpreter_language.strip() or None,
            disability_flags=clean_flags,
            has_will=has_will,
            will_location=will_location.strip() or None,
            fmo_date=fmo_date.strip() or None,
            fmo_authority=fmo_authority.strip() or None,
            d_and_a_reference=d_and_a_reference.strip() or None,
            customer_reference_number=customer_reference_number.strip() or None,
        )
        update_managed_person(conn, mp_id, updated)
        st.success("Managed person updated.")
        st.rerun()


# ---------------------------------------------------------------------------
# Tab: Private Manager (Section A.2)
# ---------------------------------------------------------------------------

def _render_private_manager_tab(conn, mp_id: int) -> None:
    st.subheader("Private Manager — Section A.2")
    managers = list_private_managers(conn, mp_id)

    if len(managers) > 1:
        st.warning(
            f"{len(managers)} private manager rows found. "
            "Editing the first row only. Remove duplicates via the DB CLI."
        )

    if not managers:
        st.info("No private manager record yet. Add one via the DB seed or CLI.")
        return

    pm = managers[0]
    pm_id = pm.id

    with st.form("form_private_manager"):
        col1, col2 = st.columns(2)
        with col1:
            surname = st.text_input("Surname", value=pm.surname or "")
            given_name = st.text_input("Given name", value=pm.given_name or "")
            relationship = st.text_input("Relationship", value=pm.relationship or "")
        with col2:
            address_line1 = st.text_input("Address line 1", value=pm.address_line1 or "")
            address_line2 = st.text_input("Address line 2", value=pm.address_line2 or "")
            postcode = st.text_input("Postcode", value=pm.postcode or "")

        col3, col4 = st.columns(2)
        with col3:
            home_phone = st.text_input("Home phone", value=pm.home_phone or "")
            mobile = st.text_input("Mobile", value=pm.mobile or "")
            email = st.text_input("Email", value=pm.email or "")
        with col4:
            appt_idx = (
                _APPOINTMENT_OPTIONS.index(pm.appointment_type)
                if pm.appointment_type in _APPOINTMENT_OPTIONS
                else 0
            )
            appointment_type = st.selectbox(
                "Appointment type",
                options=_APPOINTMENT_OPTIONS,
                index=appt_idx,
                format_func=lambda v: v or "— unset —",
            )
            remuneration_order_date = st.text_input(
                "Remuneration order date",
                value=pm.remuneration_order_date or "",
            )

        submitted = st.form_submit_button("Save", type="primary", use_container_width=True)

    if submitted:
        updated = PrivateManager(
            id=pm_id,
            managed_person_id=mp_id,
            surname=surname.strip(),
            given_name=given_name.strip(),
            relationship=relationship.strip() or None,
            address_line1=address_line1.strip() or None,
            address_line2=address_line2.strip() or None,
            postcode=postcode.strip() or None,
            home_phone=home_phone.strip() or None,
            mobile=mobile.strip() or None,
            email=email.strip() or None,
            appointment_type=appointment_type,
            remuneration_order_date=remuneration_order_date.strip() or None,
        )
        update_private_manager(conn, pm_id, updated)
        st.success("Private manager updated.")
        st.rerun()


# ---------------------------------------------------------------------------
# Tab: Significant People (Section A.3)
# ---------------------------------------------------------------------------

def _render_significant_people_tab(conn, mp_id: int) -> None:
    st.subheader("Significant People — Section A.3")

    people = list_significant_people(conn, mp_id, include_estranged=True, include_deceased=True)

    if not people:
        st.info("No significant people yet. Add one below.")
        _render_add_significant_person_form(conn, mp_id)
        return

    # Build editable dataframe for existing rows.
    rows = [
        {
            "id": sp.id,
            "Given name": sp.given_name,
            "Surname": sp.surname,
            "Relationship": sp.relationship or "",
            "Mobile": sp.mobile or "",
            "Email": sp.email or "",
            "Status": sp.consultation_status,
            "Notes": sp.notes or "",
        }
        for sp in people
    ]
    df = pd.DataFrame(rows)

    edited = st.data_editor(
        df,
        column_config={
            "id": st.column_config.NumberColumn("ID", disabled=True),
            "Status": st.column_config.SelectboxColumn(
                "Status", options=_STATUS_OPTIONS
            ),
        },
        use_container_width=True,
        hide_index=True,
        num_rows="fixed",
        key="sp_editor",
    )

    if st.button("Save Changes", type="primary", use_container_width=True):
        changes = 0
        for _, row in edited.iterrows():
            sp_id = int(row["id"])
            original = get_significant_person(conn, sp_id)
            if original is None:
                continue
            updated = SignificantPerson(
                id=sp_id,
                managed_person_id=mp_id,
                surname=str(row["Surname"]).strip(),
                given_name=str(row["Given name"]).strip(),
                relationship=str(row["Relationship"]).strip() or None,
                mobile=str(row["Mobile"]).strip() or None,
                email=str(row["Email"]).strip() or None,
                consultation_status=str(row["Status"]),
                notes=str(row["Notes"]).strip() or None,
            )
            # Only write if something changed.
            if (
                updated.given_name != original.given_name
                or updated.surname != original.surname
                or updated.relationship != original.relationship
                or updated.mobile != original.mobile
                or updated.email != original.email
                or updated.consultation_status != original.consultation_status
                or updated.notes != original.notes
            ):
                update_significant_person(conn, sp_id, updated)
                changes += 1
        if changes:
            st.success(f"Updated {changes} person(s).")
            st.rerun()
        else:
            st.info("No changes to save.")

    st.divider()
    _render_add_significant_person_form(conn, mp_id)


def _render_add_significant_person_form(conn, mp_id: int) -> None:
    st.markdown("**Add person**")
    with st.form("form_add_sp", clear_on_submit=True):
        col1, col2 = st.columns(2)
        with col1:
            new_given = st.text_input("Given name")
            new_surname = st.text_input("Surname")
            new_rel = st.text_input("Relationship")
        with col2:
            new_mobile = st.text_input("Mobile")
            new_email = st.text_input("Email")
            new_status = st.selectbox("Status", options=_STATUS_OPTIONS)

        add_submitted = st.form_submit_button("Add", type="secondary")

    if add_submitted:
        if not new_given.strip() or not new_surname.strip():
            st.error("Given name and surname are required.")
            return
        insert_significant_person(
            conn,
            SignificantPerson(
                managed_person_id=mp_id,
                given_name=new_given.strip(),
                surname=new_surname.strip(),
                relationship=new_rel.strip() or None,
                mobile=new_mobile.strip() or None,
                email=new_email.strip() or None,
                consultation_status=new_status,
            ),
        )
        st.success(f"Added {new_given.strip()} {new_surname.strip()}.")
        st.rerun()
