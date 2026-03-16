"""
PDF → raw transactions extractor for ANZ Transaction Reports.

Uses pdfplumber to extract words, groups them by y-coordinate into lines,
then classifies each word into columns by x-position:
  - Date:        x < 80
  - Description: 80 <= x < 447
  - Withdrawal:  447 <= x < 515 (right-aligned ending ~494)
  - Deposit:     x >= 515       (right-aligned ending ~563)

Transaction lines are detected by a date pattern (DD MMM).
Continuation lines (no date) are appended to the previous transaction.
Month+year headers (e.g. "MAR 2026") set the current year context.
"""

import re
from collections import defaultdict
from datetime import date
from typing import Optional

import pdfplumber

from src.models.transaction import AccountMeta, Transaction
from src.parser.header_parser import extract_account_meta

# Month name → number
MONTH_MAP = {
    "JAN": 1, "FEB": 2, "MAR": 3, "APR": 4, "MAY": 5, "JUN": 6,
    "JUL": 7, "AUG": 8, "SEP": 9, "OCT": 10, "NOV": 11, "DEC": 12,
}

# Column boundaries (x-coordinates)
X_DATE_MAX = 80
X_DESC_MAX = 447
X_WITHDRAWAL_MAX = 515
# Deposit: >= X_WITHDRAWAL_MAX

# Pattern for transaction date: "DD MMM"
DATE_PATTERN = re.compile(r"^(\d{2})\s+(JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)$")

# Pattern for month header: "MMM YYYY"
MONTH_HEADER_PATTERN = re.compile(
    r"^(JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)\s+(\d{4})$"
)


def _infer_recent_year(meta: AccountMeta) -> int:
    """Use the report end year for the 'RECENT' section before any month header."""
    match = re.search(r"(\d{4})$", meta.report_end or "")
    if match:
        return int(match.group(1))
    return date.today().year


def _parse_amount(text: str) -> Optional[float]:
    """Parse a dollar amount string like '$1,234.56' to float."""
    if not text:
        return None
    cleaned = text.replace("$", "").replace(",", "").strip()
    if not cleaned:
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def _line_from_words(words: list[dict]) -> dict:
    """
    Given a list of word dicts on the same y-line, classify into columns.
    Returns dict with keys: date_text, desc_text, withdrawal_text, deposit_text, raw.
    """
    words = sorted(words, key=lambda w: w["x0"])

    date_parts = []
    desc_parts = []
    withdrawal_parts = []
    deposit_parts = []

    for w in words:
        x0 = float(w["x0"])
        text = w["text"].strip()
        if not text or text == "blank":
            continue

        if x0 < X_DATE_MAX:
            date_parts.append(text)
        elif x0 < X_DESC_MAX:
            desc_parts.append(text)
        elif x0 < X_WITHDRAWAL_MAX:
            withdrawal_parts.append(text)
        else:
            deposit_parts.append(text)

    return {
        "date_text": " ".join(date_parts),
        "desc_text": " ".join(desc_parts),
        "withdrawal_text": " ".join(withdrawal_parts),
        "deposit_text": " ".join(deposit_parts),
        "raw": " ".join(w["text"] for w in words),
    }


