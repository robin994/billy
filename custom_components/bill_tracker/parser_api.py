"""WebSocket API for Billy automatic parser management."""
from __future__ import annotations

import base64
from typing import Any

import voluptuous as vol
from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .parser.manager import ParserManager

_REGISTERED_KEY = "parser_ws_registered"


def _manager(hass: HomeAssistant) -> ParserManager:
    manager = hass.data.get(DOMAIN, {}).get("parser_manager")
    if manager is None:
        raise RuntimeError("Billy automatic parsing is not configured")
    return manager


def register_parser_websockets(hass: HomeAssistant) -> None:
    domain_data = hass.data.setdefault(DOMAIN, {})
    if domain_data.get(_REGISTERED_KEY):
        return
    for command in (
        ws_parser_list,
        ws_parser_refresh,
        ws_parser_install,
        ws_parser_uninstall,
        ws_parser_configure,
        ws_parser_custom_save,
        ws_parser_custom_delete,
        ws_parser_custom_export,
        ws_parser_test,
        ws_parser_sources_set,
        ws_parser_feedback,
        ws_parser_imports,
        ws_parser_import_approve,
        ws_parser_import_reject,
        ws_parser_import_retry,
    ):
        websocket_api.async_register_command(hass, command)
    domain_data[_REGISTERED_KEY] = True


@websocket_api.websocket_command({vol.Required("type"): "bill_tracker/parser/list"})
@websocket_api.async_response
async def ws_parser_list(hass, connection, msg):
    try:
        manager = _manager(hass)
        result = {
            "catalog": manager.catalog_snapshot(),
            "installed": manager.installed_snapshot(),
            "sources": manager.sources_snapshot(),
            "imports": manager.imports_snapshot(limit=50),
            "diagnostic": manager.ingestion_diagnostic(),
        }
    except RuntimeError as err:
        connection.send_error(msg["id"], "not_configured", str(err))
        return
    connection.send_result(msg["id"], result)


@websocket_api.websocket_command({vol.Required("type"): "bill_tracker/parser/refresh"})
@websocket_api.async_response
async def ws_parser_refresh(hass, connection, msg):
    try:
        result = await _manager(hass).async_refresh_catalog()
    except Exception as err:  # noqa: BLE001
        connection.send_error(msg["id"], "catalog_error", str(err))
        return
    connection.send_result(msg["id"], result)


@websocket_api.websocket_command(
    {
        vol.Required("type"): "bill_tracker/parser/install",
        vol.Required("parser_id"): str,
        vol.Required("category_id"): str,
        vol.Optional("enabled", default=True): bool,
        vol.Optional("auto_import", default=False): bool,
        vol.Optional("default_payer_id"): str,
        vol.Optional("default_split"): list,
    }
)
@websocket_api.async_response
async def ws_parser_install(hass, connection, msg):
    try:
        result = await _manager(hass).async_install(
            msg["parser_id"],
            category_id=msg["category_id"],
            enabled=msg["enabled"],
            auto_import=msg["auto_import"],
            default_payer_id=msg.get("default_payer_id"),
            default_split=msg.get("default_split"),
        )
    except Exception as err:  # noqa: BLE001
        connection.send_error(msg["id"], "install_error", str(err))
        return
    connection.send_result(msg["id"], result)


@websocket_api.websocket_command(
    {vol.Required("type"): "bill_tracker/parser/uninstall", vol.Required("parser_id"): str}
)
@websocket_api.async_response
async def ws_parser_uninstall(hass, connection, msg):
    try:
        deleted = await _manager(hass).async_uninstall(msg["parser_id"])
    except Exception as err:  # noqa: BLE001
        connection.send_error(msg["id"], "uninstall_error", str(err))
        return
    connection.send_result(msg["id"], {"deleted": deleted})


@websocket_api.websocket_command(
    {
        vol.Required("type"): "bill_tracker/parser/configure",
        vol.Required("parser_id"): str,
        vol.Required("category_id"): str,
        vol.Required("enabled"): bool,
        vol.Required("auto_import"): bool,
        vol.Optional("default_payer_id"): str,
        vol.Optional("default_split"): list,
    }
)
@websocket_api.async_response
async def ws_parser_configure(hass, connection, msg):
    try:
        result = await _manager(hass).async_configure(
            msg["parser_id"],
            category_id=msg["category_id"],
            enabled=msg["enabled"],
            auto_import=msg["auto_import"],
            default_payer_id=msg.get("default_payer_id"),
            default_split=msg.get("default_split"),
        )
    except Exception as err:  # noqa: BLE001
        connection.send_error(msg["id"], "configure_error", str(err))
        return
    connection.send_result(msg["id"], result)


@websocket_api.websocket_command(
    {
        vol.Required("type"): "bill_tracker/parser/custom/save",
        vol.Required("content"): str,
        vol.Required("category_id"): str,
        vol.Optional("expected_parser_id"): str,
        vol.Optional("enabled", default=True): bool,
        vol.Optional("auto_import", default=False): bool,
        vol.Optional("default_payer_id"): str,
        vol.Optional("default_split"): list,
    }
)
@websocket_api.async_response
async def ws_parser_custom_save(hass, connection, msg):
    try:
        result = await _manager(hass).async_save_custom(
            msg["content"],
            category_id=msg["category_id"],
            expected_parser_id=msg.get("expected_parser_id"),
            enabled=msg["enabled"],
            auto_import=msg["auto_import"],
            default_payer_id=msg.get("default_payer_id"),
            default_split=msg.get("default_split"),
        )
    except Exception as err:  # noqa: BLE001
        connection.send_error(msg["id"], "custom_parser_error", str(err))
        return
    connection.send_result(msg["id"], result)


