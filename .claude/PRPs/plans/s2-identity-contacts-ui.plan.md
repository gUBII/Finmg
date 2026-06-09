# Plan: S2 — Identity & Contacts UI

## Summary

Build the first NCAT-editable view of the FinMg v3 dashboard. A new
`src/views/identity.py` lets Linda edit Ron's identity (Section A.1), her
own private-manager record (Section A.2), and the list of significant
people who must be consulted on financial decisions (Section A.3 + gift
recipients). All three back onto the schema laid down in S1
(`managed_persons`, `private_managers`, `significant_people`) via
`queries_estate.py`.

## User Story

As Linda (Private Financial Manager), I want to edit Ron's identity,
my own record, and the significant-people list inside FinMg, so that
Section A of the NSWTG Private Manager's Plan can be auto-populated and
kept current without re-keying anything by hand.

## Problem → Solution

**Current state (post-S1):** The schema and seed exist but the only way
to edit identity data is via SQL or `scripts/seed.py`. Linda can't
self-service.

**Desired state:** Linda opens the **Identity** view in the sidebar, sees
Ron + herself + 15 significant people pre-populated from S1's seed, and
can fix typos, fill missing fields (FMO date, Will status, NDIS flags),
and add or retire significant people.

## Metadata
- **Complexity**: Medium
- **Source PRD**: `docs/DASHBOARD_REVAMP_v3.md` (§2 sprint S2; §3 schema; §4 view layout; §8 build order)
- **PRD Phase**: S2 — Identity & contacts
- **Estimated Files**: 5 (1 new view, 1 query module extension, 1 model helper, 1 view-wiring, 1 test file)

---

## UX Design

### Before

```
┌─────────────────────────────────────────────────────────────────┐
│  Sidebar:  Dashboard | Upload | Transactions | Export           │
│                                                                  │
│  No way to view or edit who Ron is, who Linda is, or who         │
│  significant people are. Data exists only in SQLite, only        │
│  editable via scripts/seed.py or raw SQL.                        │
└─────────────────────────────────────────────────────────────────┘
```

### After

```
┌─────────────────────────────────────────────────────────────────┐
│  Sidebar:  Dashboard | Upload | Transactions | Identity | Export│
│                                                                  │
│  Identity view — three tabs:                                     │
│                                                                  │
│  ┌─ Managed Person ─┬─ Private Manager ─┬─ Significant People ─┐│
│  │                                                              ││
│  │ [Managed Person tab]                                         ││
│  │ ┌────────────────────────────────────────────────────────┐  ││
│  │ │ Surname        [ GENTILI                            ]  │  ││
│  │ │ Given names    [ Renato                             ]  │  ││
│  │ │ DOB            [ 1955-01-01                         ]  │  ││
│  │ │ Address line 1 [ 136 MADELINE ST                    ]  │  ││
│  │ │ Address line 2 [ BELFIELD NSW                       ]  │  ││
│  │ │ Postcode       [ 2191                               ]  │  ││
│  │ │ ☐ Interpreter required   Language [           ]        │  ││
│  │ │ Disabilities   ☒ Physical  ☒ Brain injury  ☐ Stroke   │  ││
│  │ │ Will           ( ) Yes  ( ) No  (•) Unsure             │  ││
│  │ │ FMO date       [ 2024-XX-XX  ]  Authority [ NCAT  ]   │  ││
│  │ │ D&A reference  [                                    ]  │  ││
│  │ │ CRN            [                                    ]  │  ││
│  │ │                          [ Save Managed Person ]       │  ││
│  │ └────────────────────────────────────────────────────────┘  ││
│  │                                                              ││
│  │ Last saved: 2026-06-08 09:48 UTC                             ││
│  └──────────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────┘
```

The Private Manager tab follows the same form shape. The Significant
People tab is an editable table (`st.data_editor`) with row
add/remove + a "Save Changes" button.

### Interaction Changes

| Touchpoint | Before | After | Notes |
|---|---|---|---|
| Edit Ron's surname | `sqlite3` / `seed.py` | Identity → Managed Person → form field | Persists to `managed_persons` |
| Add a new significant person | None | Identity → Significant People → add row | Persists to `significant_people` |
| Retire a deceased person | None | Identity → Significant People → set status "deceased" | Soft-delete; row stays in DB |
| Read Ron's DOB | Raw SQL | Identity → Managed Person → DOB field | Plain text input ISO `YYYY-MM-DD` |
| Mark Will status | Not represented | Identity → Managed Person → radio | Stored as `'yes'|'no'|'unsure'` |

---

## Mandatory Reading

