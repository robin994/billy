"""Exercise issue #10 against the complete manager with only HA I/O replaced."""
from __future__ import annotations

import ast
import asyncio
from copy import deepcopy
from datetime import date, datetime
import importlib.util
from pathlib import Path
import re
import sys
from types import ModuleType, SimpleNamespace
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

import pytest
import voluptuous as vol

ROOT = Path(__file__).resolve().parents[1]
COMPONENT = ROOT / "custom_components" / "bill_tracker"


class Store:
    def __class_getitem__(cls, _item):
        return cls

    def __init__(self, *_args):
        self.data = None
        self.saves = 0

    async def async_load(self):
        return deepcopy(self.data)

    async def async_save(self, data):
        self.data = deepcopy(data)
        self.saves += 1


@pytest.fixture
def manager():
    # Load real serialization/validation helpers without importing HA setup.
    package = ModuleType("billy_placeholder_tests")
    package.__path__ = [str(COMPONENT)]
    sys.modules[package.__name__] = package
    modules = {}
    for name in ("const", "errors", "localization", "exporter", "income", "accounts"):
        spec = importlib.util.spec_from_file_location(f"{package.__name__}.{name}", COMPONENT / f"{name}.py")
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        modules[name] = module
    tree = ast.parse((COMPONENT / "manager.py").read_text())
    imports = [n for n in tree.body if isinstance(n, (ast.Import, ast.ImportFrom))
               and not (isinstance(n, ast.ImportFrom) and (n.level or (n.module or "").startswith("homeassistant")))]
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef))
    namespace = {"Store": Store, "HomeAssistant": object, "_UNSET_TOTAL": object()}
    for module in modules.values():
        namespace.update({k: v for k, v in vars(module).items() if not k.startswith("_")})
    namespace["_cents"] = modules["accounts"]._cents
    namespace["_value"] = modules["accounts"]._value
    archive_tree = ast.parse((COMPONENT / "document_archive.py").read_text())
    archive_validator = next(
        node for node in archive_tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "normalize_archive_config"
    )
    archive_namespace = {"re": re, "urlsplit": urlsplit, "_PART": re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]{0,79}$")}
    exec(compile(ast.Module(body=[archive_validator], type_ignores=[]), str(COMPONENT / "document_archive.py"), "exec"), archive_namespace)
    namespace["normalize_archive_config"] = archive_namespace["normalize_archive_config"]
    clock = SimpleNamespace(value=datetime(2026, 10, 11, tzinfo=ZoneInfo("Europe/Rome")))

    class LocalDate(date):
        @classmethod
        def today(cls):
            return clock.value.date()

    namespace["dt_util"] = SimpleNamespace(now=lambda: clock.value)
    exec(compile(ast.Module(body=imports + [cls], type_ignores=[]), str(COMPONENT / "manager.py"), "exec"), namespace)
    namespace["date"] = LocalDate
    events = []
    hass = SimpleNamespace(config=SimpleNamespace(currency="EUR"), bus=SimpleNamespace(async_fire=events.append))
    instance = namespace["BillTrackerManager"](hass)
    instance._migrate_houses()
    instance.clock = clock
    instance.events = events
    instance.exporter = modules["exporter"]
    instance.categories = [{"id": "electricity", "name": "Electricity", "interval_months": 1, "enabled": True}]
    instance._normalize_categories()
    return instance


def run(awaitable):
    return asyncio.run(awaitable)


def configure(manager, **settings):
    category = manager.categories[0]
    category["placeholder"] = manager._normalize_placeholder_config(category, {"enabled": True, **settings})
    return category["placeholder"]


def add(manager, **kwargs):
    return run(manager.async_add(year=2026, month=kwargs.pop("month", 10), category_id="electricity", category_name=None, amount=kwargs.pop("amount", 80), **kwargs))


def test_legacy_categories_are_opt_in_and_snapshot_is_safe_without_history(manager):
    assert manager.categories[0]["placeholder"]["enabled"] is False
    assert not run(manager.async_sync_bill_placeholders())
    assert manager.snapshot()["current_month_unpaid_bills"] == []


