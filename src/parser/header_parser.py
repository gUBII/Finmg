"""Extract account metadata from the first page of an ANZ transaction report PDF."""

import re
from collections import defaultdict

import pdfplumber

from src.models.transaction import AccountMeta


def extract_account_meta(pdf_path: str) -> AccountMeta:
    """Parse the header section of page 0 to extract account metadata."""
    pdf = pdfplumber.open(pdf_path)
    page = pdf.pages[0]
    words = page.extract_words(x_tolerance=3, y_tolerance=3)

    # Group words into lines by y-coordinate
    lines = defaultdict(list)
    for w in words:
        y = round(float(w["top"]), 0)
        lines[y].append(w)

    sorted_ys = sorted(lines.keys())
    full_lines = []
    for y in sorted_ys:
        ws = sorted(lines[y], key=lambda w: w["x0"])
        text = " ".join(w["text"] for w in ws)
        full_lines.append(text)

    # Line 0: "Transaction Report"
    # Line 1: Account type (e.g. "ACCESS ACCOUNT")
    # Line 2: Date range (e.g. "15 November 2025 to 15 March 2026")
    # Then account name, BSB, account number, balance

    account_type = full_lines[1] if len(full_lines) > 1 else ""
    date_range = full_lines[2] if len(full_lines) > 2 else ""

    # Parse date range
    report_start = ""
    report_end = ""
    m = re.match(r"(\d+ \w+ \d{4}) to (\d+ \w+ \d{4})", date_range)
    if m:
        report_start = m.group(1)
        report_end = m.group(2)

    # Find account name - line starting with name (after "Account Name...")
    account_name = ""
    bsb = ""
    account_number = ""
    balance = 0.0

    for line_text in full_lines:
        # BSB and account number line
        bsb_match = re.match(r"^(\d{6})\s+(\d{9})\s+\$([0-9,.]+)", line_text)
        if bsb_match:
            bsb = bsb_match.group(1)
            account_number = bsb_match.group(2)
            balance = float(bsb_match.group(3).replace(",", ""))
            continue

        # Account name line (contains the actual name, comes after "Account Name..." header)
        if re.match(r"^[A-Z]{2,}\s+[A-Z]{2,}", line_text) and "Account" not in line_text and "Branch" not in line_text and "Transaction" not in line_text and "Date" not in line_text:
            # Extract just the account holder name (first two words typically)
            name_match = re.match(r"^([A-Z]+\s+[A-Z]+)", line_text)
            if name_match and not account_name:
                account_name = name_match.group(1)

    pdf.close()

    return AccountMeta(
        account_type=account_type,
        account_name=account_name,
        bsb=bsb,
        account_number=account_number,
        balance=balance,
        report_start=report_start,
        report_end=report_end,
        source_file=pdf_path,
    )