| Priority | File | Lines | Why |
|---|---|---|---|
| P0 (critical) | `src/views/transactions.py` | 1–137 | The closest analog: open conn → render filters/widgets → `st.data_editor` → "Save Changes" button → loop through edits → call query helper → `st.success` + `st.rerun`. Mirror this shape for the Significant People tab. |
| P0 (critical) | `src/app.py` | 1–101 | Wiring pattern. New view must be (a) imported, (b) added to `VIEW_OPTIONS`, (c) added to `view_map`. |
| P0 (critical) | `src/db/queries_estate.py` | 1–268 | The query layer we extend. Existing helpers do `INSERT` + `SELECT` only — we must add `update_*` and `update_significant_person_by_id`. |
| P0 (critical) | `src/models/estate.py` | 1–138 | All three dataclasses we render forms for: `ManagedPerson`, `PrivateManager`, `SignificantPerson`. Frozen — use `dataclasses.replace` for edits. |
| P1 (important) | `src/views/upload.py` | 95–212 | Same render-view pattern with widget groupings + `st.success` after action. Useful for the form-with-button shape (Managed Person, Private Manager tabs). |
| P1 (important) | `tests/test_estate_queries.py` | 1–end | Test-style template. New `tests/test_estate_queries_updates.py` should mirror this AAA / `_conn(tmp_path)` style. |
| P1 (important) | `tests/test_seed.py` | 1–66 | Demonstrates importing from `scripts.seed` + using `init_db(conn)` + assertion style on listed DTOs. |
| P2 (reference) | `src/views/dashboard.py` | 1–60 | Existing `_short_month` + columnar layout idioms. Identity view is much simpler but uses the same `st.set_page_config` envelope established by `app.py`. |
| P2 (reference) | `docs/DASHBOARD_REVAMP_v3.md` | §3, §4, §6 | Schema column list + view-table mapping + architectural calls (Streamlit stays, single-user, audit-log immutability via service layer — but no service layer in S2 yet). |
| P2 (reference) | `data/reference_docs/02_PFM_first_submission_template.md` | search for "Section A" | Authoritative field list for what Section A actually demands — defines which form fields are mandatory for NCAT acceptance. |

## External Documentation

| Topic | Source | Key Takeaway |
|---|---|---|
| Streamlit forms vs raw widgets | Streamlit docs `st.form` | `st.form(...)` batches widget state so changes don't trigger a rerun until the submit button is pressed. Use this for Managed Person + Private Manager tabs to avoid flicker. |
| Streamlit tabs API | Streamlit docs `st.tabs` | `tab1, tab2, tab3 = st.tabs([...])` returns context managers — render each form inside `with tab1:` etc. |
| `st.data_editor` add/delete rows | Streamlit docs `st.data_editor(num_rows="dynamic")` | Use `num_rows="dynamic"` to let Linda add/remove significant people inline. The return value contains the edited dataframe; diff against original to compute inserts/updates. |
| Streamlit version pin | `requirements.txt` and live install | We are on Streamlit **1.58.0** — all the above APIs exist (>= 1.23 for `st.data_editor`, >= 1.30 for `num_rows="dynamic"`). |

> No truly external library research needed — Streamlit, sqlite3, dataclasses are all already in use and well-understood internally.

---

## Patterns to Mirror

### NAMING_CONVENTION
```python
# SOURCE: src/views/transactions.py:19
def render_transactions_view() -> None:
    """Render a filterable, editable transactions table backed by SQLite."""
    st.title("Transactions")
```
Every view module exports exactly one `render_<name>_view()` function returning `None`. The new view exports `render_identity_view`.

### DB_OPEN_CLOSE_PATTERN
```python
# SOURCE: src/views/transactions.py:23-24, 136
conn = get_connection()
init_db(conn)
...
conn.close()
```
Always open at the top of the render function, always close at the bottom. Multiple `return` paths must each call `conn.close()` before returning — see `src/views/transactions.py:32-34, 86-87`. Use `try/finally` if logic gets branchy.

### FORM_SAVE_PATTERN
```python
# SOURCE: src/views/transactions.py:120-134
if st.button("Save Changes", type="primary", use_container_width=True):
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
```
Primary button → diff edited vs original → call typed query helper → toast result → `st.rerun()`. Mirror this for the Significant People tab. For the two single-record tabs, the diff is trivial (whole DTO) so just call the update helper directly inside the button block.

### SIDEBAR_WIRING_PATTERN
```python
# SOURCE: src/app.py:17-23, 91-97
from src.views.transactions import render_transactions_view
...
VIEW_OPTIONS = ["Dashboard", "Upload", "Transactions", "Export"]
...
view_map = {
    "Dashboard": render_dashboard_view,
    "Upload": render_upload_view,
    "Transactions": render_transactions_view,
    "Export": render_export_view,
}
view_map[selected_view]()
```
Three places to change in `src/app.py`. Per `docs/DASHBOARD_REVAMP_v3.md` §4, the new view sits in the **Submission preparation** group conceptually — but the sidebar doesn't have visual groupings yet, so just add "Identity" between "Upload" and "Transactions" (closer to its data dependency on `accounts` plus future S3/S4 views that will sit next to it).

### QUERY_HELPER_PATTERN
```python
# SOURCE: src/db/queries_estate.py:35-50
def _insert(conn: sqlite3.Connection, table: str, dto, exclude: set[str] | None = None) -> int:
    """Insert dataclass `dto` into `table`, returning the new row id."""
    exclude = (exclude or set()) | {"id"}
    data = {k: v for k, v in asdict(dto).items() if k not in exclude}
    cols = ", ".join(data.keys())
    placeholders = ", ".join("?" for _ in data)
    cur = conn.execute(
        f"INSERT INTO {table} ({cols}) VALUES ({placeholders})",
        tuple(data.values()),
    )
    conn.commit()
    return cur.lastrowid
```
Add an `_update(conn, table, dto, id_field='id')` helper that mirrors this shape — column list from `asdict`, parameter list from `dict.values()`, `WHERE id = ?` at the end. Reuse it from `update_managed_person`, `update_private_manager`, `update_significant_person`. Existing helpers commit at the end — preserve that.