def test_generates_once_and_persists_at_startup_and_after_restart(manager):
    configure(manager, amount_mode="fixed", fixed_amount=42, due_day=20)
    run(manager._save())
    run(manager.async_load())
    first = deepcopy(manager.expenses[0])
    assert first["amount"] == 42
    assert first["due_date"] == "2026-10-20"
    assert first["paid"] is False and first["is_placeholder"] is True
    assert manager.snapshot()["normalized_monthly"] == []
    assert manager.snapshot()["summary"]["current_month"] == 0
    run(manager.async_load())
    assert len(manager.expenses) == 1
    assert all(manager.expenses[0].get(key) == value for key, value in first.items())
    assert not run(manager.async_sync_bill_placeholders())


@pytest.mark.parametrize("interval", [1, 2, 3, 4, 6, 12])
def test_respects_all_cadences_across_year_boundary_without_backfill(manager, interval):
    manager.categories[0]["interval_months"] = interval
    configure(manager, start_month="2026-11", amount_mode="fixed", fixed_amount=20)
    assert not manager._sync_bill_placeholders(date(2026, 10, 31))
    assert manager._sync_bill_placeholders(date(2026, 11, 1))
    year, month = manager._add_months(2026, 11, interval)
    if interval > 1:
        assert not manager._sync_bill_placeholders(date(2026, 12, 1))
    assert manager._sync_bill_placeholders(date(year, month, 1))
    assert len(manager.expenses) == 2
    later = manager._add_months(year, month, interval * 3)
    assert manager._sync_bill_placeholders(date(*later, 1))
    assert len(manager.expenses) == 3


@pytest.mark.parametrize("year,last_day", [(2027, 28), (2028, 29)])
def test_creation_and_due_days_clip_at_end_of_february(manager, year, last_day):
    configure(manager, day=31, due_day=31, start_month=f"{year}-02")
    assert not manager._sync_bill_placeholders(date(year, 2, last_day - 1))
    assert manager._sync_bill_placeholders(date(year, 2, last_day))
    assert manager.expenses[0]["due_date"] == f"{year}-02-{last_day}"


def test_infers_next_bimonthly_period_from_latest_real_history(manager):
    manager.categories[0]["interval_months"] = 2
    add(manager, month=9)
    config = configure(manager)
    assert config["start_month"] == "2026-11"
    assert not manager._sync_bill_placeholders()
    assert manager._sync_bill_placeholders(date(2026, 11, 1))
    assert manager.expenses[0]["amount"] == 80


@pytest.mark.parametrize("paid", [False, True])
def test_existing_real_invoice_blocks_generation_regardless_of_payment_status(manager, paid):
    add(manager, paid=paid)
    configure(manager, start_month="2026-10")
    assert not manager._sync_bill_placeholders()
    assert len(manager.expenses) == 1


def test_last_amount_ignores_synthetic_history_and_future_invoices(manager):
    add(manager, month=8, amount=80)
    add(manager, month=12, amount=999)
    configure(manager, start_month="2026-09")
    assert manager._sync_bill_placeholders(date(2026, 9, 1))
    assert manager._sync_bill_placeholders()
    october = next(x for x in manager.expenses if x["paid_month"] == 10)
    assert october["amount"] == 80


def test_forecast_uses_real_estimator_and_honors_bill_exclusions(manager):
    add(manager, month=8, amount=80)
    add(manager, month=9, amount=100)
    add(manager, month=7, amount=999, exclude_from_estimates=True)
    configure(manager, amount_mode="forecast")
    assert manager._sync_bill_placeholders()
    assert manager.expenses[0]["amount"] == 97
    history, amounts = manager._forecast_category_history(manager.categories[0])
    assert len(history) == 4 and len(amounts) == 2
    assert manager._estimate_category_amount(amounts) == 97


@pytest.mark.parametrize("mode", ["last", "forecast", "fixed"])
def test_empty_history_keeps_bill_on_checklist_including_zero_amounts(manager, mode):
    configure(manager, amount_mode=mode, fixed_amount=0)
    assert manager._sync_bill_placeholders()
    assert manager.current_month_unpaid_bills()[0]["amount"] == 0


def test_delete_skips_this_period_even_after_restart_or_settings_update(manager):
    configure(manager)
    run(manager.async_sync_bill_placeholders())
    run(manager.async_delete(manager.expenses[0]["id"]))
    run(manager.async_load())
    run(manager.async_update_category("electricity", name="Electricity", interval_months=1, enabled=True, placeholder={"enabled": True, "day": 1, "start_month": "2026-10"}))
    assert manager.expenses == []
    assert manager.categories[0]["placeholder"]["last_generated_month"] == "2026-10"
    assert manager._sync_bill_placeholders(date(2026, 11, 1))


