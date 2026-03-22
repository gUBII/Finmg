# FinMg — CSV Ingestion: Modular Change Plan
**Created:** 2026-03-22 | **Status:** IN PLANNING | **Agents:** CLAUDE (impl), CODEX (verify), GEMINI (QA)

---

## 1. Scope

Add CSV as a second ingestion path alongside PDF. **671 transactions** across 3 accounts (May 2025 → present) need to flow through the existing pipeline with zero downstream changes.

| Boundary | Decision |
|----------|----------|
| Files changed | 1 new (`csv_extractor.py`), 1 modified (`upload.py`), 1 new test |
| DB schema | **Untouched** — reuse `uploaded_pdfs` table for CSV metadata |
| Models | **Untouched** — same `AccountMeta` + `Transaction` dataclasses |
| Categoriser | **Untouched** — same keyword matching on descriptions |
| Merger | **Untouched** — same internal transfer detection |
| Excel export | **Untouched** — same downstream path |

---

## 2. CSV Contract (confirmed from 3 dropped files)

**Format:** `DD/MM/YYYY,"signed_amount",description[,,,,,]`

| File | Rows | Account # | BSB | Account Type | Notes |
|------|------|-----------|-----|--------------|-------|
| `living_account(may2025-present).csv` | 358 | 178865319 | 012401 | ACCESS ACCOUNT | Has trailing empty columns |
| `savings_account(may2025-present).csv` | 29 | 178870011 | 012401 | PROGRESS SAVER | Clean 3-column format |
| `spendingaccount(may2025-present).csv` | 284 | 437669532 | 013711 | ANZ FIRST | Clean 3-column format |

**Amount rules:**
- Negative = withdrawal (e.g. `"-42.20"`)
- Positive = deposit (e.g. `"2817.00"`)
- Quoted, no `$` prefix, no thousands separator

---

## 3. Architecture — Interface Preservation

The core design principle: **`csv_extractor.py` returns the same `(AccountMeta, list[Transaction])` tuple as `pdf_extractor.py`**. This means `upload.py` only needs a routing `if` — everything after the parse call is identical.

```
                    ┌─────────────────┐
                    │   upload.py     │
                    │  file_uploader  │
                    └───────┬─────────┘
                            │
                    ┌───────┴───────┐
                    │  .pdf?  .csv? │
                    └───┬───────┬───┘
                        │       │
              ┌─────────┴──┐ ┌──┴──────────┐
              │pdf_extractor│ │csv_extractor│
              │  (existing) │ │   (NEW)     │
              └─────────┬──┘ └──┬──────────┘
                        │       │
                        ▼       ▼
               (AccountMeta, list[Transaction])
                        │
                ┌───────┴───────┐
                │ UNCHANGED:    │
                │ split_by_month│
                │ categorise_all│
                │ detect_xfers  │
                │ insert to DB  │
                └───────────────┘
```

---

## 4. File-by-File Change Spec

### 4.1 NEW: `src/parser/csv_extractor.py`

**Single function:**
```python
def extract_transactions_csv(csv_path: str, filename: str) -> tuple[AccountMeta, list[Transaction]]
```

**Internal logic:**

1. **Account inference** — match filename against keywords (case-insensitive):
   ```python
   ACCOUNT_MAP = {
       "living":   {"number": "178865319", "bsb": "012401", "type": "ACCESS ACCOUNT"},
       "savings":  {"number": "178870011", "bsb": "012401", "type": "PROGRESS SAVER"},
       "spending": {"number": "437669532", "bsb": "013711", "type": "ANZ FIRST"},
   }
   ```

2. **Row parsing** — `csv.reader` with standard dialect:
   - Parse `DD/MM/YYYY` → `datetime.date`
   - Parse signed amount → split into `withdrawal` (if negative) / `deposit` (if positive)
   - Description = third field, stripped
   - Ignore trailing empty fields (living account has 5 extra commas)

3. **AccountMeta construction:**
   - `report_start` / `report_end` = min/max date from parsed transactions, formatted as "DD Month YYYY"
   - `balance` = 0.0 (not available from CSV)
   - `account_name` = "GENTILI RENATO" (hardcoded — single-user system)
   - `source_file` = filename

4. **Return** — `(meta, transactions)` with same shape as PDF path

**Dependencies:** `csv` (stdlib), `src.models.transaction` — no new packages.

### 4.2 MODIFIED: `src/views/upload.py`

**Changes (minimal):**

1. **Line ~104:** Add `"csv"` to the `type=` list in `st.file_uploader`:
   ```python
   type=["pdf", "csv"]
   ```

2. **Line ~107:** Update caption to mention CSV support

3. **Line ~127–132:** Add routing logic:
   ```python
   if uploaded.name.lower().endswith(".csv"):
       from src.parser.csv_extractor import extract_transactions_csv
       meta, transactions = extract_transactions_csv(tmp_path, uploaded.name)
   else:
       meta, transactions = extract_transactions(tmp_path)
   ```

4. **Line ~146–151:** Make PDF-specific total validation conditional:
   ```python
   if not uploaded.name.lower().endswith(".csv"):
       expected = EXPECTED_TOTALS.get(meta.account_number, {})
       validation = validate_totals(transactions, ...)
   else:
       # CSV has no expected footer totals — just report parsed sums
       validation = {
           "parsed_withdrawals": round(sum(t.withdrawal or 0 for t in all_txns), 2),
           "parsed_deposits": round(sum(t.deposit or 0 for t in all_txns), 2),
           "transaction_count": len(all_txns),
       }
   ```

