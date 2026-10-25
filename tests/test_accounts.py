"""Regression tests for user-defined N-account cash ledger and legacy migration."""
import asyncio
from datetime import date
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "custom_components" / "bill_tracker" / "accounts.py"
SPEC = spec_from_file_location("billy_accounts_harness", SOURCE)
MODULE = module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class AccountsHarness(MODULE.AccountMixin):
    def __init__(self):
        self.accounts = []
        self.payers = [{"id": "owner", "name": "Owner"}]
        self.default_account_id = None
        self.accounts_config = {}
        self.internal_transfers = []
        self.incomes = []
        self.income_rules = []
        self.expenses = []
        self.save_count = 0
        self._migrate_accounts()

    async def _save_and_notify(self):
        self.save_count += 1


def run(coro):
    return asyncio.run(coro)


def add(manager, name="Joint account", kind="checking", initial=100, opening="2026-01-01",
        default=False, payer_id="owner"):
    return run(manager.async_add_account(
        name=name, account_type=kind, opening_balance=initial,
        opening_date=opening, make_default=default, payer_id=payer_id,
    ))


def transfer(manager, source, target, amount=20.14, on="2026-01-20"):
    return run(manager.async_add_internal_transfer(
        from_account=source, to_account=target,
        amount=amount, transfer_date=on, note="Transfer",
    ))


def balance(manager, account_id, as_of=date(2026, 10, 18)):
    result = manager.account_balances(as_of)
    return next(item for item in result["accounts"] if item["id"] == account_id)


def test_balance_adjustment_preserves_opening_and_past_balances():
    manager = AccountsHarness()
    account = add(manager, initial=100)
    result = run(manager.async_adjust_account_balance(account["id"], balance=125.25, note="Correction"))
    assert result["adjusted"] is True
    assert result["movement"]["type"] == "income"
    assert result["movement"]["amount"] == 25.25
    assert manager.account(account["id"])["opening_balance"] == 100
    assert manager.account_balances()["total"] == 125.25
    assert manager.account_balances()["accounts"][0]["manual_income"] == 25.25
    assert manager.account_balances()["accounts"][0]["manual_expenses"] == 0
    assert manager.account_balances()["accounts"][0]["income"] == 0
    assert manager.account_balances()["accounts"][0]["expenses"] == 0
    assert balance(manager, account["id"], date(2026, 1, 2))["balance"] == 100
    assert manager._migrate_accounts() is False
    assert manager.account_balances()["total"] == 125.25
    correction = run(manager.async_adjust_account_balance(
        account["id"], balance=90.10, note="Purchase outside Billy",
    ))
    assert correction["movement"]["type"] == "expense"
    assert correction["movement"]["amount"] == -35.15
    assert manager.account_balances()["total"] == 90.10
    assert manager.account_balances()["accounts"][0]["manual_expenses"] == 35.15
    assert balance(manager, account["id"], date(2026, 1, 2))["balance"] == 100
    with pytest.raises(ValueError, match="adjustment history"):
        run(manager.async_delete_account(account["id"]))
    assert run(manager.async_adjust_account_balance(account["id"], balance=90.10))["adjusted"] is False
    assert len(manager.account(account["id"])["balance_adjustments"]) == 2


def test_manual_movements_do_not_change_real_receipts_or_paid_bills():
    manager = AccountsHarness()
    item = add(manager, "Bank", initial=100)
    manager.incomes.append({
        "account_id": item["id"], "received": True, "actual_amount": 30,
        "received_date": "2026-01-20",
    })
    manager.expenses.append({
        "account_id": item["id"], "paid": True, "amount": 10,
        "payment_date": "2026-01-25",
    })
    run(manager.async_adjust_account_balance(item["id"], balance=150))
    row = manager.account_balances()["accounts"][0]
    assert row["income"] == 30
    assert row["expenses"] == 10
    assert row["manual_income"] == 30
    assert row["manual_expenses"] == 0
    assert row["balance"] == 150
    assert len(manager.incomes) == len(manager.expenses) == 1
    assert manager.incomes[0]["actual_amount"] == 30
    assert manager.expenses[0]["amount"] == 10


