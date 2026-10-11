"""Validate the actual WebSocket schemas without requiring a running HA instance."""
import ast
import asyncio
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
import voluptuous as vol

ROOT = Path(__file__).resolve().parents[1]
API = ROOT / "custom_components" / "bill_tracker" / "parser_api.py"


def _command(name):
    tree = ast.parse(API.read_text(encoding="utf-8"))
    function = next(
        node for node in tree.body
        if isinstance(node, ast.AsyncFunctionDef) and node.name == name
    )
    decorator = next(
        node for node in function.decorator_list
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "websocket_command"
    )
    schema = eval(
        compile(ast.Expression(decorator.args[0]), str(API), "eval"),
        {"vol": vol},
    )
    function.decorator_list = []
    module = ast.Module(body=[function], type_ignores=[])
    ast.fix_missing_locations(module)
    namespace = {}
    exec(compile(module, str(API), "exec"), namespace)
    # HA supplies the common request ID in addition to each command's schema.
    return vol.Schema(schema).extend({vol.Required("id"): int}), namespace[name]


def _save_request(**kwargs):
    return {
        "id": 1,
        "type": "bill_tracker/parser/custom/save",
        "content": "schema: 1\nid: gr.protergia.electricity\nversion: 1\n",
        "category_id": "electricity",
        **kwargs,
    }


@pytest.mark.parametrize("editing", [False, True])
def test_custom_save_validates_and_forwards_original_id(editing):
    schema, handler = _command("ws_parser_custom_save")
    request = _save_request(**({"expected_parser_id": "gr.protergia.electricity"} if editing else {}))
    message = schema(request)
    manager = SimpleNamespace(async_save_custom=AsyncMock(return_value={"id": "gr.protergia.electricity"}))
    handler.__globals__["_manager"] = lambda _hass: manager
    connection = SimpleNamespace(send_result=Mock(), send_error=Mock())
    asyncio.run(handler(None, connection, message))
    manager.async_save_custom.assert_awaited_once_with(
        message["content"], category_id="electricity",
        expected_parser_id="gr.protergia.electricity" if editing else None,
        enabled=True, auto_import=False, default_payer_id=None, default_split=None,
    )
    connection.send_result.assert_called_once_with(1, {"id": "gr.protergia.electricity"})
    connection.send_error.assert_not_called()


@pytest.mark.parametrize("invalid_id", [42, None, ["gr.protergia.electricity"]])
def test_custom_save_rejects_non_string_original_id(invalid_id):
    schema, _handler = _command("ws_parser_custom_save")
    with pytest.raises(vol.Invalid):
        schema(_save_request(expected_parser_id=invalid_id))


def test_custom_save_rejects_unknown_fields():
    schema, _handler = _command("ws_parser_custom_save")
    with pytest.raises(vol.Invalid):
        schema(_save_request(unexpected="value"))


def test_install_does_not_accept_custom_edit_identity():
    schema, _handler = _command("ws_parser_install")
    with pytest.raises(vol.Invalid):
        schema({
            "id": 1, "type": "bill_tracker/parser/install",
            "parser_id": "gr.protergia.electricity", "category_id": "electricity",
            "expected_parser_id": "gr.protergia.electricity",
        })


def test_custom_save_reports_an_identity_change_as_an_error():
    schema, handler = _command("ws_parser_custom_save")
    message = schema(_save_request(expected_parser_id="gr.protergia.electricity"))
    manager = SimpleNamespace(async_save_custom=AsyncMock(
        side_effect=ValueError("Custom parser ID cannot be changed while editing")
    ))
    handler.__globals__["_manager"] = lambda _hass: manager
    connection = SimpleNamespace(send_result=Mock(), send_error=Mock())
    asyncio.run(handler(None, connection, message))
    connection.send_error.assert_called_once_with(
        1, "custom_parser_error", "Custom parser ID cannot be changed while editing"
    )
    connection.send_result.assert_not_called()


@pytest.mark.parametrize("changed_id", [False, True])
def test_manager_preserves_custom_identity_and_payment_defaults(changed_id):
    path = ROOT / "custom_components" / "bill_tracker" / "parser" / "manager.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    cls = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "ParserManager")
    method = next(node for node in cls.body if isinstance(node, ast.AsyncFunctionDef) and node.name == "async_save_custom")
    module = ast.Module(body=[
        ast.ImportFrom(module="__future__", names=[ast.alias(name="annotations")], level=0),
        method,
    ], type_ignores=[])
    ast.fix_missing_locations(module)
    parser_id = "gr.other.electricity" if changed_id else "gr.protergia.electricity"
    namespace = {"datetime": datetime, "load_parser_yaml": lambda _content: {"id": parser_id, "version": 2}}
    exec(compile(module, str(path), "exec"), namespace)
    original_id = "gr.protergia.electricity"
    split = [{"payer_id": "payer-1", "percentage": 100}]
    existing = {"id": original_id, "default_payer_id": "payer-1", "default_split": split}
    storage = SimpleNamespace(
        data={"installed": {}, "custom": {original_id: existing}},
        async_write_custom=AsyncMock(return_value="custom/parser.yaml"),
        async_save=AsyncMock(),
    )
    manager = SimpleNamespace(storage=storage, parsers={}, _ensure_category=lambda _category: None)
    call = namespace["async_save_custom"](
        manager, "updated YAML", category_id="electricity", expected_parser_id=original_id,
    )
    if changed_id:
        with pytest.raises(ValueError, match="Custom parser ID cannot be changed while editing"):
            asyncio.run(call)
        storage.async_write_custom.assert_not_awaited()
        storage.async_save.assert_not_awaited()
        assert storage.data["custom"] == {original_id: existing}
    else:
        result = asyncio.run(call)
        storage.async_write_custom.assert_awaited_once_with(original_id, "updated YAML")
        storage.async_save.assert_awaited_once()
        assert list(storage.data["custom"]) == [original_id]
        assert result["default_payer_id"] == "payer-1"
        assert result["default_split"] == split