### TEST_STRUCTURE
```python
# SOURCE: tests/test_estate_queries.py:46-50
def _conn(tmp_path):
    conn = get_connection(tmp_path / "test.db")
    init_db(conn)
    return conn

class TestManagedPersons:
    def test_round_trip(self, tmp_path):
        conn = _conn(tmp_path)
        mp_id = _seed_ron(conn)
        ...
        conn.close()
```
Test fixtures: `_conn(tmp_path)` + helper `_seed_ron(conn)`. One `class TestXxx:` per query area. AAA pattern. Always `conn.close()` at the end of each test. No `pytest.fixture` decorators — plain helper functions. Mirror for the new test file.

### FROZEN_DATACLASS_EDIT_PATTERN
```python
# SOURCE: scripts/seed.py:142-146
from dataclasses import replace
linda = replace(LINDA, managed_person_id=managed_person_id)
return insert_private_manager(conn, linda)
```
Models are frozen — never mutate. Always `dataclasses.replace(existing_dto, field=new_value)` to construct the updated DTO before passing to the update helper.

---

## Files to Change

| File | Action | Justification |
|---|---|---|
| `src/views/identity.py` | CREATE | The new view. Three tabs: Managed Person, Private Manager, Significant People. |
| `src/db/queries_estate.py` | UPDATE | Add `_update` helper + `update_managed_person`, `update_private_manager`, `update_significant_person`, `get_significant_person`. Also `bootstrap_if_empty()` helper that creates a placeholder `managed_persons` row if none exists yet, so the view doesn't error on a fresh DB. |
| `src/app.py` | UPDATE | Add identity import, append "Identity" to `VIEW_OPTIONS`, add to `view_map`. |
| `tests/test_estate_queries_updates.py` | CREATE | Round-trip update tests + idempotency check (updating to same value is a no-op). |
| `CLAUDE.md` | UPDATE | Add `src/views/identity.py` to "Key Files" list (the v3 schema section already exists from S1). |

## NOT Building

- **Audit-log integration.** Updates in S2 do NOT write to `audit_log`. That's deferred to the `audit_logger` service in S2.5 / S3. Linda can still see what changed via SQLite history if needed; full audit is theatre until the service layer lands.
- **PDF upload of FMO / D&A documents.** Linda will type the FMO date / authority / D&A reference as strings. Document upload + storage under `data/attachments/` is S5 (Submission Generator) scope.
- **Multi-managed-person support.** UI assumes exactly one `managed_persons` row. The schema supports N rows; the UI does not. Per `docs/DASHBOARD_REVAMP_v3.md` §6 "Multi-user out of scope".
- **NDIS amount or Centrelink dollars.** Stored elsewhere (forecast tables, S4). S2 only touches identity demographics and the consultation-relationship list.
- **Real estate / vehicles / debts.** Those are Section B/C — owned by S3 (Estate Inventory).
- **Validation that the user typed a real address / phone / email format.** No regex gates. Linda's a trusted operator; bad data is correctable in the same form.
- **Soft-delete UI for managed_persons or private_managers.** Only `significant_people` has a `consultation_status` for soft-deletion. Ron and Linda records are never deleted via the UI.

---

## Step-by-Step Tasks

### Task 1: Extend `queries_estate.py` with update helpers
- **ACTION**: Add a generic `_update(conn, table, dto)` helper plus typed wrappers for the three identity DTOs.
- **IMPLEMENT**:
  ```python
  def _update(conn: sqlite3.Connection, table: str, dto, dto_id: int,
              exclude: set[str] | None = None) -> None:
      exclude = (exclude or set()) | {"id"}
      data = {k: v for k, v in asdict(dto).items() if k not in exclude}
      assignments = ", ".join(f"{k} = ?" for k in data.keys())
      conn.execute(
          f"UPDATE {table} SET {assignments}, updated_at = datetime('now') WHERE id = ?",
          (*data.values(), dto_id),
      )
      conn.commit()

  def update_managed_person(conn, mp: ManagedPerson) -> None:
      # interpreter_required is bool in DTO, int in SQLite
      data = asdict(mp)
      mp_id = data.pop("id")
      data["interpreter_required"] = int(data["interpreter_required"])
      assignments = ", ".join(f"{k} = ?" for k in data.keys())
      conn.execute(
          f"UPDATE managed_persons SET {assignments}, "
          f"updated_at = datetime('now') WHERE id = ?",
          (*data.values(), mp_id),
      )
      conn.commit()

  def update_private_manager(conn, pm: PrivateManager) -> None:
      _update(conn, "private_managers", pm, pm.id)

  def update_significant_person(conn, sp: SignificantPerson) -> None:
      _update(conn, "significant_people", sp, sp.id)

  def get_significant_person(conn, sp_id: int) -> SignificantPerson | None:
      row = conn.execute(
          "SELECT * FROM significant_people WHERE id = ?", (sp_id,)
      ).fetchone()
      return _row_to_dto(row, SignificantPerson) if row else None

  def bootstrap_managed_person_if_empty(conn) -> int:
      """Return managed_person_id, creating an empty placeholder if needed."""
      existing = list_managed_persons(conn)
      if existing:
          return existing[0].id
      placeholder = ManagedPerson(surname="", given_names="")
      return insert_managed_person(conn, placeholder)
  ```