def test_legacy_signed_adjustments_migrate_to_dated_income_and_expense():
    manager = AccountsHarness()
    item = add(manager, initial=100)
    manager.account(item["id"])["balance_adjustments"] = [
        {"id": "old", "date": "2026-02-01", "amount": -12.5, "note": "Old correction"},
        {"id": "new", "date": "2026-02-02", "amount": 7.25, "note": ""},
    ]
    assert manager._migrate_accounts()
    assert [row["type"] for row in manager.account(item["id"])["balance_adjustments"]] == [
        "expense", "income",
    ]
    assert manager._migrate_accounts() is False
    assert balance(manager, item["id"], date(2026, 1, 31))["balance"] == 100
    assert balance(manager, item["id"], date(2026, 2, 1))["balance"] == 87.5
    assert balance(manager, item["id"], date(2026, 2, 2))["balance"] == 94.75
    with pytest.raises(ValueError, match="exclude balance adjustments"):
        run(manager.async_update_account(
            item["id"], name=item["name"], account_type="checking",
            opening_date="2026-03-01", opening_balance=100, payer_id="owner",
        ))


@pytest.mark.parametrize("balance", [float("nan"), float("inf"), 100.001, 1e12])
def test_invalid_manual_balance_does_not_record_or_save(balance):
    manager = AccountsHarness()
    item = add(manager)
    saved = manager.save_count
    with pytest.raises(ValueError):
        run(manager.async_adjust_account_balance(item["id"], balance=balance))
    assert manager.save_count == saved
    assert not manager.account(item["id"]).get("balance_adjustments")


def test_accounts_start_empty_and_have_no_fabricated_balances():
    manager = AccountsHarness()
    result = manager.account_balances()
    assert not result["configured"]
    assert result["total"] is None
    assert result["accounts"] == []
    assert manager.default_account_id is None
    with pytest.raises(ValueError, match="missing account"):
        transfer(manager, "checking", "savings")


def test_account_requires_valid_payer_and_supports_reassignment():
    manager = AccountsHarness()
    manager.payers.append({"id": "partner", "name": "Partner"})
    with pytest.raises(ValueError, match="existing payer"):
        add(manager, payer_id="")
    with pytest.raises(ValueError, match="existing payer"):
        add(manager, payer_id="unknown")
    assert manager.accounts == []
    item = add(manager)
    assert item["payer_id"] == "owner"
    updated = run(manager.async_update_account(
        item["id"], name=item["name"], account_type=item["account_type"],
        opening_balance=item["opening_balance"], opening_date=item["opening_date"],
        payer_id="partner",
    ))
    assert updated["payer_id"] == "partner"
    with pytest.raises(ValueError, match="existing payer"):
        run(manager.async_update_account(
            item["id"], name="Modified", account_type="cash",
            opening_balance=5, opening_date=item["opening_date"],
            payer_id="unknown",
        ))
    assert manager.account(item["id"])["name"] == item["name"]


def test_legacy_accounts_get_an_owner_without_changing_balances():
    manager = AccountsHarness()
    manager.payers = []
    manager.accounts = [{
        "id": "legacy", "name": "Old bank", "account_type": "checking",
        "opening_balance": 140, "opening_date": "2026-01-01",
    }]
    assert manager._migrate_accounts()
    assert len(manager.payers) == 1
    assert manager.accounts[0]["payer_id"] == manager.payers[0]["id"]
    assert balance(manager, "legacy")["balance"] == 140
    assert manager._migrate_accounts() is False
    manager.accounts[0]["payer_id"] = "deleted-payer"
    with pytest.raises(ValueError, match="existing payer"):
        manager._migrate_accounts()


def test_unlimited_user_defined_account_types_and_distinct_ids():
    manager = AccountsHarness()
    rows = [
        add(manager, "Family bank", initial=1000),
        add(manager, "Vacation cash", kind="cash", initial=500),
        add(manager, "Digital wallet", kind="prepaid", initial=320),
        add(manager, "Investments", kind="portfolio", initial=1700),
    ]
    ids = [item["id"] for item in rows]
    assert len(ids) == len(set(ids)) == 4
    assert manager.default_account_id == ids[0]
    assert manager.account_balances()["total"] == 3520
    assert len(manager.account_balances()["accounts"]) == 4
    assert balance(manager, ids[-1])["account_type"] == "portfolio"
    with pytest.raises(ValueError, match="name already exists"):
        add(manager, "family BANK")
    with pytest.raises(ValueError, match="Account name"):
        add(manager, "")
    with pytest.raises(ValueError, match="Opening date"):
        add(manager, "Future", opening="2190-01-01")


