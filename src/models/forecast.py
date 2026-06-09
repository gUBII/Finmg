"""Dataclass DTOs for forecast tables (NSWTG Plan Sections D + E)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ForecastCategory:
    """A row in Section D or E (e.g. 'Groceries', 'Disability Support Pension')."""
    section: str                              # 'D_income'|'D_expenditure'|'E_one_off_receipt'|'E_one_off_expenditure'
    category_name: str
    id: int | None = None
    display_order: int = 0


@dataclass(frozen=True)
class Forecast:
    """Actual vs forecast for one category over one period.

    Linda owns `forecast_value` and may override `actual_value` derived from
    transactions. An override requires a non-empty `override_reason` at the
    service layer.
    """
    managed_person_id: int
    period_start: str
    period_end: str
    category_id: int
    id: int | None = None
    actual_value: float | None = None
    forecast_value: float | None = None
    override_reason: str | None = None
    last_updated_at: str | None = None


@dataclass(frozen=True)
class OneOffEvent:
    """Section E — one-off receipt or expenditure (anticipated or completed)."""
    managed_person_id: int
    event_type: str                           # 'receipt'|'expenditure'
    event_description: str
    status: str                               # 'anticipated'|'proposed'|'completed'
    id: int | None = None
    amount: float | None = None
    date_occurred: str | None = None
    linked_transaction_id: int | None = None
    notes: str | None = None
