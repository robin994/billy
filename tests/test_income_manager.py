"""Regression tests for income records and variable monthly salaries (no HA required)."""
import asyncio
from datetime import date
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

import pytest

SOURCE = Path(__file__).resolve().parents[1] / "custom_components" / "bill_tracker" / "income.py"
SPEC = spec_from_file_location("billy_income_harness", SOURCE)
MODULE = module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class IncomeHarness(MODULE.IncomeMixin):
    def __init__(self):
        self.income_categories = []
        self.incomes = []
        self.income_rules = []
        self.saves = 0
        self._migrate_income()

    def _sort(self):
        self.incomes.sort(key=lambda row: row["expected_date"], reverse=True)

    async def _save_and_notify(self):
        self.saves += 1


def run(coro):
    return asyncio.run(coro)


def salary_rule(manager, start):
    return run(manager.async_add_income_rule(
        name="Monthly salary", category_id="salary",
        start_date=start, estimated_amount=2000,
        interval_months=1, amount_mode="last", active=True,
        end_date="", note="",
    ))


def edit_salary(manager, row, actual, received=True):
    return run(manager.async_update_income(
        row["id"], description=row["description"], category_id="salary",
        expected_date=row["expected_date"], estimated_amount=row["estimated_amount"],
        received=received, actual_amount=actual,
        received_date=row["expected_date"] if received else "",
        note="Salary after deductions",
    ))


def test_salary_occurrences_are_independent_and_retroactively_editable():
    manager = IncomeHarness()
    rule = salary_rule(manager, "2026-01-27")
    assert rule["estimated_amount"] == 2000
    manager._sync_income_occurrences(today=date(2026, 3, 31))
    rows = sorted(
        (row for row in manager.incomes if row["rule_id"] == rule["id"]),
        key=lambda row: row["expected_date"],
    )
    assert [row["expected_date"] for row in rows][:3] == [
        "2026-01-27", "2026-02-27", "2026-03-27",
    ]
    january, february, march = rows[:3]
    edit_salary(manager, january, 1941.75)
    assert february["estimated_amount"] == 1941.75
    edit_salary(manager, february, 2117.83)
    assert january["actual_amount"] == 1941.75
    assert february["actual_amount"] == 2117.83
    assert march["actual_amount"] is None
    assert march["received"] is False
    assert january["estimated_amount"] == 2000
    # February's pre-confirmation estimate follows January's confirmed net,
    # but is preserved after February is confirmed.
    assert february["estimated_amount"] == 1941.75

    # Correcting an already confirmed salary changes only that receipt.
    edit_salary(manager, january, 1960.25)
    assert january["actual_amount"] == 1960.25
    assert february["actual_amount"] == 2117.83
    assert manager.income_monthly_totals()[:2] == [
        {"key": "2026-01", "year": 2026, "month": 1, "total": 1960.25},
        {"key": "2026-02", "year": 2026, "month": 2, "total": 2117.83},
    ]


def test_deleted_recurring_occurrence_is_not_regenerated():
    manager = IncomeHarness()
    rule = salary_rule(manager, "2026-01-31")
    manager._sync_income_occurrences(today=date(2026, 3, 31))
    rows = sorted(
        (row for row in manager.incomes if row["rule_id"] == rule["id"]),
        key=lambda row: row["expected_date"],
    )
    assert [row["expected_date"] for row in rows[:3]] == [
        "2026-01-31", "2026-02-28", "2026-03-31",
    ]
    removed = rows[1]
    assert run(manager.async_delete_income(removed["id"]))
    assert removed["voided"]
    manager._sync_income_occurrences(today=date(2026, 3, 31))
    assert sum(row["expected_date"] == "2026-02-28" for row in manager.incomes) == 1
    assert removed not in [row for row in manager.incomes if not row["voided"]]


def test_income_categories_are_independent_of_bill_categories():
    manager = IncomeHarness()
    row = run(manager.async_add_income_category(name="Consulting", color="#11aa77"))
    assert row["name"] == "Consulting"
    updated = run(manager.async_update_income_category(row["id"], name="Contracting", color="#aa7711"))
    assert updated["name"] == "Contracting"
    entry = run(manager.async_add_income(
        description="Job", category_id=row["id"], expected_date="2026-10-12",
        estimated_amount=120, received=True, actual_amount=105.35,
        received_date="2026-10-12", note="",
    ))
    assert entry["actual_amount"] == 105.35
    with pytest.raises(ValueError, match="recorded history"):
        run(manager.async_delete_income_category(row["id"]))


def test_unreceived_income_excluded_from_actual_and_invalid_amounts_rejected():
    manager = IncomeHarness()
    pending = run(manager.async_add_income(
        description="Bonus", category_id="bonus", expected_date="2026-10-01",
        estimated_amount=800, received=False, actual_amount=None,
        received_date=None, note="",
    ))
    assert manager.income_monthly_totals() == []
    assert pending["received_date"] is None
    assert not pending["received"]
    with pytest.raises(ValueError, match="finite"):
        run(manager.async_add_income(
            description="Bad", category_id="bonus", expected_date="2026-10-01",
            estimated_amount=float("nan"), received=False,
        ))
    with pytest.raises(ValueError, match="nonnegative"):
        run(manager.async_add_income(
            description="Negative", category_id="bonus", expected_date="2026-10-01",
            estimated_amount=-50, received=False,
        ))
    assert len(manager.incomes) == 1


def test_last_salary_estimate_uses_last_confirmed_not_future_planned():
    manager = IncomeHarness()
    rule = salary_rule(manager, "2026-01-27")
    manager._sync_income_occurrences(today=date(2026, 1, 31))
    january = next(row for row in manager.incomes if row["expected_date"] == "2026-01-27")
    edit_salary(manager, january, 2244.11)
    manager._sync_income_occurrences(today=date(2026, 2, 28))
    february = next(row for row in manager.incomes if row["expected_date"] == "2026-02-27")
    assert february["estimated_amount"] == 2244.11
    assert february["received"] is False
    assert manager._income_estimate(rule, date(2026, 3, 27)) == 2244.11


def test_future_occurrence_edit_does_not_change_rule_or_other_months():
    manager = IncomeHarness()
    rule = salary_rule(manager, "2026-01-27")
    manager._sync_income_occurrences(today=date(2026, 4, 30))
    april = next(row for row in manager.incomes if row["expected_date"] == "2026-04-27")
    edit_salary(manager, april, 1750.25)
    assert rule["estimated_amount"] == 2000
    assert len(manager.incomes) >= 4
    assert all(row["actual_amount"] is None for row in manager.incomes if row["id"] != april["id"])
