"""House grouping: safe migration, scoped financial analytics, and backup."""
from __future__ import annotations

import json

import pytest

from test_bill_placeholders import manager, run, add


def test_existing_bills_migrate_into_one_default_house_without_changing_their_money(manager):
    old_id = manager.default_house_id
    original = add(manager, amount=125, paid=True, payment_date="2026-10-10")
    assert original["house_id"] == old_id
    expected = manager.summary()["current_month"]
    run(manager._save())
    # Simulate a pre-houses 0.16.0 store.
    saved = manager._store.data
    saved.pop("houses", None)
    saved.pop("default_house_id", None)
    for row in saved["expenses"]:
        row.pop("house_id", None)
    run(manager.async_load())
    assert len(manager.houses) == 1
    assert manager.expenses[0]["house_id"] == manager.default_house_id
    assert manager.summary()["current_month"] == expected
    assert manager._store.data["houses"][0]["id"] == manager.default_house_id


def test_house_creation_renaming_default_selection_and_safety_guards(manager):
    home = manager.default_house_id
    villa = run(manager.async_add_house("Villa"))
    assert villa["id"] != home
    with pytest.raises(ValueError, match="already exists"):
        run(manager.async_add_house("villa"))
    with pytest.raises(ValueError, match="House not found"):
        run(manager.async_set_default_house("missing"))
    updated = run(manager.async_update_house(villa["id"], "Country villa"))
    assert updated["name"] == "Country villa"
    bill = add(manager, house_id=villa["id"], paid=True, payment_date="2026-10-11")
    assert bill["house_id"] == villa["id"]
    with pytest.raises(ValueError, match="Move the linked bills"):
        run(manager.async_delete_house(villa["id"]))
    run(manager.async_set_default_house(villa["id"]))
    with pytest.raises(ValueError, match="Choose another default"):
        run(manager.async_delete_house(villa["id"]))
    assert manager.default_house_id == villa["id"]


def test_scope_separates_bills_and_recurring_forecasts_but_not_bank_accounts(manager):
    first = manager.default_house_id
    second = run(manager.async_add_house("Second home"))["id"]
    add(manager, amount=100, paid=True, payment_date="2026-10-08", house_id=first)
    add(manager, amount=240, paid=True, payment_date="2026-10-09", house_id=second)
    recurring = run(manager.async_add_recurring(
        name="Garden subscription", kind="subscription", amount=50,
        interval_months=1, start_date="2026-11-04", end_date=None,
        house_id=second,
    ))
    assert recurring["house_id"] == second
    original = manager.snapshot()
    first_only = manager.snapshot(house_id=first)
    second_only = manager.snapshot(house_id=second)
    assert original["summary"]["current_month"] == 340
    assert first_only["summary"]["current_month"] == 100
    assert second_only["summary"]["current_month"] == 240
    assert len(original["expenses"]) == 2
    assert {x["house_id"] for x in first_only["expenses"]} == {first}
    assert {x["house_id"] for x in second_only["expenses"]} == {second}
    assert first_only["forecast"][0]["recurring_total"] == 0
    assert second_only["forecast"][0]["recurring_total"] == 50
    assert original["summary"]["current_month"] == 340, "scoped requests must never mutate global state"
    assert len(manager.expenses) == 2
    assert {x["house_id"] for x in manager.recurring_expenses} == {second}
    assert first_only["houses"] == original["houses"]
    assert second_only["default_house_id"] == first
    with pytest.raises(ValueError, match="House not found"):
        manager.snapshot(house_id="not-a-house")
    assert len(manager.expenses) == 2


def test_switching_a_bill_house_reassigns_only_that_bill_and_preserves_totals(manager):
    first = manager.default_house_id
    second = run(manager.async_add_house("Vacation"))["id"]
    bill = add(manager, amount=75, paid=True, payment_date="2026-10-09", house_id=first)
    updated = run(manager.async_update(
        bill["id"], year=2026, month=10,
        category_id="electricity", category_name=None,
        amount=75, paid=True, house_id=second,
    ))
    assert updated["house_id"] == second
    assert manager.snapshot(house_id=first)["expenses"] == []
    assert manager.snapshot(house_id=second)["summary"]["current_month"] == 75
    assert manager.snapshot()["summary"]["current_month"] == 75
    with pytest.raises(ValueError, match="House not found"):
        run(manager.async_update(
            bill["id"], year=2026, month=10,
            category_id="electricity", category_name=None,
            amount=75, paid=True, house_id="foreign",
        ))


