# Plan: S3 — Estate Inventory UI (Section B + C)

## Summary
Add `src/views/inventory.py` exposing six asset/liability classes that drive the
NSWTG Plan Sections B (estate inventory) and C (debts). Extend
`src/db/queries_estate.py` with the missing `update_*` and `get_*` helpers
following the exact pattern S2 established. Wire the new view into the
sidebar between **Identity** and **Upload**.

## User Story
As Linda the Private Financial Manager,
I want to edit Ron's accounts, real estate, vehicles, investments,
accommodation bonds and debts inside the dashboard,
so that Section B + C of the Plan are populated from the same source-of-truth
the audit log will eventually wrap.

## Problem → Solution
- **Current:** S1 created the tables and `insert_* / list_*` query helpers.
  S2 added `update_*` + `get_*` only for managed_persons, private_managers,
  significant_people. There is no UI for Section B + C; the data lives only
  in `scripts/seed.py`.
- **Desired:** Linda can view all six inventory classes, edit any row, add
  new rows for the manual classes (real_estate / investments / motor_vehicles
  / accommodation_bonds / debts_liabilities). Accounts are read-only on the
  primary identity fields (institution, account_number, bsb) since those come
  from parsed PDFs; the bookkeeping fields (role_label, ownership,
  inception_date, current_balance, balance_as_of_date, notes) are editable.

## Metadata
- **Complexity:** Medium
- **Source PRD:** `docs/DASHBOARD_REVAMP_v3.md` §2 Phase 1 S3
- **PRD Phase:** S3 — Estate inventory
- **Estimated Files:** 4 modified + 1 new view + 1 new test module
- **Dependencies:** S1 (tables exist), S2 (CRUD pattern, replace-pattern in view)

---

## Mandatory Reading

| Priority | File | Lines | Why |
|---|---|---|---|
| P0 | `src/db/queries_estate.py` | 1-380 | Pattern for `_update`, `_row_to_dto`, `_insert`. Note SP-UPDATE-FIELDS lesson at `_update` comment near line 64. |
| P0 | `src/views/identity.py` | 1-100, 240-330 | Tabs pattern, data_editor + replace() pattern, add-form pattern. **The `dataclasses.replace(original, ...)` pattern is now a hard rule — do not construct full DTOs from data_editor rows.** |
| P0 | `src/models/estate.py` | 1-180 | DTOs for Account / RealEstate / Investment / MotorVehicle / AccommodationBond / DebtLiability. All frozen dataclasses. |
| P1 | `tests/test_estate_queries_updates.py` | 1-310 | Test conventions, AAA structure, _conn fixture, _seed_ron helper, **the SP regression test at `test_replace_pattern_preserves_hidden_address_fields`** |
| P1 | `src/db/schema/002_estate_tables.sql` | all | Column types, NOT NULL constraints, role_label CHECK constraint on accounts |
| P1 | `src/app.py` | 1-103 | VIEW_OPTIONS list, routing pattern — insert "Inventory" between "Identity" and "Upload" |
| P2 | `scripts/seed.py` | all | Reference for how accounts get seeded (institution, account_number, bsb) |
| P2 | `tests/test_estate_queries.py` | all | The original (S1) test patterns for insert/list of Section B/C classes |

---

## Patterns to Mirror

### NAMING & FILE LAYOUT
// SOURCE: src/views/identity.py:1-40
```python
"""Inventory view — Sections B (estate) + C (debts) of the NSWTG Plan."""

from __future__ import annotations

from dataclasses import replace

import pandas as pd
import streamlit as st

from src.db.database import get_connection, init_db
from src.db.queries_estate import (
    bootstrap_managed_person_if_empty,
    list_accounts, update_account, get_account,
    list_real_estate, insert_real_estate, update_real_estate, get_real_estate,
    # ... etc
)
from src.models.estate import (
    Account, RealEstate, Investment, MotorVehicle,
    AccommodationBond, DebtLiability,
)
```

### UPDATE HELPER
// SOURCE: src/db/queries_estate.py:107-114, 162-166, 187-193
Mirror exactly for each new class — full DTO, `data.pop("id")`, delegate to
`_update`. For `Account` only, also pop `account_number`, `bsb`, `institution`
from the update payload so the API can't accidentally null out identity fields.

### GET HELPER
// SOURCE: src/db/queries_estate.py:117-123, 196-205
Mirror exactly. Returns `Optional[DTO]`.

