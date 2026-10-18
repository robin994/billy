"""Manual income tracking with independent recurring occurrences.

This module deliberately has no banking APIs. A recurrence generates an
estimate; only an explicitly confirmed receipt is treated as actual income.
"""
from __future__ import annotations

from calendar import monthrange
from collections import defaultdict
from datetime import date, datetime
from math import isfinite
from statistics import mean
from uuid import uuid4


DEFAULT_INCOME_CATEGORIES = (
    ("salary", "Salary", "#198C83"),
    ("pension", "Pension", "#508DA8"),
    ("rent", "Rental income", "#B08D57"),
    ("bonus", "Bonus", "#8E71C4"),
    ("refund", "External refund", "#C38B45"),
    ("other", "Other income", "#6B8394"),
)
INCOME_MODES = ("fixed", "last", "average3", "average6", "average12")
INCOME_INTERVALS = (1, 2, 3, 4, 6, 12)


def _money(value):
    try:
        amount = float(value)
    except (ValueError, TypeError, OverflowError) as err:
        raise ValueError("Invalid income amount") from err
    if not isfinite(amount) or amount < 0 or amount > 1_000_000_000:
        raise ValueError("Income amounts must be finite and nonnegative")
    return round(amount, 2)


def _iso_date(value, *, required=False):
    if not value:
        if required:
            raise ValueError("An income date is required")
        return None
    try:
        parsed = date.fromisoformat(str(value))
    except ValueError as err:
        raise ValueError("Invalid income date") from err
    if not (2000 <= parsed.year <= 2200):
        raise ValueError("Income date out of range")
    return parsed.isoformat()


def _add_months(anchor, months):
    """Preserve the start day for month-end salaries (31 -> 28 -> 31)."""
    month_index = anchor.year * 12 + anchor.month - 1 + months
    year, zero_based_month = divmod(month_index, 12)
    month = zero_based_month + 1
    day = min(anchor.day, monthrange(year, month)[1])
    return date(year, month, day)


