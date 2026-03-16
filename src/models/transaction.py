"""Data models for bank transactions and account metadata."""

from dataclasses import dataclass, field
from datetime import date
from typing import Optional


@dataclass
class AccountMeta:
    """Metadata extracted from the PDF header."""
    account_type: str          # e.g. "ACCESS ACCOUNT", "PROGRESS SAVER"
    account_name: str          # e.g. "GENTILI RENATO"
    bsb: str                   # e.g. "012401"
    account_number: str        # e.g. "178865319"
    balance: float             # Balance as of report date
    report_start: str          # e.g. "15 November 2025"
    report_end: str            # e.g. "15 March 2026"
    source_file: str = ""      # Original PDF filename


@dataclass
class Transaction:
    """A single bank transaction."""
    date: date
    description: str
    withdrawal: Optional[float] = None
    deposit: Optional[float] = None
    account_number: str = ""
    account_type: str = ""
    category: str = "Uncategorised"
    month: str = ""            # YYYY-MM
    is_internal_transfer: bool = False

    @property
    def amount(self) -> float:
        """Signed amount: negative for withdrawals, positive for deposits."""
        if self.withdrawal:
            return -self.withdrawal
        if self.deposit:
            return self.deposit
        return 0.0

    def to_dict(self) -> dict:
        return {
            "Date": self.date.isoformat(),
            "Description": self.description,
            "Withdrawal": self.withdrawal,
            "Deposit": self.deposit,
            "Account": self.account_number,
            "Account Type": self.account_type,
            "Category": self.category,
            "Month": self.month,
            "Internal Transfer": self.is_internal_transfer,
        }
