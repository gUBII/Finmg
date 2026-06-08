"""Dataclass DTOs for the estate-inventory tables (NSWTG Plan Sections A, B, C).

Frozen by default — mutations go through `dataclasses.replace(...)`.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ManagedPerson:
    """Section A.1 — the person under management (Ron)."""
    surname: str
    given_names: str
    id: int | None = None
    other_names: str | None = None
    dob: str | None = None
    address_line1: str | None = None
    address_line2: str | None = None
    postcode: str | None = None
    email: str | None = None
    phone: str | None = None
    interpreter_required: bool = False
    interpreter_language: str | None = None
    disability_flags: str | None = None      # JSON array string
    has_will: str | None = None              # 'yes'|'no'|'unsure'
    will_location: str | None = None
    fmo_date: str | None = None
    fmo_authority: str | None = None
    d_and_a_reference: str | None = None
    customer_reference_number: str | None = None


@dataclass(frozen=True)
class PrivateManager:
    """Section A.2 — the Private Financial Manager (Linda)."""
    managed_person_id: int
    surname: str
    given_name: str
    id: int | None = None
    relationship: str | None = None
    address_line1: str | None = None
    address_line2: str | None = None
    postcode: str | None = None
    home_phone: str | None = None
    mobile: str | None = None
    email: str | None = None
    appointment_type: str | None = None      # 'sole'|'jointly'|'jointly_severally'
    remuneration_order_date: str | None = None


@dataclass(frozen=True)
class SignificantPerson:
    """Section A.3 — significant people to consult; also gift recipients."""
    managed_person_id: int
    surname: str
    given_name: str
    id: int | None = None
    relationship: str | None = None
    address_line1: str | None = None
    address_line2: str | None = None
    postcode: str | None = None
    home_phone: str | None = None
    mobile: str | None = None
    email: str | None = None
    consultation_status: str = "active"      # 'active'|'estranged'|'deceased'
    notes: str | None = None


@dataclass(frozen=True)
class Account:
    """Section B.1 — bank/credit-union account."""
    managed_person_id: int
    institution: str
    account_number: str
    id: int | None = None
    bsb: str | None = None
    account_type: str | None = None
    role_label: str | None = None            # 'living'|'spending'|'savings'|'other'
    ownership: str = "sole"
    inception_date: str | None = None
    current_balance: float | None = None
    balance_as_of_date: str | None = None
    notes: str | None = None


@dataclass(frozen=True)
class RealEstate:
    """Section B.2."""
    managed_person_id: int
    address: str
    id: int | None = None
    postcode: str | None = None
    ownership: str | None = None
    occupancy: str | None = None
    value: float | None = None
    valuation_date: str | None = None


@dataclass(frozen=True)
class Investment:
    """Section B.3."""
    managed_person_id: int
    id: int | None = None
    type: str | None = None
    description: str | None = None
    ownership: str | None = None
    units: float | None = None
    amount: float | None = None
    last_review_date: str | None = None


@dataclass(frozen=True)
class MotorVehicle:
    """Section B.4."""
    managed_person_id: int
    id: int | None = None
    type: str | None = None
    model: str | None = None
    year: int | None = None
    ownership: str | None = None
    value: float | None = None


@dataclass(frozen=True)
class AccommodationBond:
    """Section B.5."""
    managed_person_id: int
    id: int | None = None
    facility_name: str | None = None
    facility_address: str | None = None
    date_of_entry: str | None = None
    paid_unpaid: str | None = None           # 'paid'|'unpaid'
    amount: float | None = None


@dataclass(frozen=True)
class DebtLiability:
    """Section C."""
    managed_person_id: int
    id: int | None = None
    lender: str | None = None
    type: str | None = None
    term: str | None = None
    amount: float | None = None
