"""Tests for the month splitter module."""

import sys
from datetime import date
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.models.transaction import Transaction
from src.pipeline.month_splitter import split_by_month


class TestMonthSplitter:

    def test_basic_split(self):
        txns = [
            Transaction(date=date(2026, 1, 5), description="A", withdrawal=10.0),
            Transaction(date=date(2026, 1, 20), description="B", withdrawal=20.0),
            Transaction(date=date(2026, 2, 3), description="C", withdrawal=30.0),
            Transaction(date=date(2025, 12, 15), description="D", deposit=100.0),
        ]
        result = split_by_month(txns)
        assert set(result.keys()) == {"2025-12", "2026-01", "2026-02"}
        assert len(result["2026-01"]) == 2
        assert len(result["2026-02"]) == 1
        assert len(result["2025-12"]) == 1

    def test_sorted_within_month(self):
        txns = [
            Transaction(date=date(2026, 1, 20), description="Later", withdrawal=20.0),
            Transaction(date=date(2026, 1, 5), description="Earlier", withdrawal=10.0),
        ]
        result = split_by_month(txns)
        assert result["2026-01"][0].description == "Earlier"
        assert result["2026-01"][1].description == "Later"

    def test_months_sorted(self):
        txns = [
            Transaction(date=date(2026, 3, 1), description="Mar", withdrawal=10.0),
            Transaction(date=date(2025, 11, 20), description="Nov", withdrawal=10.0),
            Transaction(date=date(2026, 1, 10), description="Jan", withdrawal=10.0),
        ]
        result = split_by_month(txns)
        assert list(result.keys()) == ["2025-11", "2026-01", "2026-03"]

    def test_month_field_set(self):
        txns = [
            Transaction(date=date(2026, 2, 14), description="Valentine", withdrawal=50.0),
        ]
        result = split_by_month(txns)
        assert result["2026-02"][0].month == "2026-02"

    def test_empty_list(self):
        result = split_by_month([])
        assert result == {}
