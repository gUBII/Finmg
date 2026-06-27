"""Learning loop: promote stable manual overrides into the categoriser rules.

Reads the `category_overrides` audit log, extracts a merchant key from each
overridden transaction, and — for merchant-based, unambiguous signals —
proposes adding that key as a pattern to `config/categories.json` so future
uploads auto-categorise. The more Linda corrects, the less she corrects next
time.

Safety is enforced by SIMULATING the real categoriser, never by trusting the
extractor:

  1. Blocklist — one-off / context / PII classes are never learned
     (ATM cash deposits, person-to-person transfers, refunds, and any merchant
     deliberately left ambiguous by test policy, e.g. 7-ELEVEN).
  2. Consistency — every override sharing a merchant key must agree on the
     target category, else the key is skipped.
  3. Source-match — adding the candidate pattern must actually recategorise
     its own source transaction to the target (uses categorise_transaction).
  4. Conflict guard — the candidate must not match ANY transaction currently
     sitting in a *different* definite category (DB-wide scan). This is what
     makes auto-learning safe: a too-generic key is rejected automatically.

Dry-run by default. Pass --apply to write categories.json.

Run:
  source .venv/bin/activate && python3 scripts/learn_from_overrides.py
  source .venv/bin/activate && python3 scripts/learn_from_overrides.py --apply
"""

from __future__ import annotations

import argparse
import copy
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.db.database import get_connection
from src.models.transaction import Transaction
from src.pipeline.categoriser import categorise_transaction, load_category_rules

CATEGORIES_PATH = Path(__file__).resolve().parent.parent / "src" / "config" / "categories.json"

# Description classes we never learn from — one-off, context-dependent, PII, or
# deliberately ambiguous by test policy.
BLOCKLIST = [
    (re.compile(r"\bATM\b"), "ATM cash deposit — source varies"),
    (re.compile(r"MOBILE BANKING PAYMENT"), "person-to-person transfer (PII)"),
    (re.compile(r"\bREFUND\b"), "refund — not a recurring merchant"),
    (re.compile(r"PAYMENT FROM"), "inbound credit — not a merchant"),
    (re.compile(r"VISA DEBIT DEPOSIT"), "card deposit/refund — ambiguous"),
    (re.compile(r"7-ELEVEN"), "ambiguous fuel/food/tobacco — locked by test policy"),
]

# Method / network noise tokens stripped during merchant-key extraction.
_NOISE_TOKENS = {
    "EFTPOS", "VISA", "DEBIT", "CREDIT", "PURCHASE", "CARD", "ANZ", "MOBILE",
    "BANKING", "PAYMENT", "AU", "NSW", "NSWAU", "VIC", "QLD", "NS", "PTY",
    "LTD", "LT", "THE", "PURCHASES",
    # Payment-aggregator prefixes (Square, Stripe, PayPal, etc.).
    "SQ", "SP", "SMP", "ZLR", "PAYPAL",
}
_NETWORK_PREFIX = re.compile(r"^[A-Z]{2,4}\*")  # ZLR*, SMP*, SQ*, SP*, PAYPAL*…


def _merchant_key(description: str, max_words: int = 3) -> str | None:
    """Extract a distinctive merchant substring from a bank description.

    Returns a key that is a literal substring of description.upper() (so the
    real categoriser, which does `pattern in desc_upper`, will match it), or
    None if no usable merchant phrase survives cleaning.
    """
    raw = description.upper()
    tokens = re.split(r"[\s\\]+", raw)
    kept: list[str] = []
    for tok in tokens:
        tok = _NETWORK_PREFIX.sub("", tok)          # drop ZLR* / SMP* prefix
        tok = re.sub(r"\d+$", "", tok)               # trailing digits (store #s)
        tok = tok.strip("*#/.-")
        if not tok or tok in _NOISE_TOKENS:
            if kept:                                  # noise after merchant → stop
                break
            continue
        if any(c.isdigit() for c in tok):            # card/ref number token → stop
            if kept:
                break
            continue
        kept.append(tok)
        if len(kept) >= max_words:
            break
    # Shrink from the right until the phrase is a contiguous literal substring
    # of the raw description (suburb/location tokens often break contiguity).
    while kept:
        key = " ".join(kept)
        if key in raw:
            break
        kept.pop()
    else:
        return None
    # Reject too-generic keys: need at least one ≥4-char token to be distinctive.
    if max(len(t) for t in kept) < 4:
        return None
    return key if len(key) >= 4 else None


