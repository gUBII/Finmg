"""Regex-based transaction categoriser using configurable keyword rules.

Categories match Renato's budget template exactly:
- Expense categories: Groceries, Fast food & Restaurant, Medicine (Webster), etc.
- Income categories: Savings, Disability Support Pension, Bonus, etc.
- Internal transfers are detected separately and excluded from budget totals.
"""

import json
from pathlib import Path
from typing import Optional

from src.models.transaction import Transaction

DEFAULT_CATEGORIES_PATH = Path(__file__).parent.parent / "config" / "categories.json"


def load_category_rules(path: Optional[str] = None) -> dict:
    """Load category rules from JSON file. Returns the full config dict."""
    config_path = Path(path) if path else DEFAULT_CATEGORIES_PATH
    with open(config_path) as f:
        return json.load(f)


def categorise_transaction(txn: Transaction, config: dict) -> str:
    """
    Categorise a single transaction using first-match-wins rules.

    For withdrawals → match against expense_categories
    For deposits → match against income_categories
    Internal transfers are detected by pattern match.
    Falls back to "Uncategorised".
    """
    desc_upper = txn.description.upper()

    # Check internal transfers first
    for pattern in config.get("internal_transfer_patterns", []):
        if pattern.upper() in desc_upper:
            return "Internal Transfer"

    if txn.withdrawal:
        # Match against expense categories
        for rule in config.get("expense_categories", []):
            for pattern in rule["patterns"]:
                if pattern.upper() in desc_upper:
                    return rule["name"]

        # Check subscriptions → map to Miscellaneous
        for pattern in config.get("subscription_patterns", []):
            if pattern.upper() in desc_upper:
                return "Miscellaneous"

        # Check fees → map to Miscellaneous
        for pattern in config.get("fee_patterns", []):
            if pattern.upper() in desc_upper:
                return "Miscellaneous"

    if txn.deposit:
        # Match against income categories
        for rule in config.get("income_categories", []):
            for pattern in rule["patterns"]:
                if pattern.upper() in desc_upper:
                    return rule["name"]

    return "Uncategorised"


def categorise_all(
    transactions: list[Transaction],
    config: Optional[dict] = None,
) -> list[Transaction]:
    """
    Apply category rules to all transactions.
    Modifies transactions in place and returns them.
    """
    if config is None:
        config = load_category_rules()

    for txn in transactions:
        txn.category = categorise_transaction(txn, config)
        txn.is_internal_transfer = txn.category == "Internal Transfer"

    return transactions


def get_category_summary(transactions: list[Transaction]) -> dict[str, dict]:
    """
    Summarise transactions by category.

    Returns dict mapping category name to:
        count, total_withdrawals, total_deposits
    """
    summary: dict[str, dict] = {}
    for txn in transactions:
        cat = txn.category
        if cat not in summary:
            summary[cat] = {"count": 0, "total_withdrawals": 0.0, "total_deposits": 0.0}
        summary[cat]["count"] += 1
        summary[cat]["total_withdrawals"] += txn.withdrawal or 0
        summary[cat]["total_deposits"] += txn.deposit or 0

    # Round totals
    for cat in summary:
        summary[cat]["total_withdrawals"] = round(summary[cat]["total_withdrawals"], 2)
        summary[cat]["total_deposits"] = round(summary[cat]["total_deposits"], 2)

    return dict(sorted(summary.items()))


def get_all_category_names(config: Optional[dict] = None) -> tuple[list[str], list[str]]:
    """Return (expense_category_names, income_category_names) from config."""
    if config is None:
        config = load_category_rules()
    expense = [r["name"] for r in config.get("expense_categories", [])]
    income = [r["name"] for r in config.get("income_categories", [])]
    return expense, income
