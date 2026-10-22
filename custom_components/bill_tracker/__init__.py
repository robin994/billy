"""Bill Tracker integration for Home Assistant."""
from __future__ import annotations

import base64
import binascii
import inspect
import logging
from datetime import datetime
from pathlib import Path

import voluptuous as vol

from homeassistant.components import websocket_api
from homeassistant.components.frontend import (
    add_extra_js_url,
    async_panel_exists,
    async_remove_panel,
)
from homeassistant.components.panel_custom import async_register_panel
from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ID, CONF_TYPE, CONF_URL
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.event import async_track_time_change
from homeassistant.helpers.typing import ConfigType
from homeassistant.loader import async_get_integration

from .const import (
    DOMAIN,
    FRONTEND_CACHE_VERSION,
    FRONTEND_VERSION,
    RECURRING_INTERVALS,
    RECURRING_KINDS,
    SUPPORTED_INTERVALS,
)
from .manager import BillTrackerManager
from .document_archive import MAX_PDF_BYTES
from .updater import BillyUpdater

_LOGGER = logging.getLogger(__name__)

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

PLATFORMS = ["sensor", "update"]
FRONTEND_DIR = Path(__file__).parent / "frontend"
FRONTEND_PATH = FRONTEND_DIR / "bill-tracker-card.js"
FRONTEND_IMPL_PATH = FRONTEND_DIR / "bill-tracker-card-impl.js"
LOVELACE_BOOTSTRAP_PATH = FRONTEND_DIR / "billy-lovelace.js"
FRONTEND_I18N_PATH = FRONTEND_DIR / "bill-tracker-i18n.js"
PARSER_MANAGER_PATH = FRONTEND_DIR / "billy-parser-manager.js"
BILLY_REIMBURSEMENT_HISTORY_PATH = FRONTEND_DIR / "billy-reimbursement-history.js"
BILLY_PANEL_PATH = FRONTEND_DIR / "billy-panel.js"
EXTRA_I18N_PATH = FRONTEND_DIR / "billy-extra-i18n.js"
BILLY_WIDGETS_PATH = FRONTEND_DIR / "billy-widgets.js"
BILLY_INCOME_PATH = FRONTEND_DIR / "billy-income.js"
BILLY_ACCOUNTS_PATH = FRONTEND_DIR / "billy-accounts.js"
FRONTEND_URL = "/bill_tracker/bill-tracker-card.js"
FRONTEND_IMPL_URL = "/bill_tracker/bill-tracker-card-impl.js"
LOVELACE_BOOTSTRAP_URL = "/bill_tracker/billy-lovelace.js"
FRONTEND_I18N_URL = "/bill_tracker/bill-tracker-i18n.js"
PARSER_MANAGER_URL = "/bill_tracker/billy-parser-manager.js"
BILLY_REIMBURSEMENT_HISTORY_URL = "/bill_tracker/billy-reimbursement-history.js"
BILLY_PANEL_URL = "/bill_tracker/billy-panel.js"
EXTRA_I18N_URL = "/bill_tracker/billy-extra-i18n.js"
BILLY_WIDGETS_URL = "/bill_tracker/billy-widgets.js"
BILLY_INCOME_URL = "/bill_tracker/billy-income.js"
BILLY_ACCOUNTS_URL = "/bill_tracker/billy-accounts.js"
BILLY_PANEL_MODULE_URL = f"{BILLY_PANEL_URL}?v={FRONTEND_CACHE_VERSION}"
BILLY_PANEL_ROUTE = "billy"
# The legacy card stays available for dashboards that already use it.
FRONTEND_MODULE_URL = f"{FRONTEND_URL}?v={FRONTEND_CACHE_VERSION}"
LOVELACE_BOOTSTRAP_MODULE_URL = f"{LOVELACE_BOOTSTRAP_URL}?v={FRONTEND_CACHE_VERSION}"


async def _async_register_lovelace_resource(hass: HomeAssistant) -> None:
    """Register widgets and the legacy host independently in Lovelace storage."""
    try:
        from homeassistant.components.lovelace.const import LOVELACE_DATA
        from homeassistant.components.lovelace.resources import ResourceStorageCollection

        lovelace_data = hass.data.get(LOVELACE_DATA)
        if lovelace_data is None:
            return
        resources = lovelace_data.resources
        if not isinstance(resources, ResourceStorageCollection):
            return

        ensure_loaded = getattr(resources, "_async_ensure_loaded", None)
        if ensure_loaded is not None:
            await ensure_loaded()
        elif not getattr(resources, "loaded", True):
            await resources.async_load()
            try:
                resources.loaded = True
            except AttributeError:
                pass

        items = resources.async_items()
        if inspect.isawaitable(items):
            items = await items
        items = items or []
        # Keep the old resource registered until 1.0.0. Lovelace resources
        # load after HA's custom-element registry polyfill; extra modules can
        # run before it and lose custom element registrations.
        for resource_url, module_url in (
            (LOVELACE_BOOTSTRAP_URL, LOVELACE_BOOTSTRAP_MODULE_URL),
            (FRONTEND_URL, FRONTEND_MODULE_URL),
        ):
            match = next(
                (
                    item
                    for item in items
                    if str(item.get(CONF_URL, "")).split("?", 1)[0] == resource_url
                ),
                None,
            )
            if match is None:
                await resources.async_create_item(
                    {"res_type": "module", CONF_URL: module_url}
                )
            elif match.get(CONF_URL) != module_url or match.get(CONF_TYPE) != "module":
                await resources.async_update_item(
                    match[CONF_ID],
                    {"res_type": "module", CONF_URL: module_url},
                )
    except Exception:  # noqa: BLE001
        _LOGGER.exception("Could not register Billy as a Lovelace resource")