def test_manual_add_promotes_in_place_with_actual_metadata_and_one_notification(manager):
    configure(manager, due_day=31)
    run(manager.async_sync_bill_placeholders())
    original = deepcopy(manager.expenses[0])
    manager.events.clear()
    result = add(manager, amount=123, paid=True, due_date="2026-10-18", provider="Provider", note="Actual invoice")
    assert len(manager.expenses) == 1
    assert result["id"] == original["id"]
    assert result["created_at"] == original["created_at"]
    assert result["is_placeholder"] is False
    assert result["amount"] == 123 and result["paid"] is True
    assert result["due_date"] == "2026-10-18"
    assert result["note"] == "Actual invoice"
    assert len(manager.events) == 1
    assert manager.current_month_unpaid_bills() == []
    assert manager.summary()["current_month"] == 123


def test_parser_import_promotes_same_month_and_preserves_exact_billing_period(manager):
    sys.path.insert(0, str(COMPONENT))
    from importers.coordinator import BillImportCoordinator
    configure(manager)
    manager._sync_bill_placeholders()
    original_id = manager.expenses[0]["id"]
    result = run(BillImportCoordinator(manager).async_import({"id": "import-1", "category_id": "electricity", "data": {"amount": 74.5, "period_start": "2026-10-01", "period_end": "2026-10-31", "due_date": "2026-11-15"}}))
    assert len(manager.expenses) == 1
    assert result["id"] == original_id and result["is_placeholder"] is False
    assert result["period_end_date"] == "2026-10-31"
    assert result["due_date"] == "2026-11-15"


def test_split_bills_remain_separate_after_placeholder_promotion(manager):
    configure(manager)
    manager._sync_bill_placeholders()
    first = add(manager, amount=45, period_start_date="2026-10-01", period_end_date="2026-10-15")
    second = add(manager, amount=60, period_start_date="2026-10-16", period_end_date="2026-10-31")
    assert first["id"] != second["id"]
    assert len(manager.expenses) == 2


def test_editing_or_marking_paid_confirms_placeholder_without_reopening_on_unpay(manager):
    configure(manager)
    manager._sync_bill_placeholders()
    expense_id = manager.expenses[0]["id"]
    updated = run(manager.async_update(expense_id, year=2026, month=10, category_id="electricity", category_name=None, amount=55, paid=False))
    assert updated["is_placeholder"] is False and updated["paid"] is False
    assert manager.normalized_monthly_totals()[0]["total"] == 55
    manager.expenses[0]["is_placeholder"] = True
    run(manager.async_set_paid(expense_id, True))
    run(manager.async_set_paid(expense_id, False))
    assert manager.expenses[0]["is_placeholder"] is False


def test_provisional_payer_splits_create_no_reimbursement_until_confirmed(manager):
    run(manager.async_add_payer(name="A", share_percent=50))
    run(manager.async_add_payer(name="B", share_percent=50))
    configure(manager, amount_mode="fixed", fixed_amount=100)
    manager._sync_bill_placeholders()
    assert manager.debts() == []
    assert manager.snapshot()["expenses"][0]["reimbursement_status"] == "none"
    add(manager, amount=120)
    assert manager.debts()[0]["amount"] == 60
    assert manager.snapshot()["expenses"][0]["reimbursement_status"] == "pending"


def test_default_payer_can_be_disabled_without_breaking_automatic_creation(manager):
    payer = run(manager.async_add_payer(name="A", share_percent=100, enabled=False))
    manager.categories[0]["default_payer_id"] = payer["id"]
    configure(manager)
    assert manager._sync_bill_placeholders()
    assert manager.expenses[0]["split"] == [{"payer_id": payer["id"], "percentage": 100.0}]


@pytest.mark.parametrize("disable_category", [False, True])
def test_disabling_generation_keeps_existing_unpaid_entries(manager, disable_category):
    configure(manager)
    manager._sync_bill_placeholders()
    if disable_category:
        manager.categories[0]["enabled"] = False
    else:
        manager.categories[0]["placeholder"]["enabled"] = False
    assert not manager._sync_bill_placeholders(date(2026, 11, 1))
    assert len(manager.expenses) == 1


