# Parser Bugs — Investigation Log

Originally surfaced during the 2026-06-09 UAT cycle on Budget_2026-02_February.xlsx and
Budget_2026-04_April.xlsx. Re-investigated 2026-06-09 against the source PDFs; both
original diagnoses were wrong. Real root cause + fix below.

## ~~Bug 1: Phantom duplicate rows from continuation-line bleed~~ (NOT A BUG)

**Original claim:** PDF page 6 of `living_account(feb2026-jun2026).pdf` shows one
`20 FEB ANZ ATM ROSELANDS BRANCH $400` line, but the DB has two `$400` rows on
2026-02-20, one with a `LINDA JANE TRAVIA 0405211554` suffix → parser duplicating.

**Reality:** The two `$400` rows are on **different accounts**:
- `437669532` (LIVING — Ron's): `ANZ ATM ROSELANDS BRANCH #2 ROSELANDS NS` — $400
- `178865319` (SPENDING — Linda's card): `ANZ ATM ROSELANDS BRANCH #2 ROSELANDS NS LINDA JANE TRAVIA 0405211554` — $400

Both transactions appear exactly once in their respective PDFs. The "LINDA JANE TRAVIA"
suffix is in the ANZ-generated PDF text itself (cardholder identification on Linda's
withdrawal). Two real people, two real withdrawals, same ATM, same day. Not duplication.

**Resolution:** Closed. No parser change needed.

## Bug 2: Disclaimer-page text bleeding into the last transaction (REAL — fix below)

**Symptom:** The final transaction of each PDF has the last page's disclaimer block
appended to its `description`, producing 500–700-character descriptions. Live impact
on `data/finmg.db`:

| id  | account     | length | excerpt                                                                    |
|-----|-------------|--------|----------------------------------------------------------------------------|
| 160 | 178865319   | 728    | `... COCACOLAEPP LIVERPOOL such as pending transactions, reversals ...`     |
| 2   | 437669532   | 719    | `... EFTPOS NEWSAGENCY BURWOOD ... such as pending transactions ...`        |
| 363 | 178870011   | 556    | `... ANZ M-BANKING FUNDS TFER TRANSFER 417924 FROM 437669532 such as ...`   |

**Root cause:** `src/parser/pdf_extractor.py:207-221` (the `elif line["desc_text"] and
transactions:` continuation-line branch) appends any non-dated line with description
text onto `transactions[-1]`. The parser carries `transactions[-1]` across page
boundaries, so the disclaimer text on the final page bleeds onto the previous
page's last transaction. The existing skip list at lines 136-155 catches most
disclaimer fragments, but fragments like "transactions, such as pending..." (lowercase
'transactions,' not 'Transactions') and "The date shown may..." slip through.

**Original mis-diagnosis:** Original TODO claimed this was a "description column
right-boundary" bleed. It's not — the lines column-classify cleanly. The bleed is a
**page-boundary / continuation-eligibility** issue, not a column-boundary issue.

**Fix approach (structural, not whack-a-mole):**

1. Reset continuation-eligibility at the start of each page.
2. Set eligibility True after each successful dated-row parse.
3. Set eligibility False when we hit the `Total` row (natural end-of-table marker).
4. Gate the continuation branch on this flag.

Why not just expand the skip-pattern list? The list is whack-a-mole — ANZ disclaimer
text drifts between statement versions, and we'd be one wording change away from
re-introducing the bug. The structural fix makes the skip-list defense-in-depth.

**Severity:** Was MEDIUM cosmetic; downgraded to LOW for accounting (length-bleed is
purely description-side and doesn't affect amount totals or categorisation matching).
But the malformed descriptions look unprofessional in NCAT-facing budgets.
