# IACP Quality Gates (Python-adapted)

## g1: Tests Pass
```bash
source .venv/bin/activate
python3 -m pytest tests/ -v
```
All tests must pass. Zero failures allowed.

## g2: Source Compilation
```bash
python3 -m py_compile src/app.py
python3 -m py_compile src/parser/pdf_extractor.py
python3 -m py_compile src/parser/header_parser.py
python3 -m py_compile src/pipeline/categoriser.py
python3 -m py_compile src/pipeline/merger.py
python3 -m py_compile src/pipeline/excel_writer.py
python3 -m py_compile src/pipeline/month_splitter.py
python3 -m py_compile src/checkpoints/checkpoint_io.py
python3 -m py_compile src/models/transaction.py
```
No syntax errors in any source file.

## g3: Parsed Totals Match PDF Footers
Verified by `test_pdf_extractor.py::test_totals_match`:
- Account 178865319: W=$28,171.78 D=$30,125.60
- Account 178870011: W=$13,315.83 D=$13,315.79
- Account 437669532: W=$28,519.93 D=$7,471.46

## g5: Data Integrity
- Total transactions: 416 across all 3 accounts
- No duplicate transactions (same date+description+amount+account)
- No dropped transactions (sum matches expected count per account)
- Internal transfers correctly identified and flagged
