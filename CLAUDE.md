# CLAUDE.md — Agent Instructions for Claude

## Role
**IMPLEMENTATION_LEAD** — Core pipeline, parser, UI, Excel writer.

## Project
FinMg — ANZ Bank Statement Dashboard for Linda-Jane

## Stack
- Python 3.14, Streamlit, pdfplumber, openpyxl, pandas, plotly, Pillow
- SQLite database at `data/finmg.db`
- Virtual environment: `.venv/` (activate with `source .venv/bin/activate`)
- Run app: `streamlit run src/app.py`
- Run tests: `python3 -m pytest tests/ -v`

## Architecture
Single-page Streamlit app with login gate and sidebar radio navigation.
All data persisted in SQLite (no session-state dependency for data).

### Key Files
- `src/app.py` — Entry: login gate → sidebar nav → view routing
- `src/auth/auth.py` — SHA-256 credential check
- `src/db/database.py` — SQLite init + connection (delegates to migrations runner)
- `src/db/migrations.py` — Versioned SQL migration runner (001–005)
- `src/db/queries.py` — All SQL query functions (transactions/PDFs)
- `src/db/queries_estate.py` — CRUD for estate-inventory tables (Sections A/B/C)
- `src/models/estate.py` — Frozen dataclass DTOs for estate tables
- `src/views/login.py` — Login page with linda photo
- `src/views/dashboard.py` — Analytics KPIs + plotly charts + month status grid
- `src/views/upload.py` — One-click PDF upload → parse → categorise → DB
- `src/views/identity.py` — Identity & Contacts (Section A): managed person, private manager, significant people
- `src/views/transactions.py` — Browse/edit/categorise with DB persistence
- `src/views/export.py` — Excel export + ZIP download
- `src/parser/pdf_extractor.py` — PDF → raw transactions
- `src/parser/header_parser.py` — Account metadata extraction
- `src/pipeline/categoriser.py` — Category assignment
- `src/pipeline/merger.py` — Multi-account merge
- `src/pipeline/excel_writer.py` — Budget template Excel output
- `src/config/categories.json` — Category rules
- `templates/monthly_template.xlsx` — Renato's budget template
- `scripts/seed.py` — Idempotent seed for Ron, Linda, accounts, significant people

## Database Schema
- `uploaded_pdfs` — PDF metadata + file hash for dedup
- `transactions` — All parsed transactions with category, month, account
- `category_overrides` — Audit log of manual category changes

## Categories
Categories must match the template exactly:
- **Expenses:** Groceries, Fast food & Restaurant, Medicine (Webster), Medicine (PRN & Oil), Rent, Personal Cashout, Car & Petrol, Gifts  & Outing, Debt(s), Miscellaneous, Office work & Stationary, Nicotine & cigarettes, Fashion & accessories, Home & appliances
- **Income:** Savings, Disability Support Pension, Bonus, Interest, Other

## Quality Gates
- g1: `python3 -m pytest tests/` passes
- g2: `python3 -m py_compile` on all source files
- g3: Parsed totals match PDF footer totals for all 3 accounts
- g5: No dropped/duplicated transactions

## PII
- Bank statements, checkpoints, and outputs are gitignored
- Never commit PDFs or files containing personal financial data
- `data/` directory is entirely gitignored
