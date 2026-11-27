"""Issue #29: category cost allocation, overrides and persistence."""
from copy import deepcopy
from datetime import date

import pytest

from test_bill_placeholders import add, configure, manager, run
from test_issue17_websocket_schemas import _schema, _installment_request, _category_request


def payers(manager):
    a = run(manager.async_add_payer(name="A", share_percent=80))
    b = run(manager.async_add_payer(name="B", share_percent=20))
    return a["id"], b["id"]


def allocation(a, b, first=50):
    return [
        {"payer_id": payer, "percentage": share}
        for payer, share in ((a, first), (b, 100 - first))
        if share
    ]


def change_category(manager, **kwargs):
    return run(manager.async_update_category(
        "electricity", name="Electricity", interval_months=1, enabled=True, **kwargs
    ))


def shares(item):
    return [{"payer_id": part["payer_id"], "percentage": part["percentage"]}
            for part in item["split"]]


def recurring(manager, **kwargs):
    return run(manager.async_add_recurring(
        name="Streaming", kind="subscription", amount=25, interval_months=1,
        start_date="2026-10-01", **kwargs
    ))


def test_equal_default_is_independent_of_global_weights(manager):
    a, b = payers(manager)
    assert manager.default_split() == allocation(a, b, 80)
    assert manager.snapshot()["categories"][0]["effective_default_split"] == allocation(a, b)
    assert shares(add(manager)) == allocation(a, b)
    assert shares(recurring(manager)) == allocation(a, b)
    c = run(manager.async_add_payer(name="C", share_percent=100))["id"]
    assert manager.equal_split() == [
        {"payer_id": a, "percentage": 33.34},
        {"payer_id": b, "percentage": 33.33},
        {"payer_id": c, "percentage": 33.33},
    ]


def test_category_override_payer_and_manual_override_are_independent(manager):
    a, b = payers(manager)
    change_category(manager, default_payer_id=b, default_split=allocation(a, b, 100))
    item = add(manager, paid=True)
    assert item["payer_id"] == b
    assert shares(item) == allocation(a, b, 100)
    assert shares(add(manager, month=11, split=allocation(a, b, 25))) == allocation(a, b, 25)
    rule = recurring(manager, category_id="electricity")
    assert rule["category_id"] == "electricity"
    assert rule["payer_id"] == b
    assert shares(rule) == allocation(a, b, 100)
    assert shares(recurring(manager, category_id="electricity", split=allocation(a, b, 25))) == allocation(a, b, 25)
    assert manager.recurring_occurrences
    assert any(x["split"] == allocation(a, b, 100) for x in manager.recurring_occurrences)


def test_category_changes_do_not_rewrite_existing_allocations(manager):
    a, b = payers(manager)
    change_category(manager, default_split=allocation(a, b, 100))
    bill = add(manager)
    rule = recurring(manager, category_id="electricity")
    old_occurrences = deepcopy(manager.recurring_occurrences)
    change_category(manager, default_split=allocation(a, b, 0))
    assert shares(add(manager, month=11)) == allocation(a, b, 0)
    assert manager.recurring_occurrences == old_occurrences
    assert manager.recurring_expense(rule["id"])["split"] == allocation(a, b, 100)
    edited = run(manager.async_update(
        bill["id"], year=2026, month=10, category_id="electricity",
        category_name=None, amount=80, note="Edited",
    ))
    assert shares(edited) == allocation(a, b, 100)
    updated = run(manager.async_update_recurring(
        rule["id"], name="Renamed", kind="subscription", amount=25,
        interval_months=1, start_date="2026-10-01",
    ))
    assert updated["category_id"] == "electricity"
    assert shares(updated) == allocation(a, b, 100)
    assert shares(recurring(manager, category_id="electricity")) == allocation(a, b, 0)


def test_placeholder_and_storage_round_trip(manager):
    a, b = payers(manager)
    change_category(manager, default_split=allocation(a, b, 0))
    configure(manager, start_month="2026-10")
    assert manager._sync_bill_placeholders(date(2026, 10, 11))
    assert manager.expenses[0]["split"] == allocation(a, b, 0)
    rule = recurring(manager, category_id="electricity")
    run(manager.async_load())
    assert manager.category("electricity")["default_split"] == allocation(a, b, 0)
    assert manager.recurring_expense(rule["id"])["category_id"] == "electricity"
    assert manager.recurring_expense(rule["id"])["split"] == allocation(a, b, 0)
    backup = manager.export_backup()
    change_category(manager, default_split=allocation(a, b, 100))
    run(manager.async_import_backup(backup.decode("utf-8")))
    assert manager.category("electricity")["default_split"] == allocation(a, b, 0)
    assert manager.recurring_expense(rule["id"])["category_id"] == "electricity"
    change_category(manager, default_split=[])
    assert manager.category("electricity")["default_split"] == []
    assert shares(add(manager, month=12)) == allocation(a, b)


def test_validation_deletion_and_old_category_clients(manager):
    a, b = payers(manager)
    change_category(manager, default_split=allocation(a, b, 75))
    change_category(manager)
    assert manager.category("electricity")["default_split"] == allocation(a, b, 75)
    old = deepcopy(manager.categories)
    for invalid in ([{"payer_id": a, "percentage": 0}],
                    [{"payer_id": a, "percentage": 20}],
                    [{"payer_id": "missing", "percentage": 100}]):
        with pytest.raises(ValueError):
            change_category(manager, default_split=invalid)
        assert manager.categories == old
    with pytest.raises(ValueError):
        run(manager.async_delete_payer(b))
    recurring(manager, category_id="electricity")
    with pytest.raises(ValueError):
        run(manager.async_delete_category("electricity"))


def test_optional_fields_are_accepted_by_websocket_schemas():
    for action in ("add", "update"):
        command = f"bill_tracker/category/{action}"
        payload = _category_request(command)
        payload["default_split"] = allocation("a", "b", 100)
        assert _schema("_CATEGORY_COMMON", command)(payload)["default_split"] == allocation("a", "b", 100)
        command = f"bill_tracker/recurring/{action}"
        payload = _installment_request(command)
        payload.pop("recurring_id", None)
        payload["category_id"] = "electricity"
        assert _schema("_RECURRING_COMMON", command)(payload)["category_id"] == "electricity"


def test_parser_explicit_allocation_overrides_category_default(manager):
    from test_import_coordinator import BillImportCoordinator

    a, b = payers(manager)
    change_category(manager, default_payer_id=b, default_split=allocation(a, b, 0))
    coordinator = BillImportCoordinator(manager)
    candidate = {"category_id": "electricity", "data": {"amount": 42, "period_end": "2026-10-31"}}
    inherited = run(coordinator.async_import(candidate))
    assert shares(inherited) == allocation(a, b, 0)
    assert inherited["payer_id"] == b
    explicit = run(coordinator.async_import({
        **candidate, "default_payer_id": a, "default_split": allocation(a, b, 75),
    }))
    assert explicit["payer_id"] == a
    assert shares(explicit) == allocation(a, b, 75)
