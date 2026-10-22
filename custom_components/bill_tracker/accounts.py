"""Manual N-account cash ledger, without banking integrations.

Accounts are user-defined; each keeps a dated opening balance. Transfers move
exact cents between two distinct accounts and never affect income or spending.
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from uuid import uuid4

_MAX_AMOUNT = Decimal("1000000000")
MAX_ACCOUNTS = 200


def _cents(value, *, signed=False) -> int:
    """Use integer cents so transfers never create or destroy rounding cents."""
    try:
        decimal = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as err:
        raise ValueError("Invalid account amount") from err
    if not decimal.is_finite() or abs(decimal) > _MAX_AMOUNT:
        raise ValueError("Account amount must be finite and within limits")
    if not signed and decimal < 0:
        raise ValueError("Amount must be nonnegative")
    normalized = decimal.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    if normalized != decimal:
        raise ValueError("Account amounts support at most two decimal places")
    return int(normalized * 100)


def _value(cents: int) -> float:
    return round(cents / 100, 2)


def _date(value, *, required=True) -> str | None:
    if not value and not required:
        return None
    try:
        parsed = date.fromisoformat(str(value))
    except ValueError as err:
        raise ValueError("Invalid account date") from err
    if not (2000 <= parsed.year <= 2200):
        raise ValueError("Account date outside supported range")
    return parsed.isoformat()


def _account(*, name, account_type, opening_balance, opening_date, payer_id) -> dict:
    title = str(name or "").strip()
    kind = str(account_type or "other").strip()
    if not title or len(title) > 90:
        raise ValueError("Account name must be between 1 and 90 characters")
    if not kind or len(kind) > 50:
        raise ValueError("Account type must be between 1 and 50 characters")
    starting = _date(opening_date)
    if starting > date.today().isoformat():
        raise ValueError("Opening date cannot be in the future")
    return {
        "name": title,
        "payer_id": str(payer_id or "").strip(),
        "account_type": kind,
        "opening_date": starting,
        "opening_balance": _value(_cents(opening_balance, signed=True)),
    }


def _transfer(*, from_account, to_account, amount, transfer_date, note="") -> dict:
    source, target = str(from_account or ""), str(to_account or "")
    if not source or not target or source == target:
        raise ValueError("A transfer needs two distinct accounts")
    cents = _cents(amount)
    if cents <= 0:
        raise ValueError("Transfer amount must be greater than zero")
    return {
        "from_account": source,
        "to_account": target,
        "amount": _value(cents),
        "transfer_date": _date(transfer_date),
        "note": str(note or "").strip()[:500],
    }


class AccountMixin:
    """Persistence remains owned by BillTrackerManager's Home Assistant Store."""

    def account(self, account_id: str) -> dict | None:
        return next((row for row in self.accounts if row["id"] == account_id), None)

    def _validate_account_payer(self, payer_id: str) -> str:
        selected = str(payer_id or "").strip()
        if not selected or not any(row.get("id") == selected for row in self.payers):
            raise ValueError("Account requires an existing payer")
        return selected

    def _legacy_account_payer(self) -> str:
        if self.payers:
            return self.payers[0]["id"]
        # Existing account data must remain usable without inventing balances.
        # Create one identifiable owner only when legacy accounts are orphaned.
        payer = {
            "id": uuid4().hex, "name": "Legacy account owner",
            "share_percent": 0.0, "payment_methods": {},
            "preferred_payment_method": "", "paypal_me": "", "enabled": True,
        }
        self.payers.append(payer)
        return payer["id"]

    def _resolve_account_id(self, account_id=None) -> str | None:
        """Assign unlinked transactions to the current default exactly once."""
        selected = str(account_id or "") or self.default_account_id
        if selected and self.account(selected) is None:
            raise ValueError("Account does not exist")
        return selected

    def _assign_legacy_account_ids(self) -> bool:
        changed = False
        valid = {item["id"] for item in self.accounts}
        for row in (*self.expenses, *self.incomes):
            selected = str(row.get("account_id") or "") or None
            if selected and selected not in valid:
                raise ValueError("A transaction refers to a missing account")
            if not selected and self.default_account_id:
                row["account_id"] = self.default_account_id
                changed = True
        for row in getattr(self, "income_rules", []):
            selected = str(row.get("account_id") or "") or None
            if selected and selected not in valid:
                raise ValueError("An income rule refers to a missing account")
            if not selected and self.default_account_id:
                row["account_id"] = self.default_account_id
                changed = True
        return changed

    def _migrate_accounts(self) -> bool:
        changed = False
        # The unreleased two-account prototype had a single opening date.
        # Preserve its IDs and historical transfers when upgrading.
        legacy = self.accounts_config if isinstance(self.accounts_config, dict) else {}
        if not self.accounts and legacy.get("opening_date"):
            legacy_payer_id = self._legacy_account_payer()
            for account_id, name, kind in (
                ("checking", "Checking", "checking"),
                ("savings", "Savings", "savings"),
            ):
                item = _account(
                    name=name, account_type=kind,
                    opening_balance=legacy.get(f"{account_id}_opening_balance", 0),
                    opening_date=legacy["opening_date"],
                    payer_id=legacy_payer_id,
                )
                self.accounts.append({"id": account_id, **item})
            self.default_account_id = self.default_account_id or "checking"
            changed = True
        if legacy:
            self.accounts_config = {}
            changed = True
        if len(self.accounts) > MAX_ACCOUNTS:
            raise ValueError("Too many accounts")
        normalized_accounts = []
        orphan_payer_id = None
        account_ids = set()
        names = set()
        for raw in self.accounts:
            if not isinstance(raw, dict):
                raise ValueError("Malformed account")
            account_id = str(raw.get("id") or "")
            if not account_id or len(account_id) > 90 or account_id in account_ids:
                raise ValueError("Invalid or duplicate account ID")
            payer_id = str(raw.get("payer_id") or "").strip()
            if not payer_id:
                if orphan_payer_id is None:
                    orphan_payer_id = self._legacy_account_payer()
                payer_id = orphan_payer_id
            payer_id = self._validate_account_payer(payer_id)
            payload = _account(
                name=raw.get("name"), account_type=raw.get("account_type"),
                opening_balance=raw.get("opening_balance", 0),
                opening_date=raw.get("opening_date"),
                payer_id=payer_id,
            )
            if payload["name"].casefold() in names:
                raise ValueError("Account names must be unique")
            names.add(payload["name"].casefold())
            account_ids.add(account_id)
            item = {"id": account_id, **payload}
            normalized_accounts.append(item)
            changed |= item != raw
        self.accounts = normalized_accounts
        if not self.default_account_id and self.accounts:
            self.default_account_id = self.accounts[0]["id"]
            changed = True
        if self.default_account_id and self.default_account_id not in account_ids:
            raise ValueError("Default account no longer exists")
        if not self.accounts and self.default_account_id:
            self.default_account_id = None
            changed = True
        valid_transfers = []
        seen = set()
        for raw in self.internal_transfers:
            if not isinstance(raw, dict):
                raise ValueError("Malformed internal transfer")
            record = _transfer(
                from_account=raw.get("from_account"), to_account=raw.get("to_account"),
                amount=raw.get("amount"), transfer_date=raw.get("transfer_date"),
                note=raw.get("note", ""),
            )
            record["id"] = str(raw.get("id") or uuid4().hex)
            record["created_at"] = str(raw.get("created_at") or "")
            if record["id"] in seen:
                raise ValueError("Duplicate transfer ID")
            self._validate_transfer_accounts(record)
            seen.add(record["id"])
            valid_transfers.append(record)
            changed |= record != raw
        self.internal_transfers = valid_transfers
        self.internal_transfers.sort(
            key=lambda row: (row["transfer_date"], row["created_at"]), reverse=True
        )
        changed |= self._assign_legacy_account_ids()
        return changed

    def _validate_transfer_accounts(self, record: dict) -> None:
        source = self.account(record["from_account"])
        target = self.account(record["to_account"])
        if source is None or target is None:
            raise ValueError("Transfer references a missing account")
        if record["transfer_date"] < max(source["opening_date"], target["opening_date"]):
            raise ValueError("Transfer predates an account's opening balance")

    async def async_add_account(
        self, *, name: str, account_type: str, opening_balance: float,
        opening_date: str, payer_id: str, make_default=False,
    ) -> dict:
        if len(self.accounts) >= MAX_ACCOUNTS:
            raise ValueError("Maximum number of accounts reached")
        item = _account(
            name=name, account_type=account_type,
            opening_balance=opening_balance, opening_date=opening_date,
            payer_id=self._validate_account_payer(payer_id),
        )
        if any(row["name"].casefold() == item["name"].casefold() for row in self.accounts):
            raise ValueError("Account name already exists")
        item["id"] = uuid4().hex
        self.accounts.append(item)
        if len(self.accounts) == 1 or make_default:
            self.default_account_id = item["id"]
        self._assign_legacy_account_ids()
        await self._save_and_notify()
        return dict(item)

    async def async_update_account(
        self, account_id: str, *, name: str, account_type: str,
        opening_balance: float, opening_date: str, payer_id: str, make_default=False,
    ) -> dict | None:
        account = self.account(account_id)
        if account is None:
            return None
        changes = _account(
            name=name, account_type=account_type, opening_balance=opening_balance,
            opening_date=opening_date, payer_id=self._validate_account_payer(payer_id),
        )
        if any(
            row["id"] != account_id and
            row["name"].casefold() == changes["name"].casefold()
            for row in self.accounts
        ):
            raise ValueError("Account name already exists")
        if any(
            row["transfer_date"] < changes["opening_date"]
            for row in self.internal_transfers
            if account_id in (row["from_account"], row["to_account"])
        ):
            raise ValueError("New opening date would exclude existing transfers")
        if changes["opening_date"] > account["opening_date"]:
            # Moving the opening snapshot past posted money flows would hide
            # those flows without changing their records.
            for item in self.incomes:
                if (item.get("account_id") == account_id and item.get("received")
                        and not item.get("voided")
                        and account["opening_date"] <= str(item.get("received_date") or "") < changes["opening_date"]):
                    raise ValueError("New opening date would exclude recorded income")
            for item in self.expenses:
                if (item.get("account_id") == account_id and item.get("paid")
                        and not item.get("is_placeholder")):
                    paid_on = self._bill_cash_date(item)
                    if paid_on and account["opening_date"] <= paid_on < changes["opening_date"]:
                        raise ValueError("New opening date would exclude paid bills")
            for payment in getattr(self, "recurring_payments", []):
                if (payment.get("account_id") == account_id
                    and account["opening_date"] <= str(payment.get("payment_date") or "") < changes["opening_date"]):
                    raise ValueError("New opening date would exclude recorded recurring payments")
        account.update(changes)
        if make_default:
            self.default_account_id = account_id
        await self._save_and_notify()
        return dict(account)

    async def async_set_default_account(self, account_id: str) -> dict:
        if not self.account(account_id):
            raise ValueError("Account not found")
        self.default_account_id = account_id
        await self._save_and_notify()
        return {"default_account_id": account_id}

    async def async_delete_account(self, account_id: str) -> bool:
        account = self.account(account_id)
        if not account:
            return False
        if any(account_id in (row["from_account"], row["to_account"]) for row in self.internal_transfers):
            raise ValueError("Account has internal transfer history")
        if any(str(row.get("account_id") or "") == account_id for row in (*self.expenses, *self.incomes, *self.income_rules)):
            raise ValueError("Account has linked bills or income")
        if any(row.get("account_id") == account_id for row in getattr(self, "recurring_payments", [])):
            raise ValueError("Account has recorded recurring payments")
        self.accounts = [row for row in self.accounts if row["id"] != account_id]
        if self.default_account_id == account_id:
            self.default_account_id = self.accounts[0]["id"] if self.accounts else None
        await self._save_and_notify()
        return True

    async def async_add_internal_transfer(
        self, *, from_account: str, to_account: str, amount: float,
        transfer_date: str, note: str = "",
    ) -> dict:
        record = _transfer(
            from_account=from_account, to_account=to_account,
            amount=amount, transfer_date=transfer_date, note=note,
        )
        self._validate_transfer_accounts(record)
        if record["transfer_date"] > date.today().isoformat():
            raise ValueError("Future transfers must be recorded when completed")
        record["id"] = uuid4().hex
        record["created_at"] = datetime.now().astimezone().isoformat(timespec="seconds")
        self.internal_transfers.append(record)
        self.internal_transfers.sort(key=lambda row: (row["transfer_date"], row["created_at"]), reverse=True)
        await self._save_and_notify()
        return dict(record)

    async def async_update_internal_transfer(
        self, transfer_id: str, *, from_account: str, to_account: str, amount: float,
        transfer_date: str, note: str = "",
    ) -> dict | None:
        current = next((row for row in self.internal_transfers if row["id"] == transfer_id), None)
        if current is None:
            return None
        updated = _transfer(
            from_account=from_account, to_account=to_account,
            amount=amount, transfer_date=transfer_date, note=note,
        )
        self._validate_transfer_accounts(updated)
        if updated["transfer_date"] > date.today().isoformat():
            raise ValueError("Future transfers must be recorded when completed")
        current.update(updated)
        self.internal_transfers.sort(key=lambda row: (row["transfer_date"], row["created_at"]), reverse=True)
        await self._save_and_notify()
        return dict(current)

    async def async_delete_internal_transfer(self, transfer_id: str) -> bool:
        original = len(self.internal_transfers)
        self.internal_transfers = [
            row for row in self.internal_transfers if row["id"] != transfer_id
        ]
        if len(self.internal_transfers) == original:
            return False
        await self._save_and_notify()
        return True

    @staticmethod
    def _bill_cash_date(bill: dict) -> str | None:
        explicit = str(bill.get("payment_date") or "")
        if explicit:
            try:
                return _date(explicit)
            except ValueError:
                return None
        # Legacy paid bills may lack a date. Attribute them to the beginning
        # of their recorded payment month rather than pretending to know a day.
        try:
            return date(int(bill["paid_year"]), int(bill["paid_month"]), 1).isoformat()
        except (ValueError, TypeError, KeyError):
            return None

    def account_balances(self, as_of: date | None = None) -> dict:
        as_of = as_of or date.today()
        result = {
            "configured": bool(self.accounts),
            "default_account_id": self.default_account_id,
            "as_of": as_of.isoformat(),
            "accounts": [],
            "total": None,
        }
        if not self.accounts:
            return result
        end = as_of.isoformat()
        buckets = {
            row["id"]: {"income": 0, "expenses": 0, "transfers_in": 0, "transfers_out": 0}
            for row in self.accounts
        }
        opening_dates = {row["id"]: row["opening_date"] for row in self.accounts}
        for row in self.incomes:
            if not row.get("received") or row.get("voided"):
                continue
            received_date = str(row.get("received_date") or "")
            account_id = row.get("account_id") or self.default_account_id
            if (
                account_id in buckets and opening_dates[account_id] <= received_date <= end
                and row.get("actual_amount") is not None
            ):
                buckets[account_id]["income"] += _cents(row["actual_amount"])
        for row in self.expenses:
            if not row.get("paid") or row.get("is_placeholder"):
                continue
            paid_on = self._bill_cash_date(row)
            account_id = row.get("account_id") or self.default_account_id
            if (
                paid_on and account_id in buckets
                and opening_dates[account_id] <= paid_on <= end
            ):
                buckets[account_id]["expenses"] += _cents(row.get("amount", 0))
        for payment in getattr(self, "recurring_payments", []):
            if payment.get("already_recorded"):
                continue
            paid_on = str(payment.get("payment_date") or "")
            account_id = payment.get("account_id")
            if (
                account_id in buckets and opening_dates[account_id] <= paid_on <= end
            ):
                buckets[account_id]["expenses"] += _cents(payment.get("amount", 0))
        for row in self.internal_transfers:
            if row["transfer_date"] > end:
                continue
            amount = _cents(row["amount"])
            # Only completed transfers involving two valid, opened accounts
            # are ever saved; both legs are posted in the same operation.
            buckets[row["from_account"]]["transfers_out"] += amount
            buckets[row["to_account"]]["transfers_in"] += amount
        total_cents = 0
        for account in self.accounts:
            amounts = buckets[account["id"]]
            start_cents = _cents(account["opening_balance"], signed=True)
            is_open = account["opening_date"] <= end
            current = (
                start_cents + amounts["income"] - amounts["expenses"]
                + amounts["transfers_in"] - amounts["transfers_out"]
            ) if is_open else None
            if current is not None:
                total_cents += current
            result["accounts"].append({
                **dict(account),
                "is_default": account["id"] == self.default_account_id,
                "income": _value(amounts["income"]),
                "expenses": _value(amounts["expenses"]),
                "transfers_in": _value(amounts["transfers_in"]),
                "transfers_out": _value(amounts["transfers_out"]),
                "balance": _value(current) if current is not None else None,
            })
        result["total"] = _value(total_cents)
        return result
