"""Income/expense account selection and N-account ledger integration tests."""
import asyncio
from datetime import date
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "custom_components" / "bill_tracker"


def load(name, filename):
    spec = spec_from_file_location(name, ROOT / filename)
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ACCOUNTS = load("billy_accounts_for_income_tests", "accounts.py")
INCOME = load("billy_income_for_account_tests", "income.py")


class CombinedHarness(INCOME.IncomeMixin, ACCOUNTS.AccountMixin):
    def __init__(self):
        self.accounts = []
        self.payers = [{"id": "owner", "name": "Owner"}]
        self.default_account_id = None
        self.accounts_config = {}
        self.internal_transfers = []
        self.income_categories = []
        self.incomes = []
        self.income_rules = []
        self.expenses = []
        self._migrate_income()
        self._migrate_accounts()

    async def _save_and_notify(self):
        pass

    def _sort(self):
        self.incomes.sort(key=lambda item: item["expected_date"], reverse=True)


def run(awaitable):
    return asyncio.run(awaitable)


def account(manager, name, kind="checking"):
    return run(manager.async_add_account(
        name=name, account_type=kind, opening_balance=0,
        opening_date="2026-01-01", payer_id="owner",
    ))


def test_income_one_off_and_recurring_can_use_any_account():
    manager = CombinedHarness()
    bank = account(manager, "Bank")
    wallet = account(manager, "Wallet", "prepaid")
    cash = account(manager, "Cash", "cash")
    run(manager.async_add_income(
        description="Contract", category_id="other",
        expected_date="2026-01-10", estimated_amount=500,
        received=True, actual_amount=456.70, received_date="2026-01-10",
        account_id=wallet["id"],
    ))
    rule = run(manager.async_add_income_rule(
        name="Salary", category_id="salary", estimated_amount=2000,
        start_date="2026-01-27", interval_months=1, end_date="",
        amount_mode="fixed", active=True, note="", account_id=bank["id"],
    ))
    january = next(row for row in manager.incomes if row.get("rule_id") == rule["id"] and row["expected_date"] == "2026-01-27")
    assert january["account_id"] == bank["id"]
    updated = run(manager.async_update_income(
        january["id"], description="Salary", category_id="salary",
        expected_date="2026-01-27", estimated_amount=2000,
        received=True, actual_amount=1977.23, received_date="2026-01-27",
        account_id=cash["id"],
    ))
    assert updated["account_id"] == cash["id"]
    assert updated["account_manually_set"] is True
    assert manager.account_balances()["total"] == 2433.93
    parts = {row["id"]: row for row in manager.account_balances()["accounts"]}
    assert parts[wallet["id"]]["balance"] == 456.7
    assert parts[cash["id"]]["balance"] == 1977.23
    assert parts[bank["id"]]["balance"] == 0

    # Changing the default affects new income but not recorded receipts.
    run(manager.async_set_default_account(wallet["id"]))
    new = run(manager.async_add_income(
        description="Gift", category_id="other",
        expected_date="2026-01-12", estimated_amount=30,
        received=True, actual_amount=30, received_date="2026-01-12",
    ))
    assert new["account_id"] == wallet["id"]
    assert updated["account_id"] == cash["id"]
    assert manager.account_balances()["total"] == 2463.93


def test_recurring_rule_account_change_preserves_confirmed_and_manual_occurrences():
    manager = CombinedHarness()
    first = account(manager, "Salary bank")
    next_bank = account(manager, "Other bank")
    rule = run(manager.async_add_income_rule(
        name="Salary", category_id="salary", estimated_amount=2000,
        start_date="2026-01-27", interval_months=1, end_date="",
        amount_mode="fixed", active=True, note="", account_id=first["id"],
    ))
    jan = next(row for row in manager.incomes if row.get("rule_id") == rule["id"] and row["expected_date"] == "2026-01-27")
    feb = next(row for row in manager.incomes if row.get("rule_id") == rule["id"] and row["expected_date"] == "2026-02-27")
    mar = next(row for row in manager.incomes if row.get("rule_id") == rule["id"] and row["expected_date"] == "2026-03-27")
    run(manager.async_update_income(
        jan["id"], description=jan["description"], category_id=jan["category_id"],
        expected_date=jan["expected_date"], estimated_amount=jan["estimated_amount"],
        account_id=first["id"], received=True,
        actual_amount=1960, received_date="2026-01-27",
    ))
    run(manager.async_update_income(
        feb["id"], description=feb["description"], category_id=feb["category_id"],
        expected_date=feb["expected_date"], estimated_amount=feb["estimated_amount"],
        account_id=first["id"], received=False, note="Manual account unchanged",
    ))
    # First manually point March to first account? It is already first; mark
    # Feb as a manual override by changing its account to another account.
    run(manager.async_update_income(
        feb["id"], description=feb["description"], category_id=feb["category_id"],
        expected_date=feb["expected_date"], estimated_amount=feb["estimated_amount"],
        account_id=next_bank["id"], received=False,
    ))
    assert feb["account_manually_set"] is True
    run(manager.async_update_income_rule(
        rule["id"], name=rule["name"], category_id="salary", estimated_amount=2000,
        start_date="2026-01-27", interval_months=1, end_date="",
        amount_mode="fixed", active=True, note="", account_id=next_bank["id"],
    ))
    assert jan["account_id"] == first["id"]
    assert feb["account_id"] == next_bank["id"]
    assert mar["account_id"] == next_bank["id"]
    assert manager.account_balances()["total"] == 1960


def test_invalid_account_id_does_not_store_an_income():
    manager = CombinedHarness()
    account(manager, "Default")
    try:
        run(manager.async_add_income(
            description="Unexpected", category_id="other", expected_date="2026-02-05",
            estimated_amount=100, received=True, actual_amount=100,
            received_date="2026-02-05", account_id="not-an-account",
        ))
    except ValueError:
        pass
    else:
        raise AssertionError("Expected invalid account ID to be rejected")
    assert manager.incomes == []
