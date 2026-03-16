"""Save and load checkpoint CSV/Excel files for pipeline steps."""

from datetime import date
from pathlib import Path

import pandas as pd

from src.models.transaction import Transaction


def transactions_to_dataframe(transactions: list[Transaction]) -> pd.DataFrame:
    """Convert a list of Transaction objects to a pandas DataFrame."""
    records = [t.to_dict() for t in transactions]
    df = pd.DataFrame(records)
    return df


def _is_blank(value) -> bool:
    """Return True for NaN/None and empty string values."""
    return pd.isna(value) or (isinstance(value, str) and not value.strip())


def _parse_date(value, row_number: int) -> date:
    """Parse a date-like cell from Streamlit/pandas into a date object."""
    if _is_blank(value):
        raise ValueError(f"Row {row_number}: Date is required")

    parsed = pd.to_datetime(value, errors="coerce")
    if pd.isna(parsed):
        raise ValueError(f"Row {row_number}: invalid date '{value}'")

    return parsed.date()


def _parse_string(value, default: str = "") -> str:
    """Convert cells to strings without turning NaN into the literal 'nan'."""
    if _is_blank(value):
        return default
    return str(value).strip()


def _parse_bool(value) -> bool:
    """Convert common spreadsheet/CSV truthy values into a stable boolean."""
    if _is_blank(value):
        return False
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)

    text = str(value).strip().lower()
    if text in {"true", "yes", "y", "1"}:
        return True
    if text in {"false", "no", "n", "0", ""}:
        return False
    return False


def dataframe_to_transactions(df: pd.DataFrame) -> list[Transaction]:
    """Convert a DataFrame back to Transaction objects."""
    transactions = []
    tracked_columns = [
        "Date",
        "Description",
        "Withdrawal",
        "Deposit",
        "Account",
        "Account Type",
        "Category",
        "Month",
        "Internal Transfer",
    ]

    for idx, row in df.iterrows():
        row_number = idx + 2
        if all(_is_blank(row.get(column)) for column in tracked_columns):
            continue

        txn_date = _parse_date(row.get("Date"), row_number)
        description = _parse_string(row.get("Description"))
        if not description:
            raise ValueError(f"Row {row_number}: Description is required")

        txn = Transaction(
            date=txn_date,
            description=description,
            withdrawal=float(row["Withdrawal"]) if pd.notna(row.get("Withdrawal")) else None,
            deposit=float(row["Deposit"]) if pd.notna(row.get("Deposit")) else None,
            account_number=_parse_string(row.get("Account")),
            account_type=_parse_string(row.get("Account Type")),
            category=_parse_string(row.get("Category"), "Uncategorised"),
            month=_parse_string(row.get("Month")),
            is_internal_transfer=_parse_bool(row.get("Internal Transfer")),
        )
        transactions.append(txn)
    return transactions


def save_checkpoint(
    transactions: list[Transaction],
    filepath: str,
) -> str:
    """Save transactions to a CSV checkpoint file."""
    df = transactions_to_dataframe(transactions)
    Path(filepath).parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(filepath, index=False)
    return filepath


def load_checkpoint(filepath: str) -> list[Transaction]:
    """Load transactions from a CSV checkpoint file."""
    df = pd.read_csv(filepath)
    return dataframe_to_transactions(df)