- **MIRROR**: QUERY_HELPER_PATTERN. `update_managed_person` is the only one that can't use `_update` because of the `interpreter_required` bool → int conversion — keep its body explicit, mirror `insert_managed_person` lines 56-71.
- **IMPORTS**: `from dataclasses import asdict` (already present); models already imported.
- **GOTCHA**:
  - The schema's `updated_at` column has a default but we must update it explicitly on UPDATE (SQLite doesn't fire DEFAULT on UPDATE). Always add `updated_at = datetime('now')` to the assignment list.
  - `interpreter_required` is `bool` in the DTO, `INTEGER` in SQLite. The `insert_managed_person` helper already handles this conversion (lines 56-60); the update helper must too.
  - `id` on a frozen DTO can be `None` if the DTO was hand-constructed — update helpers must reject `None` id with a clear `ValueError` rather than write `WHERE id = NULL`. Add `if dto.id is None: raise ValueError(...)` at the top of each typed wrapper.
- **VALIDATE**:
  - `python -m pytest tests/test_estate_queries.py -v` still passes
  - `python -c "from src.db.queries_estate import update_managed_person; print('ok')"` imports cleanly

### Task 2: Write `tests/test_estate_queries_updates.py`
- **ACTION**: TDD coverage of the new update helpers + `bootstrap_managed_person_if_empty`.
- **IMPLEMENT**: Five test classes:
  ```python
  class TestUpdateManagedPerson:
      def test_round_trip_updates_persisted_fields(self, tmp_path): ...
      def test_interpreter_required_round_trips_after_update(self, tmp_path): ...
      def test_updated_at_advances(self, tmp_path): ...
      def test_update_with_none_id_raises(self, tmp_path): ...

  class TestUpdatePrivateManager:
      def test_round_trip(self, tmp_path): ...

  class TestUpdateSignificantPerson:
      def test_round_trip(self, tmp_path): ...
      def test_soft_delete_via_status(self, tmp_path): ...  # set to 'deceased'

  class TestBootstrapManagedPersonIfEmpty:
      def test_creates_placeholder_when_empty(self, tmp_path): ...
      def test_returns_existing_id_when_present(self, tmp_path): ...
      def test_idempotent(self, tmp_path): ...
  ```
- **MIRROR**: TEST_STRUCTURE. Reuse the `_conn(tmp_path)` + `_seed_ron(conn)` helpers (copy them in to keep test files self-contained — `tests/test_estate_queries.py` already does this so duplication is local-by-design).
- **IMPORTS**:
  ```python
  from dataclasses import replace
  from src.db.queries_estate import (
      bootstrap_managed_person_if_empty,
      get_managed_person,
      get_significant_person,
      insert_managed_person,
      insert_private_manager,
      insert_significant_person,
      list_significant_people,
      update_managed_person,
      update_private_manager,
      update_significant_person,
  )
  from src.models.estate import ManagedPerson, PrivateManager, SignificantPerson
  ```
- **GOTCHA**: `dataclasses.replace` on a frozen DTO returns a new instance — old reference is unchanged. Tests that assert on the post-update state must `get_managed_person(conn, id)` re-fetch, not check the local Python object.
- **VALIDATE**: `python -m pytest tests/test_estate_queries_updates.py -v` reports 10/10 passing.

