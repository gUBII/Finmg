"""Tests for PDF extraction against known totals."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.parser.pdf_extractor import extract_transactions, validate_totals
from src.parser.header_parser import extract_account_meta

PDF_DIR = Path(__file__).parent.parent / "bank_Statement"

# Expected totals from PDF footer "Total" rows
ACCOUNTS = [
    {
        "file": "17xxxxx19_120d_y.pdf",
        "account_type": "ACCESS ACCOUNT",
        "bsb": "012401",
        "account_number": "178865319",
        "expected_withdrawals": 28171.78,
        "expected_deposits": 30125.60,
    },
    {
        "file": "17xxxxx11_120d_y.pdf",
        "account_type": "PROGRESS SAVER",
        "bsb": "012401",
        "account_number": "178870011",
        "expected_withdrawals": 13315.83,
        "expected_deposits": 13315.79,
    },
    {
        "file": "43xxxxx32_120d_n.pdf",
        "account_type": "ANZ ACCESS ADVANTAGE",
        "bsb": "013711",
        "account_number": "437669532",
        "expected_withdrawals": 28519.93,
        "expected_deposits": 7471.46,
    },
]


@pytest.mark.skipif(not PDF_DIR.exists(), reason="bank_Statement directory not found")
class TestPDFExtraction:

    @pytest.mark.parametrize("account", ACCOUNTS, ids=lambda a: a["account_number"])
    def test_header_parsing(self, account):
        pdf_path = str(PDF_DIR / account["file"])
        meta = extract_account_meta(pdf_path)
        assert meta.bsb == account["bsb"]
        assert meta.account_number == account["account_number"]
        assert account["account_type"] in meta.account_type

    @pytest.mark.parametrize("account", ACCOUNTS, ids=lambda a: a["account_number"])
    def test_totals_match(self, account):
        pdf_path = str(PDF_DIR / account["file"])
        meta, txns = extract_transactions(pdf_path)
        result = validate_totals(
            txns,
            account["expected_withdrawals"],
            account["expected_deposits"],
        )
        assert result["withdrawals_match"], (
            f"Withdrawals mismatch: parsed {result['parsed_withdrawals']} "
            f"vs expected {account['expected_withdrawals']}"
        )
        assert result["deposits_match"], (
            f"Deposits mismatch: parsed {result['parsed_deposits']} "
            f"vs expected {account['expected_deposits']}"
        )

    @pytest.mark.parametrize("account", ACCOUNTS, ids=lambda a: a["account_number"])
    def test_no_empty_descriptions(self, account):
        pdf_path = str(PDF_DIR / account["file"])
        _, txns = extract_transactions(pdf_path)
        for txn in txns:
            assert txn.description.strip(), f"Empty description on {txn.date}"

    @pytest.mark.parametrize("account", ACCOUNTS, ids=lambda a: a["account_number"])
    def test_all_have_amount(self, account):
        pdf_path = str(PDF_DIR / account["file"])
        _, txns = extract_transactions(pdf_path)
        for txn in txns:
            assert txn.withdrawal or txn.deposit, (
                f"Transaction {txn.date} '{txn.description}' has no amount"
            )