async def _billy_version(hass: HomeAssistant) -> str:
    """The installed integration version from manifest.json (single source of truth)."""
    try:
        integration = await async_get_integration(hass, DOMAIN)
        if integration.version:
            return str(integration.version)
    except Exception:  # noqa: BLE001
        _LOGGER.debug("Could not read Billy version from the manifest", exc_info=True)
    return FRONTEND_VERSION


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up Bill Tracker and its frontend module."""
    version = await _billy_version(hass)
    hass.data.setdefault(DOMAIN, {})["version"] = version

    for command in (
        ws_list,
        ws_add,
        ws_delete,
        ws_update,
        ws_set_paid,
        ws_set_reimbursement,
        ws_document_archive,
        ws_document_read,
        ws_document_upload,
        ws_document_delete,
        ws_income_add,
        ws_income_update,
        ws_income_delete,
        ws_income_rule_add,
        ws_income_rule_update,
        ws_income_rule_delete,
        ws_income_category_add,
        ws_income_category_update,
        ws_income_category_delete,
        ws_account_add,
        ws_account_update,
        ws_account_delete,
        ws_account_set_default,
        ws_house_add,
        ws_house_update,
        ws_house_delete,
        ws_house_set_default,
        ws_internal_transfer_add,
        ws_internal_transfer_update,
        ws_internal_transfer_delete,
        ws_recurring_add,
        ws_recurring_update,
        ws_recurring_set_active,
        ws_recurring_set_reimbursement,
        ws_recurring_payment_set,
        ws_recurring_payment_delete,
        ws_recurring_delete,
        ws_category_add,
        ws_category_update,
        ws_category_delete,
        ws_payer_add,
        ws_payer_update,
        ws_payer_delete,
        ws_settlement_add,
        ws_settlement_delete,
        ws_import_csv,
        ws_export,
        ws_export_recurring,
        ws_export_template,
        ws_backup_export,
        ws_backup_import,
        ws_update_status,
        ws_update_install,
    ):
        websocket_api.async_register_command(hass, command)

    await hass.http.async_register_static_paths(
        [
            StaticPathConfig(
                LOVELACE_BOOTSTRAP_URL, str(LOVELACE_BOOTSTRAP_PATH), False
            ),
            StaticPathConfig(FRONTEND_URL, str(FRONTEND_PATH), False),
            StaticPathConfig(FRONTEND_IMPL_URL, str(FRONTEND_IMPL_PATH), False),
            StaticPathConfig(FRONTEND_I18N_URL, str(FRONTEND_I18N_PATH), False),
            StaticPathConfig(PARSER_MANAGER_URL, str(PARSER_MANAGER_PATH), False),
            StaticPathConfig(
                BILLY_REIMBURSEMENT_HISTORY_URL,
                str(BILLY_REIMBURSEMENT_HISTORY_PATH),
                False,
            ),
            StaticPathConfig(BILLY_PANEL_URL, str(BILLY_PANEL_PATH), False),
            StaticPathConfig(EXTRA_I18N_URL, str(EXTRA_I18N_PATH), False),
            StaticPathConfig(BILLY_WIDGETS_URL, str(BILLY_WIDGETS_PATH), False),
            StaticPathConfig(BILLY_INCOME_URL, str(BILLY_INCOME_PATH), False),
            StaticPathConfig(BILLY_ACCOUNTS_URL, str(BILLY_ACCOUNTS_PATH), False),
        ]
    )
    # Widgets and the lightweight legacy host are registered independently.
    # The deprecated full card implementation is loaded only if requested.
    add_extra_js_url(hass, LOVELACE_BOOTSTRAP_MODULE_URL)
    add_extra_js_url(hass, FRONTEND_MODULE_URL)
    # Register Billy through Home Assistant's supported custom-panel loader.
    # Remove a previous definition first so integration reloads cannot retain stale panel metadata.
    if async_panel_exists(hass, BILLY_PANEL_ROUTE):
        async_remove_panel(hass, BILLY_PANEL_ROUTE, warn_if_unknown=False)
    await async_register_panel(
        hass,
        frontend_url_path=BILLY_PANEL_ROUTE,
        webcomponent_name="billy-panel",
        sidebar_title="Billy",
        sidebar_icon="mdi:receipt-text-outline",
        module_url=BILLY_PANEL_MODULE_URL,
        require_admin=False,
        config={"version": version},
    )
    await _async_register_lovelace_resource(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Bill Tracker from a config entry."""
    manager = BillTrackerManager(hass)
    await manager.async_load()

    async def _sync_recurring_at_midnight(_now) -> None:
        recurring_changed = await manager.async_sync_recurring_occurrences()
        income_changed = await manager.async_sync_income_occurrences()
        placeholders_changed = await manager.async_sync_bill_placeholders()
        if not recurring_changed and not income_changed and not placeholders_changed:
            hass.bus.async_fire(EVENT_UPDATED)

    entry.async_on_unload(
        async_track_time_change(
            hass,
            _sync_recurring_at_midnight,
            hour=0,
            minute=0,
            second=0,
        )
    )
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = manager
    hass.data[DOMAIN]["manager"] = manager
    hass.data[DOMAIN].setdefault(
        "updater",
        BillyUpdater(hass, hass.data[DOMAIN].get("version", FRONTEND_VERSION)),
    )
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a Bill Tracker config entry."""
    ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if ok:
        manager = hass.data.get(DOMAIN, {}).get(entry.entry_id)
        hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
        if hass.data.get(DOMAIN, {}).get("manager") is manager:
            hass.data[DOMAIN].pop("manager", None)
        hass.data.get(DOMAIN, {}).pop("updater", None)
    return ok


def _manager(hass: HomeAssistant) -> BillTrackerManager:
    manager = hass.data.get(DOMAIN, {}).get("manager")
    if manager is None:
        raise RuntimeError("Billy is not configured yet")
    return manager


def _ws_error(connection, msg, err, default_code):
    """Forward a business error to the frontend with a stable code."""
    code = getattr(err, "code", None) or default_code
    connection.send_error(msg["id"], code, str(err))


@websocket_api.websocket_command(
    {
        vol.Required("type"): "bill_tracker/list",
        vol.Optional("forecast_months", default=12): vol.All(
            vol.Coerce(int), vol.Range(min=1, max=24)
        ),
        vol.Optional("house_id"): str,
    }
)
@websocket_api.async_response
async def ws_list(hass, connection, msg):
    try:
        result = _manager(hass).snapshot(msg["forecast_months"], msg.get("house_id"))
        result["version"] = hass.data.get(DOMAIN, {}).get("version", FRONTEND_VERSION)
        parser_manager = hass.data.get(DOMAIN, {}).get("parser_manager")
        if parser_manager is not None:
            result.setdefault("summary", {})["automatic_import_pending"] = len(
                parser_manager.imports_snapshot("pending", 500)
            )
    except ValueError as err:
        _ws_error(connection, msg, err, "invalid_house")
        return
    except RuntimeError as err:
        _ws_error(connection, msg, err, "not_configured")
        return
    connection.send_result(msg["id"], result)


_SPLIT_ITEM_SCHEMA = vol.Schema(
    {
        vol.Required("payer_id"): str,
        vol.Required("percentage"): vol.Coerce(float),
    }
)

_EXPENSE_SCHEMA = {
    vol.Required("year"): vol.Coerce(int),
    vol.Required("month"): vol.All(vol.Coerce(int), vol.Range(min=1, max=12)),
    vol.Optional("category_id"): str,
    vol.Optional("category"): str,
    vol.Required("amount"): vol.Coerce(float),
    vol.Optional("note", default=""): str,
    vol.Optional("period_start_year"): vol.Coerce(int),
    vol.Optional("period_start_month"): vol.All(vol.Coerce(int), vol.Range(min=1, max=12)),
    vol.Optional("period_end_year"): vol.Coerce(int),
    vol.Optional("period_end_month"): vol.All(vol.Coerce(int), vol.Range(min=1, max=12)),
    vol.Optional("period_start_date"): str,
    vol.Optional("period_end_date"): str,
    vol.Optional("payer_id"): str,
    vol.Optional("split"): [_SPLIT_ITEM_SCHEMA],
    vol.Optional("paid"): bool,
    vol.Optional("exclude_from_estimates"): bool,
    vol.Optional("payment_date"): str,
    vol.Optional("due_date"): str,
    vol.Optional("provider"): str,
    vol.Optional("contract"): str,
    vol.Optional("consumption"): vol.Coerce(float),
    vol.Optional("document_url"): str,
    vol.Optional("account_id"): str,
    vol.Optional("house_id"): str,
}


def _expense_kwargs(msg):
    return {
        "year": msg["year"],
        "month": msg["month"],
        "category_id": msg.get("category_id"),
        "category_name": msg.get("category"),
        "amount": msg["amount"],
        "note": msg["note"],
        "period_start_year": msg.get("period_start_year"),
        "period_start_month": msg.get("period_start_month"),
        "period_end_year": msg.get("period_end_year"),
        "period_end_month": msg.get("period_end_month"),
        "period_start_date": msg.get("period_start_date"),
        "period_end_date": msg.get("period_end_date"),
        "payer_id": msg.get("payer_id"),
        "split": msg.get("split"),
        "paid": msg.get("paid"),
        "exclude_from_estimates": msg.get("exclude_from_estimates"),
        "payment_date": msg.get("payment_date"),
        "due_date": msg.get("due_date"),
        "provider": msg.get("provider"),
        "contract": msg.get("contract"),
        "consumption": msg.get("consumption"),
        "document_url": msg.get("document_url"),
        "account_id": msg.get("account_id"),
        "house_id": msg.get("house_id"),
    }


@websocket_api.websocket_command({
    vol.Required("type"): "bill_tracker/house/add",
    vol.Required("name"): str,
})
@websocket_api.async_response
async def ws_house_add(hass, connection, msg):
    try:
        result = await _manager(hass).async_add_house(msg["name"])
    except (ValueError, RuntimeError) as err:
        _ws_error(connection, msg, err, "invalid_house")
        return
    connection.send_result(msg["id"], result)


@websocket_api.websocket_command({
    vol.Required("type"): "bill_tracker/house/update",
    vol.Required("house_id"): str,
    vol.Required("name"): str,
})
@websocket_api.async_response
async def ws_house_update(hass, connection, msg):
    try:
        result = await _manager(hass).async_update_house(msg["house_id"], msg["name"])
    except (ValueError, RuntimeError) as err:
        _ws_error(connection, msg, err, "invalid_house")
        return
    connection.send_result(msg["id"], result)


@websocket_api.websocket_command({
    vol.Required("type"): "bill_tracker/house/default",
    vol.Required("house_id"): str,
})
@websocket_api.async_response
async def ws_house_set_default(hass, connection, msg):
    try:
        result = await _manager(hass).async_set_default_house(msg["house_id"])
    except (ValueError, RuntimeError) as err:
        _ws_error(connection, msg, err, "invalid_house")
        return
    connection.send_result(msg["id"], result)


@websocket_api.websocket_command({
    vol.Required("type"): "bill_tracker/house/delete",
    vol.Required("house_id"): str,
})
@websocket_api.async_response
async def ws_house_delete(hass, connection, msg):
    try:
        result = await _manager(hass).async_delete_house(msg["house_id"])
    except (ValueError, RuntimeError) as err:
        _ws_error(connection, msg, err, "invalid_house")
        return
    connection.send_result(msg["id"], {"deleted": result})


@websocket_api.websocket_command({vol.Required("type"): "bill_tracker/add", **_EXPENSE_SCHEMA})
@websocket_api.async_response
async def ws_add(hass, connection, msg):
    try:
        item = await _manager(hass).async_add(**_expense_kwargs(msg))
    except (ValueError, RuntimeError) as err:
        _ws_error(connection, msg, err, "invalid_expense")
        return
    connection.send_result(msg["id"], item)


@websocket_api.websocket_command(
    {
        vol.Required("type"): "bill_tracker/update",
        vol.Required("expense_id"): str,
        **_EXPENSE_SCHEMA,
    }
)
@websocket_api.async_response
async def ws_update(hass, connection, msg):
    try:
        item = await _manager(hass).async_update(
            msg["expense_id"], **_expense_kwargs(msg)
        )
    except (ValueError, RuntimeError) as err:
        _ws_error(connection, msg, err, "invalid_expense")
        return
    if item is None:
        connection.send_error(msg["id"], "expense_not_found", "Expense not found")
        return
    connection.send_result(msg["id"], item)


@websocket_api.websocket_command(
    {
        vol.Required("type"): "bill_tracker/set_paid",
        vol.Required("expense_id"): str,
        vol.Required("paid"): bool,
    }
)
@websocket_api.async_response
async def ws_set_paid(hass, connection, msg):
    try:
        item = await _manager(hass).async_set_paid(msg["expense_id"], msg["paid"])
    except RuntimeError as err:
        _ws_error(connection, msg, err, "not_configured")
        return
    if item is None:
        connection.send_error(msg["id"], "expense_not_found", "Expense not found")
        return
    connection.send_result(msg["id"], item)


@websocket_api.websocket_command(
    {
        vol.Required("type"): "bill_tracker/set_reimbursement",
        vol.Required("expense_id"): str,
        vol.Required("done"): bool,
    }
)
@websocket_api.async_response
async def ws_set_reimbursement(hass, connection, msg):
    try:
        item = await _manager(hass).async_set_reimbursement_done(
            msg["expense_id"], msg["done"]
        )
    except (ValueError, RuntimeError) as err:
        _ws_error(connection, msg, err, "invalid_reimbursement")
        return
    if item is None:
        connection.send_error(msg["id"], "expense_not_found", "Expense not found")
        return
    connection.send_result(msg["id"], item)


@websocket_api.websocket_command(
    {vol.Required("type"): "bill_tracker/delete", vol.Required("expense_id"): str}
)
@websocket_api.async_response
async def ws_delete(hass, connection, msg):
    try:
        deleted = await _manager(hass).async_delete(msg["expense_id"])
    except RuntimeError as err:
        _ws_error(connection, msg, err, "not_configured")
        return
    connection.send_result(msg["id"], {"deleted": deleted})


@websocket_api.websocket_command(
    {vol.Required("type"): "bill_tracker/document/archive", vol.Required("expense_id"): str}
)
@websocket_api.async_response
async def ws_document_archive(hass, connection, msg):
    if not connection.user.is_admin:
        connection.send_error(msg["id"], "unauthorized", "Only administrators can fetch remote PDFs")
        return
    try:
        item = await _manager(hass).async_archive_document(msg["expense_id"])
    except (ValueError, RuntimeError) as err:
        _ws_error(connection, msg, err, "archive_failed")
        return
    connection.send_result(msg["id"], item)


@websocket_api.websocket_command(
    {vol.Required("type"): "bill_tracker/document/read", vol.Required("expense_id"): str}
)
@websocket_api.async_response
async def ws_document_read(hass, connection, msg):
    try:
        document = await _manager(hass).async_read_document(msg["expense_id"])
    except (ValueError, RuntimeError, OSError) as err:
        _ws_error(connection, msg, err, "document_not_found")
        return
    connection.send_result(msg["id"], document)


@websocket_api.websocket_command({
    vol.Required("type"): "bill_tracker/document/upload",
    vol.Required("expense_id"): str,
    vol.Required("upload_id"): vol.All(str, vol.Length(min=1, max=80)),
    vol.Required("chunk_index"): vol.All(vol.Coerce(int), vol.Range(min=0, max=127)),
    vol.Required("total_chunks"): vol.All(vol.Coerce(int), vol.Range(min=1, max=128)),
    vol.Required("total_size"): vol.All(vol.Coerce(int), vol.Range(min=5, max=MAX_PDF_BYTES)),
    vol.Required("content_base64"): str,
})
@websocket_api.async_response
async def ws_document_upload(hass, connection, msg):
    if not connection.user.is_admin:
        connection.send_error(msg["id"], "unauthorized", "Only administrators can upload PDFs")
        return
    encoded = msg["content_base64"]
    if len(encoded) > ((256 * 1024 + 2) // 3) * 4:
        connection.send_error(msg["id"], "document_too_large", "PDF chunk is too large")
        return
    try:
        chunk = base64.b64decode(encoded, validate=True)
        result = await _manager(hass).async_receive_document_chunk(
            connection.user.id, msg["expense_id"], msg["upload_id"],
            msg["chunk_index"], msg["total_chunks"], msg["total_size"], chunk,
        )
    except (ValueError, RuntimeError, OSError, binascii.Error) as err:
        _ws_error(connection, msg, err, "invalid_pdf_upload")
        return
    connection.send_result(msg["id"], result)


@websocket_api.websocket_command({
    vol.Required("type"): "bill_tracker/document/delete",
    vol.Required("expense_id"): str,
})
@websocket_api.async_response
async def ws_document_delete(hass, connection, msg):
    if not connection.user.is_admin:
        connection.send_error(msg["id"], "unauthorized", "Only administrators can remove PDFs")
        return
    try:
        result = await _manager(hass).async_delete_document(msg["expense_id"])
    except (ValueError, RuntimeError, OSError) as err:
        _ws_error(connection, msg, err, "document_delete_failed")
        return
    connection.send_result(msg["id"], result)


_INCOME_ENTRY = {
    vol.Required("description"): str,
    vol.Required("category_id"): str,
    vol.Required("expected_date"): str,
    vol.Required("estimated_amount"): vol.Coerce(float),
    vol.Optional("received", default=False): bool,
    vol.Optional("actual_amount"): vol.Coerce(float),
    vol.Optional("received_date"): str,
    vol.Optional("note", default=""): str,
    vol.Optional("account_id"): str,
}


def _income_kwargs(msg):
    return {
        "description": msg["description"],
        "category_id": msg["category_id"],
        "expected_date": msg["expected_date"],
        "estimated_amount": msg["estimated_amount"],
        "received": msg["received"],
        "actual_amount": msg.get("actual_amount"),
        "received_date": msg.get("received_date"),
        "note": msg.get("note", ""),
        "account_id": msg.get("account_id"),
    }


@websocket_api.websocket_command({vol.Required("type"): "bill_tracker/income/add", **_INCOME_ENTRY})
@websocket_api.async_response
async def ws_income_add(hass, connection, msg):
    try:
        item = await _manager(hass).async_add_income(**_income_kwargs(msg))
    except (ValueError, RuntimeError) as err:
        _ws_error(connection, msg, err, "invalid_income")
        return
    connection.send_result(msg["id"], item)


@websocket_api.websocket_command({
    vol.Required("type"): "bill_tracker/income/update",
    vol.Required("income_id"): str,
    **_INCOME_ENTRY,
})
@websocket_api.async_response
async def ws_income_update(hass, connection, msg):
    try:
        item = await _manager(hass).async_update_income(msg["income_id"], **_income_kwargs(msg))
    except (ValueError, RuntimeError) as err:
        _ws_error(connection, msg, err, "invalid_income")
        return
    if item is None:
        connection.send_error(msg["id"], "income_not_found", "Income not found")
        return
    connection.send_result(msg["id"], item)


@websocket_api.websocket_command({
    vol.Required("type"): "bill_tracker/income/delete", vol.Required("income_id"): str,
})
@websocket_api.async_response
async def ws_income_delete(hass, connection, msg):
    connection.send_result(msg["id"], {
        "deleted": await _manager(hass).async_delete_income(msg["income_id"]),
    })


_INCOME_RULE_ENTRY = {
    vol.Required("name"): str,
    vol.Required("category_id"): str,
    vol.Required("estimated_amount"): vol.Coerce(float),
    vol.Required("interval_months"): vol.In((1, 2, 3, 4, 6, 12)),
    vol.Required("start_date"): str,
    vol.Optional("end_date", default=""): str,
    vol.Optional("amount_mode", default="fixed"): vol.In(("fixed", "last", "average3", "average6", "average12")),
    vol.Optional("active", default=True): bool,
    vol.Optional("house_id"): str,
    vol.Optional("note", default=""): str,
    vol.Optional("account_id"): str,
}


def _income_rule_kwargs(msg):
    result = {key: msg[key] for key in (
        "name", "category_id", "estimated_amount", "interval_months",
        "start_date", "end_date", "amount_mode", "active", "note",
    )}
    result["account_id"] = msg.get("account_id")
    return result


@websocket_api.websocket_command({vol.Required("type"): "bill_tracker/income/rule/add", **_INCOME_RULE_ENTRY})
@websocket_api.async_response
async def ws_income_rule_add(hass, connection, msg):
    try:
        item = await _manager(hass).async_add_income_rule(**_income_rule_kwargs(msg))
    except (ValueError, RuntimeError) as err:
        _ws_error(connection, msg, err, "invalid_income_rule")
        return
    connection.send_result(msg["id"], item)


@websocket_api.websocket_command({
    vol.Required("type"): "bill_tracker/income/rule/update",
    vol.Required("rule_id"): str, **_INCOME_RULE_ENTRY,
})
@websocket_api.async_response
async def ws_income_rule_update(hass, connection, msg):
    try:
        item = await _manager(hass).async_update_income_rule(msg["rule_id"], **_income_rule_kwargs(msg))
    except (ValueError, RuntimeError) as err:
        _ws_error(connection, msg, err, "invalid_income_rule")
        return
    if item is None:
        connection.send_error(msg["id"], "income_rule_not_found", "Recurring income not found")
        return
    connection.send_result(msg["id"], item)


@websocket_api.websocket_command({
    vol.Required("type"): "bill_tracker/income/rule/delete", vol.Required("rule_id"): str,
})
@websocket_api.async_response
async def ws_income_rule_delete(hass, connection, msg):
    connection.send_result(msg["id"], {
        "deleted": await _manager(hass).async_delete_income_rule(msg["rule_id"]),
    })


_INCOME_CATEGORY_ENTRY = {
    vol.Required("name"): str,
    vol.Optional("color", default="#6B8394"): str,
}


@websocket_api.websocket_command({
    vol.Required("type"): "bill_tracker/income/category/add", **_INCOME_CATEGORY_ENTRY,
})
@websocket_api.async_response
async def ws_income_category_add(hass, connection, msg):
    try:
        item = await _manager(hass).async_add_income_category(name=msg["name"], color=msg["color"])
    except (ValueError, RuntimeError) as err:
        _ws_error(connection, msg, err, "invalid_income_category")
        return
    connection.send_result(msg["id"], item)


@websocket_api.websocket_command({
    vol.Required("type"): "bill_tracker/income/category/update",
    vol.Required("category_id"): str, **_INCOME_CATEGORY_ENTRY,
})
@websocket_api.async_response
async def ws_income_category_update(hass, connection, msg):
    try:
        item = await _manager(hass).async_update_income_category(
            msg["category_id"], name=msg["name"], color=msg["color"]
        )
    except (ValueError, RuntimeError) as err:
        _ws_error(connection, msg, err, "invalid_income_category")
        return
    if item is None:
        connection.send_error(msg["id"], "income_category_not_found", "Income category not found")
        return
    connection.send_result(msg["id"], item)


@websocket_api.websocket_command({
    vol.Required("type"): "bill_tracker/income/category/delete",
    vol.Required("category_id"): str,
})
@websocket_api.async_response
async def ws_income_category_delete(hass, connection, msg):
    try:
        deleted = await _manager(hass).async_delete_income_category(msg["category_id"])
    except (ValueError, RuntimeError) as err:
        _ws_error(connection, msg, err, "income_category_in_use")
        return
    connection.send_result(msg["id"], {"deleted": deleted})


@websocket_api.websocket_command({
    vol.Required("type"): "bill_tracker/accounts/add",
    vol.Required("name"): str,
    vol.Required("account_type"): str,
    vol.Required("opening_balance"): vol.Coerce(float),
    vol.Required("opening_date"): str,
    vol.Required("payer_id"): str,
    vol.Optional("make_default", default=False): bool,
})
@websocket_api.async_response
async def ws_account_add(hass, connection, msg):
    try:
        result = await _manager(hass).async_add_account(
            name=msg["name"],
            account_type=msg["account_type"],
            opening_balance=msg["opening_balance"],
            opening_date=msg["opening_date"],
            payer_id=msg["payer_id"],
            make_default=msg["make_default"],
        )
    except (ValueError, RuntimeError) as err:
        _ws_error(connection, msg, err, "invalid_accounts")
        return
    connection.send_result(msg["id"], result)


_ACCOUNT_UPDATE = {
    vol.Required("name"): str,
    vol.Required("account_type"): str,
    vol.Required("opening_balance"): vol.Coerce(float),
    vol.Required("opening_date"): str,
    vol.Required("payer_id"): str,
    vol.Optional("make_default", default=False): bool,
}


@websocket_api.websocket_command({
    vol.Required("type"): "bill_tracker/accounts/update",
    vol.Required("account_id"): str,
    **_ACCOUNT_UPDATE,
})
@websocket_api.async_response
async def ws_account_update(hass, connection, msg):
    try:
        result = await _manager(hass).async_update_account(
            msg["account_id"],
            name=msg["name"],
            account_type=msg["account_type"],
            opening_balance=msg["opening_balance"],
            opening_date=msg["opening_date"],
            payer_id=msg["payer_id"],
            make_default=msg["make_default"],
        )
    except (ValueError, RuntimeError) as err:
        _ws_error(connection, msg, err, "invalid_accounts")
        return
    if result is None:
        connection.send_error(msg["id"], "account_not_found", "Account not found")
        return
    connection.send_result(msg["id"], result)


@websocket_api.websocket_command({
    vol.Required("type"): "bill_tracker/accounts/delete",
    vol.Required("account_id"): str,
})
@websocket_api.async_response
async def ws_account_delete(hass, connection, msg):
    try:
        deleted = await _manager(hass).async_delete_account(msg["account_id"])
    except (ValueError, RuntimeError) as err:
        _ws_error(connection, msg, err, "account_in_use")
        return
    connection.send_result(msg["id"], {"deleted": deleted})


@websocket_api.websocket_command({
    vol.Required("type"): "bill_tracker/accounts/default",
    vol.Required("account_id"): str,
})
@websocket_api.async_response
async def ws_account_set_default(hass, connection, msg):
    try:
        result = await _manager(hass).async_set_default_account(msg["account_id"])
    except (ValueError, RuntimeError) as err:
        _ws_error(connection, msg, err, "account_not_found")
        return
    connection.send_result(msg["id"], result)


_TRANSFER_SCHEMA = {
    vol.Required("from_account"): str,
    vol.Required("to_account"): str,
    vol.Required("amount"): vol.Coerce(float),
    vol.Required("transfer_date"): str,
    vol.Optional("note", default=""): str,
}


def _transfer_kwargs(msg):
    return {
        "from_account": msg["from_account"],
        "to_account": msg["to_account"],
        "amount": msg["amount"],
        "transfer_date": msg["transfer_date"],
        "note": msg.get("note", ""),
    }


@websocket_api.websocket_command({
    vol.Required("type"): "bill_tracker/accounts/transfer/add",
    **_TRANSFER_SCHEMA,
})
@websocket_api.async_response
async def ws_internal_transfer_add(hass, connection, msg):
    try:
        result = await _manager(hass).async_add_internal_transfer(**_transfer_kwargs(msg))
    except (ValueError, RuntimeError) as err:
        _ws_error(connection, msg, err, "invalid_transfer")
        return
    connection.send_result(msg["id"], result)


@websocket_api.websocket_command({
    vol.Required("type"): "bill_tracker/accounts/transfer/update",
    vol.Required("transfer_id"): str,
    **_TRANSFER_SCHEMA,
})
@websocket_api.async_response
async def ws_internal_transfer_update(hass, connection, msg):
    try:
        result = await _manager(hass).async_update_internal_transfer(
            msg["transfer_id"], **_transfer_kwargs(msg)
        )
    except (ValueError, RuntimeError) as err:
        _ws_error(connection, msg, err, "invalid_transfer")
        return
    if result is None:
        connection.send_error(msg["id"], "transfer_not_found", "Internal transfer not found")
        return
    connection.send_result(msg["id"], result)


@websocket_api.websocket_command({
    vol.Required("type"): "bill_tracker/accounts/transfer/delete",
    vol.Required("transfer_id"): str,
})
@websocket_api.async_response
async def ws_internal_transfer_delete(hass, connection, msg):
    connection.send_result(msg["id"], {
        "deleted": await _manager(hass).async_delete_internal_transfer(msg["transfer_id"]),
    })


_RECURRING_COMMON = {
    vol.Required("name"): str,
    vol.Required("kind"): vol.In(RECURRING_KINDS),
    vol.Required("amount"): vol.Coerce(float),
    vol.Required("interval_months"): vol.In(RECURRING_INTERVALS),
    vol.Required("start_date"): str,
    vol.Optional("end_date", default=""): str,
    vol.Optional("auto_renew", default=False): bool,
    vol.Optional("renewal_interval_months", default=12): vol.All(
        vol.Coerce(int), vol.Range(min=1, max=120)
    ),
    vol.Optional("installment_count"): vol.All(
        vol.Coerce(int), vol.Range(min=1, max=1200)
    ),
    vol.Optional("payer_id"): str,
    vol.Optional("split"): [_SPLIT_ITEM_SCHEMA],
    vol.Optional("provider", default=""): str,
    vol.Optional("contract", default=""): str,
    vol.Optional("color", default=""): str,
    vol.Optional("note", default=""): str,
    vol.Optional("active", default=True): bool,
}


def _recurring_kwargs(msg):
    return {
        "name": msg["name"],
        "kind": msg["kind"],
        "amount": msg["amount"],
        "interval_months": msg["interval_months"],
        "start_date": msg["start_date"],
        "end_date": msg.get("end_date") or None,
        "auto_renew": msg.get("auto_renew", False),
        "renewal_interval_months": msg.get("renewal_interval_months", 12),
        "installment_count": msg.get("installment_count"),
        "payer_id": msg.get("payer_id"),
        "split": msg.get("split"),
        "provider": msg.get("provider", ""),
        "contract": msg.get("contract", ""),
        "color": msg.get("color", ""),
        "note": msg.get("note", ""),
        "active": msg.get("active", True),
        "house_id": msg.get("house_id"),
    }


@websocket_api.websocket_command(
    {vol.Required("type"): "bill_tracker/recurring/add", **_RECURRING_COMMON}
)
@websocket_api.async_response
async def ws_recurring_add(hass, connection, msg):
    try:
        item = await _manager(hass).async_add_recurring(**_recurring_kwargs(msg))
    except (ValueError, RuntimeError) as err:
        _ws_error(connection, msg, err, "invalid_recurring")
        return
    connection.send_result(msg["id"], item)


@websocket_api.websocket_command(
    {
        vol.Required("type"): "bill_tracker/recurring/update",
        vol.Required("recurring_id"): str,
        **_RECURRING_COMMON,
    }
)
@websocket_api.async_response
async def ws_recurring_update(hass, connection, msg):
    try:
        item = await _manager(hass).async_update_recurring(
            msg["recurring_id"], **_recurring_kwargs(msg)
        )
    except (ValueError, RuntimeError) as err:
        _ws_error(connection, msg, err, "invalid_recurring")
        return
    if item is None:
        connection.send_error(msg["id"], "recurring_not_found", "Recurring expense not found")
        return
    connection.send_result(msg["id"], item)


@websocket_api.websocket_command(
    {
        vol.Required("type"): "bill_tracker/recurring/set_active",
        vol.Required("recurring_id"): str,
        vol.Required("active"): bool,
    }
)
@websocket_api.async_response
async def ws_recurring_set_active(hass, connection, msg):
    try:
        item = await _manager(hass).async_set_recurring_active(
            msg["recurring_id"], msg["active"]
        )
    except RuntimeError as err:
        _ws_error(connection, msg, err, "not_configured")
        return
    if item is None:
        connection.send_error(msg["id"], "recurring_not_found", "Recurring expense not found")
        return
    connection.send_result(msg["id"], item)


@websocket_api.websocket_command(
    {
        vol.Required("type"): "bill_tracker/recurring/set_reimbursement",
        vol.Required("occurrence_id"): str,
        vol.Required("done"): bool,
    }
)
@websocket_api.async_response
async def ws_recurring_set_reimbursement(hass, connection, msg):
    try:
        item = await _manager(hass).async_set_recurring_reimbursement_done(
            msg["occurrence_id"], msg["done"]
        )
    except (ValueError, RuntimeError) as err:
        _ws_error(connection, msg, err, "invalid_reimbursement")
        return
    if item is None:
        connection.send_error(msg["id"], "occurrence_not_found", "Recurring charge not found")
        return
    connection.send_result(msg["id"], item)


@websocket_api.websocket_command(
    {
        vol.Required("type"): "bill_tracker/recurring/payment/set",
        vol.Required("recurring_id"): str,
        vol.Required("due_date"): str,
        vol.Required("payment_date"): str,
        vol.Required("amount"): vol.Coerce(float),
        vol.Optional("account_id"): str,
        vol.Optional("note", default=""): str,
        vol.Optional("already_recorded", default=False): bool,
    }
)
@websocket_api.async_response
async def ws_recurring_payment_set(hass, connection, msg):
    try:
        result = await _manager(hass).async_record_recurring_payment(
            recurring_id=msg["recurring_id"],
            due_date=msg["due_date"],
            payment_date=msg["payment_date"],
            amount=msg["amount"],
            account_id=msg.get("account_id"),
            note=msg.get("note", ""),
            already_recorded=msg.get("already_recorded", False),
        )
    except (ValueError, RuntimeError) as err:
        _ws_error(connection, msg, err, "invalid_recurring_payment")
        return
    connection.send_result(msg["id"], result)


@websocket_api.websocket_command(
    {
        vol.Required("type"): "bill_tracker/recurring/payment/delete",
        vol.Required("recurring_id"): str,
        vol.Required("due_date"): str,
    }
)
@websocket_api.async_response
async def ws_recurring_payment_delete(hass, connection, msg):
    try:
        result = await _manager(hass).async_delete_recurring_payment(
            recurring_id=msg["recurring_id"], due_date=msg["due_date"]
        )
    except (ValueError, RuntimeError) as err:
        _ws_error(connection, msg, err, "invalid_recurring_payment")
        return
    connection.send_result(msg["id"], {"deleted": result})


@websocket_api.websocket_command(
    {
        vol.Required("type"): "bill_tracker/recurring/delete",
        vol.Required("recurring_id"): str,
    }
)
@websocket_api.async_response
async def ws_recurring_delete(hass, connection, msg):
    try:
        deleted = await _manager(hass).async_delete_recurring(msg["recurring_id"])
    except (ValueError, RuntimeError) as err:
        _ws_error(connection, msg, err, "invalid_recurring")
        return
    connection.send_result(msg["id"], {"deleted": deleted})


_CATEGORY_COMMON = {
    vol.Required("name"): str,
    vol.Required("interval_months"): vol.In(SUPPORTED_INTERVALS),
    vol.Optional("enabled", default=True): bool,
    vol.Optional("exclude_from_estimates"): bool,
    vol.Optional("default_payer_id"): str,
    vol.Optional("color"): str,
    vol.Optional("consumption_unit", default=""): str,
    vol.Optional("default_provider", default=""): str,
    vol.Optional("default_contract", default=""): str,
    vol.Optional("document_archive"): {
        vol.Optional("enabled", default=False): bool,
        vol.Optional("subpath", default="billy/documents"): str,
        vol.Optional("source_host", default=""): str,
    },
    vol.Optional("placeholder"): {
        vol.Optional("enabled", default=False): bool,
        vol.Optional("day", default=1): vol.All(vol.Coerce(int), vol.Range(min=1, max=31)),
        vol.Optional("amount_mode", default="last"): vol.In(("last", "forecast", "fixed")),
        vol.Optional("fixed_amount", default=0): vol.Coerce(float),
        vol.Optional("due_day"): vol.Any(None, vol.All(vol.Coerce(int), vol.Range(min=1, max=31))),
        vol.Optional("start_month", default=""): str,
    },
}


@websocket_api.websocket_command(
    {vol.Required("type"): "bill_tracker/category/add", **_CATEGORY_COMMON}
)
@websocket_api.async_response
async def ws_category_add(hass, connection, msg):
    if msg.get("document_archive", {}).get("enabled") and not connection.user.is_admin:
        connection.send_error(msg["id"], "unauthorized", "Only administrators can enable PDF downloads")
        return
    try:
        category = await _manager(hass).async_add_category(
            name=msg["name"],
            interval_months=msg["interval_months"],
            enabled=msg["enabled"],
            exclude_from_estimates=msg.get("exclude_from_estimates", False),
            default_payer_id=msg.get("default_payer_id"),
            color=msg.get("color"),
            consumption_unit=msg.get("consumption_unit", ""),
            default_provider=msg.get("default_provider", ""),
            default_contract=msg.get("default_contract", ""),
            placeholder=msg.get("placeholder"),
            document_archive=msg.get("document_archive"),
        )
    except (ValueError, RuntimeError) as err:
        _ws_error(connection, msg, err, "invalid_category")
        return
    connection.send_result(msg["id"], category)


@websocket_api.websocket_command(
    {
        vol.Required("type"): "bill_tracker/category/update",
        vol.Required("category_id"): str,
        **_CATEGORY_COMMON,
    }
)
@websocket_api.async_response
async def ws_category_update(hass, connection, msg):
    if msg.get("document_archive", {}).get("enabled") and not connection.user.is_admin:
        connection.send_error(msg["id"], "unauthorized", "Only administrators can configure PDF downloads")
        return
    try:
        category = await _manager(hass).async_update_category(
            msg["category_id"],
            name=msg["name"],
            interval_months=msg["interval_months"],
            enabled=msg["enabled"],
            exclude_from_estimates=msg.get("exclude_from_estimates"),
            default_payer_id=msg.get("default_payer_id"),
            color=msg.get("color"),
            consumption_unit=msg.get("consumption_unit", ""),
            default_provider=msg.get("default_provider", ""),
            default_contract=msg.get("default_contract", ""),
            placeholder=msg.get("placeholder"),
            document_archive=msg.get("document_archive"),
        )
    except (ValueError, RuntimeError) as err:
        _ws_error(connection, msg, err, "invalid_category")
        return
    if category is None:
        connection.send_error(msg["id"], "category_not_found", "Bill type not found")
        return
    connection.send_result(msg["id"], category)


@websocket_api.websocket_command(
    {vol.Required("type"): "bill_tracker/category/delete", vol.Required("category_id"): str}
)
@websocket_api.async_response
async def ws_category_delete(hass, connection, msg):
    try:
        deleted = await _manager(hass).async_delete_category(msg["category_id"])
    except (ValueError, RuntimeError) as err:
        _ws_error(connection, msg, err, "category_in_use")
        return
    connection.send_result(msg["id"], {"deleted": deleted})


_PAYER_COMMON = {
    vol.Required("name"): str,
    vol.Optional("share_percent", default=50.0): vol.All(
        vol.Coerce(float), vol.Range(min=0, max=100)
    ),
    vol.Optional("paypal_me", default=""): str,
    vol.Optional("payment_methods", default={}): dict,
    vol.Optional("preferred_payment_method", default=""): str,
    vol.Optional("enabled", default=True): bool,
}


@websocket_api.websocket_command(
    {vol.Required("type"): "bill_tracker/payer/add", **_PAYER_COMMON}
)
@websocket_api.async_response
async def ws_payer_add(hass, connection, msg):
    try:
        payer = await _manager(hass).async_add_payer(
            name=msg["name"],
            share_percent=msg["share_percent"],
            paypal_me=msg["paypal_me"],
            payment_methods=msg["payment_methods"],
            preferred_payment_method=msg["preferred_payment_method"],
            enabled=msg["enabled"],
        )
    except (ValueError, RuntimeError) as err:
        _ws_error(connection, msg, err, "invalid_payer")
        return
    connection.send_result(msg["id"], payer)


@websocket_api.websocket_command(
    {
        vol.Required("type"): "bill_tracker/payer/update",
        vol.Required("payer_id"): str,
        **_PAYER_COMMON,
    }
)
@websocket_api.async_response
async def ws_payer_update(hass, connection, msg):
    try:
        payer = await _manager(hass).async_update_payer(
            msg["payer_id"],
            name=msg["name"],
            share_percent=msg["share_percent"],
            paypal_me=msg["paypal_me"],
            payment_methods=msg["payment_methods"],
            preferred_payment_method=msg["preferred_payment_method"],
            enabled=msg["enabled"],
        )
    except (ValueError, RuntimeError) as err:
        _ws_error(connection, msg, err, "invalid_payer")
        return
    if payer is None:
        connection.send_error(msg["id"], "payer_not_found", "Payer not found")
        return
    connection.send_result(msg["id"], payer)


@websocket_api.websocket_command(
    {vol.Required("type"): "bill_tracker/payer/delete", vol.Required("payer_id"): str}
)
@websocket_api.async_response
async def ws_payer_delete(hass, connection, msg):
    try:
        deleted = await _manager(hass).async_delete_payer(msg["payer_id"])
    except (ValueError, RuntimeError) as err:
        _ws_error(connection, msg, err, "payer_in_use")
        return
    connection.send_result(msg["id"], {"deleted": deleted})


@websocket_api.websocket_command(
    {
        vol.Required("type"): "bill_tracker/settlement/add",
        vol.Required("from_payer_id"): str,
        vol.Required("to_payer_id"): str,
        vol.Required("amount"): vol.Coerce(float),
        vol.Optional("line_items", default=[]): [dict],
        vol.Optional("note", default=""): str,
    }
)
@websocket_api.async_response
async def ws_settlement_add(hass, connection, msg):
    try:
        item = await _manager(hass).async_add_settlement(
            from_payer_id=msg["from_payer_id"],
            to_payer_id=msg["to_payer_id"],
            amount=msg["amount"],
            line_items=msg["line_items"],
            note=msg["note"],
        )
    except (ValueError, RuntimeError) as err:
        _ws_error(connection, msg, err, "invalid_settlement")
        return
    connection.send_result(msg["id"], item)


@websocket_api.websocket_command(
    {
        vol.Required("type"): "bill_tracker/settlement/delete",
        vol.Required("settlement_id"): str,
    }
)
@websocket_api.async_response
async def ws_settlement_delete(hass, connection, msg):
    try:
        deleted = await _manager(hass).async_delete_settlement(msg["settlement_id"])
    except RuntimeError as err:
        _ws_error(connection, msg, err, "not_configured")
        return
    connection.send_result(msg["id"], {"deleted": deleted})


@websocket_api.websocket_command(
    {
        vol.Required("type"): "bill_tracker/import_csv",
        vol.Required("content"): vol.All(str, vol.Length(max=5_000_000)),
        vol.Optional("create_missing_categories", default=True): bool,
        vol.Optional("create_missing_payers", default=True): bool,
    }
)
@websocket_api.async_response
async def ws_import_csv(hass, connection, msg):
    try:
        result = await _manager(hass).async_import_csv(
            msg["content"],
            create_missing_categories=msg["create_missing_categories"],
            create_missing_payers=msg["create_missing_payers"],
        )
    except (ValueError, RuntimeError) as err:
        _ws_error(connection, msg, err, "invalid_csv")
        return
    connection.send_result(msg["id"], result)


@websocket_api.websocket_command(
    {
        vol.Required("type"): "bill_tracker/export",
        vol.Required("format"): vol.In(("csv", "xlsx", "pdf")),
        vol.Optional("from_month", default=""): str,
        vol.Optional("to_month", default=""): str,
        vol.Optional("status", default="all"): vol.In(("all", "paid", "unpaid")),
        vol.Optional("category_id", default="all"): str,
        vol.Optional("trend", default="both"): vol.In(("payments", "normalized", "both")),
        vol.Optional("language", default="en"): str,
    }
)
@websocket_api.async_response
async def ws_export(hass, connection, msg):
    try:
        payload, mime_type, extension = _manager(hass).export_data(
            file_format=msg["format"],
            from_month=msg.get("from_month") or None,
            to_month=msg.get("to_month") or None,
            status=msg["status"],
            category_id=msg.get("category_id") or "all",
            trend=msg["trend"],
            language=msg.get("language", "en"),
        )
    except (ValueError, RuntimeError) as err:
        _ws_error(connection, msg, err, "export_failed")
        return
    stamp = datetime.now().strftime("%Y%m%d-%H%M")
    from_part = (msg.get("from_month") or "all").replace("-", "")
    to_part = (msg.get("to_month") or "all").replace("-", "")
    filename = f"billy-{from_part}-{to_part}-{stamp}.{extension}"
    connection.send_result(
        msg["id"],
        {
            "filename": filename,
            "mime_type": mime_type,
            "content_base64": base64.b64encode(payload).decode("ascii"),
        },
    )


@websocket_api.websocket_command(
    {
        vol.Required("type"): "bill_tracker/export_recurring",
        vol.Required("format"): vol.In(("csv", "xlsx", "pdf")),
        vol.Optional("status", default="all"): vol.In(("all", "active", "inactive", "ended")),
        vol.Optional("kind", default="all"): str,
        vol.Optional("from_date", default=""): str,
        vol.Optional("to_date", default=""): str,
        vol.Optional("language", default="en"): str,
    }
)
@websocket_api.async_response
async def ws_export_recurring(hass, connection, msg):
    try:
        payload, mime_type, extension = _manager(hass).export_recurring_data(
            file_format=msg["format"],
            status=msg["status"],
            kind=msg.get("kind") or "all",
            from_date=msg.get("from_date") or None,
            to_date=msg.get("to_date") or None,
            language=msg.get("language", "en"),
        )
    except (ValueError, RuntimeError) as err:
        _ws_error(connection, msg, err, "export_failed")
        return
    stamp = datetime.now().strftime("%Y%m%d-%H%M")
    connection.send_result(
        msg["id"],
        {
            "filename": f"billy-recurring-{stamp}.{extension}",
            "mime_type": mime_type,
            "content_base64": base64.b64encode(payload).decode("ascii"),
        },
    )


@websocket_api.websocket_command({vol.Required("type"): "bill_tracker/export_template"})
@websocket_api.async_response
async def ws_export_template(hass, connection, msg):
    try:
        payload = _manager(hass).export_csv_template()
    except RuntimeError as err:
        _ws_error(connection, msg, err, "not_configured")
        return
    connection.send_result(
        msg["id"],
        {
            "filename": "billy-import-template.csv",
            "mime_type": "text/csv;charset=utf-8",
            "content_base64": base64.b64encode(payload).decode("ascii"),
        },
    )


@websocket_api.websocket_command({vol.Required("type"): "bill_tracker/backup/export"})
@websocket_api.async_response
async def ws_backup_export(hass, connection, msg):
    try:
        payload = _manager(hass).export_backup()
    except RuntimeError as err:
        _ws_error(connection, msg, err, "not_configured")
        return
    stamp = datetime.now().strftime("%Y%m%d-%H%M")
    connection.send_result(
        msg["id"],
        {
            "filename": f"billy-backup-{stamp}.json",
            "mime_type": "application/json;charset=utf-8",
            "content_base64": base64.b64encode(payload).decode("ascii"),
        },
    )


@websocket_api.websocket_command(
    {
        vol.Required("type"): "bill_tracker/backup/import",
        vol.Required("content"): vol.All(str, vol.Length(max=10_000_000)),
    }
)
@websocket_api.async_response
async def ws_backup_import(hass, connection, msg):
    try:
        result = await _manager(hass).async_import_backup(msg["content"])
    except (ValueError, RuntimeError) as err:
        _ws_error(connection, msg, err, "invalid_backup")
        return
    connection.send_result(msg["id"], result)


def _updater(hass: HomeAssistant) -> BillyUpdater:
    updater = hass.data.get(DOMAIN, {}).get("updater")
    if updater is None:
        raise RuntimeError("Billy is not configured yet")
    return updater


@websocket_api.websocket_command(
    {
        vol.Required("type"): "bill_tracker/update/status",
        vol.Optional("refresh", default=False): bool,
    }
)
@websocket_api.async_response
async def ws_update_status(hass, connection, msg):
    try:
        updater = _updater(hass)
    except RuntimeError as err:
        _ws_error(connection, msg, err, "not_configured")
        return
    if msg["refresh"]:
        await updater.async_check()
    connection.send_result(msg["id"], updater.as_dict())


@websocket_api.websocket_command({vol.Required("type"): "bill_tracker/update/install"})
@websocket_api.async_response
async def ws_update_install(hass, connection, msg):
    try:
        updater = _updater(hass)
        await updater.async_install()
    except RuntimeError as err:
        _ws_error(connection, msg, err, "update_failed")
        return
    except Exception as err:  # noqa: BLE001
        connection.send_error(msg["id"], "update_failed", str(err))
        return
    connection.send_result(msg["id"], updater.as_dict())
