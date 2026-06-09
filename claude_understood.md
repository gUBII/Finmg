# Claude's Understanding of the FinMg Repository

**Agent:** CLAUDE (Implementation Lead)
**Date:** 2026-06-08 (updated; account mapping corrected after Linda's verbal confirmation)

---

## What This Project Is

FinMg is a **personal household finance dashboard** built for Linda-Jane (partner of Renato, the operator). It ingests ANZ bank statement PDFs (and soon CSVs), parses every transaction, auto-categorises them against a fixed budget template, stores everything in SQLite, and presents it through a Streamlit web UI with charts, editing, and Excel export.

It is a **single-user system** — there is one household, three ANZ accounts, one login.

---

## The Three Accounts (Linda-confirmed 2026-06-08)

| Role     | Account #   | BSB    | PDF header     | Notes                                                            |
|----------|-------------|--------|----------------|------------------------------------------------------------------|
| Living   | 437669532   | 013711 | ACCESS ACCOUNT | Wages (LACTALIS) + Centrelink pension (CTRLINK); funds rent      |
| Spending | 178865319   | 012401 | ACCESS ACCOUNT | Daily Visa Debit card purchases; topped up from Living           |
| Savings  | 178870011   | 012401 | PROGRESS SAVER | Weekly $200 sweeps in from Living; interest credits              |

Accounts are in **Renato Gentili's** name; **Linda Jane Travia** (court-recognised Private Financial Manager post-TBI) operates them. FinMg is her NCAT-compliance tool.

> ⚠️ Earlier project docs (and the prior version of this file) had Living/Spending **inverted**. Data was the source of truth; docs were wrong. Fixed 2026-06-08.

---

## How the Pipeline Works

1. **Upload** (`src/views/upload.py`) — User drops a PDF via Streamlit's file uploader. File is SHA-256 hashed for dedup.
2. **Parse** (`src/parser/pdf_extractor.py`) — pdfplumber extracts words, groups them by y-coordinate into lines, then classifies each word into Date / Description / Withdrawal / Deposit columns using x-position thresholds. Month+year headers set the year context. Continuation lines (no date) append to the previous transaction.
3. **Header extraction** (`src/parser/header_parser.py`) — Pulls account metadata (number, BSB, type, date range) from the first page.
4. **Month splitting** (`src/pipeline/month_splitter.py`) — Groups transactions by `YYYY-MM`.
5. **Categorisation** (`src/pipeline/categoriser.py`) — Regex keyword matching against `src/config/categories.json`. First match wins. Withdrawals match expense categories; deposits match income categories. Internal transfers detected separately.
6. **Merge** (`src/pipeline/merger.py`) — Detects internal transfers across the three accounts.
7. **DB insert** (`src/db/queries.py`) — Transactions stored in SQLite with category, month, account. Existing rows for the same account+date range are deleted before insert (handles re-uploads).
8. **Views** — Dashboard (KPIs + Plotly charts), Transactions (browse/edit/re-categorise), Export (Excel + ZIP download using Renato's budget template).

---

## Database (SQLite at `data/finmg.db`)

Three tables:
- `uploaded_pdfs` — source file metadata + hash for dedup
- `transactions` — every parsed transaction with category, month, account, FK to source
- `category_overrides` — audit log when user manually re-categorises

WAL mode enabled. Foreign keys enforced.

---

## Categories (must match budget template exactly)

**Expenses:** Groceries, Fast food & Restaurant, Medicine (Webster), Medicine (PRN & Oil), Rent, Personal Cashout, Car & Petrol, Gifts & Outing, Debt(s), Miscellaneous, Office work & Stationary, Nicotine & cigarettes, Fashion & accessories, Home & appliances

**Income:** Savings, Disability Support Pension, Bonus, Interest, Other

Subscriptions and bank fees map to Miscellaneous.

---

## Current State & Next Phase

The app is functional for PDF ingestion (v2 modular architecture shipped in recent commits). The next planned work is **CSV ingestion** — a `csv_extractor.py` that returns the same `(AccountMeta, list[Transaction])` tuple as the PDF path, so the entire downstream pipeline stays untouched. This is documented in `ProjectManagement.md` with a detailed change plan.

671 CSV transactions across 3 accounts (May 2025 onward) need to be ingested.

---

## Quality Gates I Watch For

- `pytest tests/` passes
- All `.py` files compile cleanly
- Parsed totals match PDF footer totals (for PDFs)
- No dropped or duplicated transactions
- PII never committed (PDFs, `data/` directory gitignored)

---

## Tech Stack

Python 3.14 | Streamlit | pdfplumber | openpyxl | pandas | plotly | Pillow | SQLite

No external services, no cloud dependencies, no API keys. Fully local.

---

## My Role

I am the **Implementation Lead** — responsible for core pipeline code, parser logic, UI views, and the Excel writer. I write the code, Codex verifies, Gemini does QA.

---

## What I Understood from the Other Agents

### Codex (Code/Repo Analyzer)

Codex approached the repo bottom-up — he read the actual source files and described what each module does at the code level. Key things I took from his report:

- He confirmed the upload view is **PDF-only today** and that `csv_extractor.py` does not yet exist in the tree, which aligns with my understanding that CSV ingestion is the next phase.
- He noted the auth uses `hmac.compare_digest` with SHA-256 hashes and falls back to local secrets — a detail I didn't call out explicitly but is accurate.
- He flagged the `docs/iacp/` directory as inter-agent coordination docs, which is separate from the finance app itself. Good observation — that's the multi-agent process layer sitting alongside the product code.
- His description of the parser's x-coordinate word grouping and column classification matches my pipeline walkthrough. We agree on the mechanics.
- He correctly identified that the test suite is unusually broad for a project this size, covering auth, DB, categoriser, checkpoints, PDF extraction, merger, month splitting, and Excel writing.

**Overall:** Codex's structural/code-level analysis complements my functional pipeline view. No contradictions. His repo-state observations are accurate.

### Gemini (Independent Verifier)

Gemini defined her role clearly as the **verification and QA layer** — she's checking that parsed totals match PDF footers, no transactions are dropped/duplicated, categorisation logic works correctly, and Excel output matches the template structure. Key takeaways:

- She correctly positioned her role as **dependent on** the implementation work (mine) and the code analysis (Codex's). She verifies what we build.
- Her synthesis of Claude vs Codex is accurate: she noted I focus on the "how" (pipeline flow) while Codex focuses on the "what" (code structure). Fair characterisation.
- She identified the common ground correctly: all three of us agree on the core purpose, tech stack, and that CSV ingestion is the next feature.

**Overall:** Gemini has a clear, well-scoped understanding of her verification mandate. The three roles are complementary — I build, Codex analyzes structure, Gemini validates output correctness.
