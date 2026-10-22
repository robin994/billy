"""Issue #17: confirmed, editable historical recurring payments and account accuracy."""
from __future__ import annotations

import ast
import asyncio
from calendar import monthrange
from collections import defaultdict
from datetime import date, datetime, timedelta
from importlib.util import module_from_spec, spec_from_file_location
from math import isfinite
from pathlib import Path
from uuid import uuid4

import pytest


ROOT = Path(__file__).resolve().parents[1] / "custom_components" / "bill_tracker"
account_spec = spec_from_file_location("issue17_accounts", ROOT / "accounts.py")
account_module = module_from_spec(account_spec)
account_spec.loader.exec_module(account_module)

tree = ast.parse((ROOT / "manager.py").read_text(encoding="utf-8"))
manager_class = next(
    node for node in tree.body
    if isinstance(node, ast.ClassDef) and node.name == "BillTrackerManager"
)
methods = {
    "_normalize_recurring_payload", "_normalize_optional_text",
    "_normalize_optional_iso_date", "_normalize_color", "_validate_optional_payer",
    "_resolve_expense_split", "_normalize_split", "active_payers", "default_split",
    "payer", "recurring_expense", "_recurring_payment_due",
    "_normalize_recurring_payment", "async_record_recurring_payment",
    "async_delete_recurring_payment", "_migrate_recurring_payments",
    "async_update_recurring", "async_delete_recurring", "_recurring_occurrence",
    "_next_recurring_due", "_recurring_occurrences_between", "_add_months_date",
    "_recurring_progress", "_next_renewal_date", "_public_recurring_expense",
    "recurring_history_items", "cashflow_monthly_totals", "_month_range",
    "_next_month", "_add_months", "_recurring_tracking_start",
}
body = [
    node for node in manager_class.body
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in methods
]
fake_class = ast.ClassDef(
    name="PaymentMethods", bases=[], keywords=[],
    body=body, decorator_list=[],
)
module = ast.Module(body=[fake_class], type_ignores=[])
ast.fix_missing_locations(module)
ns = {
    "Any": object,
    "date": date, "datetime": datetime, "timedelta": timedelta,
    "uuid4": uuid4, "monthrange": monthrange, "defaultdict": defaultdict,
    "isfinite": isfinite,
    "RECURRING_KINDS": ("subscription", "mortgage", "installment", "recurring"),
    "RECURRING_INTERVALS": (1, 2, 3, 4, 6, 12),
    "FALLBACK_COLORS": ("#5B8FF9", "#5AD8A6", "#5D7092", "#F6BD16"),
    "_cents": account_module._cents,
    "_value": account_module._value,
    "billy_error": lambda key, **kwargs: ValueError(key),
}
exec(compile(module, str(ROOT / "manager.py"), "exec"), ns)
ns["BillTrackerManager"] = ns["PaymentMethods"]


class PaymentHarness(ns["PaymentMethods"], account_module.AccountMixin):
    def __init__(self):
        self.houses = [{"id": "home", "name": "Home"}]
        self.default_house_id = "home"
        self.accounts = []
        self.payers = [{"id": "owner", "name": "Owner", "enabled": True, "share_percent": 100}]
        self.default_account_id = None
        self.accounts_config = {}
        self.incomes = []
        self.income_rules = []
        self.expenses = []
        self.settlements = []
        self.internal_transfers = []
        self.recurring_expenses = []
        self.recurring_occurrences = []
        self.recurring_payments = []
        self.save_count = 0

    def _resolve_house_id(self, house_id=None):
        selected = house_id or self.default_house_id
        if selected != "home":
            raise ValueError("House not found")
        return selected

    @property
    def currency(self):
        return "EUR"

    async def _save_and_notify(self):
        self.save_count += 1

    def _sort(self):
        self.recurring_payments.sort(key=lambda row: row["payment_date"], reverse=True)

    def monthly_totals(self):
        return []

    def _sync_recurring_occurrences(self):
        return False

    def _refresh_open_recurring_occurrences(self, recurring):
        return False


def run(coro):
    return asyncio.run(coro)


def setup():
    manager = PaymentHarness()
    account = run(manager.async_add_account(
        name="Current", account_type="checking", opening_balance=5000,
        opening_date="2026-01-01", payer_id="owner",
    ))
    rule = manager._normalize_recurring_payload(
        name="House mortgage", kind="mortgage", amount=800,
        interval_months=1, start_date="2026-02-02", end_date="2027-10-01",
        auto_renew=True, renewal_interval_months=12, installment_count=None,
        payer_id="owner", provider="Bank",
    )
    rule["id"] = "mortgage-1"
    manager.recurring_expenses = [rule]
    manager.save_count = 0
    return manager, account, rule


def pay(manager, account_id, due="2026-02-02", on="2026-02-05", amount=800, **kwargs):
    return run(manager.async_record_recurring_payment(
        recurring_id="mortgage-1", due_date=due, payment_date=on,
        amount=amount, account_id=account_id, **kwargs,
    ))


def test_backdated_mortgage_payment_updates_actual_balance_and_cashflow_only():
    manager, account, _ = setup()
    assert manager.account_balances()["total"] == 5000
    assert manager.cashflow_monthly_totals() == []
    first = pay(manager, account["id"])
    assert first["due_date"] == "2026-02-02"
    assert first["payment_date"] == "2026-02-05"
    assert first["amount"] == 800
    assert manager.account_balances()["total"] == 4200
    assert next(row for row in manager.cashflow_monthly_totals() if row["key"] == "2026-02")["recurring_total"] == 800
    planned = next(row for row in manager.recurring_history_items() if row["due_date"] == "2026-02-02")
    assert planned["paid"] is True
    assert planned["actual_amount"] == 800
    assert planned["payment_date"] == "2026-02-05"
    march = next(row for row in manager.recurring_history_items() if row["due_date"] == "2026-03-02")
    assert march["paid"] is False
    assert manager.save_count == 1


