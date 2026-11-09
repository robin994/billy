"""Regression tests for imported-bill scheduled autopay (#23)."""
from __future__ import annotations

from copy import deepcopy
from datetime import date, datetime
from zoneinfo import ZoneInfo

from test_bill_placeholders import add, manager, run


def test_scheduled_bill_stays_unpaid_until_due_and_sync_is_idempotent(manager):
    bill = add(
        manager, due_date="2026-10-20",
        scheduled_autopay_date="2026-10-20",
    )
    assert bill["payment_status"] == "scheduled"
    assert bill["paid"] is False
    assert bill["payment_date"] is None
    assert bill["scheduled_autopay_date"] == "2026-10-20"
    assert manager.current_month_unpaid_bills() == []
    assert manager._sync_scheduled_autopay(date(2026, 10, 19)) is False
    assert manager._sync_scheduled_autopay(date(2026, 10, 20)) is True
    settled = manager._public_expense(manager.expenses[0])
    assert settled["payment_status"] == "paid"
    assert settled["payment_date"] == "2026-10-20"
    assert settled["scheduled_autopay_date"] is None
    assert manager._sync_scheduled_autopay(date(2026, 10, 21)) is False


def test_scheduler_recovers_missed_payment_on_reload(manager):
    bill = add(manager, due_date="2026-10-12", scheduled_autopay_date="2026-10-12")
    assert bill["payment_status"] == "scheduled"
    previous = deepcopy(manager._store.data)
    manager.clock.value = datetime(2026, 10, 16, tzinfo=ZoneInfo("Europe/Rome"))
    restarted = type(manager)(manager.hass)
    restarted._store.data = previous
    run(restarted.async_load())
    assert len(restarted.expenses) == 1
    assert restarted.expenses[0]["paid"] is True
    assert restarted.expenses[0]["payment_date"] == "2026-10-12"
    assert restarted.expenses[0]["scheduled_autopay_date"] is None
    assert restarted._store.data["expenses"][0]["paid"] is True


def test_schedule_with_due_date_today_is_paid_immediately(manager):
    bill = add(manager, due_date="2026-10-11", scheduled_autopay_date="2026-10-11")
    assert bill["payment_status"] == "paid"
    assert bill["payment_date"] == "2026-10-11"
    assert bill["scheduled_autopay_date"] is None


def test_manual_toggle_cancels_scheduled_payment(manager):
    bill = add(manager, due_date="2026-10-20", scheduled_autopay_date="2026-10-20")
    unpaid = run(manager.async_set_paid(bill["id"], False))
    assert unpaid["payment_status"] == "unpaid"
    assert unpaid["scheduled_autopay_date"] is None
    assert manager._sync_scheduled_autopay(date(2026, 10, 20)) is False


def test_scheduled_joint_reimbursement_is_deferred_to_actual_due_date(manager):
    manager.payers = [
        {"id": "a", "name": "Alice", "enabled": True},
        {"id": "b", "name": "Bob", "enabled": True},
    ]
    bill = add(
        manager, amount=100, payer_id="a",
        split=[
            {"payer_id": "a", "percentage": 60},
            {"payer_id": "b", "percentage": 40},
        ],
        due_date="2026-10-20", scheduled_autopay_date="2026-10-20",
        scheduled_autopay_joint=True,
    )
    assert bill["payment_status"] == "scheduled"
    assert bill["reimbursement_status"] == "none"
    assert manager._pairwise_debts() == []
    assert manager._sync_scheduled_autopay(date(2026, 10, 20)) is True
    paid = manager._public_expense(manager.expenses[0])
    assert paid["paid"] is True
    assert paid["reimbursement_status"] == "done"
    assert paid["reimbursement_manual_done"] is True
    assert manager._pairwise_debts() == []
