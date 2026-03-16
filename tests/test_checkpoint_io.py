"""Tests for checkpoint DataFrame conversion."""

import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.checkpoints.checkpoint_io import dataframe_to_transactions


class TestCheckpointIO:

    def test_ignores_completely_blank_rows(self):
        df = pd.DataFrame(
            [
                {
                    "Date": "2026-01-01",
                    "Description": "WOOLWORTHS",
                    "Withdrawal": 10.0,
                    "Deposit": None,
                    "Account": "123",
                    "Account Type": "ACCESS ACCOUNT",
                    "Category": "Groceries",
                    "Month": "2026-01",
                    "Internal Transfer": False,
                },
                {
                    "Date": None,
                    "Description": None,
                    "Withdrawal": None,
                    "Deposit": None,
                    "Account": None,
                    "Account Type": None,
                    "Category": None,
                    "Month": None,
                    "Internal Transfer": None,
                },
            ]
        )

        txns = dataframe_to_transactions(df)

        assert len(txns) == 1
        assert txns[0].description == "WOOLWORTHS"

    def test_invalid_dates_raise_clear_error(self):
        df = pd.DataFrame(
            [
                {
                    "Date": "not-a-date",
                    "Description": "WOOLWORTHS",
                    "Withdrawal": 10.0,
                    "Deposit": None,
                }
            ]
        )

        with pytest.raises(ValueError, match="Row 2: invalid date 'not-a-date'"):
            dataframe_to_transactions(df)

    def test_blank_description_raises_clear_error(self):
        df = pd.DataFrame(
            [
                {
                    "Date": "2026-01-01",
                    "Description": " ",
                    "Withdrawal": 10.0,
                    "Deposit": None,
                }
            ]
        )

        with pytest.raises(ValueError, match="Row 2: Description is required"):
            dataframe_to_transactions(df)