### Task 3: Create `src/views/identity.py`
- **ACTION**: Render the three-tab view. Top-level `render_identity_view()` only.
- **IMPLEMENT**: Module skeleton:
  ```python
  """Identity & contacts view — NSWTG Plan Section A."""

  from __future__ import annotations

  from dataclasses import replace

  import pandas as pd
  import streamlit as st

  from src.db.database import get_connection, init_db
  from src.db.queries_estate import (
      bootstrap_managed_person_if_empty,
      get_managed_person,
      insert_private_manager,
      insert_significant_person,
      list_private_managers,
      list_significant_people,
      update_managed_person,
      update_private_manager,
      update_significant_person,
  )
  from src.models.estate import (
      ManagedPerson,
      PrivateManager,
      SignificantPerson,
  )

  DISABILITY_OPTIONS = ["physical", "brain_injury", "stroke", "intellectual",
                         "psychiatric", "dementia", "other"]
  WILL_OPTIONS = ["yes", "no", "unsure"]
  APPOINTMENT_OPTIONS = ["sole", "jointly", "jointly_severally"]
  STATUS_OPTIONS = ["active", "estranged", "deceased"]


  def render_identity_view() -> None:
      st.title("Identity & Contacts")
      st.caption("NSWTG Plan Section A. Edits persist immediately on Save.")

      conn = get_connection()
      init_db(conn)
      mp_id = bootstrap_managed_person_if_empty(conn)

      tab_mp, tab_pm, tab_sp = st.tabs(
          ["Managed Person", "Private Manager", "Significant People"]
      )

      with tab_mp:
          _render_managed_person_form(conn, mp_id)
      with tab_pm:
          _render_private_manager_form(conn, mp_id)
      with tab_sp:
          _render_significant_people_table(conn, mp_id)

      conn.close()


  def _render_managed_person_form(conn, mp_id: int) -> None:
      mp = get_managed_person(conn, mp_id)
      with st.form("mp_form"):
          surname = st.text_input("Surname", value=mp.surname)
          given_names = st.text_input("Given names", value=mp.given_names)
          # ... ALL other fields per ManagedPerson dataclass
          submitted = st.form_submit_button("Save Managed Person", type="primary",
                                            use_container_width=True)
      if submitted:
          # parse disability_flags multiselect → JSON array string
          updated = replace(mp, surname=surname, given_names=given_names, ...)
          update_managed_person(conn, updated)
          st.success("Saved.")
          st.rerun()


  def _render_private_manager_form(conn, mp_id: int) -> None:
      pms = list_private_managers(conn, mp_id)
      pm = pms[0] if pms else None
      with st.form("pm_form"):
          # if pm is None show an empty form + "Create" button
          # else show populated form + "Save" button
          ...
      if submitted:
          if pm is None:
              insert_private_manager(conn, PrivateManager(managed_person_id=mp_id, ...))
          else:
              updated = replace(pm, ...)
              update_private_manager(conn, updated)
          st.success("Saved.")
          st.rerun()


  def _render_significant_people_table(conn, mp_id: int) -> None:
      people = list_significant_people(
          conn, mp_id, include_estranged=True, include_deceased=True
      )
      if people:
          df = pd.DataFrame([{
              "id": p.id, "Surname": p.surname, "Given name": p.given_name,
              "Relationship": p.relationship or "", "Status": p.consultation_status,
              "Mobile": p.mobile or "", "Email": p.email or "",
          } for p in people])
      else:
          df = pd.DataFrame(
              columns=["id", "Surname", "Given name", "Relationship",
                       "Status", "Mobile", "Email"]
          )

      edited = st.data_editor(
          df,
          num_rows="dynamic",
          column_config={
              "id": st.column_config.NumberColumn("id", disabled=True),
              "Status": st.column_config.SelectboxColumn("Status",
                                                         options=STATUS_OPTIONS),
          },
          hide_index=True,
          use_container_width=True,
          key="sp_editor",
      )

      if st.button("Save Changes", type="primary", use_container_width=True):
          # Diff edited vs original; INSERT new rows (id is NaN), UPDATE existing.
          changes = _save_significant_people_diff(conn, mp_id, df, edited)
          if changes:
              st.success(f"Saved {changes} change(s).")
              st.rerun()
          else:
              st.info("No changes to save.")
  ```
- **MIRROR**:
  - Module shape from `src/views/transactions.py:1-19`
  - DB open/close from `src/views/transactions.py:23-24, 136`
  - Diff-edited-vs-original from `src/views/transactions.py:120-134`
  - Form pattern: use `st.form(...)` blocks for the two single-DTO tabs so a stray keystroke doesn't trigger a rerun mid-edit.
- **IMPORTS**: see code skeleton above.
- **GOTCHA**:
  - `st.data_editor(num_rows="dynamic")` returns rows where new rows have `id = NaN` (float). Convert: `pd.isna(row.id)` → INSERT path; otherwise → UPDATE path.
  - `disability_flags` round-trips as a JSON-array string. Convert to/from `list[str]` at the form boundary: `json.dumps(selected)` on save, `json.loads(mp.disability_flags or "[]")` on read.
  - `has_will` is nullable — `st.radio` does not support a null option. Use `st.selectbox` with `options=[None, "yes", "no", "unsure"]` and a format function that renders `None` as "— unset —".
  - The `private_managers` table allows 0..N rows. UI assumes 1. If 0, treat as "create"; if 1, treat as "update"; if 2+, show a warning and operate on the first one only. Multi-PM is explicitly out of scope.
  - When a new significant person is added inline, `relationship` is the most-likely-missing field — Linda may leave it blank. That's fine; the schema allows NULL.
  - `st.rerun()` inside a `with st.form(...)` block is safe but `st.success` inside an `if submitted:` block AFTER the form context still shows because Streamlit re-orders messages. The pattern is: `if submitted: do_save(); st.success(...); st.rerun()` — exactly as in `src/views/transactions.py:131-132`.
- **VALIDATE**:
  - File-level: `python -c "from src.views.identity import render_identity_view; print('ok')"`
  - Behavior: start Streamlit, log in, click Identity tab, every form widget renders without exception, save round-trips through SQLite (verify via `sqlite3 data/finmg.db "SELECT * FROM managed_persons"`).

### Task 4: Wire into `src/app.py`
- **ACTION**: Three small edits to the existing wiring.
- **IMPLEMENT**:
  ```python
  # 1. Add to imports near line 17-21:
  from src.views.identity import render_identity_view

  # 2. Update VIEW_OPTIONS at line 23:
  VIEW_OPTIONS = ["Dashboard", "Upload", "Identity", "Transactions", "Export"]

  # 3. Update view_map at line 91-96:
  view_map = {
      "Dashboard": render_dashboard_view,
      "Upload": render_upload_view,
      "Identity": render_identity_view,
      "Transactions": render_transactions_view,
      "Export": render_export_view,
  }
  ```
- **MIRROR**: SIDEBAR_WIRING_PATTERN.
- **IMPORTS**: see implementation.
- **GOTCHA**: `_init_session_state` sets `current_view = "Dashboard"`. If a logged-in user was previously on "Identity" and reloads, the in-memory `current_view` is gone (sessions are not persisted). Acceptable — no fix needed.
- **VALIDATE**:
  - `python -c "import src.app; print('ok')"`
  - `python -m streamlit run src/app.py --server.headless true --server.port 8765` returns HTTP 200 on `/`
  - Manual: log in → confirm "Identity" appears as a sidebar option → click it → see three tabs render.

