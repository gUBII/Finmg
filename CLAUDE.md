# CLAUDE.md — Agent Instructions for Claude

## Role
**IMPLEMENTATION_LEAD** — Core pipeline, parser, UI, Excel writer.

## Project
FinMg — ANZ Bank Statement to Budget Pipeline

## Stack
- Python 3.14, Streamlit, pdfplumber, openpyxl, pandas
- Virtual environment: `.venv/` (activate with `source .venv/bin/activate`)
- Run app: `streamlit run src/app.py`
- Run tests: `python3 -m pytest tests/ -v`

## Key Files
- `src/app.py` — Streamlit entry point (tabbed UI)
- `src/parser/pdf_extractor.py` — PDF → raw transactions
- `src/parser/header_parser.py` — Account metadata extraction
- `src/pipeline/categoriser.py` — Category assignment
- `src/pipeline/merger.py` — Multi-account merge
- `src/pipeline/excel_writer.py` — Budget template Excel output
- `src/config/categories.json` — Category rules
- `template_empty/` — Renato's budget template (copied and populated per month)

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
