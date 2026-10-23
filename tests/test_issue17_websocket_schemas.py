"""Regression tests for reports on Billy issue #17 after v0.17.1.

Use the actual websocket schema declarations, not a reconstructed subset, so
an editor field omitted from the server schema fails before the handler runs.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest
import voluptuous as vol

from test_bill_placeholders import manager, run

SOURCE = Path(__file__).resolve().parents[1] / "custom_components" / "bill_tracker" / "__init__.py"
TREE = ast.parse(SOURCE.read_text(encoding="utf-8"))


def _schema(name, command):
    assignment = next(
        node for node in TREE.body
        if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == name for target in node.targets)
    )
    values = eval(
        compile(ast.Expression(assignment.value), str(SOURCE), "eval"),
        {"vol": vol, "SUPPORTED_INTERVALS": (1, 2, 3, 4, 6, 12),
         "RECURRING_INTERVALS": (1, 2, 3, 4, 6, 12),
         "RECURRING_KINDS": ("subscription", "mortgage", "installment", "recurring"),
         "_SPLIT_ITEM_SCHEMA": {
             vol.Required("payer_id"): str,
             vol.Required("percentage"): vol.Coerce(float),
         }},
    )
    return vol.Schema({vol.Required("type"): command, **values})


HOUSE_ID = "d736a68ed48f4935ac036b4ecef69b31"


def _installment_request(command):
    payload = {
        "type": command,
        "name": "Mortgage installments",
        "kind": "installment",
        "house_id": HOUSE_ID,
        "amount": 500,
        "total_amount": 10520.09,
        "interval_months": 1,
        "start_date": "2026-02-01",
        "end_date": "",
        "installment_count": 21,
        "auto_renew": False,
        "renewal_interval_months": 12,
        "provider": "",
        "contract": "",
        "color": "#536d9a",
        "note": "",
        "active": True,
    }
    if command.endswith("/update"):
        payload["recurring_id"] = "existing-plan"
    return payload


@pytest.mark.parametrize("command", ["bill_tracker/recurring/add", "bill_tracker/recurring/update"])
def test_issue_17_recurring_websocket_accepts_selected_house(command):
    payload = _installment_request(command)
    common = _schema("_RECURRING_COMMON", command)
    # Handler-specific path IDs are declared separately from _RECURRING_COMMON.
    if command.endswith("/update"):
        payload.pop("recurring_id")
    parsed = common(payload)
    assert parsed["house_id"] == HOUSE_ID
    assert parsed["total_amount"] == 10520.09
    assert parsed["installment_count"] == 21
    with pytest.raises(vol.Invalid):
        common({**payload, "house_id": 123})


def _category_request(command, *, provider="", contract=""):
    payload = {
        "type": command,
        "name": "Electricity",
        "interval_months": 1,
        "enabled": True,
        "exclude_from_estimates": False,
        "default_payer_id": "",
        "color": "#03a9f4",
        "consumption_unit": "kWh",
        "default_provider": "",
        "default_contract": "",
        "document_archive": {
            "enabled": False, "subpath": "billy/documents", "source_host": "",
        },
        "placeholder": {
            "enabled": False, "day": 1, "amount_mode": "last",
            "fixed_amount": 0, "due_day": None, "start_month": "",
            "provider": provider, "contract": contract,
        },
        "house_placeholders": {
            HOUSE_ID: {
                "enabled": False, "day": 1, "amount_mode": "last",
                "fixed_amount": 0, "due_day": None, "start_month": "",
                "provider": provider, "contract": contract,
            },
        },
    }
    return payload


@pytest.mark.parametrize("command", ["bill_tracker/category/add", "bill_tracker/category/update"])
@pytest.mark.parametrize("provider,contract", [("", ""), ("Power Utility", "Account 42")])
def test_issue_17_bill_type_websocket_accepts_optional_placeholder_metadata(
    command, provider, contract,
):
    parsed = _schema("_CATEGORY_COMMON", command)(
        _category_request(command, provider=provider, contract=contract)
    )
    assert parsed["placeholder"]["provider"] == provider
    assert parsed["placeholder"]["contract"] == contract
    assert parsed["house_placeholders"][HOUSE_ID]["provider"] == provider
    assert parsed["house_placeholders"][HOUSE_ID]["contract"] == contract


def test_issue_17_backend_keeps_house_validation_and_optional_bill_metadata(manager):
    existing = manager.default_house_id
    rule = run(manager.async_add_recurring(
        name="Mortgage installments", kind="installment",
        house_id=existing, amount=500, total_amount=10520.09,
        installment_count=21, interval_months=1, start_date="2026-02-01",
    ))
    assert rule["house_id"] == existing
    with pytest.raises(ValueError, match="House not found"):
        run(manager.async_add_recurring(
            name="Wrong house", kind="installment", house_id="missing-house",
            amount=500, installment_count=21, interval_months=1, start_date="2026-02-01",
        ))
    category = manager.categories[0]
    updated = run(manager.async_update_category(
        category["id"], name=category["name"], interval_months=1, enabled=True,
        placeholder={"enabled": False, "provider": "", "contract": ""},
        house_placeholders={existing: {
            "enabled": False, "provider": "", "contract": "",
        }},
    ))
    assert updated["placeholder"]["provider"] == ""
    assert updated["placeholder"]["contract"] == ""
    assert updated["house_placeholders"][existing]["provider"] == ""
    assert updated["house_placeholders"][existing]["contract"] == ""