### Task 5: Update `CLAUDE.md`
- **ACTION**: Single-line addition to "Key Files" + one schema-section sanity check.
- **IMPLEMENT**: Insert after line 26 (the existing `dashboard.py` entry):
  ```
  - `src/views/identity.py` — Section A editing: managed person, private manager, significant people
  ```
- **MIRROR**: existing bullet style (no leading hyphen change, no formatting change).
- **IMPORTS**: N/A (markdown).
- **GOTCHA**: The "Database Schema" section was already updated in S1 — leave it alone.
- **VALIDATE**: `grep "identity.py" /Users/moofasa/Finmg/CLAUDE.md` returns the new line.

---

## Testing Strategy

### Unit Tests

| Test | Input | Expected Output | Edge Case? |
|---|---|---|---|
| `test_update_managed_person_round_trip` | Updated DTO with new surname | DB row reflects new surname after refetch | No |
| `test_update_managed_person_interpreter_round_trip` | DTO with `interpreter_required=True` | DB stores `1`, refetch returns `True`/`1` | Yes (bool↔int) |
| `test_update_managed_person_updated_at_advances` | Update with same value | `updated_at` strictly later than initial value | Yes (time semantics) |
| `test_update_managed_person_none_id_raises` | `ManagedPerson(id=None, ...)` | `ValueError` | Yes (bad input) |
| `test_update_private_manager_round_trip` | Edited PM with new email | DB row reflects new email | No |
| `test_update_significant_person_round_trip` | Edited SP with new relationship | DB row reflects new relationship | No |
| `test_update_significant_person_soft_delete` | SP set to `consultation_status='deceased'` | `list_significant_people(include_deceased=False)` excludes it; `include_deceased=True` includes it | Yes (filter semantics) |
| `test_bootstrap_creates_placeholder_when_empty` | Fresh DB | One `managed_persons` row exists; returned id == 1 | Yes (empty DB) |
| `test_bootstrap_returns_existing_when_present` | Pre-seeded DB | No new row created; returns existing id | Yes (idempotency) |
| `test_bootstrap_idempotent` | Call twice on empty DB | Same id both calls, exactly one row in DB | Yes (idempotency) |

### Edge Cases Checklist
- [x] Empty DB (no `managed_persons` row) — bootstrap creates placeholder
- [x] Maximum size input — N/A for identity (no large blobs)
- [x] Invalid types — `update_managed_person(id=None)` raises
- [x] Concurrent access — N/A; single-user app per architectural call
- [x] Network failure — N/A; SQLite is local
- [x] Permission denied — N/A; login gate handles auth
- [x] Two private_managers rows when UI expects 1 — view picks `[0]`, surfaces warning toast
- [x] `disability_flags` is `NULL` in DB — view treats as empty list
- [x] `has_will` is `NULL` in DB — view shows "— unset —"

> View-level UI behaviour (form rendering, tab switching) is NOT covered by automated tests — Streamlit testing isn't wired up in this repo and isn't worth bringing in for S2. Manual verification per Task 4's VALIDATE block fills the gap.

---

## Validation Commands

### Static Analysis
```bash
.venv/bin/python -m py_compile src/views/identity.py src/db/queries_estate.py src/app.py
```
EXPECT: Zero output (silent success).

### Unit Tests — New
```bash
.venv/bin/python -m pytest tests/test_estate_queries_updates.py -v
```
EXPECT: 10 tests pass, 0 fail.

### Unit Tests — Existing (regression)
```bash
.venv/bin/python -m pytest tests/ -v
```
EXPECT: 91 passed (81 from S1 + 10 new), 12 skipped (pre-existing PDF-fixture tests).

### Database Schema Validation
```bash
sqlite3 data/finmg.db "SELECT * FROM schema_migrations;"
```
EXPECT: 5 rows (001–005). S2 adds no migrations.

### Live DB Sanity
```bash
.venv/bin/python scripts/seed.py            # idempotent, may re-run safely
sqlite3 data/finmg.db "SELECT id, surname, given_names FROM managed_persons;"
sqlite3 data/finmg.db "SELECT COUNT(*) FROM significant_people;"
```
EXPECT: One Ron row + 15 significant people (seeded). Live row counts unchanged from S1.

### Browser / App Validation
```bash
.venv/bin/python -m streamlit run src/app.py --server.headless true --server.port 8765
# In another shell:
curl -sS -o /dev/null -w "HTTP %{http_code}\n" http://localhost:8765/
```
EXPECT: `HTTP 200`. Kill the server with `lsof -ti:8765 | xargs kill` afterwards.

