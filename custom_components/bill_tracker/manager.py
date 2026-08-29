"""Persistent data model, bill splitting and forecasting for Bill Tracker."""
from __future__ import annotations

from calendar import monthrange
from collections import defaultdict
from copy import deepcopy
from datetime import date, datetime, timedelta
import json
from math import isfinite
from statistics import mean
from typing import Any
from urllib.parse import quote
from uuid import uuid4

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .const import (
    DEFAULT_CATEGORIES,
    EVENT_UPDATED,
    FALLBACK_COLORS,
    RECURRING_INTERVALS,
    RECURRING_KINDS,
    STORAGE_KEY,
    STORAGE_SCHEMA_VERSION,
    STORAGE_VERSION,
    SUPPORTED_INTERVALS,
)
from .errors import billy_error
from .exporter import (
    csv_bytes,
    csv_template_bytes,
    filter_expenses,
    month_tuple,
    parse_csv_amount,
    parse_csv_bool,
    parse_csv_records,
    pdf_bytes,
    recurring_csv_bytes,
    recurring_pdf_bytes,
    recurring_xlsx_bytes,
    xlsx_bytes,
)


class BillTrackerManager:
    """Persistent bill store, categories, payers, settlements and aggregation logic."""

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass
        self._store: Store[dict[str, Any]] = Store(hass, STORAGE_VERSION, STORAGE_KEY)
        self.expenses: list[dict[str, Any]] = []
        self.categories: list[dict[str, Any]] = []
        self.payers: list[dict[str, Any]] = []
        self.settlements: list[dict[str, Any]] = []
        self.recurring_expenses: list[dict[str, Any]] = []
        self.recurring_occurrences: list[dict[str, Any]] = []

    async def async_load(self) -> None:
        """Load and migrate the persistent database."""
        data = await self._store.async_load() or {}
        self.categories = [dict(x) for x in data.get("categories", [])]
        self.expenses = [dict(x) for x in data.get("expenses", [])]
        self.payers = [dict(x) for x in data.get("payers", [])]
        self.settlements = [dict(x) for x in data.get("settlements", [])]
        self.recurring_expenses = [dict(x) for x in data.get("recurring_expenses", [])]
        self.recurring_occurrences = [dict(x) for x in data.get("recurring_occurrences", [])]

        changed = False
        changed |= self._normalize_payers()
        if not self.categories:
            self.categories = deepcopy(DEFAULT_CATEGORIES)
            changed = True
        changed |= self._normalize_categories()
        changed |= self._migrate_expenses()
        changed |= self._migrate_settlements()
        changed |= self._migrate_recurring_expenses()
        changed |= self._migrate_recurring_occurrences()
        changed |= self._sync_recurring_occurrences()
        self._sort()

        if changed or data.get("schema_version") != STORAGE_SCHEMA_VERSION:
            await self._save()

    @property
    def currency(self) -> str:
        """Return the Home Assistant configured currency (ISO-4217 style)."""
        value = str(getattr(self.hass.config, "currency", "") or "").strip().upper()
        if len(value) == 3 and value.isalpha():
            return value
        return "EUR"

    # ------------------------------------------------------------------
    # Payers
    # ------------------------------------------------------------------
    def payer(self, payer_id: str) -> dict[str, Any] | None:
        return next((x for x in self.payers if x.get("id") == payer_id), None)

    def payer_by_name(self, name: str) -> dict[str, Any] | None:
        wanted = name.strip().casefold()
        return next(
            (x for x in self.payers if str(x.get("name", "")).casefold() == wanted),
            None,
        )

    async def async_add_payer(
        self,
        *,
        name: str,
        share_percent: float = 50.0,
        paypal_me: str = "",
        payment_methods: dict[str, str] | None = None,
        preferred_payment_method: str = "",
        enabled: bool = True,
    ) -> dict[str, Any]:
        name = name.strip()
        self._validate_payer(name, share_percent)
        if self.payer_by_name(name):
            raise billy_error("payer_name_exists")
        methods = self._normalize_payment_methods(payment_methods, paypal_me)
        preferred = self._normalize_preferred_payment_method(
            preferred_payment_method, methods
        )
        item = {
            "id": uuid4().hex,
            "name": name,
            "share_percent": round(float(share_percent), 2),
            "payment_methods": methods,
            "preferred_payment_method": preferred,
            "paypal_me": methods.get("paypal", ""),
            "enabled": bool(enabled),
        }
        self.payers.append(item)
        await self._save_and_notify()
        return dict(item)

    async def async_update_payer(
        self,
        payer_id: str,
        *,
        name: str,
        share_percent: float,
        paypal_me: str,
        payment_methods: dict[str, str] | None = None,
        preferred_payment_method: str = "",
        enabled: bool = True,
    ) -> dict[str, Any] | None:
        name = name.strip()
        self._validate_payer(name, share_percent)
        duplicate = self.payer_by_name(name)
        if duplicate and duplicate.get("id") != payer_id:
            raise billy_error("payer_name_exists")
        item = self.payer(payer_id)
        if item is None:
            return None
        methods = self._normalize_payment_methods(payment_methods, paypal_me)
        preferred = self._normalize_preferred_payment_method(
            preferred_payment_method, methods
        )
        item.update(
            {
                "name": name,
                "share_percent": round(float(share_percent), 2),
                "payment_methods": methods,
                "preferred_payment_method": preferred,
                "paypal_me": methods.get("paypal", ""),
                "enabled": bool(enabled),
            }
        )
        await self._save_and_notify()
        return dict(item)

    async def async_delete_payer(self, payer_id: str) -> bool:
        if any(x.get("payer_id") == payer_id for x in self.expenses):
            raise billy_error("payer_in_history")
        if any(
            any(part.get("payer_id") == payer_id for part in x.get("split", []))
            for x in self.expenses
        ):
            raise billy_error("payer_in_history")
        if any(x.get("payer_id") == payer_id for x in self.recurring_expenses):
            raise billy_error("payer_in_recurring")
        if any(
            any(part.get("payer_id") == payer_id for part in x.get("split", []))
            for x in self.recurring_expenses
        ):
            raise billy_error("payer_in_recurring")
        if any(
            x.get("payer_id") == payer_id
            or any(part.get("payer_id") == payer_id for part in x.get("split", []))
            for x in self.recurring_occurrences
        ):
            raise billy_error("payer_in_recurring_history")
        if any(x.get("default_payer_id") == payer_id for x in self.categories):
            raise billy_error("payer_is_default")
        if any(
            x.get("from_payer_id") == payer_id or x.get("to_payer_id") == payer_id
            for x in self.settlements
        ):
            raise billy_error("payer_in_settlements")
        before = len(self.payers)
        self.payers = [x for x in self.payers if x.get("id") != payer_id]
        changed = len(self.payers) != before
        if changed:
            await self._save_and_notify()
        return changed

    def active_payers(self) -> list[dict[str, Any]]:
        return [dict(x) for x in self.payers if x.get("enabled", True)]

    def default_split(self) -> list[dict[str, Any]]:
        """Return normalized percentages based on active payer weights."""
        active = [x for x in self.payers if x.get("enabled", True)]
        if not active:
            return []
        weights = [max(0.0, float(x.get("share_percent", 0.0) or 0.0)) for x in active]
        total = sum(weights)
        if total <= 0:
            weights = [1.0 for _ in active]
            total = float(len(active))
        result: list[dict[str, Any]] = []
        running = 0.0
        for index, (payer, weight) in enumerate(zip(active, weights)):
            if index == len(active) - 1:
                pct = round(100.0 - running, 2)
            else:
                pct = round(weight / total * 100.0, 2)
                running += pct
            result.append({"payer_id": str(payer["id"]), "percentage": pct})
        return result

    # ------------------------------------------------------------------
    # Categories
    # ------------------------------------------------------------------
    def category(self, category_id: str) -> dict[str, Any] | None:
        return next((x for x in self.categories if x.get("id") == category_id), None)

    def category_by_name(self, name: str) -> dict[str, Any] | None:
        wanted = name.strip().casefold()
        return next(
            (x for x in self.categories if str(x.get("name", "")).casefold() == wanted),
            None,
        )

    async def async_add_category(
        self,
        *,
        name: str,
        interval_months: int,
        enabled: bool = True,
        default_payer_id: str | None = None,
        color: str | None = None,
        consumption_unit: str = "",
        default_provider: str = "",
        default_contract: str = "",
    ) -> dict[str, Any]:
        name = name.strip()
        self._validate_category(name, interval_months)
        if self.category_by_name(name):
            raise billy_error("category_name_exists")
        payer_id = self._validate_optional_payer(default_payer_id)
        item = {
            "id": uuid4().hex,
            "name": name,
            "interval_months": int(interval_months),
            "enabled": bool(enabled),
            "default_payer_id": payer_id,
            "color": self._normalize_color(color, len(self.categories)),
            "consumption_unit": self._normalize_consumption_unit(consumption_unit),
            "default_provider": self._normalize_optional_text(default_provider, 100),
            "default_contract": self._normalize_optional_text(default_contract, 100),
        }
        self.categories.append(item)
        await self._save_and_notify()
        return dict(item)

    async def async_update_category(
        self,
        category_id: str,
        *,
        name: str,
        interval_months: int,
        enabled: bool,
        default_payer_id: str | None = None,
        color: str | None = None,
        consumption_unit: str = "",
        default_provider: str = "",
        default_contract: str = "",
    ) -> dict[str, Any] | None:
        name = name.strip()
        self._validate_category(name, interval_months)
        duplicate = self.category_by_name(name)
        if duplicate and duplicate.get("id") != category_id:
            raise billy_error("category_name_exists")
        item = self.category(category_id)
        if item is None:
            return None
        payer_id = self._validate_optional_payer(default_payer_id)
        item.update(
            {
                "name": name,
                "interval_months": int(interval_months),
                "enabled": bool(enabled),
                "default_payer_id": payer_id,
                "color": self._normalize_color(color or item.get("color"), 0),
                "consumption_unit": self._normalize_consumption_unit(consumption_unit),
                "default_provider": self._normalize_optional_text(default_provider, 100),
                "default_contract": self._normalize_optional_text(default_contract, 100),
            }
        )
        await self._save_and_notify()
        return dict(item)

    async def async_delete_category(self, category_id: str) -> bool:
        if any(x.get("category_id") == category_id for x in self.expenses):
            raise billy_error("category_has_history")
        before = len(self.categories)
        self.categories = [x for x in self.categories if x.get("id") != category_id]
        changed = len(self.categories) != before
        if changed:
            await self._save_and_notify()
        return changed

    # ------------------------------------------------------------------
    # Expenses
    # ------------------------------------------------------------------
    async def async_add(
        self,
        *,
        year: int,
        month: int,
        category_id: str | None,
        category_name: str | None,
        amount: float,
        note: str = "",
        period_start_year: int | None = None,
        period_start_month: int | None = None,
        period_end_year: int | None = None,
        period_end_month: int | None = None,
        period_start_date: str | None = None,
        period_end_date: str | None = None,
        payer_id: str | None = None,
        split: list[dict[str, Any]] | None = None,
        paid: bool = False,
        payment_date: str | None = None,
        due_date: str | None = None,        provider: str | None = None,
        contract: str | None = None,
        consumption: float | None = None,
    ) -> dict[str, Any]:
        category = self._resolve_category(category_id, category_name)
        self._validate_date(year, month)
        self._validate_amount(amount)
        sy, sm, ey, em = self._normalize_period(
            year, month, int(category["interval_months"]),
            period_start_year, period_start_month, period_end_year, period_end_month,
        )
        resolved_payer = self._resolve_expense_payer(category, payer_id)
        normalized_split = self._resolve_expense_split(split, resolved_payer)
        normalized_payment_date = self._normalize_optional_iso_date(payment_date)
        normalized_due_date = self._normalize_optional_iso_date(due_date)
        if paid and not normalized_payment_date:
            normalized_payment_date = date.today().isoformat()
        normalized_period_start_date = self._normalize_optional_iso_date(period_start_date)
        normalized_period_end_date = self._normalize_optional_iso_date(period_end_date)
        if normalized_period_start_date and normalized_period_end_date:
            if normalized_period_start_date > normalized_period_end_date:
                raise billy_error("period_start_after_end")
            start_date = date.fromisoformat(normalized_period_start_date)
            end_date = date.fromisoformat(normalized_period_end_date)
            sy, sm = start_date.year, start_date.month
            ey, em = end_date.year, end_date.month
        normalized_consumption = self._normalize_optional_consumption(consumption)
        item = {
            "id": uuid4().hex,
            "paid_year": int(year),
            "paid_month": int(month),
            "category_id": str(category["id"]),
            "amount": round(float(amount), 2),
            "period_start_year": sy,
            "period_start_month": sm,
            "period_end_year": ey,
            "period_end_month": em,
            "period_start_date": normalized_period_start_date,
            "period_end_date": normalized_period_end_date,
            "payer_id": resolved_payer,
            "split": normalized_split,
            "reimbursement_manual_done": False,
            "reimbursement_manual_at": None,
            "paid": bool(paid),
            "payment_date": normalized_payment_date,
            "due_date": normalized_due_date,
            "provider": self._normalize_optional_text(category.get("default_provider", "") if provider is None else provider, 100),
            "contract": self._normalize_optional_text(category.get("default_contract", "") if contract is None else contract, 100),
            "consumption": normalized_consumption,
            "consumption_unit": str(category.get("consumption_unit", "")),
            "note": note.strip(),
            "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        }
        self.expenses.append(item)
        self._sort()
        await self._save_and_notify()
        return self._public_expense(item)

    async def async_update(
        self,
        expense_id: str,
        *,
        year: int,
        month: int,
        category_id: str | None,
        category_name: str | None,
        amount: float,
        note: str = "",
        period_start_year: int | None = None,
        period_start_month: int | None = None,
        period_end_year: int | None = None,
        period_end_month: int | None = None,
        period_start_date: str | None = None,
        period_end_date: str | None = None,
        payer_id: str | None = None,
        split: list[dict[str, Any]] | None = None,
        paid: bool | None = None,
        payment_date: str | None = None,
        due_date: str | None = None,
        provider: str | None = None,
        contract: str | None = None,
        consumption: float | None = None,
    ) -> dict[str, Any] | None:
        category = self._resolve_category(category_id, category_name)
        self._validate_date(year, month)
        self._validate_amount(amount)
        sy, sm, ey, em = self._normalize_period(
            year, month, int(category["interval_months"]),
            period_start_year, period_start_month, period_end_year, period_end_month,
        )
        resolved_payer = self._resolve_expense_payer(category, payer_id)
        normalized_split = self._resolve_expense_split(split, resolved_payer)
        normalized_payment_date = (
            self._normalize_optional_iso_date(payment_date) if payment_date is not None else None
        )
        normalized_due_date = (
            self._normalize_optional_iso_date(due_date) if due_date is not None else None
        )
        normalized_period_start_date = (
            self._normalize_optional_iso_date(period_start_date)
            if period_start_date is not None
            else None
        )
        normalized_period_end_date = (
            self._normalize_optional_iso_date(period_end_date)
            if period_end_date is not None
            else None
        )
        if normalized_period_start_date and normalized_period_end_date:
            if normalized_period_start_date > normalized_period_end_date:
                raise billy_error("period_start_after_end")
            start_date = date.fromisoformat(normalized_period_start_date)
            end_date = date.fromisoformat(normalized_period_end_date)
            sy, sm = start_date.year, start_date.month
            ey, em = end_date.year, end_date.month
        normalized_consumption = self._normalize_optional_consumption(consumption)
        for item in self.expenses:
            if item.get("id") != expense_id:
                continue
            resolved_paid = bool(paid) if paid is not None else bool(item.get("paid", False))
            resolved_payment_date = (
                normalized_payment_date if payment_date is not None else item.get("payment_date")
            )
            if resolved_paid and not resolved_payment_date:
                resolved_payment_date = date.today().isoformat()
            if not resolved_paid:
                resolved_payment_date = None
            reimbursement_changed = (
                round(float(item.get("amount", 0.0) or 0.0), 2) != round(float(amount), 2)
                or str(item.get("payer_id") or "") != str(resolved_payer or "")
                or list(item.get("split", [])) != normalized_split
            )
            item.update(
                {
                    "paid_year": int(year),
                    "paid_month": int(month),
                    "category_id": str(category["id"]),
                    "amount": round(float(amount), 2),
                    "period_start_year": sy,
                    "period_start_month": sm,
                    "period_end_year": ey,
                    "period_end_month": em,
                    "period_start_date": (
                        normalized_period_start_date
                        if period_start_date is not None
                        else item.get("period_start_date")
                    ),
                    "period_end_date": (
                        normalized_period_end_date
                        if period_end_date is not None
                        else item.get("period_end_date")
                    ),
                    "payer_id": resolved_payer,
                    "split": normalized_split,
                    "reimbursement_manual_done": (
                        False if reimbursement_changed else bool(item.get("reimbursement_manual_done", False))
                    ),
                    "reimbursement_manual_at": (
                        None if reimbursement_changed else item.get("reimbursement_manual_at")
                    ),
                    "paid": resolved_paid,
                    "payment_date": resolved_payment_date,
                    "due_date": normalized_due_date if due_date is not None else item.get("due_date"),
                    "provider": self._normalize_optional_text(provider, 100) if provider is not None else str(item.get("provider", "")),
                    "contract": self._normalize_optional_text(contract, 100) if contract is not None else str(item.get("contract", "")),
                    "consumption": normalized_consumption,
                    "consumption_unit": str(category.get("consumption_unit", "")),
                    "note": note.strip(),
                }
            )
            self._sort()
            await self._save_and_notify()
            return self._public_expense(item)
        return None

    async def async_set_paid(self, expense_id: str, paid: bool) -> dict[str, Any] | None:
        """Set only the payment status of an expense without rewriting its other fields."""
        for item in self.expenses:
            if item.get("id") != expense_id:
                continue
            item["paid"] = bool(paid)
            if paid:
                if not item.get("payment_date"):
                    item["payment_date"] = date.today().isoformat()
            else:
                item["payment_date"] = None
            await self._save_and_notify()
            return self._public_expense(item)
        return None

    async def async_set_reimbursement_done(
        self, expense_id: str, done: bool
    ) -> dict[str, Any] | None:
        """Manually mark all user reimbursements for one bill as done or pending.

        This flag is intentionally independent from the provider-payment state.
        Bills already linked to a recorded settlement are managed through the
        reimbursement history, so the manual flag cannot override them.
        """
        for item in self.expenses:
            if item.get("id") != expense_id:
                continue
            state = self._expense_reimbursement_state(item)
            if state["status"] == "none":
                raise billy_error("expense_no_reimbursement")
            if state["has_recorded_settlement"]:
                raise billy_error("expense_settlement_linked")
            item["reimbursement_manual_done"] = bool(done)
            item["reimbursement_manual_at"] = (
                datetime.now().astimezone().isoformat(timespec="seconds") if done else None
            )
            await self._save_and_notify()
            return self._public_expense(item)
        return None

    async def async_delete(self, expense_id: str) -> bool:
        before = len(self.expenses)
        self.expenses = [x for x in self.expenses if x.get("id") != expense_id]
        changed = len(self.expenses) != before
        if changed:
            await self._save_and_notify()
        return changed

    # ------------------------------------------------------------------
    # Recurring expenses (subscriptions, mortgages and installments)
    # ------------------------------------------------------------------
    def recurring_expense(self, recurring_id: str) -> dict[str, Any] | None:
        return next((x for x in self.recurring_expenses if x.get("id") == recurring_id), None)

    async def async_add_recurring(
        self,
        *,
        name: str,
        kind: str,
        amount: float,
        interval_months: int,
        start_date: str,
        end_date: str | None = None,
        auto_renew: bool = False,
        renewal_interval_months: int = 12,
        installment_count: int | None = None,
        payer_id: str | None = None,
        split: list[dict[str, Any]] | None = None,
        provider: str = "",
        contract: str = "",
        color: str | None = None,
        note: str = "",
        active: bool = True,
    ) -> dict[str, Any]:
        item = self._normalize_recurring_payload(
            name=name,
            kind=kind,
            amount=amount,
            interval_months=interval_months,
            start_date=start_date,
            end_date=end_date,
            auto_renew=auto_renew,
            renewal_interval_months=renewal_interval_months,
            installment_count=installment_count,
            payer_id=payer_id,
            split=split,
            provider=provider,
            contract=contract,
            color=color,
            note=note,
            active=active,
        )
        item.update(
            {
                "id": uuid4().hex,
                "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            }
        )
        item["reimbursement_tracking_start_date"] = self._recurring_tracking_start(item)
        self.recurring_expenses.append(item)
        self._sync_recurring_occurrences()
        self._sort()
        await self._save_and_notify()
        return self._public_recurring_expense(item)

    async def async_update_recurring(
        self,
        recurring_id: str,
        *,
        name: str,
        kind: str,
        amount: float,
        interval_months: int,
        start_date: str,
        end_date: str | None = None,
        auto_renew: bool = False,
        renewal_interval_months: int = 12,
        installment_count: int | None = None,
        payer_id: str | None = None,
        split: list[dict[str, Any]] | None = None,
        provider: str = "",
        contract: str = "",
        color: str | None = None,
        note: str = "",
        active: bool = True,
    ) -> dict[str, Any] | None:
        current = self.recurring_expense(recurring_id)
        if current is None:
            return None
        was_active = bool(current.get("active", True))
        normalized = self._normalize_recurring_payload(
            name=name,
            kind=kind,
            amount=amount,
            interval_months=interval_months,
            start_date=start_date,
            end_date=end_date,
            auto_renew=auto_renew,
            renewal_interval_months=renewal_interval_months,
            installment_count=installment_count,
            payer_id=payer_id,
            split=split,
            provider=provider,
            contract=contract,
            color=color or current.get("color"),
            note=note,
            active=active,
        )
        schedule_changed = any(
            current.get(key) != normalized.get(key)
            for key in ("start_date", "end_date", "interval_months", "installment_count")
        )
        current.update(normalized)
        if schedule_changed or (not was_active and bool(current.get("active", True))):
            current["reimbursement_tracking_start_date"] = self._recurring_tracking_start(
                current, on_or_after=date.today() + timedelta(days=1)
            )
        self._refresh_open_recurring_occurrences(current)
        current["updated_at"] = datetime.now().astimezone().isoformat(timespec="seconds")
        self._sync_recurring_occurrences()
        self._sort()
        await self._save_and_notify()
        return self._public_recurring_expense(current)

    async def async_set_recurring_active(
        self, recurring_id: str, active: bool
    ) -> dict[str, Any] | None:
        item = self.recurring_expense(recurring_id)
        if item is None:
            return None
        was_active = bool(item.get("active", True))
        item["active"] = bool(active)
        if not was_active and active:
            # Resume from the next real charge and do not backfill the paused gap.
            item["reimbursement_tracking_start_date"] = self._recurring_tracking_start(
                item, on_or_after=date.today()
            )
            self._sync_recurring_occurrences()
        item["updated_at"] = datetime.now().astimezone().isoformat(timespec="seconds")
        self._sort()
        await self._save_and_notify()
        return self._public_recurring_expense(item)

    async def async_delete_recurring(self, recurring_id: str) -> bool:
        linked_occurrence_ids = {
            str(x.get("id"))
            for x in self.recurring_occurrences
            if x.get("recurring_id") == recurring_id
        }
        if linked_occurrence_ids and any(
            linked_occurrence_ids.intersection(
                {str(value) for value in settlement.get("recurring_occurrence_ids", []) if value}
            )
            for settlement in self.settlements
        ):
            raise billy_error("recurring_in_settlements")
        before = len(self.recurring_expenses)
        self.recurring_expenses = [
            x for x in self.recurring_expenses if x.get("id") != recurring_id
        ]
        changed = len(self.recurring_expenses) != before
        if changed:
            self.recurring_occurrences = [
                x for x in self.recurring_occurrences if x.get("recurring_id") != recurring_id
            ]
            await self._save_and_notify()
        return changed

    async def async_set_recurring_reimbursement_done(
        self, occurrence_id: str, done: bool
    ) -> dict[str, Any] | None:
        """Mark one materialized recurring charge reimbursement done or pending."""
        self._sync_recurring_occurrences()
        item = next(
            (x for x in self.recurring_occurrences if x.get("id") == occurrence_id),
            None,
        )
        if item is None:
            return None
        state = self._recurring_occurrence_reimbursement_state(item)
        if state["status"] == "none":
            raise billy_error("recurring_no_reimbursement")
        if state["has_recorded_settlement"]:
            raise billy_error("recurring_settlement_linked")
        item["reimbursement_manual_done"] = bool(done)
        item["reimbursement_manual_at"] = (
            datetime.now().astimezone().isoformat(timespec="seconds") if done else None
        )
        await self._save_and_notify()
        return self._public_recurring_occurrence(item)

    async def async_import_csv(
        self,
        csv_text: str,
        *,
        create_missing_categories: bool = True,
        create_missing_payers: bool = True,
    ) -> dict[str, Any]:
        """Import bill rows from a CSV file and persist once at the end.

        Billy's own export format is round-trip friendly, while a small set of
        English/Italian column aliases is accepted for hand-authored files.
        Existing IDs are skipped so re-importing the same Billy export does not
        duplicate those rows.
        """
        records = parse_csv_records(csv_text)
        if len(records) > 5000:
            raise billy_error("csv_too_many_rows")

        existing_ids = {str(x.get("id")) for x in self.expenses if x.get("id")}
        imported = 0
        skipped = 0
        created_categories = 0
        created_payers = 0
        errors: list[str] = []
        error_count = 0
        changed = False

        def ensure_category(
            name: str, interval: int, consumption_unit: str = "",
            default_provider: str = "", default_contract: str = "",
        ) -> dict[str, Any]:
            nonlocal created_categories, changed
            self._validate_category(name, interval)
            category = self.category_by_name(name)
            if category is not None:
                return category
            if not create_missing_categories:
                raise billy_error("csv_unknown_category", name=name)
            if interval not in SUPPORTED_INTERVALS:
                raise billy_error("csv_unsupported_interval", name=name, interval=interval)
            category = {
                "id": uuid4().hex,
                "name": name,
                "interval_months": interval,
                "enabled": True,
                "default_payer_id": None,
                "color": self._normalize_color(None, len(self.categories)),
                "consumption_unit": self._normalize_consumption_unit(consumption_unit),
                "default_provider": self._normalize_optional_text(default_provider, 100),
                "default_contract": self._normalize_optional_text(default_contract, 100),
            }
            self.categories.append(category)
            created_categories += 1
            changed = True
            return category

        def ensure_payer(name: str, share: float = 50.0) -> dict[str, Any]:
            nonlocal created_payers, changed
            self._validate_payer(name, share)
            payer = self.payer_by_name(name)
            if payer is not None:
                return payer
            if not create_missing_payers:
                raise billy_error("csv_unknown_payer", name=name)
            payer = {
                "id": uuid4().hex,
                "name": name,
                "share_percent": round(max(0.0, min(100.0, float(share))), 2),
                "payment_methods": {},
                "preferred_payment_method": "",
                "paypal_me": "",
                "enabled": True,
            }
            self.payers.append(payer)
            created_payers += 1
            changed = True
            return payer

        for line_no, row in records:
            try:
                incoming_id = str(row.get("id") or "").strip()
                if incoming_id and incoming_id in existing_ids:
                    skipped += 1
                    continue

                category_name = str(row.get("category") or "").strip()
                if not category_name:
                    raise billy_error("csv_missing_category")
                interval = int(row.get("interval_months") or 1)
                category = ensure_category(
                    category_name, interval, str(row.get("consumption_unit") or ""),
                    str(row.get("provider") or ""), str(row.get("contract") or ""),
                )

                amount = parse_csv_amount(row.get("amount", ""))
                self._validate_amount(amount)

                billing = month_tuple(row.get("billing_month"))
                if billing is None:
                    billing = (int(row.get("year") or 0), int(row.get("month") or 0))
                year, month = billing
                self._validate_date(year, month)

                raw_period_start = str(row.get("period_start") or "").strip()
                raw_period_end = str(row.get("period_end") or "").strip()
                period_start_date = (
                    self._normalize_optional_iso_date(raw_period_start)
                    if len(raw_period_start) == 10
                    else None
                )
                period_end_date = (
                    self._normalize_optional_iso_date(raw_period_end)
                    if len(raw_period_end) == 10
                    else None
                )
                period_start = month_tuple(raw_period_start[:7] if raw_period_start else None)
                period_end = month_tuple(raw_period_end[:7] if raw_period_end else None)
                sy, sm, ey, em = self._normalize_period(
                    year, month, int(category["interval_months"]),
                    period_start[0] if period_start else None,
                    period_start[1] if period_start else None,
                    period_end[0] if period_end else None,
                    period_end[1] if period_end else None,
                )

                payer_id = None
                payer_name = str(row.get("payer") or "").strip()
                if payer_name:
                    payer_id = str(ensure_payer(payer_name)["id"])
                resolved_payer = self._resolve_expense_payer(category, payer_id)

                split = None
                raw_split = str(row.get("split") or "").strip()
                if raw_split:
                    parsed_split = []
                    for token in raw_split.split("|"):
                        token = token.strip()
                        if not token:
                            continue
                        if ":" not in token:
                            raise billy_error("csv_invalid_share", token=token)
                        split_name, pct_text = token.rsplit(":", 1)
                        pct = float(pct_text.strip().replace(",", "."))
                        participant = ensure_payer(split_name.strip(), pct)
                        parsed_split.append({"payer_id": str(participant["id"]), "percentage": pct})
                    split = parsed_split
                normalized_split = self._resolve_expense_split(split, resolved_payer)

                paid = parse_csv_bool(row.get("paid", ""))
                payment_date = self._normalize_optional_iso_date(row.get("payment_date"))
                due_date = self._normalize_optional_iso_date(row.get("due_date"))
                incoming_currency = str(row.get("currency") or "").strip().upper()
                if incoming_currency and incoming_currency != self.currency:
                    raise billy_error("csv_currency_mismatch", incoming=incoming_currency, current=self.currency)
                consumption_text = str(row.get("consumption") or "").strip()
                consumption = self._normalize_optional_consumption(
                    float(consumption_text.replace(",", ".")) if consumption_text else None
                )
                expense_id = incoming_id or uuid4().hex
                while expense_id in existing_ids:
                    expense_id = uuid4().hex

                item = {
                    "id": expense_id,
                    "paid_year": int(year),
                    "paid_month": int(month),
                    "category_id": str(category["id"]),
                    "amount": round(float(amount), 2),
                    "period_start_year": sy,
                    "period_start_month": sm,
                    "period_end_year": ey,
                    "period_end_month": em,
                    "period_start_date": period_start_date,
                    "period_end_date": period_end_date,
                    "payer_id": resolved_payer,
                    "split": normalized_split,
                    "paid": paid,
                    "payment_date": payment_date,
                    "due_date": due_date,
                    "provider": self._normalize_optional_text(row.get("provider", ""), 100),
                    "contract": self._normalize_optional_text(row.get("contract", ""), 100),
                    "consumption": consumption,
                    "consumption_unit": self._normalize_consumption_unit(
                        row.get("consumption_unit") or category.get("consumption_unit", "")
                    ),
                    "note": str(row.get("note") or "").strip(),
                    "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
                }
                self.expenses.append(item)
                existing_ids.add(expense_id)
                imported += 1
                changed = True
            except (ValueError, TypeError, OverflowError) as err:
                error_count += 1
                if len(errors) < 30:
                    errors.append(f"Riga {line_no}: {err}")

        if changed:
            self._sort()
            await self._save_and_notify()
        return {
            "imported": imported,
            "skipped": skipped,
            "errors": errors,
            "error_count": error_count,
            "created_categories": created_categories,
            "created_payers": created_payers,
        }

    def export_data(
        self,
        *,
        file_format: str,
        from_month: str | None = None,
        to_month: str | None = None,
        status: str = "all",
        category_id: str | None = None,
        trend: str = "both",
        language: str = "en",
    ) -> tuple[bytes, str, str]:
        """Return exported bytes, MIME type and extension for the requested format."""
        fmt = str(file_format or "csv").lower()
        if fmt not in {"csv", "xlsx", "pdf"}:
            raise billy_error("export_format_unsupported")
        public_rows = [self._public_expense(x) for x in self.expenses]
        rows = filter_expenses(
            public_rows,
            from_month=from_month,
            to_month=to_month,
            status=status,
            category_id=category_id,
        )
        category_lookup = {str(x["id"]): dict(x) for x in self.categories}
        if fmt == "csv":
            return csv_bytes(rows, category_lookup, currency=self.currency), "text/csv;charset=utf-8", "csv"
        if fmt == "xlsx":
            return (
                xlsx_bytes(rows, category_lookup, from_month=from_month, to_month=to_month, currency=self.currency, language=language),
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                "xlsx",
            )
        return (
            pdf_bytes(
                rows, category_lookup, from_month=from_month, to_month=to_month, trend=trend, currency=self.currency, language=language,
            ),
            "application/pdf",
            "pdf",
        )

    def export_csv_template(self) -> bytes:
        return csv_template_bytes()

    def export_recurring_data(
        self,
        *,
        file_format: str,
        status: str = "all",
        kind: str = "all",
        from_date: str | None = None,
        to_date: str | None = None,
        language: str = "en",
    ) -> tuple[bytes, str, str]:
        """Export recurring rules in CSV, XLSX or PDF form."""
        fmt = str(file_format or "csv").lower()
        if fmt not in {"csv", "xlsx", "pdf"}:
            raise billy_error("export_format_unsupported")

        rows = [self._public_recurring_expense(x) for x in self.recurring_expenses]
        wanted_status = str(status or "all")
        wanted_kind = str(kind or "all")
        range_start = date.fromisoformat(from_date) if from_date else None
        range_end = date.fromisoformat(to_date) if to_date else None
        if range_start and range_end and range_start > range_end:
            range_start, range_end = range_end, range_start
        if wanted_status != "all":
            rows = [row for row in rows if str(row.get("status") or "") == wanted_status]
        if wanted_kind != "all":
            rows = [row for row in rows if str(row.get("kind") or "") == wanted_kind]
        if range_start or range_end:
            filtered = []
            for row in rows:
                start = date.fromisoformat(str(row.get("start_date")))
                raw_end = str(row.get("end_date") or "")
                end = None if bool(row.get("auto_renew", False)) or not raw_end else date.fromisoformat(raw_end)
                if range_end and start > range_end:
                    continue
                if range_start and end and end < range_start:
                    continue
                filtered.append(row)
            rows = filtered
        rows.sort(key=lambda row: str(row.get("name") or "").casefold())

        if fmt == "csv":
            return recurring_csv_bytes(rows, currency=self.currency), "text/csv;charset=utf-8", "csv"
        if fmt == "xlsx":
            return (
                recurring_xlsx_bytes(rows, currency=self.currency),
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                "xlsx",
            )
        return (
            recurring_pdf_bytes(rows, currency=self.currency, language=language),
            "application/pdf",
            "pdf",
        )

    def export_backup(self) -> bytes:
        """Return a complete round-trip backup of Billy's persistent data."""
        payload = {
            "format": "billy-backup",
            "version": 1,
            "schema_version": STORAGE_SCHEMA_VERSION,
            "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "currency": self.currency,
            "data": {
                "categories": deepcopy(self.categories),
                "payers": deepcopy(self.payers),
                "expenses": deepcopy(self.expenses),
                "settlements": deepcopy(self.settlements),
                "recurring_expenses": deepcopy(self.recurring_expenses),
                "recurring_occurrences": deepcopy(self.recurring_occurrences),
            },
        }
        return json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")

    async def async_import_backup(self, content: str) -> dict[str, int]:
        """Replace Billy data with a validated backup, including recurring data."""
        try:
            payload = json.loads(content)
        except json.JSONDecodeError as err:
            raise billy_error("backup_invalid_json") from err
        if not isinstance(payload, dict) or payload.get("format") != "billy-backup":
            raise billy_error("backup_not_billy")
        if int(payload.get("version", 0) or 0) != 1:
            raise billy_error("backup_unsupported_version")
        data = payload.get("data")
        if not isinstance(data, dict):
            raise billy_error("backup_no_data")

        keys = (
            "categories",
            "payers",
            "expenses",
            "settlements",
            "recurring_expenses",
            "recurring_occurrences",
        )
        for key in keys:
            if not isinstance(data.get(key, []), list):
                raise billy_error("backup_invalid_section", key=key)
        if len(data.get("expenses", [])) > 50_000:
            raise billy_error("backup_too_many_bills")
        if len(data.get("recurring_expenses", [])) > 10_000:
            raise billy_error("backup_too_many_recurring")

        previous = {key: deepcopy(getattr(self, key)) for key in keys}
        try:
            for key in keys:
                setattr(self, key, [dict(item) for item in data.get(key, [])])
            self._normalize_payers()
            if not self.categories:
                self.categories = deepcopy(DEFAULT_CATEGORIES)
            self._normalize_categories()
            self._migrate_expenses()
            self._migrate_settlements()
            self._migrate_recurring_expenses()
            self._migrate_recurring_occurrences()
            self._sync_recurring_occurrences()
            self._sort()
            await self._save_and_notify()
        except Exception:
            for key, value in previous.items():
                setattr(self, key, value)
            raise

        return {
            "categories": len(self.categories),
            "payers": len(self.payers),
            "expenses": len(self.expenses),
            "settlements": len(self.settlements),
            "recurring_expenses": len(self.recurring_expenses),
            "recurring_occurrences": len(self.recurring_occurrences),
        }

    # ------------------------------------------------------------------
    # Settlements / debt netting
    # ------------------------------------------------------------------
    async def async_add_settlement(
        self,
        *,
        from_payer_id: str,
        to_payer_id: str,
        amount: float,
        note: str = "",
    ) -> dict[str, Any]:
        """Record one complete reimbursement between payers.

        Bill payment and payer reimbursements are deliberately independent.
        ``expense.paid`` means the utility/provider bill itself has actually
        been paid by the payer. A settlement only records money transferred
        between Billy participants and must never change that bill status.
        """
        source = self.payer(from_payer_id)
        target = self.payer(to_payer_id)
        if source is None or target is None or from_payer_id == to_payer_id:
            raise billy_error("settlement_invalid_payers")
        self._validate_amount(amount, allow_zero=False)

        debt = next(
            (
                x for x in self.debts()
                if x["from_payer_id"] == from_payer_id and x["to_payer_id"] == to_payer_id
            ),
            None,
        )
        if debt is None or float(debt.get("amount", 0.0)) <= 0:
            raise billy_error("settlement_none_open")

        outstanding = float(debt["amount"])
        if abs(float(amount) - outstanding) > 0.01:
            raise billy_error("settlement_partial_unsupported")

        expense_ids = [str(x) for x in debt.get("expense_ids", []) if x]
        recurring_occurrence_ids = [
            str(x) for x in debt.get("recurring_occurrence_ids", []) if x
        ]
        if not expense_ids and not recurring_occurrence_ids:
            raise billy_error("settlement_no_expense")

        item = {
            "id": uuid4().hex,
            "from_payer_id": from_payer_id,
            "to_payer_id": to_payer_id,
            "amount": round(outstanding, 2),
            "expense_ids": expense_ids,
            "recurring_occurrence_ids": recurring_occurrence_ids,
            "note": note.strip(),
            "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        }
        self.settlements.append(item)
        self._sort()
        await self._save_and_notify()
        return self._public_settlement(item)

    async def async_delete_settlement(self, settlement_id: str) -> bool:
        """Undo a recorded payer reimbursement without touching bill status."""
        item = next((x for x in self.settlements if x.get("id") == settlement_id), None)
        if item is None:
            return False
        self.settlements = [x for x in self.settlements if x.get("id") != settlement_id]
        await self._save_and_notify()
        return True

    def _pairwise_debts(self) -> list[dict[str, Any]]:
        """Build outstanding reimbursements independently from bill payment status."""
        self._sync_recurring_occurrences()
        gross: dict[tuple[str, str], float] = defaultdict(float)
        expense_ids: dict[tuple[str, str], set[str]] = defaultdict(set)
        recurring_occurrence_ids: dict[tuple[str, str], set[str]] = defaultdict(set)

        # Every split bill creates a reimbursement obligation towards the payer
        # who advanced the provider bill. Whether that provider bill is paid is
        # a separate state and therefore intentionally not checked here.
        for item in self.expenses:
            if bool(item.get("reimbursement_manual_done", False)):
                continue
            creditor = str(item.get("payer_id") or "")
            if self.payer(creditor) is None:
                continue
            amount = float(item.get("amount", 0.0) or 0.0)
            if amount <= 0:
                continue
            item_id = str(item.get("id") or "")
            for part in item.get("split", []):
                debtor = str(part.get("payer_id") or "")
                if not debtor or debtor == creditor or self.payer(debtor) is None:
                    continue
                percentage = float(part.get("percentage", 0.0) or 0.0)
                share = amount * percentage / 100.0
                if share <= 0.009:
                    continue
                key = (debtor, creditor)
                gross[key] += share
                if item_id:
                    expense_ids[key].add(item_id)

        # Due recurring charges use the same split logic as normal bills. Each
        # materialized occurrence keeps an amount/payer/split snapshot so later
        # edits to the recurring rule do not rewrite reimbursement history.
        for item in self.recurring_occurrences:
            if bool(item.get("reimbursement_manual_done", False)):
                continue
            creditor = str(item.get("payer_id") or "")
            if self.payer(creditor) is None:
                continue
            amount = float(item.get("amount", 0.0) or 0.0)
            if amount <= 0:
                continue
            occurrence_id = str(item.get("id") or "")
            for part in item.get("split", []):
                debtor = str(part.get("payer_id") or "")
                if not debtor or debtor == creditor or self.payer(debtor) is None:
                    continue
                percentage = float(part.get("percentage", 0.0) or 0.0)
                share = amount * percentage / 100.0
                if share <= 0.009:
                    continue
                key = (debtor, creditor)
                gross[key] += share
                if occurrence_id:
                    recurring_occurrence_ids[key].add(occurrence_id)

        # Recorded reimbursements reduce only the participant-to-participant
        # balance. They never mutate ``expense.paid``.
        settled: dict[tuple[str, str], float] = defaultdict(float)
        for item in self.settlements:
            source = str(item.get("from_payer_id") or "")
            target = str(item.get("to_payer_id") or "")
            amount = float(item.get("amount", 0.0) or 0.0)
            if source and target and source != target and amount > 0:
                settled[(source, target)] += amount

        payer_ids = [str(x["id"]) for x in self.payers]
        result: list[dict[str, Any]] = []
        seen: set[frozenset[str]] = set()
        for left in payer_ids:
            for right in payer_ids:
                if left == right:
                    continue
                pair = frozenset((left, right))
                if pair in seen:
                    continue
                seen.add(pair)
                left_to_right = max(0.0, gross.get((left, right), 0.0) - settled.get((left, right), 0.0))
                right_to_left = max(0.0, gross.get((right, left), 0.0) - settled.get((right, left), 0.0))
                net = round(left_to_right - right_to_left, 2)
                if abs(net) <= 0.009:
                    continue
                if net > 0:
                    from_id, to_id, value = left, right, net
                else:
                    from_id, to_id, value = right, left, -net
                source = self.payer(from_id)
                target = self.payer(to_id)
                if source is None or target is None:
                    continue
                linked = sorted(
                    expense_ids.get((left, right), set())
                    | expense_ids.get((right, left), set())
                )
                recurring_linked = sorted(
                    recurring_occurrence_ids.get((left, right), set())
                    | recurring_occurrence_ids.get((right, left), set())
                )
                payment = self._preferred_payment(target, value, self.currency)
                result.append(
                    {
                        "from_payer_id": from_id,
                        "from_name": str(source.get("name", "")),
                        "to_payer_id": to_id,
                        "to_name": str(target.get("name", "")),
                        "amount": round(value, 2),
                        "expense_ids": linked,
                        "expense_count": len(linked),
                        "recurring_occurrence_ids": recurring_linked,
                        "recurring_count": len(recurring_linked),
                        "item_count": len(linked) + len(recurring_linked),
                        "payment_method": payment["method"],
                        "payment_handle": payment["handle"],
                        "payment_url": payment["url"],
                        "payment_methods": dict(target.get("payment_methods", {})),
                        "paypal_me": str(target.get("paypal_me", "")),
                        "paypal_url": (
                            payment["url"] if payment["method"] == "paypal" else ""
                        ),
                    }
                )
        result.sort(key=lambda x: float(x["amount"]), reverse=True)
        return result

    def balances(self) -> list[dict[str, Any]]:
        """Return payer positions generated by outstanding reimbursements."""
        positions: dict[str, float] = {str(x["id"]): 0.0 for x in self.payers}
        for debt in self._pairwise_debts():
            source = str(debt["from_payer_id"])
            target = str(debt["to_payer_id"])
            amount = float(debt["amount"])
            if source in positions:
                positions[source] -= amount
            if target in positions:
                positions[target] += amount
        return [
            {
                "payer_id": str(payer["id"]),
                "name": str(payer["name"]),
                "balance": round(positions.get(str(payer["id"]), 0.0), 2),
                "status": (
                    "credit" if positions.get(str(payer["id"]), 0.0) > 0.009
                    else "debt" if positions.get(str(payer["id"]), 0.0) < -0.009
                    else "even"
                ),
            }
            for payer in self.payers
        ]

    def debts(self) -> list[dict[str, Any]]:
        """Return outstanding pairwise reimbursements between Billy payers."""
        return self._pairwise_debts()

    # ------------------------------------------------------------------
    # Public snapshot / aggregations
    # ------------------------------------------------------------------
    def snapshot(self, forecast_months: int = 12) -> dict[str, Any]:
        forecast_months = max(1, min(int(forecast_months), 24))
        self._sync_recurring_occurrences()
        today = date.today()
        return {
            "schema_version": STORAGE_SCHEMA_VERSION,
            "currency": self.currency,
            "categories": [dict(x) for x in self.categories],
            "active_categories": [dict(x) for x in self.categories if x.get("enabled", True)],
            "payers": [dict(x) for x in self.payers],
            "active_payers": self.active_payers(),
            "default_split": self.default_split(),
            "expenses": [self._public_expense(x) for x in self.expenses],
            "settlements": [self._public_settlement(x) for x in self.settlements],
            "recurring_expenses": [self._public_recurring_expense(x) for x in self.recurring_expenses],
            "recurring_occurrences": [
                self._public_recurring_occurrence(x) for x in self.recurring_occurrences
            ],
            "recurring_history": self.recurring_history_items(),
            "current_month_recurring": self.recurring_month_items(today.year, today.month),
            "balances": self.balances(),
            "debts": self.debts(),
            "monthly": self.monthly_totals(),
            "cashflow_monthly": self.cashflow_monthly_totals(),
            "normalized_monthly": self.normalized_monthly_totals(),
            "forecast": self.forecast(forecast_months),
            "normalized_forecast": self.normalized_forecast(forecast_months),
            "upcoming": self.upcoming(forecast_months),
            "contract_savings": self.contract_savings(),
            "summary": self.summary(),
        }

    def recurring_month_items(self, year: int, month: int) -> list[dict[str, Any]]:
        """Return all expected recurring charges due in one calendar month."""
        first_day = date(int(year), int(month), 1)
        last_day = date(first_day.year, first_day.month, monthrange(first_day.year, first_day.month)[1])
        items: list[dict[str, Any]] = []
        for recurring in self.recurring_expenses:
            for due in self._recurring_occurrences_between(recurring, first_day, last_day):
                items.append(
                    {
                        "id": str(recurring.get("id", "")),
                        "name": str(recurring.get("name", "")),
                        "kind": str(recurring.get("kind", "recurring")),
                        "color": self._normalize_color(recurring.get("color"), 0),
                        "amount": round(float(recurring.get("amount", 0.0) or 0.0), 2),
                        "due_date": due.isoformat(),
                    }
                )
        items.sort(key=lambda x: (str(x.get("due_date", "")), str(x.get("name", "")).casefold()))
        return items

    def recurring_history_items(self) -> list[dict[str, Any]]:
        """Return scheduled recurring charges from activation through the current month."""
        today = date.today()
        window_end = date(today.year, today.month, monthrange(today.year, today.month)[1])
        items: list[dict[str, Any]] = []
        for recurring in self.recurring_expenses:
            if not bool(recurring.get("active", True)):
                continue
            start_text = str(recurring.get("start_date") or "")
            if not start_text:
                continue
            try:
                start = date.fromisoformat(start_text)
            except ValueError:
                continue
            if start > window_end:
                continue
            for due in self._recurring_occurrences_between(recurring, start, window_end):
                items.append(
                    {
                        "id": str(recurring.get("id", "")),
                        "name": str(recurring.get("name", "")),
                        "kind": str(recurring.get("kind", "recurring")),
                        "color": self._normalize_color(recurring.get("color"), 0),
                        "amount": round(float(recurring.get("amount", 0.0) or 0.0), 2),
                        "due_date": due.isoformat(),
                    }
                )
        items.sort(key=lambda x: (str(x.get("due_date", "")), str(x.get("name", "")).casefold()))
        return items

    def monthly_totals(self) -> list[dict[str, Any]]:
        if not self.expenses:
            return []
        buckets: dict[tuple[int, int], dict[str, float]] = defaultdict(lambda: defaultdict(float))
        for item in self.expenses:
            if not bool(item.get("paid", False)):
                continue
            cashflow_key = self._expense_cashflow_month(item)
            buckets[cashflow_key][str(item["category_id"])] += float(item["amount"])
        if not buckets:
            return []
        first = min(buckets)
        today = date.today()
        last = max(max(buckets), (today.year, today.month))
        return self._rows_from_buckets(buckets, first, last)

    def cashflow_monthly_totals(self) -> list[dict[str, Any]]:
        """Return real monthly outflow, including scheduled recurring charges."""
        bill_rows = {str(row["key"]): row for row in self.monthly_totals()}
        recurring_by_key: dict[str, float] = defaultdict(float)
        for item in self.recurring_history_items():
            try:
                due = date.fromisoformat(str(item.get("due_date") or ""))
            except ValueError:
                continue
            key = f"{due.year:04d}-{due.month:02d}"
            recurring_by_key[key] += max(0.0, float(item.get("amount", 0.0) or 0.0))

        keys = set(bill_rows) | set(recurring_by_key)
        if not keys:
            return []

        first_year, first_month = map(int, min(keys).split("-"))
        today = date.today()
        last_key = max(max(keys), f"{today.year:04d}-{today.month:02d}")
        last_year, last_month = map(int, last_key.split("-"))
        rows: list[dict[str, Any]] = []
        for year, month in self._month_range(first_year, first_month, last_year, last_month):
            key = f"{year:04d}-{month:02d}"
            bill_row = bill_rows.get(key, {})
            bill_total = round(float(bill_row.get("total", 0.0) or 0.0), 2)
            recurring_total = round(float(recurring_by_key.get(key, 0.0) or 0.0), 2)
            rows.append(
                {
                    "key": key,
                    "year": year,
                    "month": month,
                    "total": round(bill_total + recurring_total, 2),
                    "bill_total": bill_total,
                    "recurring_total": recurring_total,
                    "categories": dict(bill_row.get("categories", {})),
                }
            )
        return rows

    def normalized_monthly_totals(self) -> list[dict[str, Any]]:
        if not self.expenses:
            return []
        buckets: dict[tuple[int, int], dict[str, float]] = defaultdict(lambda: defaultdict(float))
        for item in self.expenses:
            exact_start, exact_end = self._expense_period_dates(item)
            if exact_start and exact_end:
                total_days = (exact_end - exact_start).days + 1
                if total_days <= 0:
                    continue
                cursor = exact_start
                while cursor <= exact_end:
                    month_end = date(
                        cursor.year,
                        cursor.month,
                        monthrange(cursor.year, cursor.month)[1],
                    )
                    chunk_end = min(month_end, exact_end)
                    days = (chunk_end - cursor).days + 1
                    buckets[(cursor.year, cursor.month)][str(item["category_id"])] += (
                        float(item["amount"]) * days / total_days
                    )
                    cursor = chunk_end + timedelta(days=1)
                continue
            months = self._month_range(
                int(item["period_start_year"]), int(item["period_start_month"]),
                int(item["period_end_year"]), int(item["period_end_month"]),
            )
            if not months:
                continue
            share = float(item["amount"]) / len(months)
            for key in months:
                buckets[key][str(item["category_id"])] += share
        first = min(buckets)
        today = date.today()
        last = max(max(buckets), (today.year, today.month))
        return self._rows_from_buckets(buckets, first, last)

    def forecast(self, months_ahead: int = 12) -> list[dict[str, Any]]:
        """Forecast provider bills plus exact recurring-expense due months."""
        months_ahead = max(1, min(int(months_ahead), 24))
        today = date.today()
        start = self._next_month(today.year, today.month)
        future_months: list[tuple[int, int]] = []
        y, m = start
        for _ in range(months_ahead):
            future_months.append((y, m))
            y, m = self._next_month(y, m)

        bill_buckets: dict[tuple[int, int], dict[str, float]] = defaultdict(
            lambda: defaultdict(float)
        )
        for category in self.categories:
            if not category.get("enabled", True):
                continue
            cat_id = str(category["id"])
            history = sorted(
                [x for x in self.expenses if x.get("category_id") == cat_id],
                key=lambda x: (int(x["paid_year"]), int(x["paid_month"])),
            )
            if not history:
                continue
            estimate = self._estimate_category_amount(history)
            interval = int(category["interval_months"])
            due = self._add_months(
                int(history[-1]["paid_year"]), int(history[-1]["paid_month"]), interval
            )
            while due < start:
                due = self._add_months(due[0], due[1], interval)
            end = future_months[-1]
            while due <= end:
                bill_buckets[due][cat_id] += estimate
                due = self._add_months(due[0], due[1], interval)

        recurring_buckets: dict[tuple[int, int], dict[str, float]] = defaultdict(
            lambda: defaultdict(float)
        )
        recurring_items: dict[tuple[int, int], list[dict[str, Any]]] = defaultdict(list)
        window_start = date(start[0], start[1], 1)
        last_year, last_month = future_months[-1]
        window_end = date(last_year, last_month, monthrange(last_year, last_month)[1])
        for recurring in self.recurring_expenses:
            if not bool(recurring.get("active", True)):
                continue
            for occurrence in self._recurring_occurrences_between(
                recurring, window_start, window_end
            ):
                key = (occurrence.year, occurrence.month)
                amount = round(float(recurring.get("amount", 0.0) or 0.0), 2)
                kind = str(recurring.get("kind", "recurring"))
                recurring_buckets[key][kind] += amount
                recurring_items[key].append(
                    {
                        "id": str(recurring.get("id", "")),
                        "name": str(recurring.get("name", "")),
                        "kind": kind,
                        "color": self._normalize_color(recurring.get("color"), 0),
                        "amount": amount,
                        "due_date": occurrence.isoformat(),
                    }
                )

        rows = []
        for year, month in future_months:
            by_category = self._named_category_values(bill_buckets[(year, month)])
            recurring_by_kind = {
                key: round(value, 2)
                for key, value in recurring_buckets[(year, month)].items()
                if value
            }
            bill_total = round(sum(by_category.values()), 2)
            recurring_total = round(sum(recurring_by_kind.values()), 2)
            rows.append(
                {
                    "year": year,
                    "month": month,
                    "key": f"{year:04d}-{month:02d}",
                    "total": round(bill_total + recurring_total, 2),
                    "bill_total": bill_total,
                    "recurring_total": recurring_total,
                    "categories": by_category,
                    "recurring": recurring_by_kind,
                    "recurring_items": recurring_items[(year, month)],
                }
            )
        return rows

    def normalized_forecast(self, months_ahead: int = 12) -> list[dict[str, Any]]:
        """Return monthly-equivalent forecast including recurring expenses."""
        months_ahead = max(1, min(int(months_ahead), 24))
        today = date.today()
        y, m = self._next_month(today.year, today.month)
        recurring_bills: dict[str, float] = {}
        for category in self.categories:
            if not category.get("enabled", True):
                continue
            cat_id = str(category["id"])
            history = sorted(
                [x for x in self.expenses if x.get("category_id") == cat_id],
                key=lambda x: (int(x["paid_year"]), int(x["paid_month"])),
            )
            if history:
                recurring_bills[cat_id] = self._estimate_category_amount(history) / max(
                    1, int(category["interval_months"])
                )

        rows = []
        for _ in range(months_ahead):
            first_day = date(y, m, 1)
            last_day = date(y, m, monthrange(y, m)[1])
            recurring_by_kind: dict[str, float] = defaultdict(float)
            for item in self.recurring_expenses:
                if not bool(item.get("active", True)):
                    continue
                start_date = date.fromisoformat(str(item["start_date"]))
                if start_date > last_day:
                    continue
                end_text = str(item.get("end_date") or "")
                if end_text and not bool(item.get("auto_renew", False)):
                    if date.fromisoformat(end_text) < first_day:
                        continue
                if self._next_recurring_due(item, first_day) is None:
                    continue
                recurring_by_kind[str(item.get("kind", "recurring"))] += (
                    float(item.get("amount", 0.0) or 0.0)
                    / max(1, int(item.get("interval_months", 1) or 1))
                )
            by_category = self._named_category_values(recurring_bills)
            recurring_values = {
                key: round(value, 2) for key, value in recurring_by_kind.items() if value
            }
            bill_total = round(sum(by_category.values()), 2)
            recurring_total = round(sum(recurring_values.values()), 2)
            rows.append(
                {
                    "year": y,
                    "month": m,
                    "key": f"{y:04d}-{m:02d}",
                    "total": round(bill_total + recurring_total, 2),
                    "bill_total": bill_total,
                    "recurring_total": recurring_total,
                    "categories": by_category,
                    "recurring": recurring_values,
                }
            )
            y, m = self._next_month(y, m)
        return rows

    def upcoming(self, months_ahead: int = 12) -> list[dict[str, Any]]:
        """Return upcoming estimated bills and exact recurring charge dates."""
        items: list[dict[str, Any]] = []
        for row in self.forecast(months_ahead):
            for category_name, amount in row["categories"].items():
                if amount <= 0:
                    continue
                category = self.category_by_name(category_name)
                items.append(
                    {
                        "year": row["year"],
                        "month": row["month"],
                        "key": row["key"],
                        "category_id": category.get("id") if category else None,
                        "category": category_name,
                        "amount": round(float(amount), 2),
                        "source": "bill_forecast",
                        "due_date": None,
                    }
                )

        today = date.today()
        first_year, first_month = self._next_month(today.year, today.month)
        window_start = date(first_year, first_month, 1)
        end_year, end_month = self._add_months(
            first_year, first_month, max(0, months_ahead - 1)
        )
        window_end = date(end_year, end_month, monthrange(end_year, end_month)[1])
        for recurring in self.recurring_expenses:
            for occurrence in self._recurring_occurrences_between(
                recurring, window_start, window_end
            ):
                items.append(
                    {
                        "year": occurrence.year,
                        "month": occurrence.month,
                        "key": f"{occurrence.year:04d}-{occurrence.month:02d}",
                        "category_id": None,
                        "category": str(recurring.get("name", "")),
                        "amount": round(float(recurring.get("amount", 0.0) or 0.0), 2),
                        "source": "recurring",
                        "recurring_id": str(recurring.get("id", "")),
                        "recurring_kind": str(recurring.get("kind", "recurring")),
                        "color": self._normalize_color(recurring.get("color"), 0),
                        "due_date": occurrence.isoformat(),
                    }
                )
        items.sort(
            key=lambda row: (
                int(row.get("year", 0)),
                int(row.get("month", 0)),
                str(row.get("due_date") or f"{int(row.get('year', 0)):04d}-{int(row.get('month', 0)):02d}-99"),
                str(row.get("category", "")).casefold(),
            )
        )
        return items

    def contract_savings(self) -> list[dict[str, Any]]:
        """Estimate savings after a provider/contract change, normalized by usage."""
        results: list[dict[str, Any]] = []
        for category in self.categories:
            category_id = str(category.get("id", ""))
            rows = [
                x for x in self.expenses
                if str(x.get("category_id", "")) == category_id
                and (str(x.get("provider", "")).strip() or str(x.get("contract", "")).strip())
            ]
            rows.sort(key=lambda x: (int(x.get("paid_year", 0)), int(x.get("paid_month", 0)), str(x.get("created_at", ""))))
            if len(rows) < 2:
                continue

            segments: list[dict[str, Any]] = []
            for row in rows:
                provider = str(row.get("provider", "")).strip()
                contract = str(row.get("contract", "")).strip()
                key = (provider.casefold(), contract.casefold())
                if not segments or segments[-1]["key"] != key:
                    segments.append({"key": key, "provider": provider, "contract": contract, "rows": []})
                segments[-1]["rows"].append(row)
            if len(segments) < 2:
                continue

            old_segment, new_segment = segments[-2], segments[-1]
            units = {
                str(x.get("consumption_unit", "")).strip()
                for segment in (old_segment, new_segment) for x in segment["rows"]
                if str(x.get("consumption_unit", "")).strip()
            }
            unit = str(category.get("consumption_unit", "")).strip()
            if not unit and len(units) == 1:
                unit = next(iter(units))
            old_usage_rows = [
                x for x in old_segment["rows"]
                if x.get("consumption") is not None and (not unit or str(x.get("consumption_unit", unit)) == unit)
            ]
            new_usage_rows = [
                x for x in new_segment["rows"]
                if x.get("consumption") is not None and (not unit or str(x.get("consumption_unit", unit)) == unit)
            ]
            if not unit or not old_usage_rows or not new_usage_rows:
                continue

            old_consumption = sum(float(x.get("consumption", 0) or 0) for x in old_usage_rows)
            new_consumption = sum(float(x.get("consumption", 0) or 0) for x in new_usage_rows)
            if old_consumption <= 0 or new_consumption <= 0:
                continue
            old_amount = sum(float(x.get("amount", 0) or 0) for x in old_usage_rows)
            new_amount = sum(float(x.get("amount", 0) or 0) for x in new_usage_rows)
            old_unit_price = old_amount / old_consumption
            new_unit_price = new_amount / new_consumption
            baseline_new_cost = old_unit_price * new_consumption
            estimated_savings = baseline_new_cost - new_amount
            savings_pct = estimated_savings / baseline_new_cost * 100 if baseline_new_cost > 0 else 0.0

            old_avg_amount = old_amount / len(old_usage_rows)
            new_avg_amount = new_amount / len(new_usage_rows)
            old_avg_consumption = old_consumption / len(old_usage_rows)
            new_avg_consumption = new_consumption / len(new_usage_rows)
            consumption_change_pct = (
                (new_avg_consumption - old_avg_consumption) / old_avg_consumption * 100
                if old_avg_consumption > 0 else 0.0
            )
            results.append({
                "category_id": category_id,
                "category": str(category.get("name", "")),
                "unit": unit,
                "currency": self.currency,
                "old_provider": old_segment["provider"],
                "old_contract": old_segment["contract"],
                "new_provider": new_segment["provider"],
                "new_contract": new_segment["contract"],
                "old_bill_count": len(old_usage_rows),
                "new_bill_count": len(new_usage_rows),
                "old_unit_price": round(old_unit_price, 6),
                "new_unit_price": round(new_unit_price, 6),
                "old_avg_amount": round(old_avg_amount, 2),
                "new_avg_amount": round(new_avg_amount, 2),
                "old_avg_consumption": round(old_avg_consumption, 4),
                "new_avg_consumption": round(new_avg_consumption, 4),
                "consumption_change_percent": round(consumption_change_pct, 2),
                "estimated_savings": round(estimated_savings, 2),
                "estimated_savings_percent": round(savings_pct, 2),
                "new_period_consumption": round(new_consumption, 4),
                "baseline_new_cost": round(baseline_new_cost, 2),
            })
        results.sort(key=lambda x: abs(float(x.get("estimated_savings", 0))), reverse=True)
        return results

    def summary(self) -> dict[str, Any]:
        monthly = self.cashflow_monthly_totals()
        normalized = self.normalized_monthly_totals()
        today = date.today()
        current_key = f"{today.year:04d}-{today.month:02d}"
        current = next((x for x in monthly if x["key"] == current_key), None)
        normalized_current = next((x for x in normalized if x["key"] == current_key), None)
        past_values = [float(x["total"]) for x in monthly if x["key"] <= current_key]
        avg6 = round(mean(past_values[-min(6, len(past_values)):]), 2) if past_values else 0.0
        future = self.forecast(12)
        debts = self.debts()
        unpaid_total = round(
            sum(float(x.get("amount", 0.0)) for x in self.expenses if not bool(x.get("paid", False))),
            2,
        )
        reimbursement_total = round(sum(float(x["amount"]) for x in debts), 2)
        public_recurring = [self._public_recurring_expense(x) for x in self.recurring_expenses]
        active_recurring = [x for x in public_recurring if x.get("status") == "active"]
        recurring_monthly_equivalent = round(
            sum(float(x.get("monthly_equivalent", 0.0) or 0.0) for x in active_recurring), 2
        )
        installment_remaining_total = round(
            sum(
                float(x.get("remaining_amount", 0.0) or 0.0)
                for x in active_recurring
                if x.get("kind") == "installment" and x.get("remaining_amount") is not None
            ),
            2,
        )
        return {
            "current_month": round(float(current["total"]), 2) if current else 0.0,
            "average_6_months": avg6,
            "next_month_estimate": future[0]["total"] if future else 0.0,
            "normalized_current_month": round(float(normalized_current["total"]), 2) if normalized_current else 0.0,
            "year_total": round(
                sum(float(row.get("total", 0.0) or 0.0) for row in monthly if int(row["year"]) == today.year),
                2,
            ),
            "entries": len(self.expenses),
            "paid_entries": sum(1 for x in self.expenses if bool(x.get("paid", False))),
            "unpaid_entries": sum(1 for x in self.expenses if not bool(x.get("paid", False))),
            "active_categories": sum(1 for x in self.categories if x.get("enabled", True)),
            "active_payers": sum(1 for x in self.payers if x.get("enabled", True)),
            "outstanding_total": unpaid_total,
            "unpaid_total": unpaid_total,
            "reimbursement_total": reimbursement_total,
            "active_recurring": len(active_recurring),
            "recurring_monthly_equivalent": recurring_monthly_equivalent,
            "recurring_next_month": (
                round(float(future[0].get("recurring_total", 0.0) or 0.0), 2) if future else 0.0
            ),
            "installment_remaining_total": installment_remaining_total,
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _normalize_recurring_payload(
        self,
        *,
        name: str,
        kind: str,
        amount: float,
        interval_months: int,
        start_date: str,
        end_date: str | None,
        auto_renew: bool,
        renewal_interval_months: int,
        installment_count: int | None,
        payer_id: str | None = None,
        split: list[dict[str, Any]] | None = None,
        provider: str = "",
        contract: str = "",
        color: str | None = None,
        note: str = "",
        active: bool = True,
    ) -> dict[str, Any]:
        normalized_name = self._normalize_optional_text(name, 120)
        if not normalized_name:
            raise billy_error("recurring_name_required")
        normalized_kind = str(kind or "").strip().lower()
        if normalized_kind not in RECURRING_KINDS:
            raise billy_error("recurring_invalid_kind")
        normalized_amount = float(amount)
        if not isfinite(normalized_amount) or normalized_amount <= 0:
            raise billy_error("recurring_amount_positive")
        normalized_interval = int(interval_months)
        if normalized_interval not in RECURRING_INTERVALS:
            raise billy_error("recurring_unsupported_interval")
        normalized_start = self._normalize_optional_iso_date(start_date)
        if not normalized_start:
            raise billy_error("recurring_start_required")
        normalized_end = self._normalize_optional_iso_date(end_date)
        start = date.fromisoformat(normalized_start)
        end = date.fromisoformat(normalized_end) if normalized_end else None
        if end is not None and end < start:
            raise billy_error("recurring_end_before_start")

        renewal_interval = int(renewal_interval_months or 12)
        if renewal_interval < 1 or renewal_interval > 120:
            raise billy_error("recurring_invalid_renewal")

        normalized_installments: int | None = None
        if installment_count not in (None, ""):
            normalized_installments = int(installment_count)
            if normalized_installments < 1 or normalized_installments > 1200:
                raise billy_error("recurring_invalid_installments")
        if normalized_kind != "installment":
            normalized_installments = None
        if normalized_kind == "installment":
            auto_renew = False
            if normalized_installments:
                end = self._add_months_date(
                    start, (normalized_installments - 1) * normalized_interval
                )
                normalized_end = end.isoformat()

        resolved_payer = self._validate_optional_payer(payer_id)
        if resolved_payer is None:
            active_payers = self.active_payers()
            resolved_payer = str(active_payers[0]["id"]) if active_payers else None
        normalized_split = self._resolve_expense_split(split, resolved_payer)
        color_index = sum(ord(char) for char in f"{normalized_kind}:{normalized_name}")

        return {
            "name": normalized_name,
            "kind": normalized_kind,
            "amount": round(normalized_amount, 2),
            "interval_months": normalized_interval,
            "start_date": normalized_start,
            "end_date": normalized_end,
            "auto_renew": bool(auto_renew),
            "renewal_interval_months": renewal_interval,
            "installment_count": normalized_installments,
            "payer_id": resolved_payer,
            "split": normalized_split,
            "provider": self._normalize_optional_text(provider, 120),
            "contract": self._normalize_optional_text(contract, 120),
            "color": self._normalize_color(color, color_index),
            "note": self._normalize_optional_text(note, 1000),
            "active": bool(active),
        }

    @staticmethod
    def _add_months_date(value: date, months: int) -> date:
        absolute = value.year * 12 + (value.month - 1) + int(months)
        year, month_zero = divmod(absolute, 12)
        month = month_zero + 1
        day = min(value.day, monthrange(year, month)[1])
        return date(year, month, day)

    def _recurring_occurrence(self, item: dict[str, Any], index: int) -> date | None:
        if index < 0:
            return None
        count = item.get("installment_count")
        if count is not None and index >= int(count):
            return None
        start = date.fromisoformat(str(item["start_date"]))
        occurrence = self._add_months_date(
            start, index * int(item.get("interval_months", 1) or 1)
        )
        end_text = str(item.get("end_date") or "")
        if end_text and not bool(item.get("auto_renew", False)):
            if occurrence > date.fromisoformat(end_text):
                return None
        return occurrence

    def _next_recurring_due(
        self, item: dict[str, Any], on_or_after: date
    ) -> date | None:
        start = date.fromisoformat(str(item["start_date"]))
        interval = max(1, int(item.get("interval_months", 1) or 1))
        if on_or_after <= start:
            index = 0
        else:
            months = (on_or_after.year - start.year) * 12 + on_or_after.month - start.month
            index = max(0, months // interval - 1)
        for _ in range(0, 1202):
            occurrence = self._recurring_occurrence(item, index)
            if occurrence is None:
                return None
            if occurrence >= on_or_after:
                return occurrence
            index += 1
        return None

    def _recurring_occurrences_between(
        self, item: dict[str, Any], start: date, end: date
    ) -> list[date]:
        if not bool(item.get("active", True)) or end < start:
            return []
        occurrence = self._next_recurring_due(item, start)
        if occurrence is None:
            return []
        interval = max(1, int(item.get("interval_months", 1) or 1))
        base = date.fromisoformat(str(item["start_date"]))
        months = (occurrence.year - base.year) * 12 + occurrence.month - base.month
        index = max(0, months // interval)
        result: list[date] = []
        while occurrence is not None and occurrence <= end and len(result) < 1200:
            result.append(occurrence)
            index += 1
            occurrence = self._recurring_occurrence(item, index)
        return result

    def _recurring_progress(self, item: dict[str, Any], today: date) -> tuple[int, int | None]:
        count = item.get("installment_count")
        if count is None:
            return 0, None
        total = int(count)
        elapsed = 0
        for index in range(total):
            occurrence = self._recurring_occurrence(item, index)
            if occurrence is None or occurrence >= today:
                break
            elapsed += 1
        return elapsed, max(0, total - elapsed)

    def _next_renewal_date(self, item: dict[str, Any], today: date) -> str | None:
        if not bool(item.get("auto_renew", False)) or not item.get("end_date"):
            return None
        renewal = date.fromisoformat(str(item["end_date"]))
        step = max(1, int(item.get("renewal_interval_months", 12) or 12))
        while renewal < today:
            renewal = self._add_months_date(renewal, step)
        return renewal.isoformat()

    def _recurring_tracking_start(
        self, item: dict[str, Any], on_or_after: date | None = None
    ) -> str:
        """Choose the first occurrence Billy should materialize for reimbursements.

        A newly configured long-running mortgage/subscription must not create
        years of retroactive debts. For an existing series we therefore start
        from the latest charge due today; when resuming a paused rule we start
        from the next charge on/after the resume date.
        """
        today = on_or_after or date.today()
        start = date.fromisoformat(str(item["start_date"]))
        if on_or_after is not None:
            next_due = self._next_recurring_due(item, today)
            return (next_due or today).isoformat()
        if start >= today:
            return start.isoformat()
        latest = start
        for index in range(1200):
            occurrence = self._recurring_occurrence(item, index)
            if occurrence is None or occurrence > today:
                break
            latest = occurrence
        return latest.isoformat()

    def _sync_recurring_occurrences(self, today: date | None = None) -> bool:
        """Materialize due recurring charges with payer/split snapshots."""
        today = today or date.today()
        existing = {str(x.get("id")) for x in self.recurring_occurrences if x.get("id")}
        changed = False
        for recurring in self.recurring_expenses:
            if not bool(recurring.get("active", True)):
                continue
            recurring_id = str(recurring.get("id") or "")
            if not recurring_id:
                continue
            tracking_text = str(recurring.get("reimbursement_tracking_start_date") or "")
            if not tracking_text:
                tracking_text = self._recurring_tracking_start(recurring)
                recurring["reimbursement_tracking_start_date"] = tracking_text
                changed = True
            tracking_start = date.fromisoformat(tracking_text)
            if tracking_start > today:
                continue
            for due in self._recurring_occurrences_between(recurring, tracking_start, today):
                occurrence_id = f"{recurring_id}@{due.isoformat()}"
                if occurrence_id in existing:
                    continue
                self.recurring_occurrences.append(
                    {
                        "id": occurrence_id,
                        "recurring_id": recurring_id,
                        "due_date": due.isoformat(),
                        "name": str(recurring.get("name", "")),
                        "kind": str(recurring.get("kind", "recurring")),
                        "color": self._normalize_color(recurring.get("color"), 0),
                        "amount": round(float(recurring.get("amount", 0.0) or 0.0), 2),
                        "payer_id": recurring.get("payer_id"),
                        "split": [dict(x) for x in recurring.get("split", [])],
                        "reimbursement_manual_done": False,
                        "reimbursement_manual_at": None,
                        "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
                    }
                )
                existing.add(occurrence_id)
                changed = True
        if changed:
            self._sort()
        return changed

    def _refresh_open_recurring_occurrences(self, recurring: dict[str, Any]) -> bool:
        """Apply rule edits to still-open occurrences without rewriting settled history."""
        changed = False
        recurring_id = str(recurring.get("id") or "")
        for occurrence in self.recurring_occurrences:
            if occurrence.get("recurring_id") != recurring_id:
                continue
            state = self._recurring_occurrence_reimbursement_state(occurrence)
            if bool(occurrence.get("reimbursement_manual_done", False)) or state[
                "has_recorded_settlement"
            ]:
                continue
            replacement = {
                "name": str(recurring.get("name", "")),
                "kind": str(recurring.get("kind", "recurring")),
                "color": self._normalize_color(recurring.get("color"), 0),
                "amount": round(float(recurring.get("amount", 0.0) or 0.0), 2),
                "payer_id": recurring.get("payer_id"),
                "split": [dict(x) for x in recurring.get("split", [])],
            }
            if any(occurrence.get(key) != value for key, value in replacement.items()):
                occurrence.update(replacement)
                changed = True
        return changed

    async def async_sync_recurring_occurrences(self) -> bool:
        """Persist newly due recurring charges, normally called at midnight."""
        changed = self._sync_recurring_occurrences()
        if changed:
            await self._save_and_notify()
        return changed

    def _recurring_occurrence_reimbursement_state(
        self, item: dict[str, Any]
    ) -> dict[str, Any]:
        creditor = str(item.get("payer_id") or "")
        occurrence_id = str(item.get("id") or "")
        obligations: list[str] = []
        if creditor and self.payer(creditor) is not None:
            for part in item.get("split", []):
                debtor = str(part.get("payer_id") or "")
                percentage = float(part.get("percentage", 0.0) or 0.0)
                if (
                    debtor
                    and debtor != creditor
                    and percentage > 0.009
                    and self.payer(debtor) is not None
                    and debtor not in obligations
                ):
                    obligations.append(debtor)
        total = len(obligations)
        if total == 0:
            return {
                "status": "none",
                "completed": 0,
                "total": 0,
                "manual_done": False,
                "has_recorded_settlement": False,
                "can_toggle": False,
            }
        manual_done = bool(item.get("reimbursement_manual_done", False))
        linked_pairs: set[frozenset[str]] = set()
        for settlement in self.settlements:
            if occurrence_id not in {
                str(value)
                for value in settlement.get("recurring_occurrence_ids", [])
                if value
            }:
                continue
            source = str(settlement.get("from_payer_id") or "")
            target = str(settlement.get("to_payer_id") or "")
            if source and target and source != target:
                linked_pairs.add(frozenset((source, target)))
        completed = total if manual_done else sum(
            1 for debtor in obligations if frozenset((debtor, creditor)) in linked_pairs
        )
        status = "done" if completed >= total else "partial" if completed > 0 else "pending"
        return {
            "status": status,
            "completed": completed,
            "total": total,
            "manual_done": manual_done,
            "has_recorded_settlement": bool(linked_pairs),
            "can_toggle": not bool(linked_pairs),
        }

    def _public_recurring_occurrence(self, item: dict[str, Any]) -> dict[str, Any]:
        payer = self.payer(str(item.get("payer_id", ""))) if item.get("payer_id") else None
        split = []
        for part in item.get("split", []):
            participant = self.payer(str(part.get("payer_id", "")))
            split.append(
                {
                    **dict(part),
                    "name": str(participant.get("name")) if participant else "Pagante rimosso",
                }
            )
        reimbursement = self._recurring_occurrence_reimbursement_state(item)
        return {
            **dict(item),
            "currency": self.currency,
            "payer": str(payer.get("name")) if payer else "",
            "split": split,
            "reimbursement_status": reimbursement["status"],
            "reimbursement_done": reimbursement["status"] == "done",
            "reimbursement_completed_count": reimbursement["completed"],
            "reimbursement_total_count": reimbursement["total"],
            "reimbursement_manual_done": reimbursement["manual_done"],
            "reimbursement_has_settlement": reimbursement["has_recorded_settlement"],
            "reimbursement_can_toggle": reimbursement["can_toggle"],
        }

    def _public_recurring_expense(self, item: dict[str, Any]) -> dict[str, Any]:
        today = date.today()
        next_due = self._next_recurring_due(item, today) if item.get("active", True) else None
        elapsed, remaining = self._recurring_progress(item, today)
        status = "active"
        if not bool(item.get("active", True)):
            status = "inactive"
        elif next_due is None:
            status = "ended"
        remaining_amount = (
            round(float(item.get("amount", 0.0) or 0.0) * remaining, 2)
            if remaining is not None
            else None
        )
        payer = self.payer(str(item.get("payer_id", ""))) if item.get("payer_id") else None
        split = []
        for part in item.get("split", []):
            participant = self.payer(str(part.get("payer_id", "")))
            split.append(
                {
                    **dict(part),
                    "name": str(participant.get("name")) if participant else "Pagante rimosso",
                }
            )
        occurrences = [
            self._public_recurring_occurrence(x)
            for x in self.recurring_occurrences
            if x.get("recurring_id") == item.get("id")
        ]
        occurrences.sort(key=lambda x: str(x.get("due_date", "")), reverse=True)
        reimbursable = [x for x in occurrences if x.get("reimbursement_status") != "none"]
        pending = [x for x in reimbursable if x.get("reimbursement_status") in ("pending", "partial")]
        completed_reimbursements = [x for x in reimbursable if x.get("reimbursement_status") == "done"]
        if not reimbursable:
            reimbursement_status = "none"
        elif pending and completed_reimbursements:
            reimbursement_status = "partial"
        elif pending:
            reimbursement_status = "pending"
        else:
            reimbursement_status = "done"
        return {
            **dict(item),
            "currency": self.currency,
            "payer": str(payer.get("name")) if payer else "",
            "split": split,
            "status": status,
            "next_due_date": next_due.isoformat() if next_due else None,
            "next_renewal_date": self._next_renewal_date(item, today),
            "monthly_equivalent": round(
                float(item.get("amount", 0.0) or 0.0)
                / max(1, int(item.get("interval_months", 1) or 1)),
                2,
            ),
            "installments_elapsed": elapsed if remaining is not None else None,
            "remaining_installments": remaining,
            "remaining_amount": remaining_amount,
            "reimbursement_status": reimbursement_status,
            "reimbursement_pending_count": len(pending),
            "reimbursement_done_count": len(completed_reimbursements),
            "reimbursement_occurrences": occurrences,
        }

    def _expense_reimbursement_state(self, item: dict[str, Any]) -> dict[str, Any]:
        """Return the reimbursement state for one bill, independently from provider payment."""
        creditor = str(item.get("payer_id") or "")
        expense_id = str(item.get("id") or "")
        obligations: list[str] = []
        if creditor and self.payer(creditor) is not None:
            for part in item.get("split", []):
                debtor = str(part.get("payer_id") or "")
                percentage = float(part.get("percentage", 0.0) or 0.0)
                if (
                    debtor
                    and debtor != creditor
                    and percentage > 0.009
                    and self.payer(debtor) is not None
                    and debtor not in obligations
                ):
                    obligations.append(debtor)

        total = len(obligations)
        if total == 0:
            return {
                "status": "none",
                "completed": 0,
                "total": 0,
                "manual_done": False,
                "has_recorded_settlement": False,
                "can_toggle": False,
            }

        manual_done = bool(item.get("reimbursement_manual_done", False))
        linked_pairs: set[frozenset[str]] = set()
        for settlement in self.settlements:
            if expense_id not in {str(value) for value in settlement.get("expense_ids", []) if value}:
                continue
            source = str(settlement.get("from_payer_id") or "")
            target = str(settlement.get("to_payer_id") or "")
            if source and target and source != target:
                linked_pairs.add(frozenset((source, target)))

        completed = total if manual_done else sum(
            1 for debtor in obligations if frozenset((debtor, creditor)) in linked_pairs
        )
        if completed >= total:
            status = "done"
        elif completed > 0:
            status = "partial"
        else:
            status = "pending"
        has_recorded_settlement = bool(linked_pairs)
        return {
            "status": status,
            "completed": completed,
            "total": total,
            "manual_done": manual_done,
            "has_recorded_settlement": has_recorded_settlement,
            "can_toggle": not has_recorded_settlement,
        }

    def _public_expense(self, item: dict[str, Any]) -> dict[str, Any]:
        category = self.category(str(item.get("category_id", "")))
        payer = self.payer(str(item.get("payer_id", ""))) if item.get("payer_id") else None
        split = []
        for part in item.get("split", []):
            participant = self.payer(str(part.get("payer_id", "")))
            split.append({**dict(part), "name": str(participant.get("name")) if participant else "Pagante rimosso"})
        reimbursement = self._expense_reimbursement_state(item)
        period = self._billing_period_info(
            item,
            int(category.get("interval_months", 1)) if category else 1,
        )
        return {
            **dict(item),
            "year": int(item["paid_year"]),
            "month": int(item["paid_month"]),
            "category": str(category.get("name")) if category else "Bolletta rimossa",
            "category_color": str(category.get("color", "#A0A7B4")) if category else "#A0A7B4",
            "consumption_unit": str(item.get("consumption_unit") or (category.get("consumption_unit", "") if category else "")),
            "currency": self.currency,
            "payer": str(payer.get("name")) if payer else "",
            "split": split,
            "reimbursement_status": reimbursement["status"],
            "reimbursement_done": reimbursement["status"] == "done",
            "reimbursement_completed_count": reimbursement["completed"],
            "reimbursement_total_count": reimbursement["total"],
            "reimbursement_manual_done": reimbursement["manual_done"],
            "reimbursement_has_settlement": reimbursement["has_recorded_settlement"],
            "reimbursement_can_toggle": reimbursement["can_toggle"],
            "period_type": period["type"],
            "period_days": period["days"],
            "expected_period_days": period["expected_days"],
            "period_ratio": period["ratio"],
        }

    def _public_settlement(self, item: dict[str, Any]) -> dict[str, Any]:
        source = self.payer(str(item.get("from_payer_id", "")))
        target = self.payer(str(item.get("to_payer_id", "")))
        expense_count = len([x for x in item.get("expense_ids", []) if x])
        recurring_count = len(
            [x for x in item.get("recurring_occurrence_ids", []) if x]
        )
        return {
            **dict(item),
            "from_name": str(source.get("name")) if source else "Pagante rimosso",
            "to_name": str(target.get("name")) if target else "Pagante rimosso",
            "expense_count": expense_count,
            "recurring_count": recurring_count,
            "item_count": expense_count + recurring_count,
        }

    def _rows_from_buckets(self, buckets, first, last) -> list[dict[str, Any]]:
        result = []
        y, m = first
        while (y, m) <= last:
            by_category = self._named_category_values(buckets[(y, m)])
            result.append({"year": y, "month": m, "key": f"{y:04d}-{m:02d}", "total": round(sum(by_category.values()), 2), "categories": by_category})
            y, m = self._next_month(y, m)
        return result

    def _named_category_values(self, values: dict[str, float]) -> dict[str, float]:
        result: dict[str, float] = {}
        for category in self.categories:
            amount = float(values.get(str(category["id"]), 0.0))
            if amount:
                result[str(category["name"])] = round(amount, 2)
        for category_id, amount in values.items():
            if self.category(str(category_id)) is None and amount:
                result[f"Categoria {category_id}"] = round(float(amount), 2)
        return result

    def _estimate_category_amount(self, history: list[dict[str, Any]]) -> float:
        amounts = []
        for item in history:
            amount = float(item["amount"])
            if not isfinite(amount):
                continue
            category = self.category(str(item.get("category_id", "")))
            interval = max(1, int(category.get("interval_months", 1))) if category else 1
            period = self._billing_period_info(item, interval)
            if (
                period["type"] in {"short", "long"}
                and period["days"]
                and period["expected_days"]
            ):
                amount *= float(period["expected_days"]) / float(period["days"])
            amounts.append(amount)
        if not amounts:
            return 0.0
        recent = amounts[-min(4, len(amounts)):]
        base = mean(recent)
        if len(recent) >= 2:
            slope = (recent[-1] - recent[0]) / (len(recent) - 1)
            correction = max(-base * 0.20, min(base * 0.20, slope * 0.35))
            base += correction
        return round(max(0.0, base), 2)

    @staticmethod
    def _expected_period_days(interval_months: int) -> int:
        return max(1, round(30.4375 * max(1, int(interval_months))))

    def _expense_period_dates(
        self, item: dict[str, Any]
    ) -> tuple[date | None, date | None]:
        start_text = str(item.get("period_start_date") or "")
        end_text = str(item.get("period_end_date") or "")
        if not start_text or not end_text:
            return None, None
        try:
            start = date.fromisoformat(start_text)
            end = date.fromisoformat(end_text)
        except ValueError:
            return None, None
        if start > end:
            return None, None
        return start, end

    def _billing_period_info(
        self, item: dict[str, Any], interval_months: int | None = None
    ) -> dict[str, Any]:
        start, end = self._expense_period_dates(item)
        expected = self._expected_period_days(
            interval_months
            if interval_months is not None
            else int(
                (self.category(str(item.get("category_id", ""))) or {}).get(
                    "interval_months", 1
                )
            )
        )
        if start is None or end is None:
            return {
                "type": "normal",
                "days": None,
                "expected_days": expected,
                "ratio": None,
            }
        days = (end - start).days + 1
        ratio = days / expected if expected else 1.0
        if ratio < 0.8:
            period_type = "short"
        elif ratio > 1.2:
            period_type = "long"
        else:
            period_type = "normal"
        return {
            "type": period_type,
            "days": days,
            "expected_days": expected,
            "ratio": round(ratio, 4),
        }

    def _resolve_category(self, category_id: str | None, category_name: str | None) -> dict[str, Any]:
        category = self.category(category_id or "") if category_id else None
        if category is None and category_name:
            category = self.category_by_name(category_name)
        if category is None:
            raise billy_error("category_invalid")
        return category

    def _resolve_expense_payer(self, category: dict[str, Any], payer_id: str | None) -> str | None:
        wanted = str(payer_id or category.get("default_payer_id") or "")
        if wanted:
            if self.payer(wanted) is None:
                raise billy_error("payer_invalid")
            return wanted
        active = self.active_payers()
        return str(active[0]["id"]) if active else None

    def _resolve_expense_split(self, split: list[dict[str, Any]] | None, payer_id: str | None) -> list[dict[str, Any]]:
        if payer_id is None:
            return []
        if split is None:
            split = self.default_split()
        return self._normalize_split(split)

    def _normalize_split(self, split: list[dict[str, Any]]) -> list[dict[str, Any]]:
        combined: dict[str, float] = defaultdict(float)
        for raw in split:
            payer_id = str(raw.get("payer_id") or "")
            percentage = float(raw.get("percentage", 0.0) or 0.0)
            if self.payer(payer_id) is None:
                raise billy_error("split_invalid_payer")
            if not isfinite(percentage) or percentage < 0 or percentage > 100:
                raise billy_error("split_invalid_percentage")
            if percentage > 0:
                combined[payer_id] += percentage
        if not combined:
            raise billy_error("split_empty")
        total = sum(combined.values())
        if abs(total - 100.0) > 0.05:
            raise billy_error("split_must_total_100")
        result = [{"payer_id": payer_id, "percentage": round(value, 2)} for payer_id, value in combined.items() if value > 0]
        if result:
            delta = round(100.0 - sum(float(x["percentage"]) for x in result), 2)
            result[-1]["percentage"] = round(float(result[-1]["percentage"]) + delta, 2)
        return result

    def _normalize_period(self, paid_year, paid_month, interval, start_year, start_month, end_year, end_month) -> tuple[int, int, int, int]:
        if end_year is None or end_month is None:
            end_year, end_month = paid_year, paid_month
        self._validate_date(int(end_year), int(end_month))
        if start_year is None or start_month is None:
            start_year, start_month = self._add_months(int(end_year), int(end_month), -(max(1, interval) - 1))
        self._validate_date(int(start_year), int(start_month))
        if (int(start_year), int(start_month)) > (int(end_year), int(end_month)):
            raise billy_error("period_start_after_end")
        if len(self._month_range(int(start_year), int(start_month), int(end_year), int(end_month))) > 36:
            raise billy_error("period_too_long")
        return int(start_year), int(start_month), int(end_year), int(end_month)

    def _normalize_payers(self) -> bool:
        changed = False
        seen_ids: set[str] = set()
        seen_names: set[str] = set()
        normalized = []
        for raw in self.payers:
            name = str(raw.get("name", "")).strip()
            if not name:
                changed = True
                continue
            payer_id = str(raw.get("id") or uuid4().hex)
            while payer_id in seen_ids:
                payer_id = uuid4().hex
                changed = True
            if name.casefold() in seen_names:
                changed = True
                continue
            share = float(raw.get("share_percent", 50.0) or 0.0)
            if not isfinite(share) or share < 0 or share > 100:
                share = 50.0
                changed = True
            item = {
                "id": payer_id,
                "name": name,
                "share_percent": round(share, 2),
                "payment_methods": self._normalize_payment_methods(
                    raw.get("payment_methods"), str(raw.get("paypal_me", ""))
                ),
                "preferred_payment_method": "",
                "paypal_me": "",
                "enabled": bool(raw.get("enabled", True)),
            }
            item["preferred_payment_method"] = self._normalize_preferred_payment_method(
                str(raw.get("preferred_payment_method", "")), item["payment_methods"]
            )
            item["paypal_me"] = item["payment_methods"].get("paypal", "")
            if item != raw:
                changed = True
            normalized.append(item)
            seen_ids.add(payer_id)
            seen_names.add(name.casefold())
        self.payers = normalized
        return changed

    def _normalize_categories(self) -> bool:
        changed = False
        seen_ids: set[str] = set()
        seen_names: set[str] = set()
        normalized = []
        for index, raw in enumerate(self.categories):
            name = str(raw.get("name", "")).strip()
            if not name:
                changed = True
                continue
            category_id = str(raw.get("id") or uuid4().hex)
            while category_id in seen_ids:
                category_id = uuid4().hex
                changed = True
            interval = int(raw.get("interval_months", 1) or 1)
            if interval not in SUPPORTED_INTERVALS:
                interval = 1
                changed = True
            if name.casefold() in seen_names:
                changed = True
                continue
            default_payer = str(raw.get("default_payer_id") or "") or None
            if default_payer and self.payer(default_payer) is None:
                default_payer = None
                changed = True
            item = {
                "id": category_id,
                "name": name,
                "interval_months": interval,
                "enabled": bool(raw.get("enabled", True)),
                "default_payer_id": default_payer,
                "color": self._normalize_color(raw.get("color"), index),
                "consumption_unit": self._normalize_consumption_unit(
                    raw.get("consumption_unit") or self._default_consumption_unit(category_id, name)
                ),
                "default_provider": self._normalize_optional_text(raw.get("default_provider", ""), 100),
                "default_contract": self._normalize_optional_text(raw.get("default_contract", ""), 100),
            }
            if item != raw:
                changed = True
            normalized.append(item)
            seen_ids.add(category_id)
            seen_names.add(name.casefold())
        self.categories = normalized
        return changed

    def _migrate_expenses(self) -> bool:
        changed = False
        migrated = []
        for raw in self.expenses:
            item = dict(raw)
            paid_year = int(item.get("paid_year", item.get("year", 0)) or 0)
            paid_month = int(item.get("paid_month", item.get("month", 0)) or 0)
            try:
                self._validate_date(paid_year, paid_month)
            except ValueError:
                changed = True
                continue
            category_id = str(item.get("category_id", ""))
            category = self.category(category_id) if category_id else None
            legacy_name = str(item.get("category", "")).strip()
            if category is None and legacy_name:
                category = self.category_by_name(legacy_name)
            if category is None:
                category = {
                    "id": uuid4().hex, "name": legacy_name or "Altro", "interval_months": 1,
                    "enabled": True, "default_payer_id": None,
                    "color": self._normalize_color(None, len(self.categories)),
                    "consumption_unit": self._default_consumption_unit("", legacy_name or "Altro"),
                    "default_provider": "",
                    "default_contract": "",
                }
                duplicate = self.category_by_name(category["name"])
                if duplicate:
                    category = duplicate
                else:
                    self.categories.append(category)
                changed = True
            interval = int(category["interval_months"])
            try:
                sy, sm, ey, em = self._normalize_period(
                    paid_year, paid_month, interval,
                    int(item["period_start_year"]) if item.get("period_start_year") is not None else None,
                    int(item["period_start_month"]) if item.get("period_start_month") is not None else None,
                    int(item["period_end_year"]) if item.get("period_end_year") is not None else None,
                    int(item["period_end_month"]) if item.get("period_end_month") is not None else None,
                )
            except ValueError:
                sy, sm = self._add_months(paid_year, paid_month, -(interval - 1))
                ey, em = paid_year, paid_month
                changed = True
            amount = float(item.get("amount", 0.0) or 0.0)
            if not isfinite(amount) or amount < 0:
                changed = True
                continue
            payer_id = str(item.get("payer_id") or "") or None
            if payer_id and self.payer(payer_id) is None:
                payer_id = None
                changed = True
            split: list[dict[str, Any]] = []
            if payer_id and isinstance(item.get("split"), list):
                try:
                    split = self._normalize_split([dict(x) for x in item.get("split", [])])
                except (ValueError, TypeError):
                    split = []
                    changed = True
            try:
                payment_date = self._normalize_optional_iso_date(item.get("payment_date"))
            except ValueError:
                payment_date = None
                changed = True
            try:
                due_date = self._normalize_optional_iso_date(item.get("due_date") or item.get("expiration_date"))
            except ValueError:
                due_date = None
                changed = True
            try:
                period_start_date = self._normalize_optional_iso_date(item.get("period_start_date"))
            except ValueError:
                period_start_date = None
                changed = True
            try:
                period_end_date = self._normalize_optional_iso_date(item.get("period_end_date"))
            except ValueError:
                period_end_date = None
                changed = True
            if period_start_date and period_end_date:
                if period_start_date > period_end_date:
                    period_start_date = None
                    period_end_date = None
                    changed = True
                else:
                    parsed_start = date.fromisoformat(period_start_date)
                    parsed_end = date.fromisoformat(period_end_date)
                    sy, sm = parsed_start.year, parsed_start.month
                    ey, em = parsed_end.year, parsed_end.month
            try:
                consumption = self._normalize_optional_consumption(item.get("consumption"))
            except (ValueError, TypeError, OverflowError):
                consumption = None
                changed = True
            new_item = {
                "id": str(item.get("id") or uuid4().hex),
                "paid_year": paid_year, "paid_month": paid_month,
                "category_id": str(category["id"]), "amount": round(amount, 2),
                "period_start_year": sy, "period_start_month": sm,
                "period_end_year": ey, "period_end_month": em,
                "period_start_date": period_start_date,
                "period_end_date": period_end_date,
                "payer_id": payer_id, "split": split,
                "reimbursement_manual_done": bool(item.get("reimbursement_manual_done", False)),
                "reimbursement_manual_at": (
                    str(item.get("reimbursement_manual_at")) if item.get("reimbursement_manual_at") else None
                ),
                "paid": bool(item.get("paid", False)),
                "payment_date": payment_date,
                "due_date": due_date,
                "provider": self._normalize_optional_text(item.get("provider", ""), 100),
                "contract": self._normalize_optional_text(item.get("contract", item.get("plan", "")), 100),
                "consumption": consumption,
                "consumption_unit": self._normalize_consumption_unit(
                    item.get("consumption_unit") or category.get("consumption_unit", "")
                ),
                "note": str(item.get("note", "")).strip(),
                "created_at": str(item.get("created_at") or datetime.now().astimezone().isoformat(timespec="seconds")),
            }
            if new_item != raw:
                changed = True
            migrated.append(new_item)
        self.expenses = migrated
        return changed

    def _migrate_settlements(self) -> bool:
        changed = False
        migrated = []
        for raw in self.settlements:
            source = str(raw.get("from_payer_id") or "")
            target = str(raw.get("to_payer_id") or "")
            amount = float(raw.get("amount", 0.0) or 0.0)
            if not source or not target or source == target or self.payer(source) is None or self.payer(target) is None or not isfinite(amount) or amount <= 0:
                changed = True
                continue
            item = {
                "id": str(raw.get("id") or uuid4().hex),
                "from_payer_id": source, "to_payer_id": target,
                "amount": round(amount, 2),
                "expense_ids": [str(x) for x in raw.get("expense_ids", []) if x],
                "recurring_occurrence_ids": [
                    str(x) for x in raw.get("recurring_occurrence_ids", []) if x
                ],
                "note": str(raw.get("note", "")).strip(),
                "created_at": str(raw.get("created_at") or datetime.now().astimezone().isoformat(timespec="seconds")),
            }
            if item != raw:
                changed = True
            migrated.append(item)
        self.settlements = migrated
        return changed

    def _migrate_recurring_expenses(self) -> bool:
        changed = False
        migrated: list[dict[str, Any]] = []
        for raw in self.recurring_expenses:
            try:
                normalized = self._normalize_recurring_payload(
                    name=str(raw.get("name", "")),
                    kind=str(raw.get("kind", "recurring")),
                    amount=float(raw.get("amount", 0.0) or 0.0),
                    interval_months=int(raw.get("interval_months", 1) or 1),
                    start_date=str(raw.get("start_date", "")),
                    end_date=str(raw.get("end_date") or "") or None,
                    auto_renew=bool(raw.get("auto_renew", False)),
                    renewal_interval_months=int(raw.get("renewal_interval_months", 12) or 12),
                    installment_count=(
                        int(raw["installment_count"])
                        if raw.get("installment_count") not in (None, "")
                        else None
                    ),
                    payer_id=str(raw.get("payer_id") or "") or None,
                    split=[dict(x) for x in raw.get("split", [])] or None,
                    provider=str(raw.get("provider", "")),
                    contract=str(raw.get("contract", "")),
                    color=str(raw.get("color", "")) or None,
                    note=str(raw.get("note", "")),
                    active=bool(raw.get("active", True)),
                )
            except (ValueError, TypeError, OverflowError):
                changed = True
                continue
            item = {
                "id": str(raw.get("id") or uuid4().hex),
                **normalized,
                "created_at": str(
                    raw.get("created_at")
                    or datetime.now().astimezone().isoformat(timespec="seconds")
                ),
            }
            if raw.get("updated_at"):
                item["updated_at"] = str(raw.get("updated_at"))
            tracking = str(raw.get("reimbursement_tracking_start_date") or "")
            if tracking:
                try:
                    item["reimbursement_tracking_start_date"] = date.fromisoformat(
                        tracking
                    ).isoformat()
                except ValueError:
                    item["reimbursement_tracking_start_date"] = self._recurring_tracking_start(item)
            else:
                item["reimbursement_tracking_start_date"] = self._recurring_tracking_start(item)
            if item != raw:
                changed = True
            migrated.append(item)
        self.recurring_expenses = migrated
        return changed

    def _migrate_recurring_occurrences(self) -> bool:
        changed = False
        migrated: list[dict[str, Any]] = []
        recurring_by_id = {
            str(x.get("id")): x for x in self.recurring_expenses if x.get("id")
        }
        recurring_ids = set(recurring_by_id)
        seen: set[str] = set()
        for raw in self.recurring_occurrences:
            recurring_id = str(raw.get("recurring_id") or "")
            if recurring_id not in recurring_ids:
                changed = True
                continue
            try:
                due_date = date.fromisoformat(str(raw.get("due_date") or "")).isoformat()
                amount = round(float(raw.get("amount", 0.0) or 0.0), 2)
            except (ValueError, TypeError, OverflowError):
                changed = True
                continue
            occurrence_id = str(raw.get("id") or f"{recurring_id}@{due_date}")
            if occurrence_id in seen or amount <= 0:
                changed = True
                continue
            seen.add(occurrence_id)
            try:
                payer_id = self._validate_optional_payer(
                    str(raw.get("payer_id") or "") or None
                )
            except ValueError:
                payer_id = None
                changed = True
            raw_split = [dict(x) for x in raw.get("split", [])]
            try:
                split = self._resolve_expense_split(raw_split or None, payer_id)
            except ValueError:
                split = []
                payer_id = None
                changed = True
            item = {
                "id": occurrence_id,
                "recurring_id": recurring_id,
                "due_date": due_date,
                "name": self._normalize_optional_text(raw.get("name", ""), 120),
                "kind": str(raw.get("kind", "recurring")),
                "color": self._normalize_color(
                    raw.get("color")
                    or recurring_by_id.get(recurring_id, {}).get("color"),
                    0,
                ),
                "amount": amount,
                "payer_id": payer_id,
                "split": split,
                "reimbursement_manual_done": bool(
                    raw.get("reimbursement_manual_done", False)
                ),
                "reimbursement_manual_at": raw.get("reimbursement_manual_at"),
                "created_at": str(
                    raw.get("created_at")
                    or datetime.now().astimezone().isoformat(timespec="seconds")
                ),
            }
            if item != raw:
                changed = True
            migrated.append(item)
        self.recurring_occurrences = migrated
        return changed

    async def _save_and_notify(self) -> None:
        await self._save()
        self.hass.bus.async_fire(EVENT_UPDATED)

    async def _save(self) -> None:
        await self._store.async_save(
            {
                "schema_version": STORAGE_SCHEMA_VERSION,
                "categories": self.categories,
                "payers": self.payers,
                "expenses": self.expenses,
                "settlements": self.settlements,
                "recurring_expenses": self.recurring_expenses,
                "recurring_occurrences": self.recurring_occurrences,
            }
        )

    def _sort(self) -> None:
        self.expenses.sort(key=lambda x: (int(x.get("paid_year", 0)), int(x.get("paid_month", 0)), str(x.get("created_at", ""))), reverse=True)
        self.settlements.sort(key=lambda x: str(x.get("created_at", "")), reverse=True)
        self.recurring_expenses.sort(key=lambda x: (not bool(x.get("active", True)), str(x.get("name", "")).casefold()))
        self.recurring_occurrences.sort(key=lambda x: (str(x.get("due_date", "")), str(x.get("id", ""))), reverse=True)

    def _validate_optional_payer(self, payer_id: str | None) -> str | None:
        value = str(payer_id or "")
        if not value:
            return None
        if self.payer(value) is None:
            raise billy_error("default_payer_invalid")
        return value

    @staticmethod
    def _normalize_optional_iso_date(value: Any) -> str | None:
        text = str(value or "").strip()
        if not text:
            return None
        try:
            parsed = date.fromisoformat(text)
        except ValueError as err:
            raise billy_error("date_invalid") from err
        if parsed.year < 2000 or parsed.year > 2200:
            raise billy_error("date_invalid")
        return parsed.isoformat()

    @staticmethod
    def _expense_cashflow_month(item: dict[str, Any]) -> tuple[int, int]:
        payment_date = str(item.get("payment_date") or "").strip()
        if payment_date:
            try:
                parsed = date.fromisoformat(payment_date)
                return parsed.year, parsed.month
            except ValueError:
                pass
        return int(item["paid_year"]), int(item["paid_month"])

    @staticmethod
    def _normalize_optional_text(value: Any, max_length: int) -> str:
        return str(value or "").strip()[:max_length]

    @staticmethod
    def _normalize_consumption_unit(value: Any) -> str:
        return str(value or "").strip()[:20]

    @staticmethod
    def _default_consumption_unit(category_id: str, name: str) -> str:
        key = f"{category_id} {name}".casefold()
        if "electric" in key or "elettr" in key or "power" in key:
            return "kWh"
        if "gas" in key or "water" in key or "acqua" in key:
            return "m³"
        return ""

    @staticmethod
    def _normalize_optional_consumption(value: Any) -> float | None:
        if value is None or str(value).strip() == "":
            return None
        amount = float(value)
        if not isfinite(amount) or amount < 0:
            raise billy_error("consumption_invalid")
        return round(amount, 4)

    @staticmethod
    def _validate_payer(name: str, share_percent: float) -> None:
        if not name:
            raise billy_error("name_required")
        if len(name) > 60:
            raise billy_error("name_too_long")
        share = float(share_percent)
        if not isfinite(share) or share < 0 or share > 100:
            raise billy_error("share_invalid")

    @staticmethod
    def _validate_category(name: str, interval_months: int) -> None:
        if not name:
            raise billy_error("name_required")
        if len(name) > 60:
            raise billy_error("name_too_long")
        if int(interval_months) not in SUPPORTED_INTERVALS:
            raise billy_error("interval_unsupported")

    @staticmethod
    def _validate_amount(amount: float, allow_zero: bool = True) -> None:
        value = float(amount)
        if not isfinite(value) or value < 0 or (not allow_zero and value <= 0):
            raise billy_error("amount_invalid")

    @staticmethod
    def _validate_date(year: int, month: int) -> None:
        if int(year) < 2000 or int(year) > 2200:
            raise billy_error("year_invalid")
        if int(month) < 1 or int(month) > 12:
            raise billy_error("month_invalid")

    @staticmethod
    def _normalize_paypal_me(value: str) -> str:
        text = str(value or "").strip()
        if not text:
            return ""
        text = text.split("?", 1)[0].rstrip("/")
        if "/" in text:
            text = text.rsplit("/", 1)[-1]
        return "".join(ch for ch in text if ch.isalnum() or ch in "._-")[:80]

    @classmethod
    def _normalize_payment_methods(
        cls, methods: Any, legacy_paypal: str = ""
    ) -> dict[str, str]:
        raw = dict(methods) if isinstance(methods, dict) else {}
        if legacy_paypal and not raw.get("paypal"):
            raw["paypal"] = legacy_paypal
        result: dict[str, str] = {}
        for method in ("paypal", "revolut", "venmo", "cashapp"):
            value = str(raw.get(method, "") or "").strip()
            if not value:
                continue
            if method == "paypal":
                normalized = cls._normalize_paypal_me(value)
            else:
                for prefix in ("https://", "http://"):
                    if value.startswith(prefix):
                        value = value.rstrip("/").rsplit("/", 1)[-1]
                value = value.lstrip("@$ ")
                normalized = "".join(
                    ch for ch in value if ch.isalnum() or ch in "._-"
                )[:80]
            if normalized:
                result[method] = normalized
        return result

    @staticmethod
    def _normalize_preferred_payment_method(
        method: str, methods: dict[str, str]
    ) -> str:
        requested = str(method or "").strip().lower()
        if requested in methods:
            return requested
        for candidate in ("paypal", "revolut", "venmo", "cashapp"):
            if candidate in methods:
                return candidate
        return ""

    @classmethod
    def _preferred_payment(
        cls, payer: dict[str, Any], amount: float, currency: str
    ) -> dict[str, str]:
        methods = cls._normalize_payment_methods(
            payer.get("payment_methods"), str(payer.get("paypal_me", ""))
        )
        method = cls._normalize_preferred_payment_method(
            str(payer.get("preferred_payment_method", "")), methods
        )
        handle = methods.get(method, "")
        return {
            "method": method,
            "handle": handle,
            "url": cls._payment_url(method, handle, amount, currency),
        }

    @classmethod
    def _payment_url(
        cls, method: str, handle: str, amount: float, currency: str = "EUR"
    ) -> str:
        if not handle:
            return ""
        safe = quote(handle, safe="._-")
        if method == "paypal":
            return cls._paypal_url(handle, amount, currency)
        if method == "revolut":
            return f"https://revolut.me/{safe}"
        if method == "venmo":
            return f"https://venmo.com/u/{safe}"
        if method == "cashapp":
            return f"https://cash.app/${safe}"
        return ""

    @staticmethod
    def _paypal_url(handle: str, amount: float, currency: str = "EUR") -> str:
        if not handle:
            return ""
        code = str(currency or "EUR").upper()
        return f"https://paypal.me/{quote(handle, safe='._-')}/{float(amount):.2f}{quote(code)}"

    @staticmethod
    def _normalize_color(value: Any, index: int) -> str:
        text = str(value or "").strip()
        if len(text) == 7 and text.startswith("#") and all(ch in "0123456789abcdefABCDEF" for ch in text[1:]):
            return text.upper()
        return FALLBACK_COLORS[index % len(FALLBACK_COLORS)]

    @staticmethod
    def _next_month(year: int, month: int) -> tuple[int, int]:
        return BillTrackerManager._add_months(year, month, 1)

    @staticmethod
    def _add_months(year: int, month: int, delta: int) -> tuple[int, int]:
        absolute = year * 12 + (month - 1) + delta
        return absolute // 12, absolute % 12 + 1

    @staticmethod
    def _month_range(start_year: int, start_month: int, end_year: int, end_month: int) -> list[tuple[int, int]]:
        if (start_year, start_month) > (end_year, end_month):
            return []
        result = []
        y, m = start_year, start_month
        while (y, m) <= (end_year, end_month) and len(result) <= 36:
            result.append((y, m))
            y, m = BillTrackerManager._next_month(y, m)
        return result