def test_houses_survive_persistence_and_backup_round_trip(manager):
    villa = run(manager.async_add_house("Villa"))
    run(manager.async_set_default_house(villa["id"]))
    add(manager, amount=150, paid=True, payment_date="2026-10-11")
    payload = json.loads(manager.export_backup())
    assert payload["data"]["houses"][-1]["name"] == "Villa"
    assert payload["data"]["default_house_id"] == villa["id"]
    assert payload["data"]["expenses"][0]["house_id"] == villa["id"]
    run(manager._save())
    run(manager.async_load())
    assert manager.default_house_id == villa["id"]
    assert manager.snapshot(house_id=villa["id"])["summary"]["current_month"] == 150
    run(manager.async_import_backup(json.dumps(payload)))
    assert manager.houses[-1]["id"] == villa["id"]
    assert manager.snapshot(house_id=villa["id"])["summary"]["current_month"] == 150


def test_backup_rejects_unknown_house_reference_without_rewriting_existing_records(manager):
    add(manager, amount=40, paid=True, payment_date="2026-10-10")
    good = json.loads(manager.export_backup())
    corrupted = json.loads(json.dumps(good))
    corrupted["data"]["expenses"][0]["house_id"] = "foreign"
    with pytest.raises(ValueError, match="does not exist"):
        run(manager.async_import_backup(json.dumps(corrupted)))
    assert manager.expenses[0]["house_id"] == manager.default_house_id
    assert manager.summary()["current_month"] == 40


def test_recurring_expense_house_is_stable_across_edits_and_reload(manager):
    other = run(manager.async_add_house("Second"))["id"]
    rule = run(manager.async_add_recurring(
        name="Broadband", kind="subscription", amount=30,
        interval_months=1, start_date="2026-09-01", house_id=other,
    ))
    assert rule["house_id"] == other
    revised = run(manager.async_update_recurring(
        rule["id"], name="Broadband", kind="subscription", amount=31,
        interval_months=1, start_date="2026-09-01",
    ))
    assert revised["house_id"] == other
    run(manager._save())
    run(manager.async_load())
    assert manager.recurring_expenses[0]["house_id"] == other
    with pytest.raises(ValueError, match="Move the linked bills"):
        run(manager.async_delete_house(other))


def test_placeholders_are_created_only_in_the_default_house(manager):
    other = run(manager.async_add_house("Mountain home"))["id"]
    config = manager.categories[0]["placeholder"]
    config.update({"enabled": True, "start_month": "2026-10", "day": 1,
                   "amount_mode": "fixed", "fixed_amount": 10})
    assert manager._sync_bill_placeholders()
    assert len(manager.expenses) == 1
    assert manager.expenses[0]["house_id"] == manager.default_house_id
    assert manager.snapshot(house_id=other)["expenses"] == []


def test_reimbursement_house_snapshot_survives_bill_move_backup_and_reload(manager):
    primary = manager.default_house_id
    holiday = run(manager.async_add_house("Holiday home"))["id"]
    alex = run(manager.async_add_payer(name="Alex", share_percent=50))["id"]
    ben = run(manager.async_add_payer(name="Ben", share_percent=50))["id"]
    split = [
        {"payer_id": alex, "percentage": 50},
        {"payer_id": ben, "percentage": 50},
    ]
    first = add(manager, amount=100, payer_id=alex, split=split, house_id=primary)
    second = add(manager, amount=200, payer_id=alex, split=split, house_id=holiday)
    debt = manager.debts()[0]
    assert debt["amount"] == 150
    assert {item["house_id"] for item in debt["items"]} == {primary, holiday}

    settlement = run(manager.async_add_settlement(
        from_payer_id=ben, to_payer_id=alex, amount=debt["amount"],
    ))
    assert settlement["amount"] == 150
    assert {item["house_id"] for item in settlement["items"]} == {primary, holiday}
    assert {item["house_id"] for item in manager.settlements[0]["line_items"]} == {primary, holiday}

    # A later bill reassignment must not silently rewrite the settled transfer.
    run(manager.async_update(
        second["id"], year=2026, month=10, category_id="electricity",
        category_name=None, amount=200, payer_id=alex, split=split,
        house_id=primary,
    ))
    assert manager.house(holiday)
    assert all(row["house_id"] == primary for row in manager.expenses)
    assert {item["house_id"] for item in manager.snapshot()["settlements"][0]["items"]} == {primary, holiday}
    with pytest.raises(ValueError, match="Undo reimbursements"):
        run(manager.async_delete_house(holiday))
    run(manager._save())
    run(manager.async_load())
    assert {item["house_id"] for item in manager.snapshot()["settlements"][0]["items"]} == {primary, holiday}
    assert {item["house_id"] for item in json.loads(manager.export_backup())["data"]["settlements"][0]["line_items"]} == {primary, holiday}

    bad = json.loads(manager.export_backup())
    bad["data"]["settlements"][0]["line_items"][0]["house_id"] = "missing-home"
    with pytest.raises(ValueError, match="Reimbursement refers to a house"):
        run(manager.async_import_backup(json.dumps(bad)))
    assert {item["house_id"] for item in manager.settlements[0]["line_items"]} == {primary, holiday}

    run(manager.async_delete_settlement(manager.settlements[0]["id"]))
    assert run(manager.async_delete_house(holiday))