def test_corrections_are_idempotent_and_undo_restores_the_account():
    manager, account, _ = setup()
    original = pay(manager, account["id"])
    unchanged = pay(manager, account["id"])
    assert original == unchanged
    assert manager.save_count == 1
    revised = pay(manager, account["id"], on="2026-03-04", amount=812.37)
    assert revised["id"] == original["id"]
    assert len(manager.recurring_payments) == 1
    assert manager.account_balances(date(2026, 2, 28))["total"] == 5000
    assert manager.account_balances()["total"] == 4187.63
    assert next(row for row in manager.cashflow_monthly_totals() if row["key"] == "2026-03")["recurring_total"] == 812.37
    assert run(manager.async_delete_recurring_payment(recurring_id="mortgage-1", due_date="2026-02-02"))
    assert manager.recurring_payments == []
    assert manager.account_balances()["total"] == 5000
    assert not run(manager.async_delete_recurring_payment(recurring_id="mortgage-1", due_date="2026-02-02"))


def test_already_recorded_paid_bill_can_be_marked_without_double_posting():
    manager, account, _ = setup()
    manager.expenses = [{
        "paid": True, "amount": 800, "payment_date": "2026-02-05",
        "account_id": account["id"], "category_id": "housing",
    }]
    payment = pay(manager, account["id"], already_recorded=True)
    assert payment["already_recorded"] is True
    assert payment["account_id"] is None
    assert manager.account_balances()["total"] == 4200
    assert all(row["recurring_total"] == 0 for row in manager.cashflow_monthly_totals())
    assert next(row for row in manager.recurring_history_items() if row["due_date"] == "2026-02-02")["paid"]


@pytest.mark.parametrize("due,on,amount,match", [
    ("2026-01-02", "2026-01-02", 800, "valid scheduled"),
    ("2026-02-03", "2026-02-05", 800, "valid scheduled"),
    ("2099-02-02", "2099-02-05", 800, "Future"),
    ("2026-02-02", "2099-02-02", 800, "Future"),
    ("2026-02-02", "2026-02-03", -800, "nonnegative"),
    ("2026-02-02", "2026-02-03", 12.345, "two decimal"),
])
def test_payment_validation_rejects_wrong_dates_and_amounts(due, on, amount, match):
    manager, account, _ = setup()
    with pytest.raises(ValueError, match=match):
        pay(manager, account["id"], due=due, on=on, amount=amount)
    assert not manager.recurring_payments


def test_account_opening_date_and_account_deletion_cannot_discard_paid_history():
    manager, account, _ = setup()
    with pytest.raises(ValueError, match="existing account"):
        pay(manager, "wrong-account")
    manager.account(account["id"])["opening_date"] = "2026-03-01"
    with pytest.raises(ValueError, match="predates"):
        pay(manager, account["id"])
    manager.account(account["id"])["opening_date"] = "2026-01-01"
    pay(manager, account["id"])
    with pytest.raises(ValueError, match="recurring payments"):
        run(manager.async_delete_account(account["id"]))
    with pytest.raises(ValueError, match="exclude recorded recurring payments"):
        run(manager.async_update_account(
            account["id"], name="Current", account_type="checking",
            opening_balance=5000, opening_date="2026-03-01", payer_id="owner",
        ))


def test_schedule_edit_cannot_orphan_paid_occurrences_and_delete_requires_undo():
    manager, account, rule = setup()
    pay(manager, account["id"])
    kwargs = dict(
        name=rule["name"], kind="mortgage", amount=800, interval_months=1,
        start_date="2026-03-02", end_date=rule["end_date"],
        auto_renew=True, renewal_interval_months=12, installment_count=None,
        payer_id="owner",
    )
    with pytest.raises(ValueError, match="recorded payments"):
        run(manager.async_update_recurring("mortgage-1", **kwargs))
    with pytest.raises(ValueError, match="Undo recorded"):
        run(manager.async_delete_recurring("mortgage-1"))
    assert rule["start_date"] == "2026-02-02"
    run(manager.async_delete_recurring_payment(recurring_id="mortgage-1", due_date="2026-02-02"))
    updated = run(manager.async_update_recurring("mortgage-1", **kwargs))
    assert updated["start_date"] == "2026-03-02"


def test_payment_migration_validates_duplicates_account_refs_and_roundtrips():
    manager, account, _ = setup()
    record = pay(manager, account["id"])
    before = list(manager.recurring_payments)
    assert manager._migrate_recurring_payments() is False
    manager.recurring_payments = [dict(record), dict(record)]
    with pytest.raises(ValueError, match="Duplicate"):
        manager._migrate_recurring_payments()
    manager.recurring_payments = [{**record, "account_id": "deleted"}]
    with pytest.raises(ValueError, match="existing account"):
        manager._migrate_recurring_payments()
    manager.recurring_payments = before
    assert manager._migrate_recurring_payments() is False


def test_imported_unassigned_historical_payment_never_silently_debits_new_default_account():
    manager, account, _ = setup()
    record = pay(manager, account["id"])
    manager.recurring_payments = [{**record, "account_id": None}]
    assert manager._migrate_recurring_payments() is False
    assert manager.account_balances()["total"] == 5000
    assert next(row for row in manager.recurring_history_items() if row["due_date"] == "2026-02-02")["paid"]


def test_migration_rejects_ambiguous_boolean_reconciliation_values():
    manager, account, _ = setup()
    record = pay(manager, account["id"])
    manager.recurring_payments = [{**record, "already_recorded": "false"}]
    with pytest.raises(ValueError, match="reconciliation flag"):
        manager._migrate_recurring_payments()
