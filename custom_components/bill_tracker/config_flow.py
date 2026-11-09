"""Config and options flows for Bill Tracker."""
from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import (
    DOMAIN,
    PARSER_PROJECT_URL,
    PROJECT_URL,
    SUPPORT_URL,
    SUPPORTED_INTERVALS,
)
from .localization import category_label, config_label, interval_label, normalize_language
from .manager import BillTrackerManager
from .parser.manager import ParserManager

NO_DEFAULT_PAYER = "__none__"


class BillTrackerConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle the initial Bill Tracker setup."""

    VERSION = 1

    async def async_step_user(self, user_input=None):
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()
        if user_input is not None:
            return self.async_create_entry(title="Bill Tracker", data={})
        return self.async_show_form(step_id="user")

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return BillTrackerOptionsFlow()


class BillTrackerOptionsFlow(config_entries.OptionsFlow):
    """Manage bills, payers and automatic parsing from HA settings."""

    def __init__(self) -> None:
        self._category_id: str | None = None
        self._payer_id: str | None = None
        self._parser_id: str | None = None
        self._import_id: str | None = None

    def _manager(self) -> BillTrackerManager | None:
        return self.hass.data.get(DOMAIN, {}).get("manager")

    def _parser_manager(self) -> ParserManager | None:
        return self.hass.data.get(DOMAIN, {}).get("parser_manager")

    def _language(self) -> str:
        return normalize_language(getattr(self.hass.config, "language", "en"))

    def _label(self, key: str) -> str:
        return config_label(self._language(), key)

    def _category_choices(self, manager: BillTrackerManager) -> dict[str, str]:
        return {
            str(item["id"]): (
                category_label(self._language(), item)
                + ("" if item.get("enabled", True) else f" — {self._label('disabled')}")
            )
            for item in manager.categories
        }

    async def async_step_init(self, user_input: dict[str, Any] | None = None):
        if self._manager() is None:
            return self.async_abort(reason="not_setup")
        return self.async_show_menu(
            step_id="init",
            menu_options=[
                "add_payer",
                "manage_payer",
                "add_category",
                "manage_category",
                "automatic_parsing",
                "support",
                "done",
            ],
        )

    # ------------------------------------------------------------------
    # Automatic parsing
    # ------------------------------------------------------------------
    async def async_step_automatic_parsing(self, user_input=None):
        if self._parser_manager() is None:
            return self.async_abort(reason="parser_not_setup")
        return self.async_show_menu(
            step_id="automatic_parsing",
            menu_options=[
                "parser_sources",
                "parser_manager",
                "custom_parser",
                "parser_imports",
                "init",
            ],
        )

    async def async_step_parser_manager(self, user_input=None):
        """Point users to the scalable parser management panel."""
        if self._parser_manager() is None:
            return self.async_abort(reason="parser_not_setup")
        if user_input is not None:
            return await self.async_step_automatic_parsing()
        return self.async_show_form(
            step_id="parser_manager",
            data_schema=vol.Schema({}),
            description_placeholders={"parser_manager_url": "/billy?view=parsers"},
        )

    async def async_step_parser_refresh(self, user_input=None):
        parser_manager = self._parser_manager()
        if parser_manager is None:
            return self.async_abort(reason="parser_not_setup")
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                await parser_manager.async_refresh_catalog()
            except Exception:
                errors["base"] = "parser_catalog_error"
            else:
                return await self.async_step_automatic_parsing()
        return self.async_show_form(
            step_id="parser_refresh",
            data_schema=vol.Schema({}),
            errors=errors,
            description_placeholders={"parser_project_url": PARSER_PROJECT_URL},
        )

    async def async_step_parser_sources(self, user_input: dict[str, Any] | None = None):
        parser_manager = self._parser_manager()
        if parser_manager is None:
            return self.async_abort(reason="parser_not_setup")
        rows = parser_manager.sources_snapshot()
        options = [
            selector.SelectOptionDict(value=row["entry_id"], label=row["title"])
            for row in rows
        ]
        selected = [row["entry_id"] for row in rows if row.get("selected")]
        if user_input is not None:
            await parser_manager.async_set_sources(list(user_input.get("entry_ids") or []))
            return await self.async_step_automatic_parsing()
        if not options:
            return self.async_show_form(
                step_id="parser_sources",
                data_schema=vol.Schema({}),
                description_placeholders={"imap_status": "missing"},
            )
        schema = vol.Schema(
            {
                vol.Optional("entry_ids", default=selected): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=options,
                        multiple=True,
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                )
            }
        )
        return self.async_show_form(
            step_id="parser_sources",
            data_schema=schema,
            description_placeholders={"imap_status": "available"},
        )

    async def async_step_parser_catalog(self, user_input: dict[str, Any] | None = None):
        parser_manager = self._parser_manager()
        if parser_manager is None:
            return self.async_abort(reason="parser_not_setup")
        errors: dict[str, str] = {}
        catalog = parser_manager.catalog_snapshot()
        if not catalog.get("parsers"):
            try:
                catalog = await parser_manager.async_refresh_catalog()
            except Exception:
                errors["base"] = "parser_catalog_error"
        choices: dict[str, str] = {}
        for row in catalog.get("parsers", []) or []:
            suffix = ""
            if row.get("update_available"):
                suffix = " · update"
            elif row.get("installed"):
                suffix = " · installed"
            choices[str(row["id"])] = (
                f"{row.get('name', row['id'])} · {row.get('country', '')}{suffix}"
            )
        if user_input is not None:
            self._parser_id = str(user_input["parser_id"])
            return await self.async_step_parser_install()
        return self.async_show_form(
            step_id="parser_catalog",
            data_schema=vol.Schema(
                {vol.Required("parser_id"): vol.In(choices)} if choices else {}
            ),
            errors=errors,
        )

    async def async_step_parser_install(self, user_input: dict[str, Any] | None = None):
        parser_manager = self._parser_manager()
        manager = self._manager()
        if parser_manager is None or manager is None:
            return self.async_abort(reason="parser_not_setup")
        parser_id = self._parser_id or ""
        item = next(
            (
                row
                for row in parser_manager.catalog_snapshot().get("parsers", [])
                if str(row.get("id")) == parser_id
            ),
            None,
        )
        if item is None:
            return self.async_abort(reason="parser_not_found")
        errors: dict[str, str] = {}
        current = next(
            (row for row in parser_manager.installed_snapshot() if row.get("id") == parser_id),
            {},
        )
        categories = self._category_choices(manager)
        default_category = str(
            current.get("category_id")
            or item.get("bill_type")
            or next(iter(categories), "")
        )
        if default_category not in categories:
            default_category = next(iter(categories), "")
        if user_input is not None:
            try:
                await parser_manager.async_install(
                    parser_id,
                    category_id=str(user_input["category_id"]),
                    enabled=bool(user_input["enabled"]),
                    auto_import=bool(user_input["auto_import"]),
                )
            except Exception:
                errors["base"] = "parser_install_error"
            else:
                self._parser_id = None
                return await self.async_step_automatic_parsing()
        return self.async_show_form(
            step_id="parser_install",
            data_schema=vol.Schema(
                {
                    vol.Required("category_id", default=default_category): vol.In(categories),
                    vol.Required("enabled", default=True): bool,
                    vol.Required("auto_import", default=False): bool,
                }
            ),
            errors=errors,
            description_placeholders={
                "name": str(item.get("name") or parser_id),
                "provider": str(item.get("provider") or ""),
            },
        )

    async def async_step_manage_parser(self, user_input: dict[str, Any] | None = None):
        parser_manager = self._parser_manager()
        if parser_manager is None:
            return self.async_abort(reason="parser_not_setup")
        rows = parser_manager.installed_snapshot()
        if not rows:
            return await self.async_step_parser_catalog()
        choices = {
            str(row["id"]): (
                f"{row.get('name', row['id'])} · "
                f"{'custom' if row.get('source') == 'custom' else 'official'}"
            )
            for row in rows
        }
        if user_input is not None:
            self._parser_id = str(user_input["parser_id"])
            action = str(user_input["action"])
            if action == "delete":
                return await self.async_step_delete_parser()
            if action == "export":
                return await self.async_step_export_parser()
            return await self.async_step_edit_parser()
        return self.async_show_form(
            step_id="manage_parser",
            data_schema=vol.Schema(
                {
                    vol.Required("parser_id"): vol.In(choices),
                    vol.Required("action", default="edit"): vol.In(
                        {
                            "edit": "Edit",
                            "delete": "Delete",
                            "export": "Export custom YAML",
                        }
                    ),
                }
            ),
        )

    async def async_step_edit_parser(self, user_input: dict[str, Any] | None = None):
        parser_manager = self._parser_manager()
        manager = self._manager()
        if parser_manager is None or manager is None:
            return self.async_abort(reason="parser_not_setup")
        row = next(
            (
                item
                for item in parser_manager.installed_snapshot()
                if item.get("id") == self._parser_id
            ),
            None,
        )
        if row is None:
            return self.async_abort(reason="parser_not_found")
        categories = self._category_choices(manager)
        if user_input is not None:
            await parser_manager.async_configure(
                str(row["id"]),
                category_id=str(user_input["category_id"]),
                enabled=bool(user_input["enabled"]),
                auto_import=bool(user_input["auto_import"]),
            )
            self._parser_id = None
            return await self.async_step_automatic_parsing()
        return self.async_show_form(
            step_id="edit_parser",
            data_schema=vol.Schema(
                {
                    vol.Required("category_id", default=str(row["category_id"])): vol.In(categories),
                    vol.Required("enabled", default=bool(row.get("enabled", True))): bool,
                    vol.Required("auto_import", default=bool(row.get("auto_import", False))): bool,
                }
            ),
            description_placeholders={"name": str(row.get("name") or row["id"])},
        )

    async def async_step_delete_parser(self, user_input: dict[str, Any] | None = None):
        parser_manager = self._parser_manager()
        if parser_manager is None:
            return self.async_abort(reason="parser_not_setup")
        row = next(
            (
                item
                for item in parser_manager.installed_snapshot()
                if item.get("id") == self._parser_id
            ),
            None,
        )
        if row is None:
            return self.async_abort(reason="parser_not_found")
        if user_input is not None:
            if row.get("source") == "custom":
                await parser_manager.async_delete_custom(str(row["id"]))
            else:
                await parser_manager.async_uninstall(str(row["id"]))
            self._parser_id = None
            return await self.async_step_automatic_parsing()
        return self.async_show_form(
            step_id="delete_parser",
            data_schema=vol.Schema({}),
            description_placeholders={"name": str(row.get("name") or row["id"])},
        )

    async def async_step_export_parser(self, user_input: dict[str, Any] | None = None):
        parser_manager = self._parser_manager()
        if parser_manager is None:
            return self.async_abort(reason="parser_not_setup")
        row = next(
            (
                item
                for item in parser_manager.installed_snapshot()
                if item.get("id") == self._parser_id
            ),
            None,
        )
        if row is None or row.get("source") != "custom":
            return self.async_abort(reason="custom_parser_not_found")
        await parser_manager.async_export_custom(str(row["id"]))
        if user_input is not None:
            self._parser_id = None
            return await self.async_step_automatic_parsing()
        return self.async_show_form(
            step_id="export_parser",
            data_schema=vol.Schema({}),
            description_placeholders={
                "name": str(row.get("name") or row["id"]),
                "download_url": f"/api/bill_tracker/parser/custom/{row['id']}",
            },
        )

    async def async_step_custom_parser(self, user_input: dict[str, Any] | None = None):
        parser_manager = self._parser_manager()
        manager = self._manager()
        if parser_manager is None or manager is None:
            return self.async_abort(reason="parser_not_setup")
        categories = self._category_choices(manager)
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                await parser_manager.async_save_custom(
                    str(user_input["content"]),
                    category_id=str(user_input["category_id"]),
                    enabled=bool(user_input["enabled"]),
                    auto_import=bool(user_input["auto_import"]),
                )
            except Exception:
                errors["base"] = "custom_parser_error"
            else:
                return await self.async_step_automatic_parsing()
        yaml_selector = selector.TextSelector(
            selector.TextSelectorConfig(multiline=True, type=selector.TextSelectorType.TEXT)
        )
        return self.async_show_form(
            step_id="custom_parser",
            data_schema=vol.Schema(
                {
                    vol.Required("content", default=""): yaml_selector,
                    vol.Required("category_id", default=next(iter(categories), "")): vol.In(categories),
                    vol.Required("enabled", default=True): bool,
                    vol.Required("auto_import", default=False): bool,
                }
            ),
            errors=errors,
        )

    async def async_step_parser_imports(self, user_input: dict[str, Any] | None = None):
        parser_manager = self._parser_manager()
        if parser_manager is None:
            return self.async_abort(reason="parser_not_setup")
        pending = parser_manager.imports_snapshot("pending", 100)
        if not pending:
            return self.async_show_form(step_id="parser_imports", data_schema=vol.Schema({}))
        choices: dict[str, str] = {}
        for row in pending:
            data = row.get("data", {})
            choices[str(row["id"])] = (
                f"{data.get('provider') or row.get('parser_id')} · "
                f"{data.get('amount', '?')} {data.get('currency', '')} · "
                f"{data.get('due_date', '')}"
            )
        if user_input is not None:
            import_id = str(user_input["import_id"])
            if user_input["action"] == "approve":
                await parser_manager.async_approve(import_id)
            else:
                await parser_manager.async_reject(import_id)
            return await self.async_step_parser_imports()
        return self.async_show_form(
            step_id="parser_imports",
            data_schema=vol.Schema(
                {
                    vol.Required("import_id"): vol.In(choices),
                    vol.Required("action", default="approve"): vol.In(
                        {"approve": "Import", "reject": "Ignore"}
                    ),
                }
            ),
        )

    # ------------------------------------------------------------------
    # Payers
    # ------------------------------------------------------------------
    async def async_step_add_payer(self, user_input: dict[str, Any] | None = None):
        manager = self._manager()
        if manager is None:
            return self.async_abort(reason="not_setup")
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                await manager.async_add_payer(
                    name=user_input["name"],
                    share_percent=float(user_input["share_percent"]),
                    paypal_me=user_input.get("paypal_me", ""),
                    payment_methods={
                        "paypal": user_input.get("paypal_me", ""),
                        "revolut": user_input.get("revolut", ""),
                        "venmo": user_input.get("venmo", ""),
                        "cashapp": user_input.get("cashapp", ""),
                    },
                    preferred_payment_method=user_input.get(
                        "preferred_payment_method", ""
                    ),
                    enabled=bool(user_input["enabled"]),
                )
            except ValueError:
                errors["base"] = "invalid_payer"
            else:
                return await self.async_step_init()
        return self.async_show_form(
            step_id="add_payer",
            data_schema=vol.Schema(
                {
                    vol.Required("name"): str,
                    vol.Required("share_percent", default=50.0): vol.All(
                        vol.Coerce(float), vol.Range(min=0, max=100)
                    ),
                    vol.Optional("paypal_me", default=""): str,
                    vol.Optional("revolut", default=""): str,
                    vol.Optional("venmo", default=""): str,
                    vol.Optional("cashapp", default=""): str,
                    vol.Optional("preferred_payment_method", default="paypal"): str,
                    vol.Required("enabled", default=True): bool,
                }
            ),
            errors=errors,
        )

    async def async_step_manage_payer(self, user_input: dict[str, Any] | None = None):
        manager = self._manager()
        if manager is None:
            return self.async_abort(reason="not_setup")
        if not manager.payers:
            return await self.async_step_add_payer()
        if user_input is not None:
            self._payer_id = str(user_input["payer_id"])
            if user_input["action"] == "delete":
                return await self.async_step_delete_payer()
            return await self.async_step_edit_payer()
        payers = {
            str(item["id"]): (
                f"{item['name']} — {self._label('share')} {float(item.get('share_percent', 0)):g}%"
                + ("" if item.get("enabled", True) else f" — {self._label('disabled')}")
            )
            for item in manager.payers
        }
        return self.async_show_form(
            step_id="manage_payer",
            data_schema=vol.Schema(
                {
                    vol.Required("payer_id"): vol.In(payers),
                    vol.Required("action", default="edit"): vol.In(
                        {"edit": self._label("edit"), "delete": self._label("delete")}
                    ),
                }
            ),
        )

    async def async_step_edit_payer(self, user_input: dict[str, Any] | None = None):
        manager = self._manager()
        if manager is None:
            return self.async_abort(reason="not_setup")
        item = manager.payer(self._payer_id or "")
        if item is None:
            return self.async_abort(reason="payer_not_found")
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                await manager.async_update_payer(
                    str(item["id"]),
                    name=user_input["name"],
                    share_percent=float(user_input["share_percent"]),
                    paypal_me=user_input.get("paypal_me", ""),
                    payment_methods={
                        "paypal": user_input.get("paypal_me", ""),
                        "revolut": user_input.get("revolut", ""),
                        "venmo": user_input.get("venmo", ""),
                        "cashapp": user_input.get("cashapp", ""),
                    },
                    preferred_payment_method=user_input.get(
                        "preferred_payment_method", ""
                    ),
                    enabled=bool(user_input["enabled"]),
                )
            except ValueError:
                errors["base"] = "invalid_payer"
            else:
                self._payer_id = None
                return await self.async_step_init()
        return self.async_show_form(
            step_id="edit_payer",
            data_schema=vol.Schema(
                {
                    vol.Required("name", default=str(item["name"])): str,
                    vol.Required(
                        "share_percent", default=float(item.get("share_percent", 50.0))
                    ): vol.All(vol.Coerce(float), vol.Range(min=0, max=100)),
                    vol.Optional("paypal_me", default=str(item.get("paypal_me", ""))): str,
                    vol.Optional(
                        "revolut",
                        default=str(item.get("payment_methods", {}).get("revolut", "")),
                    ): str,
                    vol.Optional(
                        "venmo",
                        default=str(item.get("payment_methods", {}).get("venmo", "")),
                    ): str,
                    vol.Optional(
                        "cashapp",
                        default=str(item.get("payment_methods", {}).get("cashapp", "")),
                    ): str,
                    vol.Optional(
                        "preferred_payment_method",
                        default=str(item.get("preferred_payment_method", "paypal")),
                    ): str,
                    vol.Required("enabled", default=bool(item.get("enabled", True))): bool,
                }
            ),
            errors=errors,
        )

    async def async_step_delete_payer(self, user_input: dict[str, Any] | None = None):
        manager = self._manager()
        if manager is None:
            return self.async_abort(reason="not_setup")
        item = manager.payer(self._payer_id or "")
        if item is None:
            return self.async_abort(reason="payer_not_found")
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                await manager.async_delete_payer(str(item["id"]))
            except ValueError:
                errors["base"] = "payer_in_use"
            else:
                self._payer_id = None
                return await self.async_step_init()
        return self.async_show_form(
            step_id="delete_payer",
            data_schema=vol.Schema({}),
            errors=errors,
            description_placeholders={"name": str(item["name"])},
        )

    # ------------------------------------------------------------------
    # Categories
    # ------------------------------------------------------------------
    def _category_schema(
        self, manager: BillTrackerManager, item: dict[str, Any] | None = None
    ):
        interval_choices = {
            str(value): interval_label(self._language(), value)
            for value in SUPPORTED_INTERVALS
        }
        payer_choices = {NO_DEFAULT_PAYER: self._label("none")}
        payer_choices.update(
            {
                str(p["id"]): str(p["name"])
                for p in manager.payers
                if p.get("enabled", True)
            }
        )
        if item and item.get("default_payer_id"):
            selected = manager.payer(str(item["default_payer_id"]))
            if selected:
                payer_choices.setdefault(
                    str(selected["id"]),
                    f"{selected['name']}"
                    f"{' — ' + self._label('disabled') if not selected.get('enabled', True) else ''}",
                )
        return vol.Schema(
            {
                vol.Required("name", default=str(item["name"]) if item else ""): str,
                vol.Required(
                    "interval_months",
                    default=str(item["interval_months"]) if item else "1",
                ): vol.In(interval_choices),
                vol.Required(
                    "default_payer_id",
                    default=(
                        str(item.get("default_payer_id") or NO_DEFAULT_PAYER)
                        if item
                        else NO_DEFAULT_PAYER
                    ),
                ): vol.In(payer_choices),
                vol.Optional(
                    "color",
                    default=str(item.get("color", "#5B8FF9")) if item else "#5B8FF9",
                ): str,
                vol.Optional(
                    "consumption_unit",
                    default=str(item.get("consumption_unit", "")) if item else "",
                ): str,
                vol.Optional(
                    "default_provider",
                    default=str(item.get("default_provider", "")) if item else "",
                ): str,
                vol.Optional(
                    "default_contract",
                    default=str(item.get("default_contract", "")) if item else "",
                ): str,
                vol.Required(
                    "enabled", default=bool(item.get("enabled", True)) if item else True
                ): bool,
            }
        )

    async def async_step_add_category(self, user_input: dict[str, Any] | None = None):
        manager = self._manager()
        if manager is None:
            return self.async_abort(reason="not_setup")
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                await manager.async_add_category(
                    name=user_input["name"],
                    interval_months=int(user_input["interval_months"]),
                    enabled=bool(user_input["enabled"]),
                    default_payer_id=(
                        None
                        if user_input.get("default_payer_id")
                        in (None, "", NO_DEFAULT_PAYER)
                        else str(user_input["default_payer_id"])
                    ),
                    color=user_input.get("color"),
                    consumption_unit=user_input.get("consumption_unit", ""),
                    default_provider=user_input.get("default_provider", ""),
                    default_contract=user_input.get("default_contract", ""),
                )
            except ValueError:
                errors["base"] = "invalid_category"
            else:
                return await self.async_step_init()
        return self.async_show_form(
            step_id="add_category",
            data_schema=self._category_schema(manager),
            errors=errors,
        )

    async def async_step_manage_category(self, user_input: dict[str, Any] | None = None):
        manager = self._manager()
        if manager is None:
            return self.async_abort(reason="not_setup")
        if not manager.categories:
            return await self.async_step_add_category()
        if user_input is not None:
            self._category_id = str(user_input["category_id"])
            if user_input["action"] == "delete":
                return await self.async_step_delete_category()
            return await self.async_step_edit_category()
        categories = {
            str(item["id"]): (
                f"{category_label(self._language(), item)} — "
                f"{interval_label(self._language(), int(item['interval_months']))}"
                + ("" if item.get("enabled", True) else f" — {self._label('disabled')}")
            )
            for item in manager.categories
        }
        return self.async_show_form(
            step_id="manage_category",
            data_schema=vol.Schema(
                {
                    vol.Required("category_id"): vol.In(categories),
                    vol.Required("action", default="edit"): vol.In(
                        {"edit": self._label("edit"), "delete": self._label("delete")}
                    ),
                }
            ),
        )

    async def async_step_edit_category(self, user_input: dict[str, Any] | None = None):
        manager = self._manager()
        if manager is None:
            return self.async_abort(reason="not_setup")
        item = manager.category(self._category_id or "")
        if item is None:
            return self.async_abort(reason="category_not_found")
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                await manager.async_update_category(
                    str(item["id"]),
                    name=user_input["name"],
                    interval_months=int(user_input["interval_months"]),
                    enabled=bool(user_input["enabled"]),
                    default_payer_id=(
                        None
                        if user_input.get("default_payer_id")
                        in (None, "", NO_DEFAULT_PAYER)
                        else str(user_input["default_payer_id"])
                    ),
                    color=user_input.get("color"),
                    consumption_unit=user_input.get("consumption_unit", ""),
                    default_provider=user_input.get("default_provider", ""),
                    default_contract=user_input.get("default_contract", ""),
                )
            except ValueError:
                errors["base"] = "invalid_category"
            else:
                self._category_id = None
                return await self.async_step_init()
        return self.async_show_form(
            step_id="edit_category",
            data_schema=self._category_schema(manager, item),
            errors=errors,
        )

    async def async_step_delete_category(self, user_input: dict[str, Any] | None = None):
        manager = self._manager()
        if manager is None:
            return self.async_abort(reason="not_setup")
        item = manager.category(self._category_id or "")
        if item is None:
            return self.async_abort(reason="category_not_found")
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                await manager.async_delete_category(str(item["id"]))
            except ValueError:
                errors["base"] = "category_in_use"
            else:
                self._category_id = None
                return await self.async_step_init()
        return self.async_show_form(
            step_id="delete_category",
            data_schema=vol.Schema({}),
            errors=errors,
            description_placeholders={"name": str(item["name"])},
        )

    async def async_step_support(self, user_input: dict[str, Any] | None = None):
        if user_input is not None:
            return await self.async_step_init()
        return self.async_show_form(
            step_id="support",
            data_schema=vol.Schema({}),
            description_placeholders={
                "project_url": PROJECT_URL,
                "support_url": SUPPORT_URL,
            },
        )

    async def async_step_done(self, user_input: dict[str, Any] | None = None):
        return self.async_create_entry(title="", data={})
