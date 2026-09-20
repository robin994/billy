"""Convert parsed BillCandidate data into Billy expenses."""
from __future__ import annotations

from datetime import date
from typing import Any
import inspect


class BillImportCoordinator:
    """Keep parser concerns outside the existing BillTrackerManager domain model."""

    def __init__(self, bill_manager) -> None:
        self.bill_manager = bill_manager

    async def async_import(self, candidate: dict[str, Any]) -> dict[str, Any]:
        data = dict(candidate.get("data") or {})
        category_id = str(candidate.get("category_id") or "")
        if not category_id:
            raise ValueError("Parser is not mapped to a Billy bill type")

        anchor = self._anchor_date(data)
        start = self._iso_date(data.get("period_start"))
        end = self._iso_date(data.get("period_end"))
        invoice_number = str(data.get("invoice_number") or "").strip()
        provider = str(data.get("provider") or "").strip()
        note_parts = ["Automatic import"]
        if invoice_number:
            note_parts.append(f"invoice {invoice_number}")

        kwargs = {
            "year": anchor.year,
            "month": anchor.month,
            "category_id": category_id,
            "category_name": None,
            "amount": float(data["amount"]),
            "note": " · ".join(note_parts),
            "period_start_year": start.year if start else None,
            "period_start_month": start.month if start else None,
            "period_end_year": end.year if end else None,
            "period_end_month": end.month if end else None,
            "period_start_date": start.isoformat() if start else None,
            "period_end_date": end.isoformat() if end else None,
            "paid": False,
            "payer_id": candidate.get("default_payer_id"),
            # An empty parser-specific split means "use Billy defaults". Passing
            # [] would instead be treated as an explicit empty split and fail
            # once the domain manager resolves a payer.
            "split": candidate.get("default_split") or None,
            "payment_date": data.get("payment_date"),
            "due_date": data.get("due_date"),
            "provider": provider or None,
            "contract": str(data.get("offer") or data.get("contract") or "").strip() or None,
            "consumption": data.get("consumption"),
        }

        # Keep the parser subsystem compatible with the 0.5.2 domain manager.
        # Future Billy versions can persist these fields directly; until then the
        # complete metadata stays in the import record.
        optional_metadata = {
            "invoice_number": invoice_number or None,
            "issue_date": data.get("issue_date"),
            "source_import_id": candidate.get("id"),
        }
        accepted = inspect.signature(self.bill_manager.async_add).parameters
        kwargs.update({key: value for key, value in optional_metadata.items() if key in accepted})
        return await self.bill_manager.async_add(**kwargs)

    @classmethod
    def _anchor_date(cls, data: dict[str, Any]) -> date:
        # Bill history is grouped by the billed/competence month, not by the
        # later due date. Prefer the parsed competence end, then the invoice
        # issue date. Payment/due dates are only fallbacks for parsers that do
        # not expose either billing reference.
        for key in ("period_end", "issue_date", "payment_date", "due_date"):
            parsed = cls._iso_date(data.get(key))
            if parsed:
                return parsed
        return date.today()

    @staticmethod
    def _iso_date(value: Any) -> date | None:
        text = str(value or "").strip()
        if not text:
            return None
        try:
            return date.fromisoformat(text)
        except ValueError:
            return None
