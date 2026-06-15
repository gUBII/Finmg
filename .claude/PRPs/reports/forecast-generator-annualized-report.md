# Implementation Report: Annualized Forecast Generator (Section D)

## Summary
Replaced the "copy trailing actual into forecast" bootstrap with a forecast generator that annualizes partial-window actuals to a 12-month equivalent, applies benchmark overrides (DSP fortnightly rate, rent cycle), excludes one-off events, and auto-writes the NCAT-required `override_reason` whenever its proposal differs from the raw actual. Surfaced via a `Generate proposals` action in the Forecast view with coverage caption, `Months of data` + `Annualized estimate` columns, a `Flag` column, and a Net-position summary. Manual overrides are preserved on regeneration.

## Assessment vs Reality

| Metric | Predicted (Plan) | Actual |
|---|---|---|
| Complexity | Medium | Medium |
| Confidence | 8/10 | Single-pass achieved (TDD GREEN, no rework) |
| Files Changed | 8 (3 create, 5 update) | 8 source/config (3 create, 4 update) + 2 test files created |

## Tasks Completed

| # | Task | Status | Notes |
|---|---|---|---|
| 1 | Benchmark config | Complete | `src/config/forecast_benchmarks.json` — DSP rate, rent (null), one-off "Other", seasonality flags |
| 2 | Coverage-aware query | Complete | Added `section_coverage_days` + `compute_actual_with_coverage` (section-wide span) |
| 3 | Proposal engine | Complete | `forecast_generator.py` — pure `generate_category_proposals` + `CategoryProposal` DTO |
| 4 | Service orchestrator | Complete | `generate_forecast_proposals` with `[auto]`-tag provenance to preserve manual edits |
| 5 | View wiring | Complete | Generate button, coverage caption, 3 new columns, Net metric |
| 6 | Help content | Complete | `forecast.generate/months_of_data/annualized` keys |
| 7 | Tests | Complete | 12 generator/service tests + 2 view smoke tests |

## Validation Results

| Level | Status | Notes |
|---|---|---|
| Static Analysis (py_compile) | Pass | All 4 source modules compile |
| Config validity (JSON) | Pass | both JSON files parse |
| Unit Tests | Pass | 12 new generator/service tests green |
| Full Suite | Pass* | 294 passed, 18 skipped; *2 pre-existing gifts failures unrelated (live-DB dependency, fail identically on untouched baseline) |
| View Smoke (AppTest) | Pass | Forecast view renders; Generate button + Net metric present; gifts tests also pass once a DB is present |
| Real-data validation | Pass | Ran on a throwaway copy of `data/finmg.db`: DSP $8,493→$37,055, Other $3,188→$0, Rent flagged, Groceries $3,285→$10,019, Net +$3,697. Real DB untouched. |

## Files Changed

| File | Action | Lines |
|---|---|---|
| `src/config/forecast_benchmarks.json` | CREATED | +32 |
| `src/services/forecast_generator.py` | CREATED | +205 |
| `tests/test_forecast_generator.py` | CREATED | +339 |
| `tests/test_views_forecast.py` | CREATED | +45 |
| `src/db/queries_forecast.py` | UPDATED | +52 |
| `src/services/forecast.py` | UPDATED | +77 |
| `src/views/forecast.py` | UPDATED | +75 / -1 |
| `src/config/help_content.json` | UPDATED | +10 |

## Deviations from Plan
1. **Injectable `benchmarks` param** — `generate_category_proposals` and `generate_forecast_proposals` accept an optional `benchmarks` dict (defaults to the config file). WHY: lets unit tests control benchmark values without coupling to the shipped config. No behaviour change in production (default path loads the file).
2. **`[auto]` provenance tag** — generator-authored `override_reason`s carry a trailing ` [auto]` marker. WHY: the plan required distinguishing generator output from manual edits without a new DB column; the tag lets a re-run refresh its own prior proposals while leaving Linda's manual reasons (which never carry the tag) untouched. Side benefit: the tag is honest provenance for NCAT (figure was system-derived, not hand-entered).
3. **`section_coverage_days` split out** — added as its own query helper feeding `compute_actual_with_coverage`. WHY: section-wide coverage must be computed once per section, not per category, to avoid a single-transaction category annualizing to absurdity.
4. **Extra `Flag` column + `tests/test_views_forecast.py`** — beyond the plan's column list, a `Flag` column surfaces seasonality / needs-input warnings inline, and a view smoke test was added to match the existing `test_views_gifts_dashboard.py` pattern.

## Issues Encountered
- **2 gifts-view test failures in the bare worktree** — root cause: those tests run against the live `data/finmg.db`, which a fresh git worktree does not carry (gitignored). Confirmed they fail identically on the untouched `main` HEAD and pass once a DB copy is present. Not a regression from this work.

## Tests Written

| Test File | Tests | Coverage |
|---|---|---|
| `tests/test_forecast_generator.py` | 12 | annualization, full-year factor, insufficient-coverage guard, DSP benchmark, null/ set rent, one-off exclusion, seasonality flag, NCAT reason, idempotency, manual-override preservation |
| `tests/test_views_forecast.py` | 2 | view renders without exception; Generate button + Net metric present |

## Next Steps
- [ ] Code review via `/code-review`
- [ ] Supply the real Rent amount → set `expenditure_benchmarks.Rent.amount` in `forecast_benchmarks.json`
- [ ] Create PR via `/prp-pr`
