"""Regression coverage for the midnight recurring synchronization event."""

import ast
import asyncio
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
INIT = ROOT / "custom_components" / "bill_tracker" / "__init__.py"


def test_midnight_sync_imports_and_fires_updated_event_when_unchanged():
    tree = ast.parse(INIT.read_text(encoding="utf-8"))
    imports = [
        node for node in tree.body
        if isinstance(node, ast.ImportFrom) and node.module == "const" and node.level == 1
    ]
    assert any("EVENT_UPDATED" in {alias.name for alias in node.names} for node in imports)

    setup = next(
        node for node in tree.body
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "async_setup_entry"
    )
    callback = next(
        node for node in setup.body
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "_sync_recurring_at_midnight"
    )
    module = ast.Module(body=[callback], type_ignores=[])
    ast.fix_missing_locations(module)
    fired = []

    async def unchanged():
        return False

    manager = SimpleNamespace(
        async_sync_scheduled_autopay=unchanged,
        async_sync_recurring_occurrences=unchanged,
        async_sync_income_occurrences=unchanged,
        async_sync_bill_placeholders=unchanged,
    )
    hass = SimpleNamespace(bus=SimpleNamespace(async_fire=fired.append))
    scope = {"manager": manager, "hass": hass, "EVENT_UPDATED": "bill_tracker_updated"}
    exec(compile(module, str(INIT), "exec"), scope)
    asyncio.run(scope["_sync_recurring_at_midnight"](None))
    assert fired == ["bill_tracker_updated"]
