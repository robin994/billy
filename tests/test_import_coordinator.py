import asyncio
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "custom_components" / "bill_tracker"))

from importers.coordinator import BillImportCoordinator  # noqa: E402


class _Manager:
    def __init__(self):
        self.kwargs = None

    async def async_add(self, **kwargs):
        self.kwargs = kwargs
        return kwargs


def test_anchor_prefers_billing_period_over_due_date():
    anchor = BillImportCoordinator._anchor_date(
        {
            "period_end": "2026-07-31",
            "issue_date": "2026-07-16",
            "due_date": "2026-08-08",
        }
    )
    assert anchor.isoformat() == "2026-07-31"


def test_anchor_prefers_issue_date_when_period_is_missing():
    anchor = BillImportCoordinator._anchor_date(
        {
            "issue_date": "2026-07-16",
            "due_date": "2026-08-08",
        }
    )
    assert anchor.isoformat() == "2026-07-16"


def test_import_preserves_exact_billing_period_dates():
    manager = _Manager()
    coordinator = BillImportCoordinator(manager)
    asyncio.run(
        coordinator.async_import(
            {
                "category_id": "electricity",
                "data": {
                    "amount": 42.0,
                    "period_start": "2026-01-13",
                    "period_end": "2026-01-21",
                },
            }
        )
    )
    assert manager.kwargs["period_start_date"] == "2026-01-13"
    assert manager.kwargs["period_end_date"] == "2026-01-21"


def test_import_applies_parser_default_payer_and_split():
    manager = _Manager()
    coordinator = BillImportCoordinator(manager)
    asyncio.run(
        coordinator.async_import(
            {
                "category_id": "electricity",
                "default_payer_id": "payer-a",
                "default_split": [
                    {"payer_id": "payer-a", "percentage": 60},
                    {"payer_id": "payer-b", "percentage": 40},
                ],
                "data": {"amount": 100, "due_date": "2026-08-31"},
            }
        )
    )
    assert manager.kwargs["payer_id"] == "payer-a"
    assert manager.kwargs["split"] == [
        {"payer_id": "payer-a", "percentage": 60},
        {"payer_id": "payer-b", "percentage": 40},
    ]


def test_import_empty_parser_split_falls_back_to_billy_defaults():
    manager = _Manager()
    coordinator = BillImportCoordinator(manager)
    asyncio.run(
        coordinator.async_import(
            {
                "category_id": "electricity",
                "default_payer_id": None,
                "default_split": [],
                "data": {"amount": 55, "due_date": "2026-09-30"},
            }
        )
    )
    assert manager.kwargs["split"] is None


def test_import_autopay_uses_due_date_and_can_set_joint_reimbursement():
    class JointManager(_Manager):
        async def async_add(self, **kwargs):
            self.kwargs = kwargs
            return {"id": "imported-1", "paid": bool(kwargs["paid"])}

        async def async_set_reimbursement_done(self, expense_id, done):
            self.reimbursed = (expense_id, done)

    manager = JointManager()
    asyncio.run(BillImportCoordinator(manager).async_import({
        "category_id": "electricity",
        "autopay": True,
        "autopay_joint": True,
        "data": {"amount": 42, "due_date": "2026-09-15", "issue_date": "2026-09-01"},
    }))
    assert manager.kwargs["paid"] is True
    assert manager.kwargs["payment_date"] == "2026-09-15"
    assert manager.reimbursed == ("imported-1", True)


def test_import_autopay_date_selection_and_disabled_default():
    for mode, expected in (("issue_date", "2026-09-01"), ("due_date", "2026-09-15")):
        manager = _Manager()
        asyncio.run(BillImportCoordinator(manager).async_import({
            "category_id": "electricity",
            "autopay": True,
            "autopay_payment_date": mode,
            "data": {"amount": 42, "issue_date": "2026-09-01", "due_date": "2026-09-15"},
        }))
        assert manager.kwargs["payment_date"] == expected
    manager = _Manager()
    asyncio.run(BillImportCoordinator(manager).async_import({
        "category_id": "electricity", "data": {"amount": 10, "due_date": "2026-09-15"},
    }))
    assert manager.kwargs["paid"] is False
    assert manager.kwargs["payment_date"] is None


def test_import_scheduled_autopay_defers_payment_and_joint_reimbursement():
    class ScheduledManager(_Manager):
        async def async_add(
            self, *, scheduled_autopay_date=None, scheduled_autopay_joint=False,
            **kwargs,
        ):
            self.kwargs = {
                **kwargs,
                "scheduled_autopay_date": scheduled_autopay_date,
                "scheduled_autopay_joint": scheduled_autopay_joint,
            }
            return {"id": "scheduled-1", "paid": False}

        async def async_set_reimbursement_done(self, *_args):
            raise AssertionError("Joint reimbursement should wait until due")

    manager = ScheduledManager()
    asyncio.run(BillImportCoordinator(manager).async_import({
        "category_id": "electricity",
        "autopay": True, "autopay_scheduled": True, "autopay_joint": True,
        "data": {"amount": 50, "due_date": "2099-03-21"},
    }))
    assert manager.kwargs["paid"] is False
    assert manager.kwargs["payment_date"] is None
    assert manager.kwargs["scheduled_autopay_date"] == "2099-03-21"
    assert manager.kwargs["scheduled_autopay_joint"] is True


def test_import_without_due_date_does_not_guess_a_scheduled_payment():
    manager = _Manager()
    asyncio.run(BillImportCoordinator(manager).async_import({
        "category_id": "electricity",
        "autopay": True, "autopay_scheduled": True,
        "data": {"amount": 50, "issue_date": "2026-10-10"},
    }))
    assert manager.kwargs["paid"] is False
    assert manager.kwargs["payment_date"] is None