### Manual Validation
- [ ] Log in with Linda's credentials
- [ ] "Identity" appears in the sidebar between "Upload" and "Transactions"
- [ ] Click Identity → three tabs render: Managed Person | Private Manager | Significant People
- [ ] **Managed Person tab:** Ron's surname pre-populated; change to "GENTILI-TEST" + Save → success toast → reload page → still "GENTILI-TEST"; change back to "GENTILI"
- [ ] **Private Manager tab:** Linda's row pre-populated; mark `remuneration_order_date` blank (it should already be); change `relationship` text + Save → success toast
- [ ] **Significant People tab:** 15 rows visible; edit Sebastian's `Mobile` field + Save → success toast; add a new row "Test Person" → Save → list grows to 16; reload → new row persists; set "Test Person" status to `deceased` + Save → row stays visible with status updated
- [ ] `sqlite3 data/finmg.db "SELECT consultation_status, given_name FROM significant_people WHERE given_name = 'Test Person';"` returns `deceased|Test Person`
- [ ] Cleanup: `sqlite3 data/finmg.db "DELETE FROM significant_people WHERE given_name = 'Test Person';"`

---

## Acceptance Criteria
- [ ] All 5 tasks completed
- [ ] All validation commands pass
- [ ] 10 new unit tests written and passing
- [ ] No type errors (`py_compile` silent on all 3 changed files)
- [ ] Full test suite still 91 passed / 12 skipped
- [ ] Identity view renders all three tabs without exception
- [ ] Round-trip edit on each tab persists to SQLite

## Completion Checklist
- [ ] Code follows discovered patterns (NAMING_CONVENTION, FORM_SAVE_PATTERN, QUERY_HELPER_PATTERN, TEST_STRUCTURE)
- [ ] Error handling matches codebase style (let exceptions propagate; toast user-friendly outcomes only)
- [ ] Logging follows codebase conventions (no `logging` module; use Streamlit toasts)
- [ ] Tests follow the AAA + `_conn(tmp_path)` pattern
- [ ] No hardcoded values (`DISABILITY_OPTIONS`, `WILL_OPTIONS`, etc. live as module constants; no inline string literals in form construction)
- [ ] `CLAUDE.md` Key Files list updated
- [ ] No unnecessary scope additions (no `audit_log` writes, no attachment upload, no Section B/C work)
- [ ] Self-contained — no questions needed during implementation

