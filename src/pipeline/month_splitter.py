"""Split a flat list of transactions into monthly buckets by date."""

from collections import defaultdict

from src.models.transaction import Transaction


def split_by_month(transactions: list[Transaction]) -> dict[str, list[Transaction]]:
    """
    Split transactions into monthly buckets.

    Args:
        transactions: Flat list of transactions

    Returns:
        Dict mapping YYYY-MM strings to lists of transactions, sorted by date.
    """
    buckets: dict[str, list[Transaction]] = defaultdict(list)

    for txn in transactions:
        month_key = f"{txn.date.year}-{txn.date.month:02d}"
        txn.month = month_key
        buckets[month_key].append(txn)

    # Sort each bucket by date
    for month_key in buckets:
        buckets[month_key].sort(key=lambda t: t.date)

    # Return sorted by month key
    return dict(sorted(buckets.items()))