### VIEW TAB PATTERN
// SOURCE: src/views/identity.py:230-325 (_render_significant_people_tab)
```python
edited = st.data_editor(df, column_config={...}, num_rows="fixed", key="...")
if st.button("Save Changes", type="primary"):
    for _, row in edited.iterrows():
        item_id = int(row["id"])
        original = get_X(conn, item_id)
        if original is None:
            continue
        updated = replace(original, field_a=str(row["A"]), field_b=...)
        if updated != original:
            update_X(conn, item_id, updated)
            changes += 1
```

### REGRESSION TEST PATTERN
// SOURCE: tests/test_estate_queries_updates.py:test_replace_pattern_preserves_hidden_address_fields
For each new class with fields that the data_editor will hide, add an
analogous regression test that proves `dataclasses.replace(original, ...)`
preserves those fields end-to-end.

---

## Files to Change

| File | Action | Justification |
|---|---|---|
| `src/db/queries_estate.py` | UPDATE | Add 6 `update_*` + 6 `get_*` helpers (12 new functions). Account update must reject identity-field mutation. |
| `src/views/inventory.py` | CREATE | Six tabs (Accounts, Real Estate, Investments, Motor Vehicles, Accommodation Bonds, Debts). Each follows the SP-tab pattern from S2. |
| `src/app.py` | UPDATE | Insert `"Inventory"` into `VIEW_OPTIONS` between `"Identity"` and `"Upload"`. Add routing branch. |
| `tests/test_estate_queries_inventory.py` | CREATE | ~24 tests: 2 per class (round-trip + replace-preserves-hidden-fields). Plus 4 account-specific tests (institution/account_number/bsb immutability). |
| `CLAUDE.md` | UPDATE | Add `src/views/inventory.py` to Key Files. |

## NOT Building

- audit_log wraps (deferred to S2.5 + S8)
- Forecast engine integration (S4)
- Inception-date auto-detection (S5+ via `inception_detector` service)
- Auto-population of `current_balance` from latest parsed transactions (planned for S4/S5 — for S3, this field is a manually-entered "balance as of date" snapshot)
- Multi-managed-person UI (out of scope for v3 per architectural call §6)
- Delete operations on inventory rows (use status / soft-delete patterns later if needed; for S3, no row deletion in the UI)

---

## Step-by-Step Tasks

### Task 1: Extend `src/db/queries_estate.py`

- **ACTION:** Add 12 functions following S2 pattern.
- **IMPLEMENT:**
  - `update_account(conn, acc_id, acc)` — assert that any caller cannot mutate
    `institution`, `account_number`, `bsb` (these come from parsed PDFs and are
    evidence-grade). Pop them from the update payload before delegating to
    `_update`. Document this in the docstring.
  - `get_account(conn, acc_id) -> Account | None`
  - `update_real_estate(conn, re_id, re_)` — full DTO, pop id, delegate.
  - `get_real_estate(conn, re_id) -> RealEstate | None`
  - Same for `investment`, `motor_vehicle`, `accommodation_bond`,
    `debt_liability` (6 update + 6 get total).
- **MIRROR:** `update_significant_person` (queries_estate.py:187-193) + the
  `int()` conversion pattern from `update_managed_person` (queries_estate.py:107-114).
- **GOTCHA 1:** `Account.account_number` has a UNIQUE constraint in SQL — even
  popping it from the payload, never allow update via the API.
- **GOTCHA 2:** For `update_*`, `updated_at` is a SQL literal in `_update`; do
  not pass it in the DTO.
- **VALIDATE:** `python3 -m pytest tests/test_estate_queries_inventory.py -v` — all new tests pass.

### Task 2: Write `tests/test_estate_queries_inventory.py`

- **ACTION:** 24+ tests covering the new helpers.
- **IMPLEMENT:** For each of the 6 classes:
  1. `test_round_trip_updates_<class>` — insert, update via fresh DTO, assert
     fields persisted.
  2. `test_replace_pattern_preserves_hidden_fields_<class>` — insert with all
     fields populated, fetch, `replace(original, field_a="new")`, update,
     refetch, assert NON-touched fields survived. This is the SP-UPDATE-FIELDS
     regression pattern propagated to Section B/C.
  3. (Accounts only) `test_update_account_cannot_change_account_number` —
     fetch, replace with new account_number, update, refetch, assert
     account_number is unchanged.
  4. (Accounts only) `test_update_account_cannot_change_institution_or_bsb` —
     analogous.
- **MIRROR:** `tests/test_estate_queries_updates.py:test_replace_pattern_preserves_hidden_address_fields`
- **GOTCHA:** Use `_conn(tmp_path)` and `_seed_ron(conn)` helpers — define them
  at module top, mirroring the S2 test module.