def test_transfers_between_arbitrary_accounts_keep_combined_total():
    manager = AccountsHarness()
    a = add(manager, "Cash", kind="cash", initial=1000)
    b = add(manager, "Wallet", kind="prepaid", initial=500)
    c = add(manager, "Card", kind="credit", initial=250)
    initial_total = manager.account_balances()["total"]
    first = transfer(manager, a["id"], b["id"], 300.15)
    second = transfer(manager, b["id"], c["id"], 90.20)
    third = transfer(manager, c["id"], a["id"], 40.05)
    assert balance(manager, a["id"])["balance"] == 739.9
    assert balance(manager, b["id"])["balance"] == 709.95
    assert balance(manager, c["id"])["balance"] == 300.15
    assert manager.account_balances()["total"] == initial_total
    assert all(value["income"] == value["expenses"] == 0 for value in manager.account_balances()["accounts"])

    run(manager.async_update_internal_transfer(
        first["id"], from_account=c["id"], to_account=b["id"],
        amount=12.07, transfer_date="2026-01-20", note="Fixed",
    ))
    assert manager.account_balances()["total"] == initial_total
    assert run(manager.async_delete_internal_transfer(second["id"]))
    assert manager.account_balances()["total"] == initial_total
    assert manager.account_balances()["default_account_id"] == a["id"]
    assert len(manager.internal_transfers) == 2


def test_paid_bills_and_confirmed_income_use_selected_account_only():
    manager = AccountsHarness()
    cash = add(manager, "Cash", kind="cash", initial=100)
    card = add(manager, "Prepaid card", kind="prepaid", initial=250)
    manager.incomes = [
        {"received": True, "actual_amount": 2450.37, "received_date": "2026-01-10",
         "account_id": card["id"]},
        {"received": False, "estimated_amount": 80000, "expected_date": "2026-01-11",
         "account_id": cash["id"]},
        {"received": True, "actual_amount": 99, "received_date": "2026-01-11",
         "account_id": card["id"], "voided": True},
        {"received": True, "actual_amount": 999, "received_date": "2026-02-01",
         "account_id": cash["id"]},
    ]
    manager.expenses = [
        {"paid": True, "amount": 79.95, "payment_date": "2026-01-12",
         "account_id": cash["id"]},
        {"paid": True, "amount": 45.10, "payment_date": "2026-01-13",
         "account_id": card["id"]},
        {"paid": True, "amount": 4000, "payment_date": "2026-01-12",
         "account_id": card["id"], "is_placeholder": True},
        {"paid": False, "amount": 50000, "account_id": cash["id"]},
    ]
    result = manager.account_balances(date(2026, 1, 31))
    assert balance(manager, cash["id"], date(2026, 1, 31))["balance"] == 20.05
    assert balance(manager, card["id"], date(2026, 1, 31))["balance"] == 2655.27
    assert result["total"] == 2675.32
    assert balance(manager, cash["id"])["income"] == 999.0


def test_change_default_affects_new_records_not_historical():
    manager = AccountsHarness()
    first = add(manager, "Home bank")
    another = add(manager, "New bank")
    manager.incomes.append({"account_id": first["id"], "received": True,
                            "actual_amount": 35, "received_date": "2026-01-20"})
    run(manager.async_set_default_account(another["id"]))
    assert manager._resolve_account_id() == another["id"]
    assert manager.incomes[0]["account_id"] == first["id"]
    assert balance(manager, first["id"])["balance"] == 135
    assert balance(manager, another["id"])["balance"] == 100


@pytest.mark.parametrize("source,target,amount,on", [
    ("same", "same", 1, "2026-02-02"),
    ("", "B", 1, "2026-02-02"),
    ("A", "ghost", 1, "2026-02-02"),
    ("A", "B", 0, "2026-02-02"),
    ("A", "B", -1, "2026-02-02"),
    ("A", "B", 1.001, "2026-02-02"),
    ("A", "B", float("nan"), "2026-02-02"),
    ("A", "B", float("inf"), "2026-02-02"),
    ("A", "B", 12, "2025-12-31"),
    ("A", "B", 12, "2200-01-01"),
    ("A", "B", 12, "invalid"),
])
def test_invalid_transfers_are_atomic(source, target, amount, on):
    manager = AccountsHarness()
    manager.accounts = [
        {"id": "A", "name": "A", "account_type": "cash",
         "opening_balance": 100, "opening_date": "2026-01-01"},
        {"id": "B", "name": "B", "account_type": "cash",
         "opening_balance": 100, "opening_date": "2026-01-01"},
    ]
    manager.default_account_id = "A"
    with pytest.raises(ValueError):
        transfer(manager, source, target, amount, on)
    assert manager.internal_transfers == []
    assert manager.account_balances()["total"] == 200


