"""N-account storage and backup round-trip tests without a full HA installation."""
import ast
import asyncio
from copy import deepcopy
from datetime import datetime
from importlib.util import module_from_spec, spec_from_file_location
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "custom_components" / "bill_tracker"


def module_file(filename, name):
    spec = spec_from_file_location(name, ROOT / filename)
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


Accounts = module_file("accounts.py", "accounts_backup_harness")
Income = module_file("income.py", "income_backup_harness")

tree = ast.parse((ROOT / "manager.py").read_text(encoding="utf-8"))
manager_cls = next(
    node for node in tree.body
    if isinstance(node, ast.ClassDef) and node.name == "BillTrackerManager"
)
METHODS = [
    node for node in manager_cls.body
    if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
    and node.name in {"export_backup", "async_import_backup", "_migrate_houses", "house", "_resolve_house_id"}
]
extracted = ast.Module(body=METHODS, type_ignores=[])
ast.fix_missing_locations(extracted)
ns = {
    "json": json, "datetime": datetime, "deepcopy": deepcopy,
    "STORAGE_SCHEMA_VERSION": 21,
    "DEFAULT_CATEGORIES": [],
    "billy_error": lambda message, **kwargs: ValueError(message),
    "Any": object,
}
from uuid import uuid4
ns["uuid4"] = uuid4
exec(compile(extracted, str(ROOT / "manager.py"), "exec"), ns)


class StorageHarness(Income.IncomeMixin, Accounts.AccountMixin):
    export_backup = ns["export_backup"]
    async_import_backup = ns["async_import_backup"]
    _migrate_houses = ns["_migrate_houses"]
    house = ns["house"]
    _resolve_house_id = ns["_resolve_house_id"]

    def __init__(self):
        self.accounts = []
        self.default_account_id = None
        self.accounts_config = {}
        self.internal_transfers = []
        self.income_categories = []
        self.income_rules = []
        self.incomes = []
        self.expenses = []
        self.houses = [{"id": "home", "name": "Home"}]
        self.default_house_id = "home"
        self.categories = []
        self.payers = [{"id": "owner", "name": "Owner"}]
        self.settlements = []
        self.recurring_expenses = []
        self.recurring_occurrences = []
        self.recurring_payments = []
        self.saves = 0
        self._migrate_income()
        self._migrate_accounts()

    @property
    def currency(self):
        return "EUR"

    async def _save_and_notify(self):
        self.saves += 1

    def _sort(self):
        pass

    def _normalize_payers(self):
        pass

    def _normalize_categories(self):
        pass

    def _migrate_expenses(self):
        pass

    def _migrate_settlements(self):
        pass

    def _migrate_recurring_expenses(self):
        pass

    def _migrate_recurring_occurrences(self):
        pass

    def _migrate_recurring_payments(self):
        pass

    def _sync_recurring_occurrences(self):
        pass

    def _sync_bill_placeholders(self):
        pass


def run(coro):
    return asyncio.run(coro)


def test_backup_round_trip_preserves_named_accounts_and_linked_transactions():
    original = StorageHarness()
    accounts = []
    for index, kind in enumerate(["checking", "cash", "investment", "prepaid"]):
        accounts.append(run(original.async_add_account(
            name=f"Account {index + 1}",
            account_type=kind,
            opening_balance=100 * (index + 1),
            opening_date="2026-01-01",
            payer_id="owner",
        )))
    run(original.async_set_default_account(accounts[-1]["id"]))
    inc = run(original.async_add_income(
        description="Contract", category_id="other", expected_date="2026-02-10",
        estimated_amount=50, received=True, actual_amount=45,
        received_date="2026-02-10", account_id=accounts[1]["id"],
    ))
    original.expenses = [{
        "id": "expense", "category_id": "test", "amount": 10.50, "paid": True,
        "payment_date": "2026-02-11", "account_id": accounts[0]["id"],
        "paid_year": 2026, "paid_month": 2,
    }]
    transfer = run(original.async_add_internal_transfer(
        from_account=accounts[-1]["id"], to_account=accounts[2]["id"],
        amount=100.30, transfer_date="2026-02-20",
    ))
    original.recurring_expenses = [{
        "id": "loan", "name": "Mortgage", "kind": "mortgage",
        "amount": 850, "interval_months": 1, "start_date": "2026-01-02",
    }]
    original.recurring_payments = [{
        "id": "loan@2026-01-02", "recurring_id": "loan",
        "due_date": "2026-01-02", "payment_date": "2026-01-03",
        "amount": 850, "account_id": accounts[0]["id"],
        "already_recorded": False, "note": "Historical payment",
    }]
    expected = original.account_balances()
    exported = original.export_backup().decode("utf-8")
    data = json.loads(exported)["data"]
    assert len(data["accounts"]) == 4
    assert data["default_account_id"] == accounts[-1]["id"]
    assert len(data["recurring_payments"]) == 1
    assert "accounts_config" not in data

    restored = StorageHarness()
    counts = run(restored.async_import_backup(exported))
    assert counts["accounts"] == 4
    assert counts["internal_transfers"] == 1
    assert counts["recurring_payments"] == 1
    assert restored.saves == 1
    assert restored.account_balances() == expected
    assert restored.incomes[0]["account_id"] == inc["account_id"]
    assert restored.internal_transfers[0]["id"] == transfer["id"]
    assert restored.expenses[0]["account_id"] == accounts[0]["id"]
    assert restored.recurring_payments == original.recurring_payments


def test_legacy_two_account_backup_converts_without_losing_money():
    original = StorageHarness()
    payload = json.loads(original.export_backup())
    payload["data"]["accounts"] = []
    payload["data"].pop("default_account_id", None)
    payload["data"]["accounts_config"] = {
        "opening_date": "2026-01-01",
        "checking_opening_balance": 110,
        "savings_opening_balance": 220,
    }
    payload["data"]["incomes"] = [{
        "id": "legacy-income", "description": "Salary", "category_id": "salary",
        "expected_date": "2026-02-15", "estimated_amount": 20,
        "actual_amount": 20, "received": True, "received_date": "2026-02-15",
    }]
    payload["data"]["internal_transfers"] = [{
        "id": "old", "from_account": "checking", "to_account": "savings",
        "amount": 10, "transfer_date": "2026-02-15", "note": "", "created_at": "",
    }]
    restored = StorageHarness()
    run(restored.async_import_backup(json.dumps(payload)))
    assert {account["id"] for account in restored.accounts} == {"checking", "savings"}
    assert restored.default_account_id == "checking"
    assert restored.incomes[0]["account_id"] == "checking"
    assert restored.account_balances()["total"] == 350
    assert restored.account_balances()["accounts"][0]["balance"] == 120
    assert restored.account_balances()["accounts"][1]["balance"] == 230


def test_malformed_backup_rolls_back_accounts_and_transfers():
    original = StorageHarness()
    run(original.async_add_account(
            name="Permanent", account_type="cash", opening_balance=77,
            opening_date="2026-01-01", payer_id="owner",
    ))
    state = json.loads(original.export_backup())
    malformed = deepcopy(state)
    malformed["data"]["accounts"] = [{"id": "a", "name": "", "opening_date": "2026-01-01"}]
    saved = original.export_backup()
    try:
        run(original.async_import_backup(json.dumps(malformed)))
    except ValueError:
        pass
    else:
        raise AssertionError("Import must reject a malformed account")
    assert original.export_backup() != b""
    expected = json.loads(saved)["data"]
    current = json.loads(original.export_backup())["data"]
    assert current == expected