class IncomeMixin:
    """Methods mixed into BillTrackerManager; persistence stays in its Store."""

    def _income_category(self, category_id):
        return next((row for row in self.income_categories if row["id"] == category_id), None)

    def _migrate_income(self):
        changed = False
        if not self.income_categories:
            self.income_categories = [
                {"id": key, "name": name, "color": color}
                for key, name, color in DEFAULT_INCOME_CATEGORIES
            ]
            changed = True
        seen = set()
        categories = []
        for raw in self.income_categories:
            if not isinstance(raw, dict):
                changed = True
                continue
            key = str(raw.get("id") or uuid4().hex)
            name = str(raw.get("name") or "").strip()[:80]
            if not name or key in seen:
                changed = True
                continue
            color = str(raw.get("color") or "#6B8394")
            if not (len(color) == 7 and color[0] == "#" and all(c in "0123456789abcdefABCDEF" for c in color[1:])):
                color = "#6B8394"
            row = {"id": key, "name": name, "color": color}
            categories.append(row)
            seen.add(key)
            changed |= row != raw
        self.income_categories = categories

        recurring = []
        seen_rules = set()
        for raw in self.income_rules:
            try:
                if not isinstance(raw, dict):
                    raise ValueError("Invalid recurring income")
                row = self._income_rule_payload(**{
                    "name": raw.get("name"), "category_id": raw.get("category_id"),
                    "estimated_amount": raw.get("estimated_amount", 0),
                    "interval_months": raw.get("interval_months", 1),
                    "start_date": raw.get("start_date"), "end_date": raw.get("end_date"),
                    "amount_mode": raw.get("amount_mode", "fixed"),
                    "active": raw.get("active", True), "note": raw.get("note", ""),
                    "account_id": raw.get("account_id"),
                })
                row["id"] = str(raw.get("id") or uuid4().hex)
                if row["id"] in seen_rules:
                    raise ValueError("Duplicate rule")
                row["created_at"] = str(raw.get("created_at") or "")
                seen_rules.add(row["id"])
                recurring.append(row)
                changed |= row != raw
            except (ValueError, TypeError):
                changed = True
        self.income_rules = recurring

        incomes = []
        seen_incomes = set()
        for raw in self.incomes:
            try:
                if not isinstance(raw, dict):
                    raise ValueError("Invalid income")
                row = self._income_payload(
                    description=raw.get("description"),
                    category_id=raw.get("category_id"),
                    expected_date=raw.get("expected_date"),
                    estimated_amount=raw.get("estimated_amount", 0),
                    received=raw.get("received", False),
                    actual_amount=raw.get("actual_amount"),
                    received_date=raw.get("received_date"),
                    note=raw.get("note", ""),
                    account_id=raw.get("account_id"),
                )
                row["id"] = str(raw.get("id") or uuid4().hex)
                if row["id"] in seen_incomes:
                    raise ValueError("Duplicate income")
                row["rule_id"] = str(raw.get("rule_id") or "") or None
                row["estimated_manually_set"] = bool(raw.get("estimated_manually_set", False))
                row["account_manually_set"] = bool(raw.get("account_manually_set", False))
                row["voided"] = bool(raw.get("voided", False))
                row["created_at"] = str(raw.get("created_at") or "")
                seen_incomes.add(row["id"])
                incomes.append(row)
                changed |= row != raw
            except (ValueError, TypeError):
                changed = True
        self.incomes = incomes
        return changed

    def _income_payload(
        self, *, description, category_id, expected_date, estimated_amount,
        received=False, actual_amount=None, received_date=None, note="", account_id=None,
    ):
        name = str(description or "").strip()[:120]
        if not name:
            raise ValueError("Income description is required")
        if not self._income_category(str(category_id or "")):
            raise ValueError("Income category not found")
        expected = _iso_date(expected_date, required=True)
        confirmed = bool(received)
        actual = _money(actual_amount) if actual_amount is not None else None
        if confirmed and actual is None:
            actual = _money(estimated_amount)
        recorded_date = _iso_date(received_date)
        if confirmed and recorded_date is None:
            recorded_date = date.today().isoformat()
        if not confirmed:
            recorded_date = None
        return {
            "description": name,
            "category_id": str(category_id),
            "expected_date": expected,
            "estimated_amount": _money(estimated_amount),
            "received": confirmed,
            "actual_amount": actual,
            "received_date": recorded_date,
            "note": str(note or "").strip()[:1000],
            "account_id": str(account_id or "") or None,
        }

    def _income_rule_payload(
        self, *, name, category_id, estimated_amount, interval_months, start_date,
        end_date=None, amount_mode="fixed", active=True, note="", account_id=None,
    ):
        title = str(name or "").strip()[:120]
        if not title or not self._income_category(str(category_id or "")):
            raise ValueError("Valid recurring income name and category required")
        interval = int(interval_months)
        if interval not in INCOME_INTERVALS:
            raise ValueError("Unsupported recurring income interval")
        mode = str(amount_mode)
        if mode not in INCOME_MODES:
            raise ValueError("Unsupported income estimation mode")
        start = _iso_date(start_date, required=True)
        end = _iso_date(end_date)
        if end and end < start:
            raise ValueError("End date must not precede start date")
        return {
            "name": title,
            "category_id": str(category_id),
            "estimated_amount": _money(estimated_amount),
            "interval_months": interval,
            "start_date": start,
            "end_date": end,
            "amount_mode": mode,
            "active": bool(active),
            "note": str(note or "").strip()[:1000],
            "account_id": str(account_id or "") or None,
        }

    async def async_add_income_category(self, *, name, color="#6B8394"):
        name = str(name or "").strip()[:80]
        if not name:
            raise ValueError("Income category name is required")
        if any(row["name"].casefold() == name.casefold() for row in self.income_categories):
            raise ValueError("Income category name already exists")
        color = str(color or "")
        if not (len(color) == 7 and color[0] == "#" and all(c in "0123456789abcdefABCDEF" for c in color[1:])):
            raise ValueError("Invalid income category color")
        row = {"id": uuid4().hex, "name": name, "color": color}
        self.income_categories.append(row)
        await self._save_and_notify()
        return dict(row)

    async def async_update_income_category(self, category_id, *, name, color="#6B8394"):
        row = self._income_category(category_id)
        if row is None:
            return None
        name = str(name or "").strip()[:80]
        if not name:
            raise ValueError("Income category name is required")
        if any(item["id"] != category_id and item["name"].casefold() == name.casefold() for item in self.income_categories):
            raise ValueError("Income category name already exists")
        color = str(color or "")
        if not (len(color) == 7 and color[0] == "#" and all(c in "0123456789abcdefABCDEF" for c in color[1:])):
            raise ValueError("Invalid income category color")
        row.update(name=name, color=color)
        await self._save_and_notify()
        return dict(row)

    async def async_delete_income_category(self, category_id):
        if any(row["category_id"] == category_id for row in (*self.incomes, *self.income_rules)):
            raise ValueError("Income category has recorded history")
        original = len(self.income_categories)
        self.income_categories = [row for row in self.income_categories if row["id"] != category_id]
        if len(self.income_categories) == original:
            return False
        await self._save_and_notify()
        return True

    async def async_add_income(self, **kwargs):
        if hasattr(self, "_resolve_account_id"):
            kwargs["account_id"] = self._resolve_account_id(kwargs.get("account_id"))
        row = self._income_payload(**kwargs)
        row.update(id=uuid4().hex, rule_id=None, estimated_manually_set=False,
                   account_manually_set=False,
                   voided=False, created_at=datetime.now().astimezone().isoformat(timespec="seconds"))
        self.incomes.append(row)
        self._sort()
        await self._save_and_notify()
        return dict(row)

    async def async_update_income(self, income_id, **kwargs):
        row = next((item for item in self.incomes if item["id"] == income_id and not item.get("voided")), None)
        if row is None:
            return None
        chosen_account = kwargs.get("account_id") or row.get("account_id")
        if hasattr(self, "_resolve_account_id"):
            chosen_account = self._resolve_account_id(chosen_account)
        kwargs["account_id"] = chosen_account
        changes = self._income_payload(**kwargs)
        if row.get("rule_id") and changes["expected_date"] != row["expected_date"]:
            raise ValueError("Change the receipt date, not the recurring schedule date")
        if changes["estimated_amount"] != row["estimated_amount"] and row.get("rule_id"):
            row["estimated_manually_set"] = True
        if changes["account_id"] != row.get("account_id") and row.get("rule_id"):
            row["account_manually_set"] = True
        row.update(changes)
        # Recalculate only unconfirmed, unmodified forecasts after a salary
        # is confirmed or corrected; previous receipts remain untouched.
        if row.get("rule_id"):
            self._sync_income_occurrences()
        await self._save_and_notify()
        return dict(row)

    async def async_delete_income(self, income_id):
        row = next((item for item in self.incomes if item["id"] == income_id), None)
        if row is None:
            return False
        if row.get("rule_id"):
            # Tombstone prevents a deleted recurring occurrence from being recreated.
            row["voided"] = True
        else:
            self.incomes.remove(row)
        await self._save_and_notify()
        return True

    async def async_add_income_rule(self, **kwargs):
        if hasattr(self, "_resolve_account_id"):
            kwargs["account_id"] = self._resolve_account_id(kwargs.get("account_id"))
        row = self._income_rule_payload(**kwargs)
        row.update(id=uuid4().hex, created_at=datetime.now().astimezone().isoformat(timespec="seconds"))
        self.income_rules.append(row)
        self._sync_income_occurrences()
        self._sort()
        await self._save_and_notify()
        return dict(row)

    async def async_update_income_rule(self, rule_id, **kwargs):
        row = next((item for item in self.income_rules if item["id"] == rule_id), None)
        if row is None:
            return None
        selected = kwargs.get("account_id") or row.get("account_id")
        if hasattr(self, "_resolve_account_id"):
            selected = self._resolve_account_id(selected)
        kwargs["account_id"] = selected
        row.update(self._income_rule_payload(**kwargs))
        # Only unconfirmed and non-overridden predictions may be refreshed.
        self._sync_income_occurrences()
        self._sort()
        await self._save_and_notify()
        return dict(row)

    async def async_delete_income_rule(self, rule_id):
        original = len(self.income_rules)
        self.income_rules = [row for row in self.income_rules if row["id"] != rule_id]
        if len(self.income_rules) == original:
            return False
        # Keep generated receipts/history; they remain editable and visible.
        await self._save_and_notify()
        return True

    def _income_estimate(self, rule, expected):
        mode = str(rule.get("amount_mode") or "fixed")
        if mode == "fixed":
            return _money(rule["estimated_amount"])
        history = sorted(
            (
                item for item in self.incomes
                if item.get("rule_id") == rule["id"]
                and not item.get("voided") and item.get("received")
                and item.get("received_date")
                and item["expected_date"] < expected.isoformat()
            ),
            key=lambda item: item["expected_date"], reverse=True,
        )
        count = 1 if mode == "last" else int(mode.replace("average", ""))
        amounts = [float(row["actual_amount"]) for row in history[:count] if row.get("actual_amount") is not None]
        return round(mean(amounts), 2) if amounts else _money(rule["estimated_amount"])

    def _sync_income_occurrences(self, today=None):
        today = today or date.today()
        month_end = date(today.year, today.month, monthrange(today.year, today.month)[1])
        existing = {
            (row.get("rule_id"), row.get("expected_date")): row
            for row in self.incomes if row.get("rule_id")
        }
        changed = False
        for rule in self.income_rules:
            if not rule.get("active", True):
                continue
            anchor = date.fromisoformat(rule["start_date"])
            if anchor > month_end:
                continue
            for index in range(360):
                expected = _add_months(anchor, index * int(rule["interval_months"]))
                if expected > month_end or (rule.get("end_date") and expected.isoformat() > rule["end_date"]):
                    break
                key = (rule["id"], expected.isoformat())
                if key in existing:
                    row = existing[key]
                    if (
                        not row.get("received") and not row.get("voided")
                        and not row.get("account_manually_set")
                        and row.get("account_id") != rule.get("account_id")
                    ):
                        row["account_id"] = rule.get("account_id")
                        changed = True
                    if (
                        not row.get("received") and not row.get("voided")
                        and not row.get("estimated_manually_set")
                        and rule["amount_mode"] != "fixed"
                    ):
                        estimate = self._income_estimate(rule, expected)
                        if row["estimated_amount"] != estimate:
                            row["estimated_amount"] = estimate
                            changed = True
                    continue
                row = {
                    "id": uuid4().hex,
                    "description": rule["name"],
                    "category_id": rule["category_id"],
                    "expected_date": expected.isoformat(),
                    "estimated_amount": self._income_estimate(rule, expected),
                    "received": False,
                    "actual_amount": None,
                    "received_date": None,
                    "note": rule.get("note", ""),
                    "rule_id": rule["id"],
                    "account_id": rule.get("account_id"),
                    "account_manually_set": False,
                    "estimated_manually_set": False,
                    "voided": False,
                    "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
                }
                self.incomes.append(row)
                existing[key] = row
                changed = True
        if changed:
            self._sort()
        return changed

    async def async_sync_income_occurrences(self):
        if not self._sync_income_occurrences():
            return False
        await self._save_and_notify()
        return True

    def income_monthly_totals(self):
        totals = defaultdict(float)
        for row in self.incomes:
            if row.get("voided") or not row.get("received") or not row.get("received_date"):
                continue
            key = str(row["received_date"])[:7]
            totals[key] += float(row.get("actual_amount") or 0)
        return [
            {"key": key, "year": int(key[:4]), "month": int(key[5:7]), "total": round(amount, 2)}
            for key, amount in sorted(totals.items())
        ]

    def income_forecast_monthly_totals(self, months_ahead=12):
        """Expected-but-unreceived income, including rules not yet materialized."""
        today = date.today()
        first = date(today.year, today.month, 1)
        limit = _add_months(first, max(0, min(int(months_ahead), 36)) + 1)
        totals = defaultdict(float)
        generated = {(r.get("rule_id"), r.get("expected_date")) for r in self.incomes if r.get("rule_id")}
        for row in self.incomes:
            expected = str(row.get("expected_date") or "")
            if not row.get("voided") and not row.get("received") and first.isoformat() <= expected < limit.isoformat():
                totals[expected[:7]] += float(row.get("estimated_amount") or 0)
        for rule in self.income_rules:
            if not rule.get("active", True):
                continue
            anchor = date.fromisoformat(rule["start_date"])
            for index in range(720):
                expected = _add_months(anchor, index * int(rule["interval_months"]))
                if expected >= limit or (rule.get("end_date") and expected.isoformat() > rule["end_date"]):
                    break
                if expected < first or (rule["id"], expected.isoformat()) in generated:
                    continue
                totals[expected.isoformat()[:7]] += self._income_estimate(rule, expected)
        return [
            {"key": key, "year": int(key[:4]), "month": int(key[5:7]), "total": round(amount, 2)}
            for key, amount in sorted(totals.items())
        ]

    def income_summary(self):
        today = date.today()
        prefix = today.strftime("%Y-%m")
        actual = sum(
            float(row.get("actual_amount") or 0)
            for row in self.incomes
            if row.get("received") and not row.get("voided")
            and str(row.get("received_date") or "").startswith(prefix)
        )
        pending = sum(
            float(row.get("estimated_amount") or 0)
            for row in self.incomes
            if not row.get("received") and not row.get("voided")
            and str(row.get("expected_date") or "").startswith(prefix)
        )
        return {
            "month_received": round(actual, 2),
            "month_pending": round(pending, 2),
            "year_received": round(sum(
                float(row.get("actual_amount") or 0)
                for row in self.incomes
                if row.get("received") and not row.get("voided")
                and str(row.get("received_date") or "").startswith(str(today.year))
            ), 2),
        }
