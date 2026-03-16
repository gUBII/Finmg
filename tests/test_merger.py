"""Tests for merge and internal transfer detection."""

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.models.transaction import Transaction
from src.pipeline.merger import detect_internal_transfers, merge_accounts


class TestMerger:

    def test_category_marked_internal_transfer_is_excluded_even_without_known_account(self):
        txn = Transaction(
            date=date(2025, 12, 10),
            description="ANZ M-BANKING FUNDS TFER TRANSFER 093292 FROM 178873749",
            deposit=49.0,
            category="Internal Transfer",
            is_internal_transfer=False,
        )

        detect_internal_transfers([txn])

        assert txn.is_internal_transfer is True

    def test_detect_internal_transfers_resets_stale_flags(self):
        txn = Transaction(
            date=date(2026, 1, 5),
            description="WOOLWORTHS/174 LAKEMBA ST LAKEMBA",
            withdrawal=20.0,
            category="Groceries",
            is_internal_transfer=True,
        )

        detect_internal_transfers([txn])

        assert txn.is_internal_transfer is False

    def test_merge_accounts_sorts_and_flags_transfers(self):
        monthly_data = {
            "178865319": {
                "2026-01": [
                    Transaction(
                        date=date(2026, 1, 20),
                        description="WOOLWORTHS",
                        withdrawal=20.0,
                        category="Groceries",
                        account_number="178865319",
                    )
                ]
            },
            "178870011": {
                "2026-01": [
                    Transaction(
                        date=date(2026, 1, 10),
                        description="ANZ M-BANKING FUNDS TFER TRANSFER 188441 TO 012401178870011",
                        withdrawal=100.0,
                        category="Internal Transfer",
                        account_number="178870011",
                    )
                ]
            },
        }

        merged = merge_accounts(monthly_data)

        assert list(merged.keys()) == ["2026-01"]
        assert [txn.date.isoformat() for txn in merged["2026-01"]] == ["2026-01-10", "2026-01-20"]
        assert merged["2026-01"][0].is_internal_transfer is True