def extract_transactions(pdf_path: str) -> tuple[AccountMeta, list[Transaction]]:
    """
    Extract all transactions from an ANZ transaction report PDF.

    Returns:
        Tuple of (account metadata, list of transactions)
    """
    meta = extract_account_meta(pdf_path)
    pdf = pdfplumber.open(pdf_path)
    recent_year = _infer_recent_year(meta)
    date_range_text = ""
    if meta.report_start and meta.report_end:
        date_range_text = f"{meta.report_start} to {meta.report_end}"

    transactions: list[Transaction] = []
    current_year: Optional[int] = None
    current_month_num: Optional[int] = None

    for page in pdf.pages:
        words = page.extract_words(x_tolerance=3, y_tolerance=3)

        # Group words by y-coordinate (line)
        lines_by_y: dict[float, list[dict]] = defaultdict(list)
        for w in words:
            y = round(float(w["top"]), 0)
            lines_by_y[y].append(w)

        for y in sorted(lines_by_y.keys()):
            line = _line_from_words(lines_by_y[y])
            raw = line["raw"].strip()

            # Skip header lines
            if raw.startswith("Transaction Report") or raw.startswith("Date"):
                continue
            if "Account Number" in raw or "Account Name" in raw:
                continue
            if "Branch Number" in raw:
                continue
            if raw.startswith("Please check") or raw.startswith("Your Transaction"):
                continue
            if raw.startswith("Transactions may") or raw.startswith("This document"):
                continue
            if raw.startswith("If you notice") or raw.startswith("The 'Requestor'"):
                continue
            if raw.startswith("The balance listed") or raw.startswith("For information"):
                continue
            if raw.startswith("Transaction Report generated") or "ABN 11 005" in raw:
                continue
            if (date_range_text and raw.startswith(date_range_text)) or "Page " in raw:
                continue
            if raw.startswith("RECENT"):
                continue

            # Check for month+year header
            month_match = MONTH_HEADER_PATTERN.match(raw)
            if month_match:
                month_name = month_match.group(1)
                current_year = int(month_match.group(2))
                current_month_num = MONTH_MAP[month_name]
                continue

            # Check for "Total" row
            if raw.startswith("Total"):
                continue

            # Check for transaction date
            date_text = line["date_text"]
            date_match = DATE_PATTERN.match(date_text)

            if date_match:
                day = int(date_match.group(1))
                month_name = date_match.group(2)
                month_num = MONTH_MAP[month_name]

                # Determine year from context
                if current_year is not None:
                    year = current_year
                    if current_month_num is not None and month_num > current_month_num:
                        year = current_year - 1
                else:
                    year = recent_year

                try:
                    txn_date = date(year, month_num, day)
                except ValueError:
                    # Invalid date, skip
                    continue

                desc = line["desc_text"]
                withdrawal = _parse_amount(line["withdrawal_text"])
                deposit = _parse_amount(line["deposit_text"])

                txn = Transaction(
                    date=txn_date,
                    description=desc,
                    withdrawal=withdrawal,
                    deposit=deposit,
                    account_number=meta.account_number,
                    account_type=meta.account_type,
                    month=f"{txn_date.year}-{txn_date.month:02d}",
                )
                transactions.append(txn)

            elif line["desc_text"] and transactions:
                # Continuation line — append description to previous transaction
                extra = line["desc_text"].strip()
                if extra and extra != "blank":
                    transactions[-1].description += " " + extra

                # A continuation line might also have an amount (rare but possible)
                if line["withdrawal_text"]:
                    amt = _parse_amount(line["withdrawal_text"])
                    if amt and transactions[-1].withdrawal is None:
                        transactions[-1].withdrawal = amt
                if line["deposit_text"]:
                    amt = _parse_amount(line["deposit_text"])
                    if amt and transactions[-1].deposit is None:
                        transactions[-1].deposit = amt

    pdf.close()
    return meta, transactions


def validate_totals(
    transactions: list[Transaction],
    expected_withdrawals: Optional[float] = None,
    expected_deposits: Optional[float] = None,
) -> dict:
    """
    Validate parsed transaction totals against expected PDF footer values.

    Returns dict with parsed totals and match status.
    """
    total_withdrawals = sum(t.withdrawal or 0 for t in transactions)
    total_deposits = sum(t.deposit or 0 for t in transactions)

    result = {
        "parsed_withdrawals": round(total_withdrawals, 2),
        "parsed_deposits": round(total_deposits, 2),
        "transaction_count": len(transactions),
    }

    if expected_withdrawals is not None:
        result["expected_withdrawals"] = expected_withdrawals
        result["withdrawals_match"] = abs(total_withdrawals - expected_withdrawals) < 0.01
    if expected_deposits is not None:
        result["expected_deposits"] = expected_deposits
        result["deposits_match"] = abs(total_deposits - expected_deposits) < 0.01

    return result
