"""Persistent data model, bill splitting and forecasting for Bill Tracker."""
from __future__ import annotations

from calendar import monthrange
from collections import defaultdict
from copy import copy, deepcopy
from datetime import date, datetime, timedelta
import json
from math import isfinite
from statistics import mean
from typing import Any
from urllib.parse import quote, urlsplit
from uuid import uuid4
import logging
import base64
from time import monotonic

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

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
from .document_archive import (
    MAX_PDF_BYTES, archive_pdf, archive_pdf_bytes, delete_archived_pdf,
    normalize_archive_config, read_pdf, validate_owned_pdf_path,
)
from .income import IncomeMixin
from .accounts import AccountMixin, _cents, _value
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


_UNSET_TOTAL = object()


class BillTrackerManager(IncomeMixin, AccountMixin):
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
        self.recurring_payments: list[dict[str, Any]] = []
        self.income_categories: list[dict[str, Any]] = []
        self.incomes: list[dict[str, Any]] = []
        self.income_rules: list[dict[str, Any]] = []
        self.accounts: list[dict[str, Any]] = []
        self.default_account_id: str | None = None
        self.accounts_config: dict[str, Any] = {}
        self.internal_transfers: list[dict[str, Any]] = []
        self.houses: list[dict[str, Any]] = []
        self.default_house_id: str | None = None
        self._logger = logging.getLogger(__name__)
        self._document_uploads: dict[tuple[str, str], dict[str, Any]] = {}

    async def async_load(self) -> None:
        """Load and migrate the persistent database."""
        data = await self._store.async_load() or {}
        self.categories = [dict(x) for x in data.get("categories", [])]
        self.expenses = [dict(x) for x in data.get("expenses", [])]
        self.payers = [dict(x) for x in data.get("payers", [])]
        self.settlements = [dict(x) for x in data.get("settlements", [])]
        self.recurring_expenses = [dict(x) for x in data.get("recurring_expenses", [])]
        self.recurring_occurrences = [dict(x) for x in data.get("recurring_occurrences", [])]
        self.recurring_payments = [dict(x) for x in data.get("recurring_payments", [])]
        self.income_categories = [dict(x) for x in data.get("income_categories", [])]
        self.incomes = [dict(x) for x in data.get("incomes", [])]
        self.income_rules = [dict(x) for x in data.get("income_rules", [])]
        self.accounts = [dict(x) for x in data.get("accounts", [])]
        self.default_account_id = str(data.get("default_account_id") or "") or None
        self.accounts_config = dict(data.get("accounts_config") or {})
        self.internal_transfers = [
            dict(x) if isinstance(x, dict) else x
            for x in data.get("internal_transfers", [])
        ]
        self.houses = [dict(x) for x in data.get("houses", [])]
        self.default_house_id = str(data.get("default_house_id") or "") or None

        changed = False
        changed |= self._migrate_houses()
        changed |= self._normalize_payers()
        if not self.categories:
            self.categories = deepcopy(DEFAULT_CATEGORIES)
            changed = True
        changed |= self._normalize_categories()
        changed |= self._migrate_expenses()
        changed |= self._migrate_settlements()
        changed |= self._migrate_recurring_expenses()
        changed |= self._migrate_recurring_occurrences()
        changed |= self._migrate_income()
        changed |= self._migrate_accounts()
        changed |= self._migrate_recurring_payments()
        changed |= self._sync_income_occurrences()
        changed |= self._sync_recurring_occurrences()
        changed |= self._sync_bill_placeholders()
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
    # Houses: grouping only, not user permissions or separate cash accounts
    # ------------------------------------------------------------------
    def house(self, house_id: str) -> dict[str, Any] | None:
        return next((row for row in self.houses if row["id"] == house_id), None)

    def _resolve_house_id(self, house_id: str | None = None) -> str:
        selected = str(house_id or self.default_house_id or "")
        if not self.house(selected):
            raise ValueError("House not found")
        return selected

    def _migrate_houses(self) -> bool:
        changed = False
        if not self.houses:
            self.houses = [{"id": uuid4().hex, "name": "Home"}]
            changed = True
        unique: set[str] = set()
        names: set[str] = set()
        for item in self.houses:
            identifier = str(item.get("id") or "")
            name = str(item.get("name") or "").strip()
            if not identifier or not name or len(name) > 80:
                raise ValueError("Invalid house in storage or backup")
            if identifier in unique or name.casefold() in names:
                raise ValueError("Duplicate house in storage or backup")
            unique.add(identifier)
            names.add(name.casefold())
        if self.default_house_id not in unique:
            self.default_house_id = self.houses[0]["id"]
            changed = True
        for records in (self.expenses, self.recurring_expenses):
            for item in records:
                if not item.get("house_id"):
                    item["house_id"] = self.default_house_id
                    changed = True
                elif item["house_id"] not in unique:
                    raise ValueError("Expense refers to a house that does not exist")
        return changed

    async def async_add_house(self, name: str) -> dict[str, Any]:
        title = str(name or "").strip()
        if not title or len(title) > 80:
            raise ValueError("House name must contain 1–80 characters")
        if any(row["name"].casefold() == title.casefold() for row in self.houses):
            raise ValueError("A house with this name already exists")
        if len(self.houses) >= 50:
            raise ValueError("Maximum number of houses reached")
        item = {"id": uuid4().hex, "name": title}
        self.houses.append(item)
        await self._save_and_notify()
        return dict(item)

    async def async_update_house(self, house_id: str, name: str) -> dict[str, Any]:
        item = self.house(house_id)
        if item is None:
            raise ValueError("House not found")
        title = str(name or "").strip()
        if not title or len(title) > 80:
            raise ValueError("House name must contain 1–80 characters")
        if any(row["id"] != house_id and row["name"].casefold() == title.casefold()
               for row in self.houses):
            raise ValueError("A house with this name already exists")
        if item["name"] != title:
            item["name"] = title
            await self._save_and_notify()
        return dict(item)

    async def async_set_default_house(self, house_id: str) -> dict[str, Any]:
        item = self.house(house_id)
        if item is None:
            raise ValueError("House not found")
        if self.default_house_id != house_id:
            self.default_house_id = house_id
            await self._save_and_notify()
        return dict(item)

    async def async_delete_house(self, house_id: str) -> bool:
        if self.house(house_id) is None:
            return False
        if house_id == self.default_house_id or len(self.houses) <= 1:
            raise ValueError("Choose another default house before deleting this one")
        if any(row.get("house_id") == house_id
               for row in (*self.expenses, *self.recurring_expenses)):
            raise ValueError("Move the linked bills and recurring expenses before deleting this house")
        if any(
            line.get("house_id") == house_id
            for settlement in self.settlements
            for line in settlement.get("line_items", [])
            if isinstance(line, dict)
        ):
            raise ValueError("Undo reimbursements linked to this house before deleting it")
        if any(
            (category.get("house_placeholders", {}).get(house_id) or {}).get("enabled")
            or ("house_placeholders" not in category
                and (category.get("placeholder") or {}).get("enabled")
                and (category.get("placeholder") or {}).get("house_id") == house_id)
            for category in self.categories
        ):
            raise ValueError("Remove this house's bill-type schedules before deleting it")
        for category in self.categories:
            category.get("house_placeholders", {}).pop(house_id, None)
            legacy = category.get("placeholder") or {}
            if legacy.get("house_id") == house_id:
                legacy["house_id"] = self.default_house_id
                legacy["enabled"] = False
        self.houses = [row for row in self.houses if row["id"] != house_id]
        await self._save_and_notify()
        return True

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
        if any(row.get("payer_id") == payer_id for row in self.accounts):
            raise ValueError("Payer owns accounts; reassign or delete them first")
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
        exclude_from_estimates: bool = False,
        default_payer_id: str | None = None,
        color: str | None = None,
        consumption_unit: str = "",
        default_provider: str = "",
        default_contract: str = "",
        placeholder: dict[str, Any] | None = None,
        house_placeholders: dict[str, dict[str, Any]] | None = None,
        document_archive: dict[str, Any] | None = None,
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
            "exclude_from_estimates": bool(exclude_from_estimates),
            "default_payer_id": payer_id,
            "color": self._normalize_color(color, len(self.categories)),
            "consumption_unit": self._normalize_consumption_unit(consumption_unit),
            "default_provider": self._normalize_optional_text(default_provider, 100),
            "default_contract": self._normalize_optional_text(default_contract, 100),
            "document_archive": normalize_archive_config(document_archive),
        }
        item["placeholder"] = self._normalize_placeholder_config(item, placeholder)
        if house_placeholders is not None:
            item["house_placeholders"] = self._normalize_house_placeholders(item, house_placeholders)
        self.categories.append(item)
        self._sync_bill_placeholders()
        await self._save_and_notify()
        return dict(item)

    async def async_update_category(
        self,
        category_id: str,
        *,
        name: str,
        interval_months: int,
        enabled: bool,
        exclude_from_estimates: bool | None = None,
        default_payer_id: str | None = None,
        color: str | None = None,
        consumption_unit: str = "",
        default_provider: str = "",
        default_contract: str = "",
        placeholder: dict[str, Any] | None = None,
        house_placeholders: dict[str, dict[str, Any]] | None = None,
        document_archive: dict[str, Any] | None = None,
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
        placeholder_config = self._normalize_placeholder_config(
            item, placeholder if placeholder is not None else item.get("placeholder"),
            interval_months=int(interval_months),
        )
        per_house = (
            self._normalize_house_placeholders(
                item, house_placeholders, interval_months=int(interval_months)
            )
            if house_placeholders is not None else item.get("house_placeholders")
        )
        item.update(
            {
                "name": name,
                "interval_months": int(interval_months),
                "enabled": bool(enabled),
                "exclude_from_estimates": (
                    bool(exclude_from_estimates)
                    if exclude_from_estimates is not None
                    else bool(item.get("exclude_from_estimates", False))
                ),
                "default_payer_id": payer_id,
                "color": self._normalize_color(color or item.get("color"), 0),
                "consumption_unit": self._normalize_consumption_unit(consumption_unit),
                "default_provider": self._normalize_optional_text(default_provider, 100),
                "default_contract": self._normalize_optional_text(default_contract, 100),
                "placeholder": placeholder_config,
                "document_archive": normalize_archive_config(
                    document_archive if document_archive is not None else item.get("document_archive")
                ),
            }
        )
        if per_house is not None:
            item["house_placeholders"] = per_house
        self._sync_bill_placeholders()
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
        exclude_from_estimates: bool = False,
        payment_date: str | None = None,
        due_date: str | None = None,        provider: str | None = None,
        contract: str | None = None,
        consumption: float | None = None,
        document_url: str = "",
        account_id: str | None = None,
        house_id: str | None = None,
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
            "exclude_from_estimates": bool(exclude_from_estimates),
            "payment_date": normalized_payment_date,
            "due_date": normalized_due_date,
            "provider": self._normalize_optional_text(category.get("default_provider", "") if provider is None else provider, 100),
            "contract": self._normalize_optional_text(category.get("default_contract", "") if contract is None else contract, 100),
            "consumption": normalized_consumption,
            "consumption_unit": str(category.get("consumption_unit", "")),
            "note": note.strip(),
            "document_url": self._normalize_document_url(document_url),
            "document_path": None,
            "document_sha256": None,
            "document_error": None,
            "account_id": self._resolve_account_id(account_id),
            "house_id": self._resolve_house_id(house_id),
            "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        }
        self._store_real_expense(item)
        self._sort()
        await self._save_and_notify()
        self._queue_document_archive(item)
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
        exclude_from_estimates: bool | None = None,
        payment_date: str | None = None,
        due_date: str | None = None,
        provider: str | None = None,
        contract: str | None = None,
        consumption: float | None = None,
        document_url: str | None = None,
        account_id: str | None = None,
        house_id: str | None = None,
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
            resolved_url = (
                self._normalize_document_url(document_url)
                if document_url is not None else str(item.get("document_url") or "")
            )
            document_changed = (
                resolved_url != str(item.get("document_url") or "")
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
                    "exclude_from_estimates": (
                        bool(exclude_from_estimates)
                        if exclude_from_estimates is not None
                        else bool(item.get("exclude_from_estimates", False))
                    ),
                    "payment_date": resolved_payment_date,
                    "due_date": normalized_due_date if due_date is not None else item.get("due_date"),
                    "provider": self._normalize_optional_text(provider, 100) if provider is not None else str(item.get("provider", "")),
                    "contract": self._normalize_optional_text(contract, 100) if contract is not None else str(item.get("contract", "")),
                    "consumption": normalized_consumption,
                    "consumption_unit": str(category.get("consumption_unit", "")),
                    "note": note.strip(),
                    "house_id": self._resolve_house_id(
                        house_id if house_id is not None else item.get("house_id")
                    ),
                    "is_placeholder": False,
                    "document_url": resolved_url,
                    "document_path": None if document_changed else item.get("document_path"),
                    "document_sha256": None if document_changed else item.get("document_sha256"),
                    "document_error": None if document_changed else item.get("document_error"),
                    "account_id": self._resolve_account_id(
                        account_id if account_id is not None else item.get("account_id")
                    ),
                }
            )
            self._sort()
            await self._save_and_notify()
            if document_changed:
                self._queue_document_archive(item)
            return self._public_expense(item)
        return None

    async def async_set_paid(self, expense_id: str, paid: bool) -> dict[str, Any] | None:
        """Set only the payment status of an expense without rewriting its other fields."""
        for item in self.expenses:
            if item.get("id") != expense_id:
                continue
            item["paid"] = bool(paid)
            if paid:
                item["is_placeholder"] = False
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
    # Monthly bill checklist
    # ------------------------------------------------------------------
    def _normalize_placeholder_config(
        self, category: dict[str, Any], raw: dict[str, Any] | None,
        *, interval_months: int | None = None,
    ) -> dict[str, Any]:
        """Validate user settings and retain the last processed month internally."""
        if raw is not None and not isinstance(raw, dict):
            raise billy_error("placeholder_invalid")
        raw = raw or {}
        try:
            day = int(raw.get("day", 1))
            due_day = int(raw["due_day"]) if raw.get("due_day") not in (None, "") else None
            fixed_amount = float(raw.get("fixed_amount", 0.0))
        except (ValueError, TypeError, OverflowError) as err:
            raise billy_error("placeholder_invalid") from err
        mode = str(raw.get("amount_mode", "last"))
        if not 1 <= day <= 31 or (due_day is not None and not 1 <= due_day <= 31):
            raise billy_error("placeholder_invalid")
        if mode not in {"last", "forecast", "fixed"}:
            raise billy_error("placeholder_invalid")
        self._validate_amount(fixed_amount)
        start_month = str(raw.get("start_month") or "")
        if start_month:
            try:
                if len(start_month) != 7:
                    raise ValueError
                date.fromisoformat(f"{start_month}-01")
            except ValueError as err:
                raise billy_error("placeholder_invalid") from err
        enabled = bool(raw.get("enabled", False))
        if enabled and not start_month:
            today = dt_util.now().date()
            current = (today.year, today.month)
            history = self._placeholder_history(
                category, str(raw.get("house_id") or self.default_house_id)
            )
            history = [x for x in history if (int(x["paid_year"]), int(x["paid_month"])) <= current]
            interval = interval_months or int(category.get("interval_months", 1))
            first = self._add_months(
                int(history[-1]["paid_year"]), int(history[-1]["paid_month"]), interval
            ) if history else current
            while first < current:
                first = self._add_months(*first, interval)
            start_month = f"{first[0]:04d}-{first[1]:02d}"
        previous = category.get("placeholder") or {}
        return {
            "enabled": enabled, "day": day, "amount_mode": mode,
            "fixed_amount": round(fixed_amount, 2), "due_day": due_day,
            "start_month": start_month,
            "last_generated_month": str(previous.get("last_generated_month") or raw.get("last_generated_month") or ""),
            "house_id": self._resolve_house_id(raw.get("house_id") or previous.get("house_id")),
            "provider": self._normalize_optional_text(raw.get("provider", ""), 100),
            "contract": self._normalize_optional_text(raw.get("contract", ""), 100),
        }

    def _normalize_house_placeholders(
        self,
        category: dict[str, Any],
        raw: dict[str, dict[str, Any]],
        *,
        interval_months: int | None = None,
    ) -> dict[str, dict[str, Any]]:
        if not isinstance(raw, dict) or len(raw) > 50:
            raise ValueError("Invalid house-specific bill schedules")
        previous = category.get("house_placeholders") or {}
        if "house_placeholders" not in category:
            legacy = category.get("placeholder") or {}
            if legacy.get("house_id"):
                previous = {legacy["house_id"]: legacy}
        result = {}
        for house_id, config in raw.items():
            selected = self._resolve_house_id(str(house_id))
            if not isinstance(config, dict):
                raise ValueError("Invalid house-specific bill schedule")
            local_category = {
                **category,
                "placeholder": previous.get(selected) or {},
            }
            result[selected] = self._normalize_placeholder_config(
                local_category, {**config, "house_id": selected},
                interval_months=interval_months,
            )
        return result

    def _placeholder_history(
        self, category: dict[str, Any], house_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Actual invoices provide estimates even for forecast-excluded bill types."""
        history = []
        for item in self.expenses:
            if item.get("category_id") != category["id"] or item.get("is_placeholder", False):
                continue
            if house_id is not None and item.get("house_id") != house_id:
                continue
            try:
                year = int(item.get("paid_year", item.get("year", 0)))
                month = int(item.get("paid_month", item.get("month", 0)))
                self._validate_date(year, month)
            except (ValueError, TypeError, OverflowError):
                continue
            history.append({**item, "paid_year": year, "paid_month": month})
        return sorted(history, key=lambda x: (x["paid_year"], x["paid_month"], str(x.get("created_at", ""))))

    def _sync_bill_placeholders(self, today: date | None = None) -> bool:
        """Create only the current local month's missing entries, without backfill."""
        today = today or dt_util.now().date()
        key = f"{today.year:04d}-{today.month:02d}"
        changed = False
        for category in self.categories:
            if not category.get("enabled", True):
                continue
            # Legacy category settings still work until the user explicitly
            # configures per-house schedules in the bill-type editor.
            rules = category.get("house_placeholders")
            if rules is None:
                legacy = category.get("placeholder") or {}
                rules = {legacy.get("house_id") or self.default_house_id: legacy}
            for house_id, config in rules.items():
                if not config.get("enabled"):
                    continue
                start = date.fromisoformat(f"{config['start_month']}-01")
                offset = (today.year - start.year) * 12 + today.month - start.month
                if offset < 0 or offset % int(category["interval_months"]):
                    continue
                creation_day = min(int(config["day"]), monthrange(today.year, today.month)[1])
                if today.day < creation_day or config.get("last_generated_month") == key:
                    continue
                if any(x.get("category_id") == category["id"]
                       and (x.get("house_id") or self.default_house_id) == house_id
                       and (int(x["paid_year"]), int(x["paid_month"])) == (today.year, today.month)
                       for x in self.expenses):
                    continue
                history = [
                    x for x in self._placeholder_history(category, house_id)
                    if (int(x["paid_year"]), int(x["paid_month"])) <= (today.year, today.month)
                ]
                if config["amount_mode"] == "fixed":
                    amount = config["fixed_amount"]
                elif config["amount_mode"] == "forecast":
                    amount = self._estimate_category_amount(
                        [x for x in history if not x.get("exclude_from_estimates", False)]
                    )
                else:
                    amount = history[-1]["amount"] if history else 0.0
                payer_id = self._resolve_expense_payer(category, None)
                default_split = self.default_split()
                if payer_id and not default_split:
                    default_split = [{"payer_id": payer_id, "percentage": 100.0}]
                split = self._resolve_expense_split(default_split or None, payer_id)
                sy, sm = self._add_months(today.year, today.month, -(int(category["interval_months"]) - 1))
                due_day = config.get("due_day")
                self.expenses.append({
                    "id": uuid4().hex, "category_id": category["id"],
                    "house_id": house_id,
                    "paid_year": today.year, "paid_month": today.month,
                    "amount": round(float(amount), 2), "is_placeholder": True,
                    "period_start_year": sy, "period_start_month": sm,
                    "period_end_year": today.year, "period_end_month": today.month,
                    "period_start_date": None, "period_end_date": None,
                    "payer_id": payer_id, "split": split,
                    "paid": False, "payment_date": None,
                    "due_date": date(today.year, today.month, min(int(due_day), monthrange(today.year, today.month)[1])).isoformat() if due_day else None,
                    "exclude_from_estimates": False,
                    "reimbursement_manual_done": False, "reimbursement_manual_at": None,
                    "provider": config.get("provider") or category.get("default_provider", ""),
                    "contract": config.get("contract") or category.get("default_contract", ""),
                    "consumption": None, "consumption_unit": category.get("consumption_unit", ""),
                    "note": "", "created_at": dt_util.now().isoformat(timespec="seconds"),
                })
                config["last_generated_month"] = key
                changed = True
        if changed:
            self._sort()
        return changed

    async def async_sync_bill_placeholders(self) -> bool:
        """Persist generated entries and refresh clients and HA automations."""
        changed = self._sync_bill_placeholders()
        if changed:
            await self._save_and_notify()
        return changed

    def _store_real_expense(self, item: dict[str, Any]) -> None:
        """Replace a matching provisional invoice in place, preserving its ID."""
        item["is_placeholder"] = False
        item["house_id"] = self._resolve_house_id(item.get("house_id"))
        target = next((x for x in self.expenses if x.get("is_placeholder", False)
                       and x["category_id"] == item["category_id"]
                       and x.get("house_id", self.default_house_id) == item.get("house_id", self.default_house_id)
                       and x["paid_year"] == item["paid_year"]
                       and x["paid_month"] == item["paid_month"]), None)
        item["account_id"] = self._resolve_account_id(
            item.get("account_id") or (target or {}).get("account_id")
        )
        if target is None:
            self.expenses.append(item)
            return
        item["id"] = target["id"]
        item["created_at"] = target["created_at"]
        target.clear()
        target.update(item)

    def current_month_unpaid_bills(self) -> list[dict[str, Any]]:
        """Compact local-month checklist shared by HA attributes and the frontend."""
        today = dt_util.now().date()
        key = f"{today.year:04d}-{today.month:02d}"
        return [
            {"id": x["id"], "category_id": x["category_id"],
             "category": str((self.category(x["category_id"]) or {}).get("name", "")),
             "amount": x["amount"], "due_date": x.get("due_date"),
             "is_placeholder": bool(x.get("is_placeholder", False)),
             "year": int(x["paid_year"]), "month": int(x["paid_month"])}
            for x in self.expenses if not x.get("paid", False)
            and ((int(x["paid_year"]), int(x["paid_month"])) == (today.year, today.month)
                 or str(x.get("due_date") or "").startswith(f"{key}-"))
        ]

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
        total_amount: float | None = None,
        payer_id: str | None = None,
        split: list[dict[str, Any]] | None = None,
        provider: str = "",
        contract: str = "",
        color: str | None = None,
        note: str = "",
        active: bool = True,
        house_id: str | None = None,
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
            total_amount=total_amount,
            payer_id=payer_id,
            split=split,
            provider=provider,
            contract=contract,
            color=color,
            note=note,
            active=active,
        )
        item["house_id"] = self._resolve_house_id(house_id)
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
        total_amount: float | None | object = _UNSET_TOTAL,
        payer_id: str | None = None,
        split: list[dict[str, Any]] | None = None,
        provider: str = "",
        contract: str = "",
        color: str | None = None,
        note: str = "",
        active: bool = True,
        house_id: str | None = None,
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
            total_amount=(
                current.get("total_amount") if total_amount is _UNSET_TOTAL
                and kind in ("installment", "mortgage") else total_amount
                if total_amount is not _UNSET_TOTAL else None
            ),
            payer_id=payer_id,
            split=split,
            provider=provider,
            contract=contract,
            color=color or current.get("color"),
            note=note,
            active=active,
        )
        normalized["house_id"] = self._resolve_house_id(
            house_id if house_id is not None else current.get("house_id")
        )
        schedule_changed = any(
            current.get(key) != normalized.get(key)
            for key in ("start_date", "end_date", "interval_months", "installment_count")
        )
        for payment in self.recurring_payments:
            if payment.get("recurring_id") == recurring_id and not self._recurring_payment_due(
                normalized, str(payment["due_date"])
            ):
                raise ValueError(
                    "Cannot change this schedule while recorded payments depend on its due dates. "
                    "Undo or correct the affected payments first."
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
        if any(p.get("recurring_id") == recurring_id for p in self.recurring_payments):
            raise ValueError("Undo recorded payments before deleting this recurring expense")
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

    def _recurring_payment_due(self, recurring: dict[str, Any], due_date: str) -> bool:
        """A paid installment must match an actual date on the rule's schedule."""
        try:
            requested = date.fromisoformat(due_date)
            enabled = {**recurring, "active": True}
            return self._next_recurring_due(enabled, requested) == requested
        except (ValueError, TypeError, OverflowError):
            return False

    def _normalize_recurring_payment(
        self,
        *,
        recurring_id: str,
        due_date: str,
        payment_date: str,
        amount: float,
        account_id: str | None,
        note: str = "",
        already_recorded: bool = False,
        allow_unassigned: bool = False,
    ) -> dict[str, Any]:
        recurring = self.recurring_expense(str(recurring_id or ""))
        if recurring is None:
            raise ValueError("Recurring expense not found")
        due = self._normalize_optional_iso_date(due_date)
        paid = self._normalize_optional_iso_date(payment_date)
        if not due or not paid or not self._recurring_payment_due(recurring, due):
            raise ValueError("Payment must reference a valid scheduled installment")
        today = date.today().isoformat()
        if due > today or paid > today:
            raise ValueError("Future installments cannot be marked paid")
        cents = _cents(amount)
        if cents <= 0:
            raise ValueError("Payment amount must be greater than zero")
        # A bill already posted to Billy's cash ledger must not be posted twice.
        if not isinstance(already_recorded, bool):
            raise ValueError("Invalid recorded-payment reconciliation flag")
        skip_posting = already_recorded
        selected_account = str(account_id or "").strip() or None
        if skip_posting:
            selected_account = None
        elif self.accounts:
            selected_account = selected_account or (
                None if allow_unassigned else self.default_account_id
            )
            account = self.account(selected_account) if selected_account else None
            if account is None and not (allow_unassigned and selected_account is None):
                raise ValueError("Select an existing account for the payment")
            if account is not None and paid < account["opening_date"]:
                raise ValueError("Payment predates the account's opening balance")
        elif selected_account:
            raise ValueError("Payment references a missing account")
        return {
            "id": f"{recurring_id}@{due}",
            "recurring_id": str(recurring_id),
            "due_date": due,
            "payment_date": paid,
            "amount": _value(cents),
            "account_id": selected_account,
            "already_recorded": skip_posting,
            "note": self._normalize_optional_text(note, 500),
        }

    async def async_record_recurring_payment(
        self,
        *,
        recurring_id: str,
        due_date: str,
        payment_date: str,
        amount: float,
        account_id: str | None = None,
        note: str = "",
        already_recorded: bool = False,
    ) -> dict[str, Any]:
        """Record or correct one actual payment; scheduled charges stay separate."""
        record = self._normalize_recurring_payment(
            recurring_id=recurring_id,
            due_date=due_date,
            payment_date=payment_date,
            amount=amount,
            account_id=account_id,
            note=note,
            already_recorded=already_recorded,
        )
        existing = next(
            (item for item in self.recurring_payments if item["id"] == record["id"]), None
        )
        now = datetime.now().astimezone().isoformat(timespec="seconds")
        if existing:
            if all(existing.get(key) == value for key, value in record.items()):
                return dict(existing)
            existing.update(record)
            existing["updated_at"] = now
            saved = existing
        else:
            saved = {**record, "created_at": now}
            self.recurring_payments.append(saved)
        self._sort()
        await self._save_and_notify()
        return dict(saved)

    async def async_delete_recurring_payment(self, *, recurring_id: str, due_date: str) -> bool:
        """Undo a provider payment, without touching payer reimbursements."""
        payment_id = f"{recurring_id}@{due_date}"
        previous_count = len(self.recurring_payments)
        self.recurring_payments = [
            item for item in self.recurring_payments if item.get("id") != payment_id
        ]
        if len(self.recurring_payments) == previous_count:
            return False
        await self._save_and_notify()
        return True

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
                "exclude_from_estimates": False,
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
                item["is_placeholder"] = parse_csv_bool(row.get("is_placeholder", "")) and not paid
                if item["is_placeholder"]:
                    self.expenses.append(item)
                else:
                    self._store_real_expense(item)
                existing_ids.add(item["id"])
                if incoming_id:
                    existing_ids.add(incoming_id)
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
                "houses": deepcopy(self.houses),
                "default_house_id": self.default_house_id,
                "settlements": deepcopy(self.settlements),
                "recurring_expenses": deepcopy(self.recurring_expenses),
                "recurring_occurrences": deepcopy(self.recurring_occurrences),
                "recurring_payments": deepcopy(self.recurring_payments),
                "income_categories": deepcopy(self.income_categories),
                "incomes": deepcopy(self.incomes),
                "income_rules": deepcopy(self.income_rules),
                "accounts": deepcopy(self.accounts),
                "default_account_id": self.default_account_id,
                "internal_transfers": deepcopy(self.internal_transfers),
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
            "houses",
            "payers",
            "expenses",
            "settlements",
            "recurring_expenses",
            "recurring_occurrences",
            "recurring_payments",
            "income_categories",
            "incomes",
            "income_rules",
            "accounts",
            "internal_transfers",
        )
        for key in keys:
            if not isinstance(data.get(key, []), list):
                raise billy_error("backup_invalid_section", key=key)
        if len(data.get("expenses", [])) > 50_000:
            raise billy_error("backup_too_many_bills")
        if len(data.get("recurring_expenses", [])) > 10_000:
            raise billy_error("backup_too_many_recurring")
        if len(data.get("recurring_payments", [])) > 50_000:
            raise ValueError("Backup contains too many recurring payments")
        if len(data.get("incomes", [])) > 50_000 or len(data.get("income_rules", [])) > 10_000:
            raise ValueError("Backup contains too many income records")
        if len(data.get("internal_transfers", [])) > 50_000:
            raise ValueError("Backup contains too many internal transfers")
        if len(data.get("accounts", [])) > 200:
            raise ValueError("Backup contains too many accounts")
        if len(data.get("houses", [])) > 50:
            raise ValueError("Backup contains too many houses")
        if not isinstance(data.get("accounts_config", {}), dict):
            raise ValueError("Backup contains an invalid accounts configuration")

        previous = {key: deepcopy(getattr(self, key)) for key in keys}
        previous_accounts_config = deepcopy(self.accounts_config)
        previous_default_account_id = self.default_account_id
        previous_default_house_id = self.default_house_id
        try:
            for key in keys:
                # Validate shape before installing imported objects. Malformed
                # data is rejected without mutating the current installation.
                values = data.get(key, [])
                if not all(isinstance(item, dict) for item in values):
                    raise ValueError(f"Invalid backup section: {key}")
                setattr(self, key, [dict(item) for item in values])
            self.accounts_config = dict(data.get("accounts_config") or {})
            self.default_account_id = str(data.get("default_account_id") or "") or None
            self.default_house_id = str(data.get("default_house_id") or "") or None
            self._migrate_houses()
            self._normalize_payers()
            if not self.categories:
                self.categories = deepcopy(DEFAULT_CATEGORIES)
            self._normalize_categories()
            self._migrate_expenses()
            self._migrate_settlements()
            self._migrate_recurring_expenses()
            self._migrate_recurring_occurrences()
            self._migrate_income()
            self._migrate_accounts()
            self._migrate_recurring_payments()
            self._sync_income_occurrences()
            self._sync_recurring_occurrences()
            self._sync_bill_placeholders()
            self._sort()
            await self._save_and_notify()
        except Exception:
            for key, value in previous.items():
                setattr(self, key, value)
            self.accounts_config = previous_accounts_config
            self.default_account_id = previous_default_account_id
            self.default_house_id = previous_default_house_id
            raise

        return {
            "categories": len(self.categories),
            "payers": len(self.payers),
            "expenses": len(self.expenses),
            "settlements": len(self.settlements),
            "recurring_expenses": len(self.recurring_expenses),
            "recurring_occurrences": len(self.recurring_occurrences),
            "recurring_payments": len(self.recurring_payments),
            "houses": len(self.houses),
            "income_categories": len(self.income_categories),
            "incomes": len(self.incomes),
            "income_rules": len(self.income_rules),
            "internal_transfers": len(self.internal_transfers),
            "accounts": len(self.accounts),
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
        line_items: list[dict[str, Any]] | None = None,
        note: str = "",
    ) -> dict[str, Any]:
        """Record one reimbursement between payers.

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
        available_items = {
            (str(item.get("kind") or ""), str(item.get("id") or "")): item
            for item in debt.get("items", [])
            if item.get("kind") and item.get("id")
        }
        selected_items: list[dict[str, Any]]
        if line_items:
            selected_items = []
            seen: set[tuple[str, str]] = set()
            for raw in line_items:
                key = (str(raw.get("kind") or ""), str(raw.get("id") or ""))
                item = available_items.get(key)
                if item is None or key in seen:
                    raise billy_error("settlement_invalid_selection")
                seen.add(key)
                selected_items.append(dict(item))
            selected_amount = round(
                sum(float(item.get("amount", 0.0) or 0.0) for item in selected_items),
                2,
            )
            if selected_amount <= 0 or abs(float(amount) - selected_amount) > 0.01:
                raise billy_error("settlement_invalid_selection")
        else:
            if abs(float(amount) - outstanding) > 0.01:
                raise billy_error("settlement_partial_unsupported")
            selected_items = [dict(item) for item in debt.get("items", [])]

        expense_ids = [
            str(item["id"]) for item in selected_items if item.get("kind") == "expense"
        ]
        recurring_occurrence_ids = [
            str(item["id"])
            for item in selected_items
            if item.get("kind") == "recurring"
        ]
        if not expense_ids and not recurring_occurrence_ids:
            raise billy_error("settlement_no_expense")

        item = {
            "id": uuid4().hex,
            "from_payer_id": from_payer_id,
            "to_payer_id": to_payer_id,
            "amount": round(float(amount), 2),
            "expense_ids": expense_ids,
            "recurring_occurrence_ids": recurring_occurrence_ids,
                "line_items": [
                    {
                        "kind": str(row.get("kind") or ""),
                        "id": str(row.get("id") or ""),
                        "amount": round(float(row.get("amount", 0.0) or 0.0), 2),
                        "house_id": self._resolve_house_id(row.get("house_id")),
                    }
                    for row in selected_items
                ],
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
        obligations: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)

        # Every split bill creates a reimbursement obligation towards the payer
        # who advanced the provider bill. Whether that provider bill is paid is
        # a separate state and therefore intentionally not checked here.
        for item in self.expenses:
            if item.get("is_placeholder", False):
                continue
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
                    category = (
                        self.category(str(item.get("category_id") or ""))
                        if hasattr(self, "category")
                        else None
                    )
                    obligations[key].append(
                        {
                            "kind": "expense",
                            "id": item_id,
                            **({"house_id": item.get("house_id") or getattr(self, "default_house_id", None)}
                               if item.get("house_id") or getattr(self, "default_house_id", None) else {}),
                            "amount": share,
                            "label": str(
                                item.get("provider")
                                or (category.get("name") if category else "")
                                or "Bill"
                            ),
                            "date": str(
                                item.get("due_date")
                                or item.get("payment_date")
                                or ""
                            ),
                        }
                    )

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
                    recurring = (
                        self.recurring_expense(str(item.get("recurring_id") or ""))
                        if hasattr(self, "recurring_expense")
                        else None
                    )
                    obligations[key].append(
                        {
                            "kind": "recurring",
                            "id": occurrence_id,
                            **({"house_id": (recurring or {}).get("house_id") or getattr(self, "default_house_id", None)}
                               if (recurring or {}).get("house_id") or getattr(self, "default_house_id", None) else {}),
                            "amount": share,
                            "label": str(
                                (recurring or {}).get("name")
                                or item.get("name")
                                or "Recurring expense"
                            ),
                            "date": str(item.get("due_date") or ""),
                        }
                    )

        # Recorded reimbursements reduce only the participant-to-participant
        # balance. They never mutate ``expense.paid``.
        settled: dict[tuple[str, str], float] = defaultdict(float)
        for item in self.settlements:
            source = str(item.get("from_payer_id") or "")
            target = str(item.get("to_payer_id") or "")
            amount = float(item.get("amount", 0.0) or 0.0)
            if source and target and source != target and amount > 0:
                key = (source, target)
                settled[key] += amount
                recorded_items = [
                    (
                        str(row.get("kind") or ""),
                        str(row.get("id") or ""),
                        float(row.get("amount", 0.0) or 0.0),
                    )
                    for row in item.get("line_items", [])
                    if row.get("kind") and row.get("id")
                ]
                if recorded_items:
                    by_key = {
                        (str(row.get("kind") or ""), str(row.get("id") or "")): row
                        for row in obligations.get(key, [])
                    }
                    for kind, item_id, recorded_amount in recorded_items:
                        obligation = by_key.get((kind, item_id))
                        if obligation is None:
                            continue
                        applied = min(
                            max(0.0, recorded_amount),
                            max(0.0, float(obligation.get("amount", 0.0) or 0.0)),
                        )
                        obligation["amount"] = max(
                            0.0,
                            float(obligation.get("amount", 0.0) or 0.0) - applied,
                        )

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
                current_key = (from_id, to_id)
                detail_rows: list[dict[str, Any]] = []
                remaining_value = value
                for obligation in obligations.get(current_key, []):
                    if remaining_value <= 0.009:
                        break
                    obligation_amount = max(
                        0.0, float(obligation.get("amount", 0.0) or 0.0)
                    )
                    if obligation_amount <= 0.009:
                        continue
                    applied = min(obligation_amount, remaining_value)
                    detail_rows.append(
                        {
                            **obligation,
                            "amount": round(applied, 2),
                        }
                    )
                    remaining_value -= applied
                detail_expense_ids = [
                    str(row["id"])
                    for row in detail_rows
                    if row.get("kind") == "expense"
                ]
                detail_recurring_ids = [
                    str(row["id"])
                    for row in detail_rows
                    if row.get("kind") == "recurring"
                ]
                result.append(
                    {
                        "from_payer_id": from_id,
                        "from_name": str(source.get("name", "")),
                        "to_payer_id": to_id,
                        "to_name": str(target.get("name", "")),
                        "amount": round(value, 2),
                        "expense_ids": detail_expense_ids,
                        "expense_count": len(detail_expense_ids),
                        "recurring_occurrence_ids": detail_recurring_ids,
                        "recurring_count": len(detail_recurring_ids),
                        "item_count": len(detail_rows),
                        "items": detail_rows,
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
    def snapshot(self, forecast_months: int = 12, house_id: str | None = None) -> dict[str, Any]:
        forecast_months = max(1, min(int(forecast_months), 24))
        if house_id is not None:
            selected = self._resolve_house_id(house_id)
            # A shallow manager copy avoids changing the active workspace or
            # applying a global house filter across concurrent WebSocket calls.
            self._sync_recurring_occurrences()
            self._sync_income_occurrences()
            view = copy(self)
            view.expenses = [dict(x) for x in self.expenses if x.get("house_id") == selected]
            view.recurring_expenses = [
                dict(x) for x in self.recurring_expenses if x.get("house_id") == selected
            ]
            recurring_ids = {row["id"] for row in view.recurring_expenses}
            view.recurring_occurrences = [
                dict(x) for x in self.recurring_occurrences if x.get("recurring_id") in recurring_ids
            ]
            view.recurring_payments = [
                dict(x) for x in self.recurring_payments if x.get("recurring_id") in recurring_ids
            ]
            expense_ids = {row["id"] for row in view.expenses}
            view.settlements = [
                dict(row) for row in self.settlements
                if all(item_id in expense_ids for item_id in row.get("expense_ids", []))
                and all(item_id.split("@", 1)[0] in recurring_ids
                        for item_id in row.get("recurring_occurrence_ids", []))
                and bool(row.get("expense_ids") or row.get("recurring_occurrence_ids"))
            ]
            # Income belongs to the household, not automatically to a house.
            # Do not show global income as house-specific revenue.
            view.incomes = []
            view.income_rules = []
            result = view.snapshot(forecast_months)
            result["house_id"] = selected
            result["account_balances"] = self.account_balances()
            return result
        self._sync_recurring_occurrences()
        self._sync_income_occurrences()
        today = date.today()
        return {
            "schema_version": STORAGE_SCHEMA_VERSION,
            "currency": self.currency,
            "houses": [dict(x) for x in self.houses],
            "default_house_id": self.default_house_id,
            "categories": [dict(x) for x in self.categories],
            "active_categories": [dict(x) for x in self.categories if x.get("enabled", True)],
            "payers": [dict(x) for x in self.payers],
            "active_payers": self.active_payers(),
            "default_split": self.default_split(),
            "expenses": [self._public_expense(x) for x in self.expenses],
            "current_month_unpaid_bills": self.current_month_unpaid_bills(),
            "settlements": [self._public_settlement(x) for x in self.settlements],
            "recurring_expenses": [self._public_recurring_expense(x) for x in self.recurring_expenses],
            "recurring_occurrences": [
                self._public_recurring_occurrence(x) for x in self.recurring_occurrences
            ],
            "recurring_payments": [dict(x) for x in self.recurring_payments],
            "income_categories": [dict(x) for x in self.income_categories],
            "incomes": [dict(x) for x in self.incomes if not x.get("voided")],
            "income_rules": [dict(x) for x in self.income_rules],
            "income_monthly": self.income_monthly_totals(),
            "income_forecast": self.income_forecast_monthly_totals(forecast_months),
            "income_summary": self.income_summary(),
            "account_balances": self.account_balances(),
            "accounts": [dict(account) for account in self.accounts],
            "default_account_id": self.default_account_id,
            "internal_transfers": [dict(item) for item in self.internal_transfers],
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
                        "amount": self._recurring_due_amount(recurring, due),
                        "due_date": due.isoformat(),
                    }
                )
        items.sort(key=lambda x: (str(x.get("due_date", "")), str(x.get("name", "")).casefold()))
        return items

    def recurring_history_items(self) -> list[dict[str, Any]]:
        """Expose scheduled installments separately from confirmed cash movements."""
        today = date.today()
        window_end = date(today.year, today.month, monthrange(today.year, today.month)[1])
        items: list[dict[str, Any]] = []
        payments = {
            (str(row.get("recurring_id")), str(row.get("due_date"))): row
            for row in getattr(self, "recurring_payments", [])
        }
        for recurring in self.recurring_expenses:
            start_text = str(recurring.get("start_date") or "")
            if not start_text:
                continue
            try:
                start = date.fromisoformat(start_text)
            except ValueError:
                continue
            if start > window_end:
                continue
            # An inactive rule can still have paid history; inactivity only
            # suppresses future due charges, not an existing cash ledger.
            historical_rule = {**recurring, "active": True}
            for due in self._recurring_occurrences_between(historical_rule, start, window_end):
                payment = payments.get((str(recurring.get("id")), due.isoformat()))
                items.append(
                    {
                        "id": str(recurring.get("id", "")),
                        "name": str(recurring.get("name", "")),
                        "kind": str(recurring.get("kind", "recurring")),
                        "color": self._normalize_color(recurring.get("color"), 0),
                        "amount": self._recurring_due_amount(recurring, due),
                        "due_date": due.isoformat(),
                        "paid": payment is not None,
                        "payment_date": payment.get("payment_date") if payment else None,
                        "actual_amount": payment.get("amount") if payment else None,
                        "account_id": payment.get("account_id") if payment else None,
                        "already_recorded": bool(payment.get("already_recorded")) if payment else False,
                        "payment_note": str(payment.get("note") or "") if payment else "",
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
        """Real cash outflow: paid bills plus confirmed, unlinked recurring payments."""
        bill_rows = {str(row["key"]): row for row in self.monthly_totals()}
        recurring_by_key: dict[str, float] = defaultdict(float)
        for item in getattr(self, "recurring_payments", []):
            if item.get("already_recorded"):
                continue
            try:
                paid = date.fromisoformat(str(item.get("payment_date") or ""))
            except ValueError:
                continue
            key = f"{paid.year:04d}-{paid.month:02d}"
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
            if item.get("is_placeholder", False):
                continue
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
        if not buckets:
            return []
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
            cat_id = str(category["id"])
            history, estimate_history = self._forecast_category_history(category)
            if not history or not estimate_history:
                continue
            estimate = self._estimate_category_amount(estimate_history)
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
                amount = self._recurring_due_amount(recurring, occurrence)
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
            cat_id = str(category["id"])
            _history, estimate_history = self._forecast_category_history(category)
            if estimate_history:
                recurring_bills[cat_id] = self._estimate_category_amount(estimate_history) / max(
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
                next_due = self._next_recurring_due(item, first_day)
                if next_due is None:
                    continue
                recurring_by_kind[str(item.get("kind", "recurring"))] += (
                    self._recurring_due_amount(item, next_due)
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
                        "amount": self._recurring_due_amount(recurring, occurrence),
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
                and not x.get("is_placeholder", False)
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
        total_amount: float | None = None,
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
        if normalized_kind not in ("installment", "mortgage"):
            normalized_installments = None
        if normalized_kind == "installment":
            auto_renew = False
            if normalized_installments:
                end = self._add_months_date(
                    start, (normalized_installments - 1) * normalized_interval
                )
                normalized_end = end.isoformat()
        total_cents: int | None = None
        if total_amount not in (None, ""):
            if normalized_kind not in ("installment", "mortgage") or not normalized_installments:
                raise ValueError("A total repayable amount requires an installment or mortgage plan with a number of payments")
            total_cents = _cents(total_amount)
            regular_cents = _cents(amount)
            if total_cents <= regular_cents * (normalized_installments - 1):
                raise ValueError("Total repayable must exceed the sum of all installments before the last one")
            if normalized_kind == "mortgage":
                auto_renew = False
                end = self._add_months_date(start, (normalized_installments - 1) * normalized_interval)
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
            "total_amount": _value(total_cents) if total_cents is not None else None,
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

    def _recurring_due_amount(self, item: dict[str, Any], due: date) -> float:
        """A fixed-term loan may have a different last installment."""
        count = item.get("installment_count")
        total = item.get("total_amount")
        if count and total is not None:
            last = self._add_months_date(
                date.fromisoformat(str(item["start_date"])),
                (int(count) - 1) * int(item.get("interval_months", 1) or 1),
            )
            if due == last:
                return _value(_cents(total) - (int(count) - 1) * _cents(item["amount"]))
        return round(float(item.get("amount", 0.0) or 0.0), 2)

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
                        "amount": self._recurring_due_amount(recurring, due),
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
                "amount": self._recurring_due_amount(
                    recurring, date.fromisoformat(str(occurrence["due_date"]))
                ),
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
        payments = [
            payment for payment in getattr(self, "recurring_payments", [])
            if payment.get("recurring_id") == item.get("id")
        ]
        paid_cents = sum(_cents(payment["amount"]) for payment in payments)
        total_amount = item.get("total_amount")
        remaining_amount = (
            _value(max(0, _cents(total_amount) - paid_cents))
            if total_amount is not None
            else round(float(item.get("amount", 0.0) or 0.0) * remaining, 2)
            if remaining is not None else None
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
            "paid_amount": _value(paid_cents),
            "paid_installments": len(payments),
            "balance_from_payments": total_amount is not None,
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
        if not item.get("is_placeholder", False) and creditor and self.payer(creditor) is not None:
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
        stored_amounts = {
            (str(row.get("kind") or ""), str(row.get("id") or "")): round(
                float(row.get("amount", 0.0) or 0.0), 2
            )
            for row in item.get("line_items", [])
            if isinstance(row, dict) and row.get("kind") and row.get("id")
        }
        stored_houses = {
            (str(row.get("kind") or ""), str(row.get("id") or "")): row.get("house_id")
            for row in item.get("line_items", [])
            if isinstance(row, dict) and row.get("kind") and row.get("id") and row.get("house_id")
        }
        details: list[dict[str, Any]] = []
        for expense_id in [str(x) for x in item.get("expense_ids", []) if x]:
            expense = next(
                (row for row in self.expenses if str(row.get("id") or "") == expense_id),
                None,
            )
            category = (
                self.category(str(expense.get("category_id") or ""))
                if expense is not None
                else None
            )
            details.append(
                {
                    "kind": "expense",
                    "id": expense_id,
                    "house_id": stored_houses.get(("expense", expense_id))
                    or (expense.get("house_id") if expense is not None else None),
                    "label": (
                        str(expense.get("provider") or "")
                        if expense is not None
                        else ""
                    )
                    or (str(category.get("name") or "") if category else "")
                    or "Bill",
                    "date": (
                        str(expense.get("due_date") or expense.get("payment_date") or "")
                        if expense is not None
                        else ""
                    ),
                    "amount": stored_amounts.get(("expense", expense_id)),
                    "source_amount": (
                        round(float(expense.get("amount", 0.0) or 0.0), 2)
                        if expense is not None
                        else None
                    ),
                    "category": str(category.get("name") or "") if category else "",
                    "provider": (
                        str(expense.get("provider") or "")
                        if expense is not None
                        else ""
                    ),
                    "contract": (
                        str(expense.get("contract") or "")
                        if expense is not None
                        else ""
                    ),
                    "legacy_amount_unknown": ("expense", expense_id) not in stored_amounts,
                }
            )
        for occurrence_id in [
            str(x) for x in item.get("recurring_occurrence_ids", []) if x
        ]:
            occurrence = next(
                (
                    row
                    for row in self.recurring_occurrences
                    if str(row.get("id") or "") == occurrence_id
                ),
                None,
            )
            recurring = (
                self.recurring_expense(str(occurrence.get("recurring_id") or ""))
                if occurrence is not None
                else None
            )
            details.append(
                {
                    "kind": "recurring",
                    "id": occurrence_id,
                    "house_id": stored_houses.get(("recurring", occurrence_id))
                    or (recurring.get("house_id") if recurring is not None else None),
                    "label": (
                        str(occurrence.get("name") or "")
                        if occurrence is not None
                        else ""
                    )
                    or (str(recurring.get("name") or "") if recurring else "")
                    or "Recurring expense",
                    "date": (
                        str(occurrence.get("due_date") or "")
                        if occurrence is not None
                        else ""
                    ),
                    "amount": stored_amounts.get(("recurring", occurrence_id)),
                    "source_amount": (
                        round(float(occurrence.get("amount", 0.0) or 0.0), 2)
                        if occurrence is not None
                        else None
                    ),
                    "category": "",
                    "provider": (
                        str(recurring.get("provider") or "") if recurring else ""
                    ),
                    "contract": (
                        str(recurring.get("contract") or "") if recurring else ""
                    ),
                    "legacy_amount_unknown": (
                        ("recurring", occurrence_id) not in stored_amounts
                    ),
                }
            )
        return {
            **dict(item),
            "from_name": str(source.get("name")) if source else "Pagante rimosso",
            "to_name": str(target.get("name")) if target else "Pagante rimosso",
            "expense_count": expense_count,
            "recurring_count": recurring_count,
            "item_count": expense_count + recurring_count,
            "status": "done",
            "items": details,
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

    def _forecast_category_history(
        self, category: dict[str, Any]
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """Return cadence history and amount-estimation history for a bill type."""
        if not category.get("enabled", True) or bool(
            category.get("exclude_from_estimates", False)
        ):
            return [], []
        category_id = str(category.get("id", ""))
        history = sorted(
            [x for x in self.expenses if str(x.get("category_id", "")) == category_id],
            key=lambda x: (int(x["paid_year"]), int(x["paid_month"])),
        )
        estimate_history = [
            item for item in history if not bool(item.get("exclude_from_estimates", False))
            and not item.get("is_placeholder", False)
        ]
        return history, estimate_history

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
                "exclude_from_estimates": bool(raw.get("exclude_from_estimates", False)),
                "default_payer_id": default_payer,
                "color": self._normalize_color(raw.get("color"), index),
                "consumption_unit": self._normalize_consumption_unit(
                    raw.get("consumption_unit") or self._default_consumption_unit(category_id, name)
                ),
                "default_provider": self._normalize_optional_text(raw.get("default_provider", ""), 100),
                "default_contract": self._normalize_optional_text(raw.get("default_contract", ""), 100),
            }
            try:
                item["document_archive"] = normalize_archive_config(raw.get("document_archive"))
            except ValueError:
                item["document_archive"] = normalize_archive_config(None)
                changed = True
            try:
                item["placeholder"] = self._normalize_placeholder_config(item, raw.get("placeholder"))
            except ValueError:
                item["placeholder"] = self._normalize_placeholder_config(item, None)
            if "house_placeholders" in raw:
                item["house_placeholders"] = self._normalize_house_placeholders(
                    raw, raw["house_placeholders"], interval_months=interval
                )
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
                    "enabled": True, "exclude_from_estimates": False, "default_payer_id": None,
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
                "house_id": self._resolve_house_id(item.get("house_id")),
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
                "is_placeholder": bool(item.get("is_placeholder", False)) and not bool(item.get("paid", False)),
                "exclude_from_estimates": bool(item.get("exclude_from_estimates", False)),
                "payment_date": payment_date,
                "due_date": due_date,
                "provider": self._normalize_optional_text(item.get("provider", ""), 100),
                "contract": self._normalize_optional_text(item.get("contract", item.get("plan", "")), 100),
                "consumption": consumption,
                "consumption_unit": self._normalize_consumption_unit(
                    item.get("consumption_unit") or category.get("consumption_unit", "")
                ),
                "note": str(item.get("note", "")).strip(),
                "account_id": str(item.get("account_id") or "") or None,
                "document_url": "",
                "document_path": None,
                "document_sha256": None,
                "document_error": None,
                "created_at": str(item.get("created_at") or datetime.now().astimezone().isoformat(timespec="seconds")),
            }
            try:
                new_item["document_url"] = self._normalize_document_url(item.get("document_url"))
            except ValueError:
                changed = True
            # The internal archive path is generated by Billy, never accepted
            # directly from a WebSocket client.
            for field in ("document_path", "document_sha256", "document_error"):
                if item.get(field):
                    new_item[field] = str(item[field])
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
            for line in raw.get("line_items", []):
                if isinstance(line, dict) and line.get("house_id") and self.house(str(line["house_id"])) is None:
                    raise ValueError("Reimbursement refers to a house that does not exist")
            item = {
                "id": str(raw.get("id") or uuid4().hex),
                "from_payer_id": source, "to_payer_id": target,
                "amount": round(amount, 2),
                "expense_ids": [str(x) for x in raw.get("expense_ids", []) if x],
                "recurring_occurrence_ids": [
                    str(x) for x in raw.get("recurring_occurrence_ids", []) if x
                ],
                "line_items": [
                    {
                        "kind": str(x.get("kind") or ""),
                        "id": str(x.get("id") or ""),
                        "amount": round(float(x.get("amount", 0.0) or 0.0), 2),
                        **({"house_id": str(x["house_id"])}
                           if x.get("house_id") else {}),
                    }
                    for x in raw.get("line_items", [])
                    if isinstance(x, dict)
                    and x.get("kind")
                    and x.get("id")
                    and isfinite(float(x.get("amount", 0.0) or 0.0))
                    and float(x.get("amount", 0.0) or 0.0) > 0
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
                    total_amount=raw.get("total_amount"),
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
                "house_id": self._resolve_house_id(raw.get("house_id")),
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

    def _migrate_recurring_payments(self) -> bool:
        """Validate confirmed payments before using them in account balances."""
        original = self.recurring_payments
        migrated: list[dict[str, Any]] = []
        seen: set[str] = set()
        for raw in original:
            normalized = self._normalize_recurring_payment(
                recurring_id=str(raw.get("recurring_id") or ""),
                due_date=str(raw.get("due_date") or ""),
                payment_date=str(raw.get("payment_date") or ""),
                amount=raw.get("amount"),
                account_id=raw.get("account_id"),
                already_recorded=raw.get("already_recorded", False),
                note=str(raw.get("note") or ""),
                allow_unassigned=True,
            )
            if normalized["id"] in seen:
                raise ValueError("Duplicate recurring payment in storage or backup")
            seen.add(normalized["id"])
            normalized["created_at"] = str(
                raw.get("created_at")
                or datetime.now().astimezone().isoformat(timespec="seconds")
            )
            if raw.get("updated_at"):
                normalized["updated_at"] = str(raw["updated_at"])
            migrated.append(normalized)
        changed = migrated != original
        self.recurring_payments = migrated
        return changed

    async def _save_and_notify(self) -> None:
        await self._save()
        self.hass.bus.async_fire(EVENT_UPDATED)

    @staticmethod
    def _normalize_document_url(value: str | None) -> str:
        url = str(value or "").strip()
        if not url:
            return ""
        parts = urlsplit(url)
        if (
            len(url) > 2048 or parts.scheme not in {"http", "https"}
            or not parts.hostname or parts.username or parts.password
        ):
            raise ValueError("Document URL must be an HTTP(S) address without credentials")
        return url

    def _queue_document_archive(self, bill: dict[str, Any]) -> None:
        """Archive in the background only for an explicitly opted-in category."""
        if not bill.get("document_url") or bill.get("document_path"):
            return
        category = self.category(str(bill.get("category_id") or ""))
        if not category:
            return
        config = normalize_archive_config(category.get("document_archive"))
        if config["enabled"] and config["source_host"]:
            self.hass.async_create_task(self._archive_document_safely(str(bill["id"])))

    async def _archive_document_safely(self, expense_id: str) -> None:
        try:
            await self.async_archive_document(expense_id)
        except Exception as err:  # noqa: BLE001
            self._logger.warning("Billy could not archive document for %s: %s", expense_id, err)

    async def async_archive_document(self, expense_id: str) -> dict[str, Any]:
        bill = next((x for x in self.expenses if x["id"] == expense_id), None)
        if bill is None:
            raise ValueError("Bill not found")
        category = self.category(str(bill.get("category_id") or ""))
        if category is None:
            raise ValueError("Bill category not found")
        source_url = str(bill.get("document_url") or "")
        try:
            relative_path, checksum = await archive_pdf(self.hass, dict(bill), dict(category))
        except Exception as err:
            if str(bill.get("document_url") or "") == source_url:
                bill["document_error"] = str(err)[:200]
                await self._save_and_notify()
            raise
        if str(bill.get("document_url") or "") != source_url or bill not in self.expenses:
            # The bill was edited/deleted while the fetch was in progress.
            raise ValueError("Document URL changed during archiving")
        bill["document_path"] = relative_path
        bill["document_sha256"] = checksum
        bill["document_error"] = None
        await self._save_and_notify()
        return self._public_expense(bill)

    async def async_read_document(self, expense_id: str) -> dict[str, str]:
        bill = next((x for x in self.expenses if x["id"] == expense_id), None)
        if not bill or not bill.get("document_path"):
            raise ValueError("Archived document not found")
        content = await read_pdf(self.hass, str(bill["document_path"]))
        return {
            "content_base64": base64.b64encode(content).decode("ascii"),
            "filename": f"billy-{expense_id}.pdf",
            "mime_type": "application/pdf",
        }

    async def async_receive_document_chunk(
        self, user_id: str, expense_id: str, upload_id: str,
        index: int, total_chunks: int, total_size: int, chunk: bytes,
    ) -> dict[str, Any]:
        """Receive bounded ordered chunks rather than a giant WebSocket message."""
        if not any(row["id"] == expense_id for row in self.expenses):
            raise ValueError("Bill not found")
        if not (1 <= total_chunks <= 128 and 0 <= index < total_chunks):
            raise ValueError("Invalid document chunk index")
        if not (5 <= total_size <= MAX_PDF_BYTES and 0 < len(chunk) <= 256 * 1024):
            raise ValueError("Document upload exceeds limits")
        now = monotonic()
        for key, current in tuple(self._document_uploads.items()):
            if now - current["started"] > 600:
                self._document_uploads.pop(key, None)
        key = (user_id, upload_id)
        if index == 0:
            if key in self._document_uploads:
                raise ValueError("Upload already started")
            # A failed/disconnected attempt must not block a fresh retry.
            for previous_key, previous in tuple(self._document_uploads.items()):
                if previous_key[0] == user_id and previous["expense_id"] == expense_id:
                    self._document_uploads.pop(previous_key, None)
            if len(self._document_uploads) >= 4:
                raise ValueError("Too many concurrent document uploads")
            self._document_uploads[key] = {
                "expense_id": expense_id, "total_chunks": total_chunks,
                "total_size": total_size, "started": now,
                "next_index": 0, "payload": bytearray(),
            }
        current = self._document_uploads.get(key)
        if (
            current is None or current["expense_id"] != expense_id
            or current["total_chunks"] != total_chunks
            or current["total_size"] != total_size
            or current["next_index"] != index
        ):
            self._document_uploads.pop(key, None)
            raise ValueError("Out-of-order document upload")
        payload = current["payload"]
        payload.extend(chunk)
        if len(payload) > total_size:
            self._document_uploads.pop(key, None)
            raise ValueError("Document upload is larger than declared")
        current["next_index"] += 1
        if index < total_chunks - 1:
            return {"complete": False, "received": len(payload)}
        self._document_uploads.pop(key, None)
        if len(payload) != total_size:
            raise ValueError("Incomplete document upload")
        bill = await self.async_upload_document(expense_id, bytes(payload))
        return {"complete": True, "bill": bill}

    async def async_upload_document(self, expense_id: str, content: bytes) -> dict[str, Any]:
        """Manually attach/replace a PDF, even when auto-archiving is disabled."""
        bill = next((row for row in self.expenses if row["id"] == expense_id), None)
        if bill is None:
            raise ValueError("Bill not found")
        category = self.category(str(bill.get("category_id") or ""))
        if category is None:
            raise ValueError("Bill category not found")
        if len(content) > MAX_PDF_BYTES or not content.startswith(b"%PDF-"):
            raise ValueError("Only PDF documents up to 8 MiB can be uploaded")
        old_path = str(bill.get("document_path") or "")
        if old_path:
            validate_owned_pdf_path(self.hass, old_path, expense_id)
        path, checksum = await archive_pdf_bytes(
            self.hass, dict(bill), dict(category), content, manual=True
        )
        if bill not in self.expenses:
            await delete_archived_pdf(self.hass, path, expense_id)
            raise ValueError("Bill was removed during upload")
        previous = {key: bill.get(key) for key in (
            "document_path", "document_sha256", "document_error", "document_url"
        )}
        bill.update({
            "document_path": path, "document_sha256": checksum,
            "document_error": None, "document_url": "",
        })
        try:
            await self._save_and_notify()
        except Exception:
            bill.update(previous)
            if path != old_path:
                await delete_archived_pdf(self.hass, path, expense_id)
            raise
        if old_path and old_path != path and not any(
            other is not bill and other.get("document_path") == old_path
            for other in self.expenses
        ):
            try:
                await delete_archived_pdf(self.hass, old_path, expense_id)
            except OSError as err:
                self._logger.warning("Could not remove replaced PDF for %s: %s", expense_id, err)
                return {**self._public_expense(bill), "document_cleanup_error": True}
        return self._public_expense(bill)

    async def async_delete_document(self, expense_id: str) -> dict[str, Any]:
        """Remove a bill's PDF association and its owned archived file."""
        bill = next((row for row in self.expenses if row["id"] == expense_id), None)
        if bill is None:
            raise ValueError("Bill not found")
        old_path = str(bill.get("document_path") or "")
        if not old_path and not bill.get("document_url"):
            raise ValueError("Bill has no document")
        if old_path:
            # Validate ownership before clearing metadata, to avoid an
            # irreversible partial deletion on a malformed imported path.
            validate_owned_pdf_path(self.hass, old_path, expense_id)
        previous = {key: bill.get(key) for key in (
            "document_path", "document_sha256", "document_error", "document_url"
        )}
        bill.update({
            "document_path": None, "document_sha256": None,
            "document_error": None, "document_url": "",
        })
        try:
            await self._save_and_notify()
        except Exception:
            bill.update(previous)
            raise
        if old_path and not any(
            other.get("document_path") == old_path for other in self.expenses
        ):
            try:
                await delete_archived_pdf(self.hass, old_path, expense_id)
            except OSError as err:
                self._logger.warning("Could not remove archived PDF for %s: %s", expense_id, err)
                return {**self._public_expense(bill), "document_cleanup_error": True}
        return self._public_expense(bill)

    async def async_archive_attachment(self, expense_id: str, content: bytes) -> dict[str, Any]:
        """Persist a PDF supplied by the existing IMAP parser for an imported bill."""
        bill = next((x for x in self.expenses if x["id"] == expense_id), None)
        if not bill:
            raise ValueError("Bill not found")
        category = self.category(str(bill.get("category_id") or ""))
        if not category:
            raise ValueError("Bill category not found")
        path, checksum = await archive_pdf_bytes(self.hass, dict(bill), dict(category), content)
        if bill not in self.expenses:
            raise ValueError("Bill was removed during archiving")
        bill["document_path"] = path
        bill["document_sha256"] = checksum
        bill["document_error"] = None
        await self._save_and_notify()
        return self._public_expense(bill)

    async def _save(self) -> None:
        await self._store.async_save(
            {
                "schema_version": STORAGE_SCHEMA_VERSION,
                "categories": self.categories,
                "houses": self.houses,
                "default_house_id": self.default_house_id,
                "payers": self.payers,
                "expenses": self.expenses,
                "settlements": self.settlements,
                "recurring_expenses": self.recurring_expenses,
                "recurring_occurrences": self.recurring_occurrences,
                "recurring_payments": self.recurring_payments,
                "income_categories": self.income_categories,
                "incomes": self.incomes,
                "income_rules": self.income_rules,
                "accounts": self.accounts,
                "default_account_id": self.default_account_id,
                "internal_transfers": self.internal_transfers,
            }
        )

    def _sort(self) -> None:
        self.expenses.sort(key=lambda x: (int(x.get("paid_year", 0)), int(x.get("paid_month", 0)), str(x.get("created_at", ""))), reverse=True)
        self.settlements.sort(key=lambda x: str(x.get("created_at", "")), reverse=True)
        self.recurring_expenses.sort(key=lambda x: (not bool(x.get("active", True)), str(x.get("name", "")).casefold()))
        self.recurring_occurrences.sort(key=lambda x: (str(x.get("due_date", "")), str(x.get("id", ""))), reverse=True)
        if hasattr(self, "recurring_payments"):
            self.recurring_payments.sort(
                key=lambda x: (str(x.get("payment_date", "")), str(x.get("due_date", ""))), reverse=True
            )
        if hasattr(self, "incomes"):
            self.incomes.sort(key=lambda x: (str(x.get("expected_date", "")), str(x.get("created_at", ""))), reverse=True)
        if hasattr(self, "income_rules"):
            self.income_rules.sort(key=lambda x: str(x.get("name", "")).casefold())

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
