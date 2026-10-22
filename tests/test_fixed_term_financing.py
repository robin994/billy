"""Fixed-term repayment schedules and per-house bill-type automation (v0.17.1)."""
from __future__ import annotations

import json

import pytest

from test_bill_placeholders import manager, run


def test_installment_plan_uses_exact_total_with_different_final_payment(manager):
    rule = run(manager.async_add_recurring(
        name="Philippe's installment plan", kind="installment",
        amount=500, total_amount=10520.09, installment_count=21,
        interval_months=1, start_date="2026-02-01",
        end_date="2027-10-30", auto_renew=True,
    ))
    assert rule["total_amount"] == 10520.09
    assert rule["installment_count"] == 21
    assert rule["end_date"] == "2027-10-01"
    assert rule["auto_renew"] is False
    assert rule["remaining_amount"] == 10520.09
    assert rule["balance_from_payments"] is True

    schedule = [
        manager._recurring_due_amount(manager.recurring_expenses[0],
                                      manager._recurring_occurrence(manager.recurring_expenses[0], idx))
        for idx in range(21)
    ]
    assert schedule == [500] * 20 + [520.09]
    assert round(sum(schedule), 2) == 10520.09
    assert manager.recurring_month_items(2027, 10)[0]["amount"] == 520.09
    assert manager.recurring_history_items()[0]["amount"] == 500

    future = next(
        row for row in manager.upcoming(12)
        if row["source"] == "recurring" and row["due_date"] == "2027-10-01"
    )
    assert future["amount"] == 520.09
    run(manager.async_record_recurring_payment(
        recurring_id=rule["id"], due_date="2026-02-01",
        payment_date="2026-02-05", amount=500,
    ))
    updated = manager._public_recurring_expense(manager.recurring_expenses[0])
    assert updated["paid_installments"] == 1
    assert updated["paid_amount"] == 500
    assert updated["remaining_amount"] == 10020.09
    # Calendar progression alone must not lower the confirmed-payment balance.
    assert updated["remaining_amount"] != 500 * updated["remaining_installments"]


def test_invalid_totals_do_not_create_or_change_saved_plans(manager):
    original = run(manager.async_add_recurring(
        name="Example", kind="installment", amount=500, interval_months=1,
        start_date="2026-02-01", installment_count=21, total_amount=10520.09,
    ))
    with pytest.raises(ValueError, match="Total repayable"):
        run(manager.async_add_recurring(
            name="Bad", kind="installment", amount=500, interval_months=1,
            start_date="2026-02-01", installment_count=21, total_amount=9999.99,
        ))
    with pytest.raises(ValueError, match="number of payments"):
        run(manager.async_add_recurring(
            name="No count", kind="installment", amount=500,
            interval_months=1, start_date="2026-02-01", total_amount=10520.09,
        ))
    with pytest.raises(ValueError, match="number of payments"):
        run(manager.async_add_recurring(
            name="Subscription", kind="subscription", amount=500,
            interval_months=1, start_date="2026-02-01", installment_count=21,
            total_amount=10520.09,
        ))
    assert len(manager.recurring_expenses) == 1
    assert manager.recurring_expenses[0]["id"] == original["id"]


def test_repayment_schedule_survives_backup_and_restart(manager):
    rule = run(manager.async_add_recurring(
        name="Mortgage payments", kind="mortgage", amount=500,
        total_amount=10520.09, installment_count=21,
        interval_months=1, start_date="2026-02-01",
    ))
    run(manager._save())
    run(manager.async_load())
    assert manager.recurring_expenses[0]["total_amount"] == 10520.09
    assert manager._public_recurring_expense(manager.recurring_expenses[0])["remaining_amount"] == 10520.09
    content = json.loads(manager.export_backup())
    assert content["data"]["recurring_expenses"][0]["total_amount"] == 10520.09
    run(manager.async_import_backup(json.dumps(content)))
    assert manager.recurring_expense(rule["id"])["total_amount"] == 10520.09