- **VALIDATE:** `python3 -m pytest tests/test_estate_queries_inventory.py -v` — all pass.

### Task 3: Create `src/views/inventory.py`

- **ACTION:** Streamlit view with six tabs.
- **IMPLEMENT:**
  - `render_inventory_view()` entry point — bootstrap managed_person id like
    identity.py does, then `st.tabs(["Accounts", "Real Estate",
    "Investments", "Motor Vehicles", "Accommodation Bonds", "Debts"])`.
  - `_render_accounts_tab(conn, mp_id)` — data_editor with `institution`,
    `account_number`, `bsb` columns marked `disabled=True` in column_config.
    Editable: `role_label` (SelectboxColumn: living/spending/savings/other),
    `ownership` (Selectbox: sole/joint), `inception_date`, `current_balance`
    (NumberColumn), `balance_as_of_date`, `notes`. Save uses `replace`.
  - `_render_real_estate_tab(conn, mp_id)` — data_editor + add form.
    `num_rows="dynamic"` is acceptable here OR keep `"fixed"` with a separate
    add form (mirror SP tab). Pick one and be consistent.
  - Mirror pattern for investments, motor vehicles, accommodation bonds, debts.
  - Each editable field uses `dataclasses.replace(original, ...)` — never
    construct a fresh DTO from row values.
- **MIRROR:** `src/views/identity.py:_render_significant_people_tab` (lines
  230-325) for the data_editor + Save pattern.
- **IMPORTS:** `from dataclasses import replace`, `import pandas as pd`,
  `import streamlit as st`, plus all new query helpers and DTOs.
- **GOTCHA 1:** `current_balance` is `float | None` — coerce empty strings to
  None before passing to `replace()`.
- **GOTCHA 2:** Dates are stored as TEXT (`YYYY-MM-DD`). No enforcement — but
  if you want, add `st.column_config.DateColumn` with `format="YYYY-MM-DD"`.
- **GOTCHA 3:** The seed populates 3 accounts. Don't let the tab render in a
  way that allows deleting a seeded row — `num_rows="fixed"` for accounts.
- **VALIDATE:** Manual: `streamlit run src/app.py`, log in, click "Inventory",
  verify each tab renders, edit a value, save, verify persistence.

### Task 4: Wire into `src/app.py`

- **ACTION:** Add Inventory to nav.
- **IMPLEMENT:** Insert `"Inventory"` into `VIEW_OPTIONS` between `"Identity"`
  and `"Upload"`. Add `elif view == "Inventory": render_inventory_view()`
  branch (or update whatever routing dict is in place).
- **MIRROR:** The Identity entry already wired in S2.
- **GOTCHA:** Don't break the existing nav ordering — Identity must come
  before Inventory; Upload after.
- **VALIDATE:** `streamlit run src/app.py` shows "Inventory" in the sidebar.

### Task 5: Update CLAUDE.md

- **ACTION:** Add `src/views/inventory.py` to Key Files.
- **IMPLEMENT:** One line under `src/views/identity.py — Identity & Contacts ...`:
  `src/views/inventory.py — Estate Inventory (Sections B + C): accounts (read-only identity fields), real estate, vehicles, investments, bonds, debts`.
- **MIRROR:** Existing Key Files style.
- **VALIDATE:** `head CLAUDE.md` shows the new line in the correct group.

---

## Testing Strategy

### New tests in `tests/test_estate_queries_inventory.py`

| Test class | Coverage |
|---|---|
| `TestUpdateAccount` | round-trip, immutable-identity-fields (3 tests) |
| `TestUpdateRealEstate` | round-trip, replace-preserves-hidden-fields |
| `TestUpdateInvestment` | round-trip, replace-preserves-hidden-fields |
| `TestUpdateMotorVehicle` | round-trip, replace-preserves-hidden-fields |
| `TestUpdateAccommodationBond` | round-trip, replace-preserves-hidden-fields |
| `TestUpdateDebtLiability` | round-trip, replace-preserves-hidden-fields |
| `TestGetByIdReturnsNoneForMissing` | one per class (6 tests) |

Expected new test count: ~24.

### Validation Commands

```bash
# Static check
source .venv/bin/activate && python3 -m py_compile src/db/queries_estate.py src/views/inventory.py src/app.py

# Targeted suite
python3 -m pytest tests/test_estate_queries_inventory.py -v

# Full suite (must stay green)
python3 -m pytest tests/ -v
# EXPECT: was 103 passed, after S3 should be ~127 passed (+24), 12 skipped
```

