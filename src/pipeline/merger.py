"""Merge transactions from multiple accounts into unified monthly views."""

from src.models.transaction import Transaction

# Known account numbers for internal transfer detection
KNOWN_ACCOUNTS = {"178865319", "178870011", "437669532"}


def detect_internal_transfers(transactions: list[Transaction]) -> list[Transaction]:
    """
    Flag transactions that are internal transfers between tracked accounts.

    Detection: description contains "FUNDS TFER" or "TRANSFER" plus a known
    account number (BSB+account concatenated).
    """
    for txn in transactions:
        desc = txn.description.upper()
        txn.is_internal_transfer = txn.category == "Internal Transfer"

        if txn.is_internal_transfer:
            continue

        if "FUNDS TFER" in desc or "TRANSFER" in desc:
            for acct in KNOWN_ACCOUNTS:
                if acct in desc:
                    txn.is_internal_transfer = True
                    break
    return transactions


def merge_accounts(
    monthly_data: dict[str, dict[str, list[Transaction]]],
) -> dict[str, list[Transaction]]:
    """
    Merge transactions from multiple accounts per month.

    Args:
        monthly_data: dict mapping account_number → {month → [transactions]}

    Returns:
        dict mapping month → merged sorted [transactions] (all accounts)
    """
    merged: dict[str, list[Transaction]] = {}

    # Collect all months across all accounts
    all_months = set()
    for acct_months in monthly_data.values():
        all_months.update(acct_months.keys())

    for month in sorted(all_months):
        month_txns: list[Transaction] = []
        for acct_months in monthly_data.values():
            if month in acct_months:
                month_txns.extend(acct_months[month])

        # Sort by date, then by account
        month_txns.sort(key=lambda t: (t.date, t.account_number))

        # Detect internal transfers
        detect_internal_transfers(month_txns)

        merged[month] = month_txns

    return merged
