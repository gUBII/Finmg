"""Tests for the categoriser module."""

import sys
from datetime import date
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.models.transaction import Transaction
from src.pipeline.categoriser import (
    categorise_transaction,
    categorise_all,
    load_category_rules,
    get_category_summary,
)


@pytest.fixture
def config():
    return load_category_rules()


class TestCategoriser:

    def test_groceries(self, config):
        txn = Transaction(date=date(2026, 1, 15), description="WOOLWORTHS/174 LAKEMBA ST LAKEMBA", withdrawal=50.0)
        assert categorise_transaction(txn, config) == "Groceries"

    def test_fuel(self, config):
        txn = Transaction(date=date(2026, 1, 15), description="AMPOL LAKEMBA", withdrawal=54.50)
        assert categorise_transaction(txn, config) == "Car & Petrol"

    def test_7eleven_is_uncategorised(self, config):
        """7-ELEVEN removed from Car & Petrol (ambiguous: fuel vs food vs tobacco)."""
        txn = Transaction(date=date(2026, 1, 15), description="7-ELEVEN 2268 LAKEMBA", withdrawal=54.50)
        assert categorise_transaction(txn, config) == "Uncategorised"

    def test_tobacco(self, config):
        txn = Transaction(date=date(2026, 1, 15), description="KPY*KING OF THE PACK L SYDNEY AU", withdrawal=15.31)
        assert categorise_transaction(txn, config) == "Nicotine & cigarettes"

    def test_internal_transfer(self, config):
        txn = Transaction(date=date(2026, 1, 15), description="ANZ M-BANKING FUNDS TFER TRANSFER 188441 TO 012401178870011", withdrawal=8085.75)
        assert categorise_transaction(txn, config) == "Internal Transfer"

    def test_salary_income(self, config):
        txn = Transaction(date=date(2026, 1, 15), description="PAY/SALARY FROM LACTALIS AUSTRAL WAGES00112535", deposit=371.42)
        assert categorise_transaction(txn, config) == "Other"

    def test_uncategorised(self, config):
        txn = Transaction(date=date(2026, 1, 15), description="RANDOM MERCHANT NOBODY KNOWS", withdrawal=10.0)
        assert categorise_transaction(txn, config) == "Uncategorised"

    def test_pharmacy(self, config):
        txn = Transaction(date=date(2026, 1, 15), description="PHARMACY 4 LESS LAKEMBA", withdrawal=7.70)
        assert categorise_transaction(txn, config) == "Medicine (PRN & Oil)"

    def test_atm_withdrawal(self, config):
        txn = Transaction(date=date(2026, 1, 15), description="ANZ ATM ROSELANDS BRANCH #1", withdrawal=300.0)
        assert categorise_transaction(txn, config) == "Personal Cashout"

    def test_fast_food(self, config):
        txn = Transaction(date=date(2026, 1, 15), description="HUNGRY JACKS WILEY PARK AU", withdrawal=27.95)
        assert categorise_transaction(txn, config) == "Fast food & Restaurant"

    def test_officeworks(self, config):
        txn = Transaction(date=date(2026, 1, 15), description="OFFICEWORKS LAKEMBA", withdrawal=33.11)
        assert categorise_transaction(txn, config) == "Office work & Stationary"

    def test_fashion(self, config):
        txn = Transaction(date=date(2026, 1, 15), description="KMART 1367 WILEY PARK", withdrawal=82.80)
        assert categorise_transaction(txn, config) == "Fashion & accessories"

    def test_eaaa_convenience_is_nicotine(self, config):
        """EAAA CONVENIENCE moved from subscriptions to Nicotine & cigarettes."""
        txn = Transaction(date=date(2026, 1, 15), description="EAAA CONVENIENCE PTY LTD LAKEMBA AU", withdrawal=10.0)
        assert categorise_transaction(txn, config) == "Nicotine & cigarettes"

    def test_subscription_as_miscellaneous(self, config):
        txn = Transaction(date=date(2026, 1, 15), description="NETFLIX.COM AU", withdrawal=16.99)
        assert categorise_transaction(txn, config) == "Miscellaneous"

    def test_categorise_all(self, config):
        txns = [
            Transaction(date=date(2026, 1, 15), description="WOOLWORTHS", withdrawal=50.0),
            Transaction(date=date(2026, 1, 16), description="ANZ M-BANKING FUNDS TFER TRANSFER 188441 TO 012401178870011", withdrawal=10.0),
            Transaction(date=date(2026, 1, 17), description="UNKNOWN SHOP", withdrawal=10.0),
        ]
        categorise_all(txns, config)
        assert txns[0].category == "Groceries"
        assert txns[1].category == "Internal Transfer"
        assert txns[1].is_internal_transfer is True
        assert txns[2].category == "Uncategorised"

    # --- new-pattern tests added when uncategorised transactions were triaged ---

    def test_bakers_delight_is_fast_food(self, config):
        txn = Transaction(date=date(2026, 5, 12), description="EFTPOS BAKERS DELIGHT MARRICKVILLE AU", withdrawal=10.60)
        assert categorise_transaction(txn, config) == "Fast food & Restaurant"

    def test_muffin_break_is_fast_food(self, config):
        txn = Transaction(date=date(2026, 3, 19), description="EFTPOS MUFFINBREAKBURWOOD BURWOOD AU", withdrawal=11.60)
        assert categorise_transaction(txn, config) == "Fast food & Restaurant"

    def test_yeeros_is_fast_food(self, config):
        txn = Transaction(date=date(2026, 6, 1), description="EFTPOS VICTORIA YEEROS MARRICKVILLE AU", withdrawal=9.14)
        assert categorise_transaction(txn, config) == "Fast food & Restaurant"

    def test_cwh_is_medicine(self, config):
        """CWH is the EFTPOS abbreviation for Chemist Warehouse."""
        txn = Transaction(date=date(2026, 3, 5), description="VISA DEBIT PURCHASE CARD 1216 CWH LAKEMBA LAKEMBA", withdrawal=50.98)
        assert categorise_transaction(txn, config) == "Medicine (PRN & Oil)"

    def test_specsavers_is_medicine(self, config):
        txn = Transaction(date=date(2026, 5, 13), description="VISA DEBIT PURCHASE CARD 6621 SPECSAVERS BURWOOD P/L BURWOOD", withdrawal=78.0)
        assert categorise_transaction(txn, config) == "Medicine (PRN & Oil)"

    def test_lindt_is_gifts(self, config):
        txn = Transaction(date=date(2026, 3, 2), description="EFTPOS LINDT AUSTRALIA HOMEBUSH AU", withdrawal=6.50)
        assert categorise_transaction(txn, config) == "Gifts  & Outing"

    def test_superbowl_is_gifts(self, config):
        txn = Transaction(date=date(2026, 6, 1), description="VISA DEBIT PURCHASE CARD 1216 SQ *STRATHFIELD SUPERBOWL STRATHFIELD S", withdrawal=12.24)
        assert categorise_transaction(txn, config) == "Gifts  & Outing"

    def test_greater_union_is_gifts(self, config):
        txn = Transaction(date=date(2026, 5, 26), description="VISA DEBIT PURCHASE CARD 6621 GREATER UNION BURWOO BURWOOD", withdrawal=17.80)
        assert categorise_transaction(txn, config) == "Gifts  & Outing"

    def test_yd_is_fashion(self, config):
        txn = Transaction(date=date(2026, 3, 2), description="EFTPOS YD PTY LTD 632 HOMEBUSH AU", withdrawal=119.94)
        assert categorise_transaction(txn, config) == "Fashion & accessories"

    def test_barber_is_fashion(self, config):
        txn = Transaction(date=date(2026, 3, 23), description="VISA DEBIT PURCHASE CARD 1216 SQ *BARBER CRAFT BURWOOD", withdrawal=50.70)
        assert categorise_transaction(txn, config) == "Fashion & accessories"

    def test_newsagency_is_office(self, config):
        txn = Transaction(date=date(2026, 2, 9), description="EFTPOS NEWSAGENCY BURWOOD WESTFIBURWOOD AU", withdrawal=39.30)
        assert categorise_transaction(txn, config) == "Office work & Stationary"

    def test_post_shop_is_office(self, config):
        txn = Transaction(date=date(2026, 5, 11), description="VISA DEBIT PURCHASE CARD 1216 POST ROSELANDS POST SH ROSELANDS", withdrawal=34.0)
        assert categorise_transaction(txn, config) == "Office work & Stationary"

    def test_reddy_express_is_car(self, config):
        txn = Transaction(date=date(2026, 2, 9), description="EFTPOS REDDY EXPRESS 1569 GREENACRE AU", withdrawal=22.86)
        assert categorise_transaction(txn, config) == "Car & Petrol"

    def test_get_fish_glebe_is_groceries(self, config):
        """GET FISH (Glebe) did not match the old GET FISH PTY LTD pattern."""
        txn = Transaction(date=date(2026, 4, 7), description="EFTPOS GET FISH \\GLEBE AU", withdrawal=13.50)
        assert categorise_transaction(txn, config) == "Groceries"

    def test_account_servicing_fee_is_miscellaneous(self, config):
        txn = Transaction(date=date(2026, 2, 27), description="ACCOUNT SERVICING FEE MINIMUM $2000 IN DEPOSITS NOT RECEIVED", withdrawal=5.0)
        assert categorise_transaction(txn, config) == "Miscellaneous"

    def test_category_summary(self, config):
        txns = [
            Transaction(date=date(2026, 1, 15), description="WOOLWORTHS", withdrawal=50.0, category="Groceries"),
            Transaction(date=date(2026, 1, 16), description="COLES", withdrawal=30.0, category="Groceries"),
            Transaction(date=date(2026, 1, 17), description="UNKNOWN", withdrawal=10.0, category="Uncategorised"),
        ]
        summary = get_category_summary(txns)
        assert summary["Groceries"]["count"] == 2
        assert summary["Groceries"]["total_withdrawals"] == 80.0