def _txn_from_row(row) -> Transaction:
    return Transaction(
        date=row["date"],
        description=row["description"],
        withdrawal=row["withdrawal"],
        deposit=row["deposit"],
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="write categories.json")
    args = ap.parse_args()

    conn = get_connection()
    # Latest override per transaction, joined to live transaction text.
    overrides = conn.execute(
        """
        SELECT o.transaction_id, o.new_category, t.date, t.description,
               t.withdrawal, t.deposit, t.category AS current_category
        FROM category_overrides o
        JOIN transactions t ON t.id = o.transaction_id
        WHERE o.id IN (
            SELECT MAX(id) FROM category_overrides GROUP BY transaction_id
        )
        """
    ).fetchall()
    all_txns = [_txn_from_row(r) for r in conn.execute(
        "SELECT date, description, withdrawal, deposit, category FROM transactions"
    ).fetchall()]
    db_cat = {  # description.upper() -> current category, for conflict scan
        r["description"].upper(): r["category"]
        for r in conn.execute("SELECT description, category FROM transactions").fetchall()
    }
    conn.close()

    config = load_category_rules()
    valid_expense = {r["name"] for r in config["expense_categories"]}
    valid_income = {r["name"] for r in config["income_categories"]}

    # 1. Group override signals by extracted merchant key.
    signals: dict[str, dict] = defaultdict(lambda: {"cats": set(), "rows": []})
    skipped_block: list[tuple[str, str]] = []
    for o in overrides:
        desc = o["description"]
        blocked = next((why for rx, why in BLOCKLIST if rx.search(desc.upper())), None)
        if blocked:
            skipped_block.append((desc, blocked))
            continue
        key = _merchant_key(desc)
        if not key:
            skipped_block.append((desc, "no distinctive merchant key"))
            continue
        signals[key]["cats"].add(o["new_category"])
        signals[key]["rows"].append(o)

    # 2-4. Validate each candidate via the real categoriser.
    learned: list[tuple[str, str]] = []        # (key, category)
    rejected: list[tuple[str, str]] = []
    for key, sig in sorted(signals.items()):
        if len(sig["cats"]) != 1:
            rejected.append((key, f"inconsistent categories {sig['cats']}"))
            continue
        cat = next(iter(sig["cats"]))
        if cat not in valid_expense and cat not in valid_income:
            rejected.append((key, f"'{cat}' not a budget category"))
            continue

        # Already covered by a category pattern?
        bucket = "expense_categories" if cat in valid_expense else "income_categories"
        existing = {p.upper() for r in config[bucket] for p in r["patterns"]}
        if any(p in key or key in p for p in existing):
            rejected.append((key, "already covered by an existing pattern"))
            continue
        # Already handled by fee / subscription rules (which map to Miscellaneous)?
        fee_subs = {p.upper() for p in
                    config.get("fee_patterns", []) + config.get("subscription_patterns", [])}
        if any(p in key for p in fee_subs):
            rejected.append((key, "already handled by fee/subscription rules"))
            continue

        # Source-match: does adding `key` recategorise its own rows to `cat`?
        trial = copy.deepcopy(config)
        target = next(r for r in trial[bucket] if r["name"] == cat)
        target["patterns"].append(key)
        ok = all(
            categorise_transaction(_txn_from_row(r), trial) == cat
            for r in sig["rows"]
        )
        if not ok:
            rejected.append((key, "pattern does not match its source row"))
            continue

        # Conflict guard: does `key` collide with a different definite category?
        conflict = next(
            (f"{desc_up} is '{c}'" for desc_up, c in db_cat.items()
             if key in desc_up and c not in (cat, "Uncategorised")),
            None,
        )
        if conflict:
            rejected.append((key, f"conflicts: {conflict}"))
            continue

        learned.append((key, cat))

    # Report.
    print("=== LEARNED (will be added as patterns) ===")
    for key, cat in learned:
        print(f"  + {key:<28} -> {cat}")
    print(f"\n=== REJECTED ({len(rejected)}) ===")
    for key, why in rejected:
        print(f"  - {key:<28} {why}")
    print(f"\n=== SKIPPED / not learnable ({len(skipped_block)}) ===")
    for desc, why in skipped_block:
        print(f"  · {desc[:46]:<46} {why}")

    if not learned:
        print("\nNothing to learn.")
        return 0

    if not args.apply:
        print(f"\nDry run. Re-run with --apply to add {len(learned)} pattern(s).")
        return 0

    # Apply immutably: load fresh, append, write back.
    data = json.loads(CATEGORIES_PATH.read_text())
    for key, cat in learned:
        bucket = "expense_categories" if cat in valid_expense else "income_categories"
        rule = next(r for r in data[bucket] if r["name"] == cat)
        if key not in rule["patterns"]:
            rule["patterns"].append(key)
    CATEGORIES_PATH.write_text(json.dumps(data, indent=2) + "\n")
    print(f"\nApplied {len(learned)} learned pattern(s) to {CATEGORIES_PATH.name}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