def test_older_category_clients_preserve_existing_placeholder_settings(manager):
    configure(manager, day=25, amount_mode="fixed", fixed_amount=50, due_day=30)
    previous = deepcopy(manager.categories[0]["placeholder"])
    run(manager.async_update_category("electricity", name="Power", interval_months=1, enabled=True))
    assert manager.categories[0]["placeholder"] == previous


def test_sensor_exposes_local_month_list_count_and_total(manager):
    configure(manager, amount_mode="fixed", fixed_amount=42)
    manager._sync_bill_placeholders()
    tree = ast.parse((COMPONENT / "sensor.py").read_text())
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef))
    method = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == "extra_state_attributes")
    method.decorator_list = []
    namespace = {}
    exec(compile(ast.Module(body=[method], type_ignores=[]), str(COMPONENT / "sensor.py"), "exec"), namespace)
    sensor = SimpleNamespace(manager=manager, parser_manager=SimpleNamespace(imports_snapshot=lambda *_args: []))
    attributes = namespace["extra_state_attributes"](sensor)
    assert attributes["current_month_unpaid_count"] == 1
    assert attributes["current_month_unpaid_total"] == 42
    assert attributes["current_month_unpaid_bills"][0]["is_placeholder"] is True


def test_backup_and_csv_preserve_provisional_identity_and_csv_real_bill_promotes(manager):
    configure(manager, amount_mode="fixed", fixed_amount=30)
    manager._sync_bill_placeholders()
    original_id = manager.expenses[0]["id"]
    backup = manager.export_backup().decode()
    run(manager.async_import_backup(backup))
    assert manager.expenses[0]["is_placeholder"] is True
    exported, _mime, _extension = manager.export_data(file_format="csv")
    records = manager.exporter.parse_csv_records(exported.decode("utf-8-sig"))
    assert records[0][1]["is_placeholder"] == "true"
    manager.expenses = []
    run(manager.async_import_csv(exported.decode("utf-8-sig")))
    assert manager.expenses[0]["is_placeholder"] is True
    result = run(manager.async_import_csv("category,amount,billing_month,paid\nElectricity,77,2026-10,true\n"))
    assert result["imported"] == 1 and result["error_count"] == 0
    assert len(manager.expenses) == 1 and manager.expenses[0]["id"] == original_id
    assert manager.expenses[0]["amount"] == 77 and manager.expenses[0]["is_placeholder"] is False


def test_local_month_checklist_includes_overdue_and_undated_entries_and_excludes_paid(manager):
    configure(manager)
    manager._sync_bill_placeholders()
    add(manager, month=9, due_date="2026-10-01")
    add(manager, month=8, due_date="2026-09-01")
    add(manager, month=7, due_date="2026-10-12", paid=True)
    assert len(manager.current_month_unpaid_bills()) == 2
    manager.clock.value = datetime(2026, 11, 1, 0, 30, tzinfo=ZoneInfo("Europe/Rome"))
    assert manager.current_month_unpaid_bills() == []
    assert run(manager.async_sync_bill_placeholders())
    assert len(manager.current_month_unpaid_bills()) == 1


@pytest.mark.parametrize("settings", [{"day": 0}, {"day": 32}, {"due_day": -1}, {"amount_mode": "other"}, {"fixed_amount": -1}, {"fixed_amount": float("nan")}, {"start_month": "2026-13"}, {"start_month": "202610"}])
def test_invalid_settings_are_rejected_without_mutation(manager, settings):
    previous = deepcopy(manager.categories)
    with pytest.raises(ValueError):
        run(manager.async_update_category("electricity", name="Changed", interval_months=1, enabled=True, placeholder={"enabled": True, **settings}))
    assert manager.categories == previous and manager.expenses == []


def test_category_websocket_schema_round_trips_optional_placeholder_settings():
    tree = ast.parse((COMPONENT / "__init__.py").read_text())
    assignment = next(n for n in tree.body if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "_CATEGORY_COMMON" for t in n.targets))
    schema = vol.Schema(eval(compile(ast.Expression(assignment.value), str(COMPONENT / "__init__.py"), "eval"), {"vol": vol, "SUPPORTED_INTERVALS": (1, 2, 3, 4, 6, 12)}))
    request = {"name": "Power", "interval_months": 2, "placeholder": {"enabled": True, "day": 31, "amount_mode": "forecast", "due_day": None}}
    assert schema(request)["placeholder"]["day"] == 31
    with pytest.raises(vol.Invalid):
        schema({**request, "placeholder": {"day": 32}})
