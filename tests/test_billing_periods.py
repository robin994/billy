from datetime import date
from pathlib import Path
import ast
from math import isfinite
from statistics import mean


ROOT = Path(__file__).resolve().parents[1]
MANAGER = ROOT / "custom_components" / "bill_tracker" / "manager.py"


def _manager_harness(*names):
    tree = ast.parse(MANAGER.read_text(encoding="utf-8"))
    cls = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "BillTrackerManager"
    )
    wanted = [
        node
        for node in cls.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in names
    ]
    harness = ast.ClassDef(
        name="ManagerHarness",
        bases=[],
        keywords=[],
        body=wanted,
        decorator_list=[],
    )
    module = ast.Module(body=[harness], type_ignores=[])
    ast.fix_missing_locations(module)
    namespace = {"date": date, "Any": object, "isfinite": isfinite, "mean": mean}
    exec(compile(module, str(MANAGER), "exec"), namespace)
    manager = namespace["ManagerHarness"]()
    manager.categories = [{"id": "electricity", "interval_months": 1}]
    manager.category = lambda category_id: next(
        (row for row in manager.categories if row["id"] == category_id), None
    )
    return manager


def test_short_and_long_billing_periods_are_classified_by_exact_days():
    names = ("_expected_period_days", "_expense_period_dates", "_billing_period_info")
    manager = _manager_harness(*names)

    short = manager._billing_period_info(
        {
            "category_id": "electricity",
            "period_start_date": "2026-01-13",
            "period_end_date": "2026-01-21",
        }
    )
    assert short["type"] == "short"
    assert short["days"] == 9

    long = manager._billing_period_info(
        {
            "category_id": "electricity",
            "period_start_date": "2026-01-01",
            "period_end_date": "2026-02-15",
        }
    )
    assert long["type"] == "long"
    assert long["days"] == 46


def test_split_tariff_bills_are_normalized_to_one_cycle_before_forecast_average():
    names = (
        "_expected_period_days",
        "_expense_period_dates",
        "_billing_period_info",
        "_estimate_category_amount",
    )
    manager = _manager_harness(*names)

    history = [
        {
            "category_id": "electricity",
            "amount": 30.0,
            "period_start_date": "2026-01-13",
            "period_end_date": "2026-01-21",
        },
        {
            "category_id": "electricity",
            "amount": 73.0,
            "period_start_date": "2026-01-22",
            "period_end_date": "2026-02-12",
        },
    ]

    estimate = manager._estimate_category_amount(history)
    assert 95 <= estimate <= 110


def test_cashflow_month_prefers_payment_date_over_billing_month():
    manager = _manager_harness("_expense_cashflow_month")
    item = {
        "paid_year": 2026,
        "paid_month": 7,
        "payment_date": "2026-08-05",
    }

    assert manager._expense_cashflow_month(item) == (2026, 8)


def test_cashflow_month_falls_back_to_billing_month_without_payment_date():
    manager = _manager_harness("_expense_cashflow_month")
    item = {"paid_year": 2026, "paid_month": 7, "payment_date": None}

    assert manager._expense_cashflow_month(item) == (2026, 7)


def test_forecast_history_ignores_excluded_bill_amount_but_keeps_cadence_anchor():
    manager = _manager_harness("_forecast_category_history")
    category = {
        "id": "electricity",
        "interval_months": 1,
        "enabled": True,
        "exclude_from_estimates": False,
    }
    manager.expenses = [
        {
            "category_id": "electricity",
            "paid_year": 2026,
            "paid_month": 1,
            "amount": 100.0,
            "exclude_from_estimates": False,
        },
        {
            "category_id": "electricity",
            "paid_year": 2026,
            "paid_month": 2,
            "amount": 999.0,
            "exclude_from_estimates": True,
        },
    ]

    history, estimate_history = manager._forecast_category_history(category)

    assert [row["paid_month"] for row in history] == [1, 2]
    assert [row["paid_month"] for row in estimate_history] == [1]


def test_bill_type_can_be_disabled_for_estimates_without_being_disabled():
    manager = _manager_harness("_forecast_category_history")
    manager.expenses = [
        {
            "category_id": "electricity",
            "paid_year": 2026,
            "paid_month": 1,
            "amount": 100.0,
        }
    ]
    category = {
        "id": "electricity",
        "interval_months": 1,
        "enabled": True,
        "exclude_from_estimates": True,
    }

    assert manager._forecast_category_history(category) == ([], [])