**Everything after this point is unchanged** — categorise, merge, DB insert, results display.

### 4.3 NEW: `tests/test_csv_extractor.py`

| Test | What it validates |
|------|-------------------|
| `test_parse_positive_amount` | `"2817.00"` → deposit=2817.00, withdrawal=None |
| `test_parse_negative_amount` | `"-42.20"` → withdrawal=42.20, deposit=None |
| `test_date_parsing` | `20/03/2026` → `date(2026, 3, 20)` |
| `test_account_inference_living` | filename with "living" → 178865319 |
| `test_account_inference_savings` | filename with "savings" → 178870011 |
| `test_account_inference_spending` | filename with "spending" → 437669532 |
| `test_trailing_commas_stripped` | Living row with 5 trailing commas → clean transaction |
| `test_row_count_living` | 358 rows parsed from actual CSV |
| `test_row_count_savings` | 29 rows parsed from actual CSV |
| `test_row_count_spending` | 284 rows parsed from actual CSV |

---

## 5. What Does NOT Change

| Component | Why it's untouched |
|-----------|--------------------|
| `src/models/transaction.py` | CSV uses same `Transaction` + `AccountMeta` |
| `src/pipeline/categoriser.py` | Keyword matching on `.description` — works identically |
| `src/pipeline/merger.py` | Internal transfer detection on description text — works |
| `src/pipeline/month_splitter.py` | Splits by `txn.date` — works |
| `src/pipeline/excel_writer.py` | Reads from DB — source format irrelevant |
| `src/db/database.py` | No schema changes |
| `src/db/queries.py` | `insert_pdf_and_transactions` takes `(meta, txns, filename, hash)` — works for CSV |
| `src/views/dashboard.py` | Reads from DB — source format irrelevant |
| `src/views/transactions.py` | Reads from DB — source format irrelevant |
| `src/views/export.py` | Reads from DB — source format irrelevant |
| `src/config/categories.json` | Category rules are description-based, format-agnostic |

---

## 6. Dedup Strategy

The existing dedup system works for CSV with no changes:

1. **File-level:** `_file_hash(bytes)` → SHA-256 checked in `is_pdf_already_uploaded()`. Same CSV = same hash = skip.
2. **Transaction-level:** `delete_account_transactions_in_range()` removes existing rows for the same account + date range before inserting. If a CSV overlaps with previously uploaded PDF data, the CSV rows replace the old ones cleanly.

**Edge case:** User uploads a PDF covering Nov 2025 → Mar 2026, then a CSV covering May 2025 → Mar 2026. The overlapping months (Nov–Mar) get replaced by CSV-sourced rows. This is correct behavior — newer upload wins within the overlap window.

---

## 7. Task Allocation

| # | Task | Owner | Depends | Status |
|---|------|-------|---------|--------|
| T1 | CSV format inspection + contract pinning | CLAUDE | — | DONE |
| T2 | Write `src/parser/csv_extractor.py` | CLAUDE | T1 | READY |
| T3 | Modify `src/views/upload.py` (routing + CSV support) | CLAUDE | T2 | BLOCKED on T2 |
| T4 | Write `tests/test_csv_extractor.py` | CLAUDE | T2 | BLOCKED on T2 |
| T5 | Verify row counts: parsed vs raw CSV line counts | CODEX | T2 | TODO |
| T6 | Integration test: CSV → DB → dashboard round-trip | CODEX | T3 | TODO |
| T7 | Verify dedup: re-upload same CSV, overlap with PDF data | CODEX | T3 | TODO |
| T8 | QA: category coverage on CSV descriptions | GEMINI | T3 | TODO |
| T9 | Clean repo artifacts (old PDFs, caches, by-products) | GEMINI | — | IN PROGRESS |
| T10 | Final sign-off + CLAUDE.md update | Operator | T4–T8 | TODO |

---

## 8. Assumptions

- ANZ CSV export format is stable across all 3 accounts (confirmed)
- Filename always contains `living`, `savings`, or `spending` (confirmed from dropped files)
- No header row in any CSV (confirmed)
- `uploaded_pdfs` table name is fine for CSV entries (pragmatic — avoids schema migration)
- `pdf_id` FK in `transactions` table is fine for CSV-sourced rows (semantically it's `source_id`)
- Python `csv` stdlib handles the quoted amounts correctly
- Single-user system — `account_name` hardcoded to "GENTILI RENATO"

---

## 9. Risks

| Risk | Impact | Mitigation |
|------|--------|------------|
| Filename doesn't contain account keyword | Parser fails to infer account | Raise clear error with supported keywords |
| Description contains commas breaking CSV parse | Wrong field split | `csv.reader` handles quoted fields — descriptions aren't quoted but commas only appear in trailing empty cols |
| Future ANZ format change (new columns, headers) | Parser breaks | Header detection: if first row looks like a header, skip it |
| Overlapping date ranges between PDF + CSV | Data replacement | By design — `delete_account_transactions_in_range` handles this correctly |

---

## 10. Definition of Done

1. All 3 CSV files upload successfully via the UI
2. Row counts match: living=358, savings=29, spending=284
3. Transactions appear in Transactions view with correct categories
4. Dashboard KPIs reflect the new data
5. Excel export includes CSV-sourced months
6. `python3 -m pytest tests/ -v` passes with no regressions
7. Re-uploading same CSV is blocked by dedup