## Risks

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| `st.form` semantics drift between Streamlit versions | Low | Medium | Pinned to 1.58.0; behaviour stable in this range. No version bump in S2. |
| Linda enters an invalid `has_will` value via form widget | Low | Low | UI uses selectbox with the three valid options + None — typing invalid is impossible from UI. The DB-level CHECK constraint backstops anything sneaking through. |
| `disability_flags` JSON parse error if DB has malformed data | Low | Medium | Wrap `json.loads(...)` in `try/except`; default to empty list on parse failure (don't crash the view). |
| User edits Significant People table while data_editor is being saved by another keystroke | Very Low | Low | Streamlit's `data_editor` debounces — the diff-on-save model means only the submit-button snapshot matters. |
| Adding "Identity" to `VIEW_OPTIONS` resets a logged-in user's `current_view` if they were on "Transactions" but the list reordering moves it | Very Low | Trivial | `_render_sidebar` validates `current_view in VIEW_OPTIONS` and falls back to index 0 (see `src/app.py:46-47`). Safe. |
| Updating `interpreter_required` bool ⇄ int mismatch silently inverts the flag | Medium | High | Dedicated test `test_interpreter_required_round_trips_after_update`. Insert helper already has the conversion; update helper must replicate it. Don't outsource to `_update`. |
| FK cascade deletion of a `managed_persons` row wipes private_managers + significant_people + accounts | Low | High | Not exercised by S2 (no UI delete of managed_persons). Add a `# DO NOT add a delete button for managed_persons` comment in the view to prevent future drift. |
| Tasks 1/2/3 land but Task 4 (app wiring) is forgotten — view exists but unreachable | Medium | High | Validation step "Identity appears in sidebar" is in the manual checklist. CI doesn't catch this. |

## Notes

- The dashboard's `EXPECTED_ACCOUNTS = ["178865319", "178870011", "437669532"]` hardcoded list is technically wrong post-S1 — the source of truth is the `accounts` table now. Don't fix that here; it's drift to track and will be cleaned up as part of S3 (Estate Inventory) when the dashboard learns to read from `accounts`.
- `private_managers` schema allows multiple rows (multi-manager appointments per Trustee Act 1925 §15). We render only the first one in S2. If Linda ever shares the appointment, that's a Change-in-Estate (Appendix A.D) and will be handled in S8.
- The "Mikayla (?) — possibly a cousin" entry in `scripts/seed.py` SIGNIFICANT_PEOPLE is intentionally tentative. The Identity → Significant People tab is where Linda will refine it (set surname, relationship, or delete). No code change to seed needed.
- After S2 lands, the **first NCAT-visible deliverable** the dashboard produces is *editable Section A data*. S3 (estate inventory) is the next big rock.
- This plan deliberately defers `audit_log` integration. Per `docs/DASHBOARD_REVAMP_v3.md` §5, that's the `audit_logger.py` service job. Wedging audit writes into the bare query helpers now would require unpicking them later when the service layer arrives.

---

## Optimization Report

> Auto-generated by the prompt-optimizer gate in /prp-plan. Advisory — does not modify task steps.

### Intent & Scope
- **Detected Intent**: New Feature (Phase 1 view + accompanying query-layer extension)
- **Scope Level**: MEDIUM (5 files, ~600 lines including tests, no new dependencies, no schema migration)
- **Model Recommendation**: Sonnet 4.6 — high reasoning not required; pattern-heavy code generation; Opus is overkill here. Switch to Opus only if a Streamlit `st.data_editor` edge case forces a redesign of the Significant People diff logic.

### Recommended ECC Components

| Type | Component | Purpose |
|------|-----------|---------|
| Command | `/prp-implement` | Execute this plan in a single pass |
| Skill | `python-patterns` | Frozen-dataclass `replace` idiom + Protocol-based query interface |
| Skill | `python-testing` | Pytest + `tmp_path` fixture + AAA structure |
| Skill | `strategic-compact` | Compact between Task 3 (view) and Task 4 (wiring) — clean phase boundary |
| Agent | `tdd-guide` | Enforces test-first on Task 1 → Task 2 ordering |
| Agent | `python-reviewer` | Final pass over `src/views/identity.py` for PEP 8, type hints, immutability |
| Agent | `code-reviewer` | Cross-cutting check on the wiring change in `src/app.py` |

### Missing Context (Advisory)

None critical. The following are minor items that the implementer can resolve from the codebase without external input:

1. **Exact Streamlit `st.selectbox` API for nullable options** — covered by the GOTCHA in Task 3.
2. **Date input widget choice** — Streamlit has both `st.date_input` and `st.text_input`; plan recommends `st.text_input` with ISO format to match the schema's `TEXT` column without timezone fuss. Implementer can swap if they prefer `st.date_input`.
3. **Whether `disability_flags` should be `st.multiselect` or `st.checkbox` per option** — implementer's call; `st.multiselect` is simpler and recommended in Task 3.

### Workflow Recommendation

```
/prp-implement .claude/PRPs/plans/s2-identity-contacts-ui.plan.md
  → Task 1 (queries_estate.py extend)
  → Task 2 (tests/test_estate_queries_updates.py)
  → run pytest — gate on green
  → Task 3 (views/identity.py)
  → Task 4 (app.py wiring)
  → Task 5 (CLAUDE.md)
  → /code-review (focus: views/identity.py + queries_estate.py diff)
  → manual browser validation per Task 4 VALIDATE block
```

### Optimized Mission Brief

> Ready-to-paste as a DevFleet `detailed_prompt` or standalone Claude Code prompt.

```
Build the FinMg v3 Identity & Contacts view (Sprint S2 per
docs/DASHBOARD_REVAMP_v3.md §2). A new src/views/identity.py — three tabs
(Managed Person, Private Manager, Significant People) — lets Linda edit
Section A of the NSWTG Plan via Streamlit forms backed by the schema
delivered in S1.

User story: As Linda (Private Financial Manager), I want to edit Ron's
identity, my own record, and the significant-people list inside FinMg,
so that Section A of the NSWTG Private Manager's Plan can be
auto-populated and kept current without re-keying anything by hand.

Tech stack: Python 3.14, Streamlit 1.58.0, SQLite via sqlite3 stdlib,
pytest, dataclasses, pandas. No new dependencies.

Tasks:
- Task 1: Extend src/db/queries_estate.py — add _update helper +
  update_managed_person (with interpreter_required bool→int conversion),
  update_private_manager, update_significant_person,
  get_significant_person, bootstrap_managed_person_if_empty.
- Task 2: Write tests/test_estate_queries_updates.py — 10 tests across
  TestUpdateManagedPerson, TestUpdatePrivateManager,
  TestUpdateSignificantPerson, TestBootstrapManagedPersonIfEmpty.
- Task 3: Create src/views/identity.py exporting
  render_identity_view() with three tabs as described in the plan.
- Task 4: Wire identity into src/app.py (import, VIEW_OPTIONS, view_map).
- Task 5: Update CLAUDE.md Key Files list with the new view path.

Acceptance:
- All 10 new tests + existing 81 still pass (91 total passing, 12 skipped)
- py_compile clean on all 3 changed Python files
- Streamlit boots; Identity tab is reachable; round-trip edit persists
  to SQLite on each tab
- No new schema migrations; no audit_log writes (deferred to S2.5)
- CLAUDE.md Key Files list reflects new view

Scope boundaries (NOT building):
- audit_log integration (deferred to S2.5 audit_logger service)
- PDF attachment upload (S5)
- multi-managed-person UI (out of scope per §6)
- NDIS / Centrelink dollar amounts (S4 forecast)
- real estate / vehicles / debts (S3 inventory)
- input format validation (Linda is a trusted operator)
- delete UI for managed_persons or private_managers

Mirror these existing patterns exactly:
- src/views/transactions.py:120-134 for save-on-button + st.success +
  st.rerun
- src/db/queries_estate.py:35-50 for INSERT helper shape
- tests/test_estate_queries.py for _conn(tmp_path) + AAA test layout
- src/app.py:17-23, 91-97 for sidebar wiring (3-point change)

Critical gotchas:
- interpreter_required is bool in DTO, int in SQLite — update helper
  must mirror the insert helper's conversion, do NOT delegate to _update.
- disability_flags is a JSON-array string in DB. Round-trip via
  json.loads/json.dumps at the form boundary.
- has_will is nullable; selectbox must include None.
- st.data_editor(num_rows="dynamic") returns NaN ids for new rows —
  distinguish INSERT vs UPDATE via pd.isna(row.id).
- private_managers schema allows N rows; UI assumes 1. Warn-and-use-[0]
  on 2+ rows.
- updated_at is NOT auto-bumped by SQLite on UPDATE — write it explicitly
  via datetime('now') in every UPDATE.
```