def test_late_opening_account_prevents_backdated_transfers():
    manager = AccountsHarness()
    first = add(manager, "Old", initial=0, opening="2026-01-01")
    later = add(manager, "New", initial=0, opening="2026-07-01")
    with pytest.raises(ValueError, match="predates"):
        transfer(manager, first["id"], later["id"], 15, "2026-02-01")
    existing = transfer(manager, first["id"], later["id"], 15, "2026-07-02")
    with pytest.raises(ValueError, match="New opening date"):
        run(manager.async_update_account(
            later["id"], name="New", account_type="cash",
            opening_balance=0, opening_date="2026-08-01", payer_id="owner",
        ))
    assert len(manager.internal_transfers) == 1
    assert existing["amount"] == 15


def test_cannot_move_opening_date_past_recorded_income_or_bill():
    manager = AccountsHarness()
    account = add(manager, "Main", initial=100, opening="2026-01-01")
    manager.incomes.append({
        "account_id": account["id"], "received": True, "voided": False,
        "received_date": "2026-01-14", "actual_amount": 60,
    })
    with pytest.raises(ValueError, match="recorded income"):
        run(manager.async_update_account(
            account["id"], name="Main", account_type="checking",
            opening_date="2026-02-01", opening_balance=160, payer_id="owner",
        ))
    manager.incomes.clear()
    manager.expenses.append({
        "account_id": account["id"], "paid": True, "is_placeholder": False,
        "payment_date": "2026-01-25", "amount": 20,
    })
    with pytest.raises(ValueError, match="paid bills"):
        run(manager.async_update_account(
            account["id"], name="Main", account_type="checking",
            opening_date="2026-02-01", opening_balance=80, payer_id="owner",
        ))
    assert manager.account(account["id"])["opening_date"] == "2026-01-01"


def test_cannot_delete_account_with_linked_history_or_transfers():
    manager = AccountsHarness()
    a = add(manager, "A")
    b = add(manager, "B")
    c = add(manager, "C")
    manager.expenses.append({"account_id": a["id"], "amount": 10, "paid": False})
    manager.income_rules.append({"account_id": b["id"]})
    transfer(manager, b["id"], c["id"])
    for account_id in (a["id"], b["id"], c["id"]):
        with pytest.raises(ValueError):
            run(manager.async_delete_account(account_id))
    manager.expenses.clear()
    assert run(manager.async_delete_account(a["id"]))
    assert manager.default_account_id == b["id"]


def test_legacy_two_account_data_and_transfers_migrate_without_loss():
    manager = AccountsHarness()
    manager.accounts_config = {
        "opening_date": "2026-01-01",
        "checking_opening_balance": 1000,
        "savings_opening_balance": 500,
    }
    manager.expenses = [{"paid": True, "amount": 90, "payment_date": "2026-01-14"}]
    manager.incomes = [{"received": True, "actual_amount": 200, "received_date": "2026-01-11"}]
    manager.internal_transfers = [{
        "id": "legacy-transfer", "from_account": "checking", "to_account": "savings",
        "amount": 150, "transfer_date": "2026-01-20", "note": "",
        "created_at": "",
    }]
    assert manager._migrate_accounts()
    assert [x["id"] for x in manager.accounts] == ["checking", "savings"]
    assert manager.default_account_id == "checking"
    assert manager.accounts_config == {}
    assert manager.incomes[0]["account_id"] == "checking"
    assert manager.expenses[0]["account_id"] == "checking"
    assert manager.account_balances()["total"] == 1610
    assert balance(manager, "checking")["balance"] == 960
    assert balance(manager, "savings")["balance"] == 650
    assert manager._migrate_accounts() is False


def test_corrupt_migration_rejects_missing_account_without_dropping_money():
    manager = AccountsHarness()
    account = add(manager, "My Bank")
    manager.internal_transfers = [{
        "id": "orphan", "from_account": account["id"], "to_account": "missing",
        "amount": 30, "transfer_date": "2026-01-20",
    }]
    with pytest.raises(ValueError, match="missing"):
        manager._migrate_accounts()
    assert len(manager.internal_transfers) == 1


def test_account_routes_and_storage_are_in_manager():
    manager = (ROOT / "custom_components" / "bill_tracker" / "manager.py").read_text()
    for keyword in ("accounts", "default_account_id", "account_balances", "account_id"):
        assert keyword in manager
    api = (ROOT / "custom_components" / "bill_tracker" / "__init__.py").read_text()
    for route in (
        "bill_tracker/accounts/add",
        "bill_tracker/accounts/update",
        "bill_tracker/accounts/delete",
        "bill_tracker/accounts/default",
        "bill_tracker/accounts/adjust_balance",
        "bill_tracker/accounts/transfer/add",
        "bill_tracker/accounts/transfer/update",
        "bill_tracker/accounts/transfer/delete",
    ):
        assert route in api
