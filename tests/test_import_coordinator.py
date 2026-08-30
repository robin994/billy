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