def test_legacy_editor_updates_keep_total_until_explicitly_cleared(manager):
    rule = run(manager.async_add_recurring(
        name="Loan", kind="installment", amount=500, total_amount=10520.09,
        installment_count=21, interval_months=1, start_date="2026-02-01",
    ))
    kwargs = dict(name="Loan renamed", kind="installment", amount=500,
                  installment_count=21, interval_months=1, start_date="2026-02-01")
    updated = run(manager.async_update_recurring(rule["id"], **kwargs))
    assert updated["total_amount"] == 10520.09
    cleared = run(manager.async_update_recurring(rule["id"], total_amount=None, **kwargs))
    assert cleared["total_amount"] is None


def test_bill_type_can_generate_independent_invoices_per_house(manager):
    primary = manager.default_house_id
    vacation = run(manager.async_add_house("Vacation home"))["id"]
    category = manager.categories[0]
    result = run(manager.async_update_category(
        category["id"], name=category["name"], interval_months=1, enabled=True,
        house_placeholders={
            primary: {
                "enabled": True, "start_month": "2026-10",
                "day": 1, "due_day": 10, "amount_mode": "fixed",
                "fixed_amount": 55, "provider": "City Grid",
            },
            vacation: {
                "enabled": True, "start_month": "2026-10",
                "day": 1, "due_day": 18, "amount_mode": "fixed",
                "fixed_amount": 90, "provider": "Beach Utilities",
            },
        },
    ))
    assert set(result["house_placeholders"]) == {primary, vacation}
    by_house = {row["house_id"]: row for row in manager.expenses}
    assert len(by_house) == 2
    assert by_house[primary]["amount"] == 55
    assert by_house[vacation]["amount"] == 90
    assert by_house[primary]["provider"] == "City Grid"
    assert by_house[vacation]["provider"] == "Beach Utilities"
    assert by_house[primary]["due_date"] == "2026-10-10"
    assert by_house[vacation]["due_date"] == "2026-10-18"
    assert not manager._sync_bill_placeholders()
    with pytest.raises(ValueError, match="Move the linked"):
        run(manager.async_delete_house(vacation))
    run(manager._save())
    run(manager.async_load())
    assert len(manager.expenses) == 2
    assert len(manager.categories[0]["house_placeholders"]) == 2
    assert manager.expenses[1]["house_id"] in {primary, vacation}


def test_disabling_house_specific_placeholder_does_not_disable_other_house(manager):
    primary = manager.default_house_id
    other = run(manager.async_add_house("Second"))["id"]
    category = manager.categories[0]
    run(manager.async_update_category(
        category["id"], name="Electricity", interval_months=1, enabled=True,
        house_placeholders={
            primary: {"enabled": False, "day": 1},
            other: {"enabled": True, "day": 1, "start_month": "2026-10",
                    "amount_mode": "fixed", "fixed_amount": 10},
        },
    ))
    assert len(manager.expenses) == 1
    assert manager.expenses[0]["house_id"] == other
    assert manager.expenses[0]["amount"] == 10
    assert manager.snapshot(house_id=primary)["expenses"] == []
    assert len(manager.snapshot(house_id=other)["expenses"]) == 1


def test_preexisting_single_house_settings_still_generate_once(manager):
    category = manager.categories[0]
    category["placeholder"] = manager._normalize_placeholder_config(
        category, {
            "enabled": True, "day": 1,
            "start_month": "2026-10", "amount_mode": "fixed",
            "fixed_amount": 17,
        },
    )
    assert manager._sync_bill_placeholders()
    assert len(manager.expenses) == 1
    assert manager.expenses[0]["amount"] == 17
    run(manager._save())
    run(manager.async_load())
    assert len(manager.expenses) == 1
    assert "house_placeholders" not in manager.categories[0]


def test_disabled_house_schedule_can_be_discarded_with_deleted_house(manager):
    old = manager.default_house_id
    second = run(manager.async_add_house("Other property"))["id"]
    category = manager.categories[0]
    run(manager.async_update_category(
        category["id"], name=category["name"], interval_months=1,
        enabled=True, house_placeholders={
            old: {"enabled": False},
            second: {"enabled": False},
        },
    ))
    assert run(manager.async_delete_house(second))
    assert second not in manager.categories[0]["house_placeholders"]
    run(manager._save())
    run(manager.async_load())
    assert len(manager.houses) == 1
    assert second not in manager.categories[0]["house_placeholders"]