@websocket_api.websocket_command(
    {vol.Required("type"): "bill_tracker/parser/custom/delete", vol.Required("parser_id"): str}
)
@websocket_api.async_response
async def ws_parser_custom_delete(hass, connection, msg):
    try:
        deleted = await _manager(hass).async_delete_custom(msg["parser_id"])
    except Exception as err:  # noqa: BLE001
        connection.send_error(msg["id"], "custom_parser_error", str(err))
        return
    connection.send_result(msg["id"], {"deleted": deleted})


@websocket_api.websocket_command(
    {vol.Required("type"): "bill_tracker/parser/custom/export", vol.Required("parser_id"): str}
)
@websocket_api.async_response
async def ws_parser_custom_export(hass, connection, msg):
    try:
        filename, content = await _manager(hass).async_export_custom(msg["parser_id"])
    except Exception as err:  # noqa: BLE001
        connection.send_error(msg["id"], "custom_parser_error", str(err))
        return
    connection.send_result(
        msg["id"],
        {
            "filename": filename,
            "mime_type": "application/yaml",
            "content_base64": base64.b64encode(content.encode("utf-8")).decode("ascii"),
        },
    )


@websocket_api.websocket_command(
    {
        vol.Required("type"): "bill_tracker/parser/test",
        vol.Required("content"): str,
        vol.Optional("sender", default=""): str,
        vol.Optional("subject", default=""): str,
        vol.Optional("email_text", default=""): str,
        vol.Optional("documents", default={}): dict,
    }
)
@websocket_api.async_response
async def ws_parser_test(hass, connection, msg):
    try:
        documents: dict[str, str] = {
            str(key): str(value) for key, value in dict(msg.get("documents") or {}).items()
        }
        result = await _manager(hass).async_test(
            msg["content"],
            sender=msg["sender"],
            subject=msg["subject"],
            email_text=msg["email_text"],
            documents=documents,
        )
    except Exception as err:  # noqa: BLE001
        connection.send_error(msg["id"], "test_error", str(err))
        return
    connection.send_result(msg["id"], result)


@websocket_api.websocket_command(
    {
        vol.Required("type"): "bill_tracker/parser/sources/set",
        vol.Required("entry_ids"): [str],
    }
)
@websocket_api.async_response
async def ws_parser_sources_set(hass, connection, msg):
    try:
        selected = await _manager(hass).async_set_sources(msg["entry_ids"])
    except Exception as err:  # noqa: BLE001
        connection.send_error(msg["id"], "source_error", str(err))
        return
    connection.send_result(msg["id"], {"entry_ids": selected})


@websocket_api.websocket_command(
    {
        vol.Required("type"): "bill_tracker/parser/feedback",
        vol.Required("parser_id"): str,
        vol.Required("result"): vol.In(["working", "partial", "failed"]),
    }
)
@websocket_api.async_response
async def ws_parser_feedback(hass, connection, msg):
    try:
        result = _manager(hass).community_feedback_payload(
            msg["parser_id"],
            msg["result"],
        )
    except Exception as err:  # noqa: BLE001
        connection.send_error(msg["id"], "feedback_error", str(err))
        return
    connection.send_result(msg["id"], result)


@websocket_api.websocket_command(
    {
        vol.Required("type"): "bill_tracker/parser/imports",
        vol.Optional("status"): vol.In(["pending", "imported", "rejected", "error"]),
        vol.Optional("limit", default=100): vol.All(vol.Coerce(int), vol.Range(min=1, max=500)),
    }
)
@websocket_api.async_response
async def ws_parser_imports(hass, connection, msg):
    try:
        result = _manager(hass).imports_snapshot(msg.get("status"), msg["limit"])
    except Exception as err:  # noqa: BLE001
        connection.send_error(msg["id"], "import_error", str(err))
        return
    connection.send_result(msg["id"], result)


@websocket_api.websocket_command(
    {vol.Required("type"): "bill_tracker/parser/import/approve", vol.Required("import_id"): str}
)
@websocket_api.async_response
async def ws_parser_import_approve(hass, connection, msg):
    try:
        result = await _manager(hass).async_approve(msg["import_id"])
    except Exception as err:  # noqa: BLE001
        connection.send_error(msg["id"], "import_error", str(err))
        return
    connection.send_result(msg["id"], result)


@websocket_api.websocket_command(
    {vol.Required("type"): "bill_tracker/parser/import/reject", vol.Required("import_id"): str}
)
@websocket_api.async_response
async def ws_parser_import_reject(hass, connection, msg):
    try:
        result = await _manager(hass).async_reject(msg["import_id"])
    except Exception as err:  # noqa: BLE001
        connection.send_error(msg["id"], "import_error", str(err))
        return
    connection.send_result(msg["id"], result)


@websocket_api.websocket_command(
    {vol.Required("type"): "bill_tracker/parser/import/retry", vol.Required("import_id"): str}
)
@websocket_api.async_response
async def ws_parser_import_retry(hass, connection, msg):
    try:
        result = await _manager(hass).async_retry(msg["import_id"])
    except Exception as err:  # noqa: BLE001
        connection.send_error(msg["id"], "import_error", str(err))
        return
    connection.send_result(msg["id"], result)
