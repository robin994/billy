"""Runtime checks for migrating the Lovelace resource from the legacy card to widgets."""

import ast
import asyncio
import inspect
import logging
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest


INIT = Path(__file__).resolve().parents[1] / "custom_components" / "bill_tracker" / "__init__.py"
NEW_URL = "/bill_tracker/billy-lovelace.js"
NEW_MODULE_URL = NEW_URL + "?v=0.17.3-r1"
OLD_URL = "/bill_tracker/bill-tracker-card.js"
OLD_MODULE_URL = OLD_URL + "?v=0.17.3-r1"


class ResourceStorageCollection:
    def __init__(self, rows=()):
        self.rows = [dict(row) for row in rows]
        self.updated = []
        self.created = []

    async def _async_ensure_loaded(self):
        pass

    def async_items(self):
        return self.rows

    async def async_update_item(self, item_id, config):
        self.updated.append((item_id, config))
        for row in self.rows:
            if row["id"] == item_id:
                row["url"] = config["url"]
                row["type"] = config["res_type"]
                return
        raise AssertionError(f"Unknown resource {item_id}")

    async def async_create_item(self, config):
        self.created.append(config)
        self.rows.append({
            "id": f"created-{len(self.rows)}",
            "url": config["url"],
            "type": config["res_type"],
        })


def register_lovelace_function(monkeypatch):
    # Exercise the real function without requiring a full Home Assistant runtime.
    module_names = (
        "homeassistant",
        "homeassistant.components",
        "homeassistant.components.lovelace",
        "homeassistant.components.lovelace.const",
        "homeassistant.components.lovelace.resources",
    )
    for name in module_names:
        module = ModuleType(name)
        if name in module_names[:3]:
            module.__path__ = []
        monkeypatch.setitem(sys.modules, name, module)
    sys.modules["homeassistant.components.lovelace.const"].LOVELACE_DATA = "lovelace"
    sys.modules[
        "homeassistant.components.lovelace.resources"
    ].ResourceStorageCollection = ResourceStorageCollection

    tree = ast.parse(INIT.read_text(encoding="utf-8"))
    function = next(
        node
        for node in tree.body
        if isinstance(node, ast.AsyncFunctionDef)
        and node.name == "_async_register_lovelace_resource"
    )
    namespace = {
        "HomeAssistant": object,
        "inspect": inspect,
        "CONF_URL": "url",
        "CONF_TYPE": "type",
        "CONF_ID": "id",
        "LOVELACE_BOOTSTRAP_URL": NEW_URL,
        "LOVELACE_BOOTSTRAP_MODULE_URL": NEW_MODULE_URL,
        "FRONTEND_URL": OLD_URL,
        "FRONTEND_MODULE_URL": OLD_MODULE_URL,
        "_LOGGER": logging.getLogger("test.billy.lovelace"),
    }
    exec(compile(ast.Module(body=[function], type_ignores=[]), str(INIT), "exec"), namespace)
    return namespace["_async_register_lovelace_resource"]


@pytest.mark.parametrize(
    ("rows", "updated_ids", "created_urls"),
    [
        ([], [], [NEW_MODULE_URL, OLD_MODULE_URL]),
        (
            [{"id": "old", "url": OLD_URL, "type": "module"}],
            ["old"],
            [NEW_MODULE_URL],
        ),
        (
            [{"id": "old", "url": OLD_URL + "?v=0.14.1-r2", "type": "module"}],
            ["old"],
            [NEW_MODULE_URL],
        ),
        (
            [{"id": "current", "url": NEW_MODULE_URL, "type": "module"}],
            [],
            [OLD_MODULE_URL],
        ),
        (
            [
                {"id": "old", "url": OLD_MODULE_URL, "type": "module"},
                {"id": "current", "url": NEW_URL + "?v=0.14.1-r2", "type": "module"},
            ],
            ["current"],
            [],
        ),
        (
            [{"id": "old", "url": OLD_URL, "type": "js"}],
            ["old"],
            [NEW_MODULE_URL],
        ),
    ],
)
def test_lovelace_resource_migration(monkeypatch, rows, updated_ids, created_urls):
    register_resource = register_lovelace_function(monkeypatch)
    resources = ResourceStorageCollection(rows)
    hass = SimpleNamespace(data={"lovelace": SimpleNamespace(resources=resources)})

    asyncio.run(register_resource(hass))
    assert [row["url"] for row in resources.created] == created_urls
    assert [item_id for item_id, _ in resources.updated] == updated_ids
    for module_url in (NEW_MODULE_URL, OLD_MODULE_URL):
        matching = [row for row in resources.rows if row["url"] == module_url]
        assert len(matching) == 1
        assert matching[0]["type"] == "module"

    # Re-running setup must not create or update either registered resource.
    resources.updated.clear()
    resources.created.clear()
    asyncio.run(register_resource(hass))
    assert resources.updated == []
    assert resources.created == []


def test_resource_registration_does_not_overwrite_unrelated_lovelace_resources(monkeypatch):
    register_resource = register_lovelace_function(monkeypatch)
    external = {"id": "other", "url": "/local/community-card.js", "type": "module"}
    resources = ResourceStorageCollection([external])
    hass = SimpleNamespace(data={"lovelace": SimpleNamespace(resources=resources)})
    asyncio.run(register_resource(hass))

    assert resources.rows[0] == external
    assert resources.created == [
        {"res_type": "module", "url": NEW_MODULE_URL},
        {"res_type": "module", "url": OLD_MODULE_URL},
    ]
