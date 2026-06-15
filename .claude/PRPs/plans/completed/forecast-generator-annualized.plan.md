# Plan: Annualized Forecast Generator (Section D)

## Summary
Replace the current "copy trailing actual into forecast" bootstrap with a **forecast generator** that produces a realistic full-year Section D figure for each category: it annualizes partial-window actuals to a 12-month equivalent, applies real-world benchmark overrides (e.g. DSP fortnightly rate, rent), excludes one-off events, and auto-writes the NCAT-required `override_reason` whenever its proposal differs from the raw trailing actual. The generator is a pure service consumed by a new "Generate proposals" action in the Forecast view; it never clobbers Linda's manual edits.

## User Story
As Linda (the private manager preparing the NSWTG Private Manager's Plan), I want each Section D forecast pre-filled with an annualized, benchmark-corrected number — not a raw copy of an incomplete trailing actual — so that the plan reflects a realistic full year and every non-trivial figure carries a defensible override reason.

## Problem → Solution
**Current:** `bootstrap_forecast_period` calls `compute_actual_value` (raw `SUM` over the trailing window) and defaults `forecast_value = actual_value`. With only ~4 months of statement data inside a 12-month trailing window, every line is understated ~3×, the single largest income line (DSP) is wrong because deposits are incomplete, a one-off March salary would be silently carried as recurring, and structurally-absent lines (Rent) read as $0. Every `forecasts` row currently has `forecast_value == actual_value` and a blank `override_reason`.

**Desired:** A generator computes, per category: months-of-data coverage → annualized estimate → benchmark/one-off correction → proposed forecast + machine-generated override reason. Linda reviews proposals in the existing editor and saves through the existing NCAT-invariant guard.

## Metadata
- **Complexity**: Medium
- **Source PRD**: N/A (free-form — derived from the forecast-generator discussion in this session)
- **PRD Phase**: N/A
- **Estimated Files**: 8 (3 created, 5 updated)

---

## UX Design

### Before
```
┌────────────────────────────────────────────────────────────┐
│ Forecast (Section D)        [Refresh actuals]                │
│ Trailing actuals window: 2025-06-09 → 2026-06-08             │
│ ┌──────────────┬──────────────────┬──────────┬────────────┐ │
│ │ Category     │ Actual (trailing)│ Forecast │ Override   │ │
│ │ DSP          │ $8,493.73        │ $8,493.73│ (blank)    │ │  ← raw 4-mo sum
│ │ Groceries    │ $3,284.83        │ $3,284.83│ (blank)    │ │  ← understated 3×
│ │ Rent         │ $0.00            │ $0.00    │ (blank)    │ │  ← structurally missing
│ │ Other        │ $3,188.42        │ $3,188.42│ (blank)    │ │  ← one-off carried as recurring
│ └──────────────┴──────────────────┴──────────┴────────────┘ │
└────────────────────────────────────────────────────────────┘
```

### After
```
┌────────────────────────────────────────────────────────────────────────────┐
│ Forecast (Section D)   [Refresh actuals]  [✨ Generate proposals]            │
│ Trailing actuals window: 2025-06-09 → 2026-06-08                             │
│ Data coverage: 4.0 months → annualization ×3.0   ⚠ 3 categories flagged      │
│ ┌──────────────┬───────────┬───────┬───────────┬──────────┬───────────────┐ │
│ │ Category     │ Actual    │ Months│ Annualized│ Forecast │ Override reason│ │
│ │ DSP          │ $8,493.73 │ 4.0   │ $25,481   │ $37,060  │ benchmark: ... │ │
│ │ Groceries    │ $3,284.83 │ 4.0   │ $9,855    │ $9,855   │ annualized ... │ │
│ │ Rent         │ $0.00     │ 4.0   │ $0.00     │ $21,840  │ benchmark: ... │ │
│ │ Other        │ $3,188.42 │ 1.0   │ —         │ $0.00    │ one-off: ...   │ │
│ └──────────────┴───────────┴───────┴───────────┴──────────┴───────────────┘ │
│ Income total: $XX,XXX   Expenditure total: $XX,XXX   Net: $X,XXX             │
└────────────────────────────────────────────────────────────────────────────┘
```

### Interaction Changes
| Touchpoint | Before | After | Notes |
|---|---|---|---|
| Forecast header | `Refresh actuals` only | adds `Generate proposals` + coverage caption | Proposals fill Forecast + Override columns in-grid |
| Forecast column set | Actual / Forecast / Override | adds read-only `Months of data` + `Annualized estimate` | Mirrors the requested deliverable table |
| Override reason | Linda types manually | pre-filled by generator, still editable | Satisfies NCAT invariant automatically |
| Save | unchanged | unchanged | Still routes through `save_forecast_override` |

---

## Mandatory Reading

| Priority | File | Lines | Why |
|---|---|---|---|
| P0 (critical) | `src/services/forecast.py` | 1-112 | `bootstrap_forecast_period` is the exact function the generator augments; preserve its idempotency + override-preservation contract |
| P0 (critical) | `src/db/queries_forecast.py` | 190-218 | `compute_actual_value` — the raw-sum aggregate; the generator needs a coverage-aware sibling |
| P0 (critical) | `src/services/compliance/rules.py` | 225-239 | `_project_to_period` — the codebase's canonical linear-extrapolation pattern to mirror for annualization math |
| P1 (important) | `src/views/forecast.py` | 47-220 | Where the `Generate proposals` button + new columns land; `_render_section_editor` build/save loop |
| P1 (important) | `src/models/forecast.py` | 1-48 | `Forecast` / `ForecastCategory` DTOs; frozen-dataclass convention |
| P1 (important) | `src/db/queries_forecast.py` | 20-30, 112-126 | `_SECTION_TO_COLUMN`, `upsert_forecast` keying tuple |
| P2 (reference) | `src/services/one_off.py` | 39-177 | `record_one_off_event` / `Candidate` — where excluded one-offs (Lactalis) are routed to Section E |
| P2 (reference) | `tests/test_services_forecast.py` | all | Service test harness (in-memory DB, txn seeding) to mirror for generator tests |
| P2 (reference) | `scripts/seed.py` | 190-235 | `_ensure_forecast_categories` — where benchmark config seeding can hook if needed |
| P2 (reference) | `src/config/categories.json` | all | Category name-space that forecast sections align to |

## External Documentation

| Topic | Source | Key Takeaway |
|---|---|---|
| Centrelink DSP rate | Services Australia "Disability Support Pension — How much you can get" | DSP is a published fortnightly rate; annual = rate × 26.0893 (365.25/14). User-confirmed input: observed steady-state **$1,420.30/fortnight** → ~$37,060/yr. Treated as a config value, not hardcoded. |

> Remaining external research: none. The annualization, projection, and persistence patterns are all established internal patterns. The only domain numbers (DSP rate, rent) are user-supplied config inputs.

---

## Patterns to Mirror

### NAMING_CONVENTION
```python
# SOURCE: src/services/forecast.py:56, src/db/queries_forecast.py:190
# Service fns: snake_case verbs taking conn first. Pure read helpers in queries_forecast.
def bootstrap_forecast_period(conn, managed_person_id, period_start, period_end) -> int: ...
def compute_actual_value(conn, category_name, section, date_from, date_to) -> float: ...
```

### ANNUALIZATION / PROJECTION
```python
# SOURCE: src/services/compliance/rules.py:225-239
def _project_to_period(amount, period_start, as_of, period_end):
    """Linearly extrapolate `amount` accrued over [period_start, as_of] to the full period."""
    start = date.fromisoformat(period_start)
    anchor = date.fromisoformat(as_of)
    end = date.fromisoformat(period_end)
    days_elapsed = (anchor - start).days + 1
    period_days = (end - start).days + 1
    if days_elapsed <= 0 or period_days <= 0:
        return None
    return amount * period_days / days_elapsed
# Generator mirrors this shape but the DENOMINATOR is data-coverage span,
# not elapsed-from-start, so mid-window/edge gaps don't deflate the estimate.
```

### ERROR_HANDLING
```python
# SOURCE: src/services/forecast.py:115-141
class ForecastOverrideError(ValueError): ...
# Invariant enforced at service layer; view surfaces inline (forecast.py:212-216).
if diff > 0.01 and not reason:
    raise ForecastOverrideError("override_reason is required when forecast_value differs from actual_value")
```

### REPOSITORY_PATTERN
```python
# SOURCE: src/db/queries_forecast.py:190-218
# Read helpers are pure, exclude internal transfers, COALESCE NULL→0.0, never write.
row = conn.execute(
    f"SELECT COALESCE(SUM({column}), 0) AS total FROM transactions "
    "WHERE category = ? AND date >= ? AND date <= ? "
    "  AND COALESCE(is_internal_transfer, 0) = 0",
    (category_name, date_from, date_to)).fetchone()
return float(row["total"] or 0.0)
```

### DTO_PATTERN
```python
# SOURCE: src/models/forecast.py:8-33  — frozen dataclasses, Optional fields default None
@dataclass(frozen=True)
class ForecastCategory:
    section: str
    category_name: str
    id: int | None = None
    display_order: int = 0
```

### CONFIG_PATTERN
```python
# SOURCE: src/pipeline/categoriser.py / src/config/categories.json
# Domain rules live in src/config/*.json, loaded by a small loader fn. No magic numbers in code.
```

### TEST_STRUCTURE
```python
# SOURCE: tests/test_forecast_rules.py:1-45
sys.path.insert(0, str(Path(__file__).parent.parent))
def _conn(tmp_path):
    conn = get_connection(tmp_path / "test.db"); init_db(conn); return conn
def _add_txns(conn, rows):  # rows: (date, withdrawal, deposit, category)
    ...
```

---

## Files to Change

| File | Action | Justification |
|---|---|---|
| `src/config/forecast_benchmarks.json` | CREATE | Externalised domain knowledge: DSP fortnightly rate, rent amount/cycle, one-off-excluded categories, per-category seasonality flags. No magic numbers in code. |
| `src/services/forecast_generator.py` | CREATE | Pure proposal engine: coverage → annualize → benchmark/one-off → `CategoryProposal`. The new logic, isolated and unit-testable. |
| `tests/test_forecast_generator.py` | CREATE | Unit coverage for annualization, DSP benchmark, one-off exclusion, rent injection, NCAT-reason generation, idempotency. |
| `src/db/queries_forecast.py` | UPDATE | Add `compute_actual_with_coverage` (returns raw sum + data-coverage span days + distinct-month count) alongside `compute_actual_value`. |
| `src/services/forecast.py` | UPDATE | Add `generate_forecast_proposals` orchestrator; keep `bootstrap_forecast_period` (raw actual still needed for the Actual column + invariant baseline). |
| `src/views/forecast.py` | UPDATE | `Generate proposals` button, coverage caption, two read-only columns (`Months of data`, `Annualized estimate`), wire proposals into the editor without clobbering existing overrides. |
| `src/config/help_content.json` | UPDATE | Help text for the new button/columns (mirrors existing `forecast.*` help keys). |
| `scripts/seed.py` | UPDATE (optional) | If benchmarks need a DB-side mirror; default is file-only load, so likely no change — listed for completeness. |

## NOT Building
- No new DB tables or migrations — `forecasts.actual_value`/`forecast_value`/`override_reason` already hold everything. (`actual_value` stays the RAW trailing sum to preserve the NCAT "differs from actual" semantics; the annualized number is the *proposed forecast*, not the actual.)
- No automatic save — the generator fills proposals; Linda still reviews and clicks Save. No silent writes.
- No change to Section E one-off mechanics beyond *routing* excluded categories (the Lactalis salary) to the existing `record_one_off_event`; the one-off subsystem itself is untouched.
- No multi-year / scenario forecasting, no inflation modelling, no per-account forecasting.
- No editing of `compute_actual_value` behaviour (other code depends on its raw-sum contract).
- No invented transactions — every proposed number traces to real data, a stated scale factor, or a config benchmark.

---

## Step-by-Step Tasks

### Task 1: Benchmark config file
- **ACTION**: Create `src/config/forecast_benchmarks.json`.
- **IMPLEMENT**:
  ```json
  {
    "annualization": { "min_coverage_days": 14, "fortnights_per_year": 26.0893 },
    "income_benchmarks": {
      "Disability Support Pension": { "type": "fortnightly_rate", "rate": 1420.30,
        "reason": "Benchmark from observed steady-state Centrelink DSP rate $1420.30/fortnight × 26.0893; trailing deposits incomplete." }
    },
    "expenditure_benchmarks": {
      "Rent": { "type": "cycle_amount", "amount": null, "cycle": "weekly",
        "reason": "Rent paid via internal transfer from Living Account; not captured as a categorised expense. Set amount before generating." }
    },
    "one_off_categories": {
      "Other": { "reason": "Single non-recurring event (e.g. final/back pay); routed to Section E, excluded from recurring forecast." }
    },
    "seasonality_flags": {
      "Gifts  & Outing": "Lumpy/seasonal — naive scaling may mislead; verify.",
      "Home & appliances": "One-off-heavy — verify before trusting scaled value.",
      "Miscellaneous": "Contains recurring NRMA insurance miscategorised here; verify."
    }
  }
  ```
- **MIRROR**: CONFIG_PATTERN (`src/config/categories.json` loaded by a loader fn).
- **IMPORTS**: none (data file).
- **GOTCHA**: Rent `amount` is `null` by design until the user supplies it. The generator MUST treat null benchmark amounts as "flag, don't fabricate" — propose $0 with a "needs input" reason, never invent a number. Category keys must match `forecast_categories.category_name` EXACTLY, including the double space in `"Gifts  & Outing"`.
- **VALIDATE**: `python3 -c "import json; json.load(open('src/config/forecast_benchmarks.json'))"`.

### Task 2: Coverage-aware aggregate query
- **ACTION**: Add `compute_actual_with_coverage` to `src/db/queries_forecast.py`.
- **IMPLEMENT**: Return `(total: float, coverage_days: int, months_with_data: float)`. `total` reuses the existing raw-sum SQL. Coverage = span of dates that actually carry non-internal transactions **for that section** within the window: `MIN(date)`/`MAX(date)` over rows where the section's column is non-null and `is_internal_transfer=0`. `coverage_days = (max-min).days + 1`; `months_with_data = round(coverage_days / 30.4375, 1)`. Return `(0.0, 0, 0.0)` when no rows.
- **MIRROR**: REPOSITORY_PATTERN (pure, exclude internal transfers, COALESCE).
- **IMPORTS**: `from datetime import date` (top of module if not present).
- **GOTCHA**: Use **section-wide** coverage (any income row for D_income, any expenditure row for D_expenditure), not per-category — a category with one transaction shouldn't read as "1 day of data" and annualize to absurdity. Compute the span once per section and pass it in.
- **VALIDATE**: unit test asserts a 4-month window of seeded data yields `months_with_data≈4.0` and `coverage_days≈120`.

### Task 3: Proposal engine (the core)
- **ACTION**: Create `src/services/forecast_generator.py` with a frozen `CategoryProposal` DTO and `generate_category_proposals(conn, mp_id, period_start, period_end) -> list[CategoryProposal]`.
- **IMPLEMENT**:
  - `CategoryProposal(category_id, category_name, section, actual_value, months_of_data, annualized_estimate, proposed_value, override_reason, flag)` (frozen dataclass).
  - For each forecast category: derive section coverage once; `annualized = actual * period_days / coverage_days` when `coverage_days >= min_coverage_days` else `actual` (with flag "insufficient data").
  - Precedence for `proposed_value`: (1) one-off category → `0.0`, reason from config; (2) income benchmark `fortnightly_rate` → `rate * fortnights_per_year`; (3) expenditure `cycle_amount` with non-null amount → annualize the cycle; null amount → `0.0` + "needs input" flag; (4) else → `annualized`.
  - `override_reason`: set to the benchmark/one-off/annualization reason **whenever `proposed_value` differs from `actual_value` by >$0.01** (NCAT invariant); empty when equal.
  - Attach `seasonality_flags[category]` to `flag` when present.
- **MIRROR**: ANNUALIZATION/PROJECTION (`_project_to_period` shape), DTO_PATTERN, NAMING_CONVENTION.
- **IMPORTS**: `from src.db.queries_forecast import list_forecast_categories, compute_actual_with_coverage`; config loader; `from dataclasses import dataclass`.
- **GOTCHA**: Pure function — no DB writes here (writes happen on Save via existing path). Annualizing a fortnightly rate by ×26.0893 must NOT also be day-scaled (benchmark overrides annualization, never stacks). Fortnights-per-year and rate both come from config.
- **VALIDATE**: `tests/test_forecast_generator.py` cases below.

### Task 4: Service orchestrator
- **ACTION**: Add `generate_forecast_proposals(conn, mp_id, period_start, period_end)` to `src/services/forecast.py`.
- **IMPLEMENT**: Ensure rows exist (call `bootstrap_forecast_period` first so `actual_value` is fresh and rows are keyed), then for each `CategoryProposal` upsert `forecast_value = proposed_value` + `override_reason`, **but only where the existing row has no Linda-authored override** (preserve manual edits: skip rows whose current `override_reason` is non-empty AND `forecast_value != actual_value` from a prior manual save). Return a summary dict `{updated, flagged, skipped}`.
- **MIRROR**: `bootstrap_forecast_period` idempotency + override-preservation contract (forecast.py:78-97); `upsert_forecast`.
- **IMPORTS**: `from src.services.forecast_generator import generate_category_proposals`.
- **GOTCHA**: Do not bypass `save_forecast_override`'s invariant intent — proposals always carry a reason when they differ, so a later manual Save won't trip `ForecastOverrideError`. Preserve-edit detection must not treat the generator's own prior proposals as "manual".
- **VALIDATE**: re-running twice is idempotent; a manually overridden row survives regeneration.

### Task 5: View — button, coverage caption, columns
- **ACTION**: Update `src/views/forecast.py`.
- **IMPLEMENT**: Add `Generate proposals` button next to `Refresh actuals` (header `col3` area) that calls `generate_forecast_proposals` then `st.rerun()`. Add a `st.caption` showing `months_of_data → ×factor` and flagged-category count. In `_render_section_editor`, add read-only `Months of data` and `Annualized estimate` columns sourced from the proposals (compute proposals once per render, map by category_id). Keep `Forecast` + `Override reason` editable and the existing Save loop intact.
- **MIRROR**: existing `st.data_editor` `column_config` block (forecast.py:169-190); `Refresh actuals` button (forecast.py:83-88).
- **IMPORTS**: `from src.services.forecast import generate_forecast_proposals`; `from src.services.forecast_generator import generate_category_proposals`.
- **GOTCHA**: `st.data_editor` requires stable column sets per `key`; add the two new read-only columns to `column_config` with `disabled=True`. Don't break the `_forecast_id` hidden column. Totals metrics (forecast.py:192-194) should now also surface **Net** (income forecast − expenditure forecast).
- **VALIDATE**: `streamlit run src/app.py`, open Forecast, click Generate, confirm DSP≈$37,060, Other=$0, Rent flagged, reasons populated.

### Task 6: Help content
- **ACTION**: Add `forecast.generate`, `forecast.months_of_data`, `forecast.annualized` keys to `src/config/help_content.json`.
- **IMPLEMENT**: Short do/why strings mirroring the existing `forecast.period` entry tone (help_content.json:164).
- **MIRROR**: existing `forecast.*` help entries.
- **IMPORTS**: none.
- **VALIDATE**: `python3 -c "import json; json.load(open('src/config/help_content.json'))"`; `widget_help("forecast.generate")` returns non-empty.

### Task 7: Tests
- **ACTION**: Create `tests/test_forecast_generator.py`.
- **IMPLEMENT**: see Testing Strategy.
- **MIRROR**: TEST_STRUCTURE (`tests/test_forecast_rules.py`, `tests/test_services_forecast.py`).
- **IMPORTS**: generator + queries + models + `get_connection/init_db`.
- **VALIDATE**: `python3 -m pytest tests/test_forecast_generator.py -v`.

---

## Testing Strategy

### Unit Tests
| Test | Input | Expected Output | Edge Case? |
|---|---|---|---|
| annualizes 4-month groceries | $3,284.83 over 120-day span, 365-day window | proposed ≈ $9,990 (±day rounding), months_of_data≈4.0, reason mentions annualization | No |
| DSP benchmark overrides actual | actual $8,493.73, config rate 1420.30 | proposed ≈ $37,060, reason cites fortnightly benchmark, NOT day-scaled | Yes |
| one-off category excluded | category "Other" actual $3,188.42 | proposed $0.00, reason cites one-off/Section E | Yes |
| rent with null benchmark amount | Rent actual $0, amount=null | proposed $0.00, flag "needs input", no fabricated value | Yes |
| rent with set amount | amount 420 cycle weekly | proposed ≈ $21,840 ($420×52), reason cites benchmark | No |
| NCAT reason generated on diff | any proposed ≠ actual | override_reason non-empty | Yes |
| no reason when equal | proposed == actual | override_reason empty | Yes |
| insufficient coverage | coverage_days < min | proposed = actual, flag "insufficient data" | Yes |
| idempotent regenerate | run twice | identical proposals, no duplicate rows | Yes |
| preserves manual override | row manually overridden then regenerate | manual value + reason survive (skipped) | Yes |

### Edge Cases Checklist
- [x] Empty input (no transactions → proposals all $0, coverage 0, no divide-by-zero)
- [x] Maximum size input (full 12-month window → factor ≈ 1.0)
- [x] Invalid types (non-numeric forecast handled in existing Save loop)
- [ ] Concurrent access (N/A — single-user Streamlit, SQLite serialised)
- [x] Network failure (N/A — local)
- [x] Permission denied (N/A)
- [x] Divide-by-zero when coverage_days == 0 (guard returns actual)
- [x] Category name with double space `"Gifts  & Outing"` maps correctly

---

## Validation Commands

### Static Analysis
```bash
python3 -m py_compile src/services/forecast_generator.py src/services/forecast.py \
  src/db/queries_forecast.py src/views/forecast.py
```
EXPECT: Zero errors

### Config Validity
```bash
python3 -c "import json; json.load(open('src/config/forecast_benchmarks.json')); json.load(open('src/config/help_content.json')); print('config OK')"
```
EXPECT: `config OK`

### Unit Tests
```bash
python3 -m pytest tests/test_forecast_generator.py -v
```
EXPECT: All pass

### Full Test Suite
```bash
python3 -m pytest tests/ -v
```
EXPECT: No regressions (quality gate g1)

### Database Validation
```bash
sqlite3 data/finmg.db "SELECT category_id, actual_value, forecast_value, override_reason FROM forecasts WHERE forecast_value != actual_value AND (override_reason IS NULL OR override_reason='');"
```
EXPECT: Zero rows (every divergence has a reason — NCAT invariant)

### Browser Validation
```bash
streamlit run src/app.py
```
EXPECT: Forecast → Generate proposals fills annualized + benchmark figures; DSP≈$37,060; Other=$0; Rent flagged; coverage caption shows 4.0 months ×3.0.

### Manual Validation
- [ ] Click `Generate proposals`; verify DSP, Groceries, Rent, Other match the discussed figures.
- [ ] Manually override one row + reason, Save, then Generate again — confirm the manual edit survives.
- [ ] Confirm Net = income forecast − expenditure forecast displays.
- [ ] Confirm no `forecasts` row has forecast ≠ actual with blank reason.

---

## Acceptance Criteria
- [ ] `Generate proposals` produces annualized, benchmark-corrected forecasts for every Section D category.
- [ ] DSP derived from config fortnightly rate (~$37,060), not raw deposits.
- [ ] One-off "Other" excluded (proposed $0) and routable to Section E.
- [ ] Rent honours a config amount; with null amount it flags rather than fabricates.
- [ ] Every proposal differing from actual carries a machine-generated `override_reason`.
- [ ] Manual overrides survive regeneration.
- [ ] All validation commands pass; no test regressions.

## Completion Checklist
- [ ] Mirrors `_project_to_period` for the scaling math and queries_forecast purity for reads.
- [ ] Error handling: reuses `ForecastOverrideError` invariant path on Save.
- [ ] No magic numbers — DSP rate, rent, fortnights/year, flags all in config.
- [ ] Tests follow `tests/test_forecast_rules.py` harness.
- [ ] `actual_value` semantics unchanged (still raw trailing sum).
- [ ] No invented transactions; null benchmarks flag, never fabricate.
- [ ] Help content updated.

## Risks
| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Section-coverage denominator over/under-states a category with genuinely different activity span | Medium | Medium | Use section-wide span + expose `Months of data` column so Linda sees the basis; seasonality flags call out lumpy categories |
| Rent amount still unknown at generation time | High | High | Null-amount benchmark flags "needs input" and proposes $0 — never fabricates; user supplies value in config |
| Generator overwrites a Linda edit | Low | High | Preserve-edit detection skips rows with manual override; idempotency test guards it |
| Benchmark category-name mismatch (double space) silently skips | Medium | Medium | Exact-match keys documented; test asserts `"Gifts  & Outing"` maps |
| NRMA insurance miscategorised in Miscellaneous distorts that line | Medium | Low | Seasonality flag on Miscellaneous prompts manual verification; out of scope to re-categorise here |

## Notes
- **Account context found while planning:** the Living Account (437669532) notes read *"source of rent transfers"* — rent likely leaves as an **internal transfer** (currently excluded from actuals), which is why Rent reads $0. The rent benchmark is the right lever; optionally a future enhancement could surface rent-sized internal transfers, but that is explicitly NOT in this scope.
- `actual_value` deliberately stays the raw trailing sum so the NCAT "forecast differs from actual → reason required" semantics remain meaningful and auditable. The annualized number is surfaced as a separate read-only column and as the *proposed forecast*, not as the actual.
- DSP user-confirmed: use observed $1,420.30/fortnight. Lactalis user-confirmed: one-off, exclude. Rent user-confirmed: real, amount pending — config-driven.

---

## Optimization Report

> Auto-generated by the prompt-optimizer gate in /prp-plan. Advisory — does not modify task steps.

### Intent & Scope
- **Detected Intent**: New Feature (replaces a naive default with a domain-aware generator)
- **Scope Level**: MEDIUM (3 created + 5 updated files; ~300-450 lines; follows established service/queries/view layering)
- **Model Recommendation**: Opus 4.8 for Task 3 (proposal-engine precedence logic) and Task 4 (preserve-edit detection); Sonnet acceptable for Tasks 1, 5, 6, 7 (config, view wiring, help, tests).

### Recommended ECC Components
| Type | Component | Purpose |
|------|-----------|---------|
| Command | `/prp-implement` | Execute this plan task-by-task with validation loops |
| Command | `/tdd` | Write the Task 7 tests first (RED→GREEN) for the generator |
| Command | `/code-review` | Review the generator + service before commit |
| Skill | `python-testing` | pytest fixtures/parametrization for the 10 generator cases |
| Skill | `python-patterns` | frozen-dataclass DTO + pure-function idioms |
| Agent | `python-reviewer` | PEP 8 / type-hint / purity review of new modules |
| Agent | `tdd-guide` | Enforce write-tests-first on the proposal engine |

### Missing Context (Advisory)
- **Rent amount** — pending from user. Non-blocking by design: the `Rent` benchmark ships with `amount: null`, and the generator flags "needs input" + proposes $0 rather than fabricating. Supply the value in `forecast_benchmarks.json` when known.
- All other context (DSP rate, one-off treatment, annualization math, persistence contract, test harness) is captured in-plan. Plan is otherwise self-contained.

### Workflow Recommendation
`/tdd (Task 7 first) → /prp-implement .claude/PRPs/plans/forecast-generator-annualized.plan.md → /code-review → /verify`

### Optimized Mission Brief
> Ready-to-paste as a standalone Claude Code prompt or DevFleet `detailed_prompt`.

Implement an annualized forecast generator for the FinMg NSWTG Plan (Section D) in `/Users/moofasa/finmg-forecast-wt` (branch `forecast/section-d-annualized`). Stack: Python 3.14, Streamlit, SQLite, pytest.

Problem: `bootstrap_forecast_period` (`src/services/forecast.py`) copies the raw trailing-actual sum into `forecast_value`. With only ~4 months of statement data in a 12-month window, every Section D line is understated ~3×, DSP is wrong (incomplete deposits), a one-off March salary would carry as recurring, and Rent reads $0 because it leaves as an internal transfer.

Build (mirroring existing patterns):
1. `src/config/forecast_benchmarks.json` — DSP fortnightly rate (1420.30 × 26.0893), Rent cycle_amount (amount null until supplied), one-off categories ("Other"), seasonality flags. Exact category-name keys incl. double-space `"Gifts  & Outing"`.
2. `src/db/queries_forecast.py::compute_actual_with_coverage` — raw sum + section-wide data-coverage span (days, months). Pure, excludes internal transfers, COALESCE NULL→0.
3. `src/services/forecast_generator.py` — pure `generate_category_proposals` returning frozen `CategoryProposal`. Precedence: one-off→$0; income fortnightly_rate→rate×fortnights; expenditure cycle_amount(non-null)→annualize, null→flag; else day-scaled annualization mirroring `_project_to_period` (`src/services/compliance/rules.py:225`). Set `override_reason` whenever proposed≠actual (NCAT invariant). Benchmarks never stack with day-scaling.
4. `src/services/forecast.py::generate_forecast_proposals` — bootstrap then upsert proposals, preserving Linda's manual overrides; idempotent.
5. `src/views/forecast.py` — `Generate proposals` button, coverage caption, read-only `Months of data` + `Annualized estimate` columns, Net metric. Save loop unchanged.
6. `src/config/help_content.json` — `forecast.generate/months_of_data/annualized` keys.
7. `tests/test_forecast_generator.py` — 10 cases (annualization, DSP benchmark, one-off exclusion, null-rent flag, set-rent, NCAT reason on/off, insufficient coverage, idempotency, manual-override preservation). Harness per `tests/test_forecast_rules.py`.

Constraints: `actual_value` stays the RAW trailing sum (do not annualize it). No invented transactions — null benchmarks flag, never fabricate. No new migrations. No silent saves. Validate: `python3 -m pytest tests/ -v`, `py_compile`, and `sqlite3 ... "SELECT ... WHERE forecast_value != actual_value AND (override_reason IS NULL OR override_reason='')"` returns zero rows.
