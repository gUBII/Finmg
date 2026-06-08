"""Regression test for the disclaimer-page bleed fix in pdf_extractor.

The bug: the disclaimer text on the final PDF page (page 10 of an ANZ
statement) bled across the page boundary onto `transactions[-1]`, producing
500-700 character descriptions on the last transaction of each PDF.

The fix: continuation-eligibility resets at each page boundary and on the
`Total` row, so footer/disclaimer text can no longer attach to a transaction
from the previous page.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.parser.pdf_extractor import extract_transactions

LIVE_PDF_DIR = Path(__file__).parent.parent / "data" / "raw_pdf"

LIVE_PDFS = [
    "living_account(feb2026-jun2026).pdf",
    "spending_account(feb2026-jun2026).pdf",
    "savings_account(feb2026-jun2026).pdf",
]

# Threshold above any legitimate continuation (longest real one in current
# data is ~77 chars: NON-ANZ ATM ... INCLUDES ATM OPER...) but well below
# any disclaimer bleed (those were 500+ chars).
MAX_LEGITIMATE_DESCRIPTION_LEN = 150


def _live_pdf(name: str) -> Path:
    return LIVE_PDF_DIR / name


@pytest.mark.skipif(
    not LIVE_PDF_DIR.exists() or not all(_live_pdf(n).exists() for n in LIVE_PDFS),
    reason="Live ANZ PDFs not present (data/ is gitignored)",
)
class TestDisclaimerBleedRegression:

    @pytest.mark.parametrize("pdf_name", LIVE_PDFS)
    def test_no_description_exceeds_legitimate_length(self, pdf_name):
        _, txns = extract_transactions(str(_live_pdf(pdf_name)))
        too_long = [t for t in txns if len(t.description) > MAX_LEGITIMATE_DESCRIPTION_LEN]
        assert not too_long, (
            f"{pdf_name}: {len(too_long)} transactions have descriptions over "
            f"{MAX_LEGITIMATE_DESCRIPTION_LEN} chars. First offender: "
            f"len={len(too_long[0].description)} desc={too_long[0].description[:120]!r}"
        )

    @pytest.mark.parametrize("pdf_name", LIVE_PDFS)
    def test_no_disclaimer_phrases_in_descriptions(self, pdf_name):
        """Defence-in-depth: specific disclaimer phrases must not appear in any description."""
        _, txns = extract_transactions(str(_live_pdf(pdf_name)))
        disclaimer_phrases = [
            "such as pending transactions",
            "ANZ App, Internet Banking",
            "balance amount displayed",
            "anz.com.au/support",
            "effective date of the transaction",
        ]
        for txn in txns:
            for phrase in disclaimer_phrases:
                assert phrase not in txn.description, (
                    f"{pdf_name}: disclaimer phrase {phrase!r} bled into transaction "
                    f"{txn.date} desc={txn.description[:120]!r}"
                )