---

## Acceptance Criteria

- [ ] 12 new functions in `src/db/queries_estate.py` (6 update + 6 get).
- [ ] Account update API rejects mutation of `institution`, `account_number`, `bsb`.
- [ ] `src/views/inventory.py` exists with `render_inventory_view()` entry point.
- [ ] All save paths use `dataclasses.replace(original, ...)` — no DTO-from-scratch in any tab.
- [ ] `src/app.py` has "Inventory" between "Identity" and "Upload".
- [ ] `tests/test_estate_queries_inventory.py` has ≥24 tests, all passing.
- [ ] Full suite: 127+ passed, 12 skipped (no regressions).
- [ ] `CLAUDE.md` Key Files updated.

## Risks

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Agent reintroduces SP-UPDATE-FIELDS pattern in any tab | Medium | High | The pattern docs + the regression test from S2 + 6 new regression tests for Section B/C catch this. |
| `Account` identity fields mutated via update API | Low | High (data integrity) | Two specific tests + API-level pop in `update_account`. |
| `num_rows="dynamic"` allows seeded account deletion | Low | Medium | Use `num_rows="fixed"` for Accounts tab. |
| current_balance type coercion (empty string vs None) | Medium | Low (UI nuisance) | Coerce in save handler before `replace()`. |

---

## Optimization Report

> Auto-summarised; standalone for DevFleet dispatch.

### Intent & Scope
- **Detected Intent:** New Feature — Estate Inventory UI + supporting query helpers
- **Scope Level:** MEDIUM (3-10 files, ~500 lines)
- **Model Recommendation:** Sonnet for the agent (codebase pattern propagation, no novel architecture)

### Missing Context — none. Plan is self-contained.

### Optimized Mission Brief (paste into DevFleet `detailed_prompt`)

```
S3 — Build Estate Inventory UI (Section B + C of NSWTG Plan) on the FinMg repo
at /Users/moofasa/Finmg (currently on main at 902f95c with 103 tests passing).

DELIVERABLES:
1) Extend src/db/queries_estate.py with 12 new functions following the EXACT
   pattern of update_significant_person + get_significant_person:
     update_account / get_account
     update_real_estate / get_real_estate
     update_investment / get_investment
     update_motor_vehicle / get_motor_vehicle
     update_accommodation_bond / get_accommodation_bond
     update_debt_liability / get_debt_liability
   update_account MUST pop institution, account_number, bsb from the update
   payload — these come from parsed PDFs and are evidence-grade.
2) Create src/views/inventory.py with render_inventory_view() entry point and
   six st.tabs() for the six asset/liability classes. ALL save paths must use
   dataclasses.replace(original, ...) — never construct DTOs from data_editor
   row values. This pattern is enforced because of the SP-UPDATE-FIELDS bug
   (commit 902f95c) — see tests/test_estate_queries_updates.py:test_replace_pattern_preserves_hidden_address_fields.
3) Wire "Inventory" into src/app.py VIEW_OPTIONS between "Identity" and
   "Upload".
4) Write tests/test_estate_queries_inventory.py with ≥24 tests including:
   - round-trip + replace-preserves-hidden-fields for each of the 6 classes
   - account-identity-immutability tests (3 tests for institution / account_number / bsb)
   - get_*_returns_none_for_missing tests (6 tests)
5) Update CLAUDE.md Key Files to mention src/views/inventory.py.

ACCEPTANCE: pytest tests/ → 127+ passed, 12 skipped. py_compile clean on all
edited Python files.

NON-NEGOTIABLE PATTERNS (codebase-enforced):
- ALL frozen dataclass DTOs from src/models/estate.py
- ALL updates via dataclasses.replace(original, **changes), then `if updated
  != original: update_*(...)` — DO NOT construct fresh DTOs from data_editor
  rows; that bug already cost one fix cycle.
- ALL tests follow AAA structure (Arrange / Act / Assert), use _conn(tmp_path)
  fixture and _seed_ron(conn) helper, mirror tests/test_estate_queries_updates.py.

OUT OF SCOPE: audit_log wraps (S2.5), forecast integration (S4), inception
detection (S5+), auto-populating current_balance from transactions (S4/S5),
row deletion in the UI, multi-managed-person UI.

REFERENCES: plan file at .claude/PRPs/plans/s3-estate-inventory-ui.plan.md
contains full task breakdown, gotchas, and mirror patterns.

After implementing, run `python3 -m pytest tests/` and report the count.
```
