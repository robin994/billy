from __future__ import annotations

import ast
from calendar import monthrange
from collections import defaultdict
from datetime import date
from math import isfinite
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANAGER = ROOT / "custom_components" / "bill_tracker" / "manager.py"
INIT = ROOT / "custom_components" / "bill_tracker" / "__init__.py"
PANEL = ROOT / "custom_components" / "bill_tracker" / "frontend" / "billy-panel.js"


def _recurring_helper_class():
    tree = ast.parse(MANAGER.read_text(encoding="utf-8"))
    source_cls = next(
        node for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "BillTrackerManager"
    )
    names = {
        "_normalize_optional_iso_date",
        "_normalize_optional_text",
        "_normalize_color",
        "_normalize_recurring_payload",
        "_add_months_date",
        "_recurring_occurrence",
        "_next_recurring_due",
        "_recurring_occurrences_between",
        "recurring_month_items",
        "recurring_history_items",
        "cashflow_monthly_totals",
        "_month_range",
        "_next_month",
        "_add_months",
        "_recurring_progress",
        "_next_renewal_date",
        "payer",
        "active_payers",
        "default_split",
        "_validate_optional_payer",
        "_resolve_expense_split",
        "_normalize_split",
    }
    methods = [
        node for node in source_cls.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in names
    ]
    cls = ast.ClassDef(
        name="RecurringHarness",
        bases=[],
        keywords=[],
        body=methods,
        decorator_list=[],
    )
    module = ast.Module(body=[cls], type_ignores=[])
    ast.fix_missing_locations(module)
    ns = {
        "Any": object,
        "date": date,
        "monthrange": monthrange,
        "isfinite": isfinite,
        "defaultdict": defaultdict,
        "RECURRING_KINDS": ("subscription", "mortgage", "installment", "recurring"),
        "RECURRING_INTERVALS": (1, 2, 3, 4, 6, 12),
        "FALLBACK_COLORS": ("#5B8FF9", "#5AD8A6", "#5D7092", "#F6BD16"),
    }
    exec(compile(module, str(MANAGER), "exec"), ns)
    # Some extracted static helpers reference the real class by name.
    ns["BillTrackerManager"] = ns["RecurringHarness"]
    return ns["RecurringHarness"]


def test_recurring_schedule_preserves_anchor_day_and_clips_short_months():
    manager = _recurring_helper_class()()
    manager.payers = []
    item = manager._normalize_recurring_payload(
        name="Service",
        kind="subscription",
        amount=12.99,
        interval_months=1,
        start_date="2026-01-31",
        end_date=None,
        auto_renew=True,
        renewal_interval_months=12,
        installment_count=None,
        provider="",
        contract="",
        note="",
        active=True,
    )
    assert manager._recurring_occurrence(item, 0) == date(2026, 1, 31)
    assert manager._recurring_occurrence(item, 1) == date(2026, 2, 28)
    assert manager._recurring_occurrence(item, 2) == date(2026, 3, 31)


def test_recurring_without_payers_keeps_requested_active_state():
    manager = _recurring_helper_class()()
    manager.payers = []
    item = manager._normalize_recurring_payload(
        name="Mortgage",
        kind="mortgage",
        amount=800,
        interval_months=1,
        start_date="2026-01-15",
        end_date=None,
        auto_renew=False,
        renewal_interval_months=12,
        installment_count=None,
        provider="Bank",
        contract="",
        note="",
        active=True,
    )
    assert item["active"] is True
    assert item["payer_id"] is None


def test_monthly_cashflow_includes_recurring_charges_in_their_due_month():
    manager = _recurring_helper_class()()
    manager.monthly_totals = lambda: [
        {
            "key": "2026-08",
            "year": 2026,
            "month": 8,
            "total": 120.0,
            "categories": {"Electricity": 120.0},
        }
    ]
    manager.recurring_history_items = lambda: [
        {"name": "Internet", "amount": 30.0, "due_date": "2026-08-01"},
    ]

    august = next(row for row in manager.cashflow_monthly_totals() if row["key"] == "2026-08")
    assert august["bill_total"] == 120.0
    assert august["recurring_total"] == 30.0
    assert august["total"] == 150.0
    assert august["categories"] == {"Electricity": 120.0}


def test_current_month_recurring_includes_mortgage_rules():
    manager = _recurring_helper_class()()
    manager.payers = []
    mortgage = manager._normalize_recurring_payload(
        name="Home mortgage",
        kind="mortgage",
        amount=800,
        interval_months=1,
        start_date="2026-01-15",
        end_date=None,
        auto_renew=False,
        renewal_interval_months=12,
        installment_count=None,
        provider="Bank",
        contract="",
        note="",
        active=True,
    )
    mortgage["id"] = "mortgage"
    manager.recurring_expenses = [mortgage]

    rows = manager.recurring_month_items(2026, 8)

    assert len(rows) == 1
    assert rows[0]["id"] == "mortgage"
    assert rows[0]["kind"] == "mortgage"
    assert rows[0]["amount"] == 800
    assert rows[0]["due_date"] == "2026-08-15"


def test_recurring_chart_history_starts_from_activation_not_creation_date():
    manager = _recurring_helper_class()()
    manager.payers = []
    today = date.today()
    start = date(today.year - 1, today.month, 15)
    mortgage = manager._normalize_recurring_payload(
        name="Home mortgage",
        kind="mortgage",
        amount=800,
        interval_months=1,
        start_date=start.isoformat(),
        end_date=None,
        auto_renew=False,
        renewal_interval_months=12,
        installment_count=None,
        provider="Bank",
        contract="",
        note="",
        active=True,
    )
    mortgage.update({"id": "mortgage", "created_at": today.isoformat()})
    manager.recurring_expenses = [mortgage]

    rows = manager.recurring_history_items()

    assert rows[0]["due_date"] == start.isoformat()
    assert rows[0]["id"] == "mortgage"
    assert rows[0]["kind"] == "mortgage"
    assert rows[0]["amount"] == 800
    assert len(rows) >= 13


def test_installment_count_calculates_last_due_and_stops_series():
    manager = _recurring_helper_class()()
    manager.payers = []
    item = manager._normalize_recurring_payload(
        name="Phone",
        kind="installment",
        amount=50,
        interval_months=1,
        start_date="2026-01-15",
        end_date=None,
        auto_renew=True,
        renewal_interval_months=12,
        installment_count=3,
        provider="",
        contract="",
        note="",
        active=True,
    )
    assert item["auto_renew"] is False
    assert item["end_date"] == "2026-03-15"
    assert manager._recurring_occurrence(item, 2) == date(2026, 3, 15)
    assert manager._recurring_occurrence(item, 3) is None


def test_auto_renew_expiration_is_a_renewal_marker_not_forecast_stop():
    manager = _recurring_helper_class()()
    manager.payers = []
    item = manager._normalize_recurring_payload(
        name="Annual contract",
        kind="subscription",
        amount=20,
        interval_months=1,
        start_date="2025-06-01",
        end_date="2026-06-01",
        auto_renew=True,
        renewal_interval_months=12,
        installment_count=None,
        provider="",
        contract="",
        note="",
        active=True,
    )
    assert manager._next_recurring_due(item, date(2026, 8, 1)) == date(2026, 8, 1)
    assert manager._next_renewal_date(item, date(2026, 8, 1)) == "2027-06-01"


def test_recurring_expenses_are_in_snapshot_forecast_and_persistence():
    source = MANAGER.read_text(encoding="utf-8")
    for token in (
        'self.recurring_expenses: list[dict[str, Any]] = []',
        'self.recurring_occurrences: list[dict[str, Any]] = []',
        '"recurring_expenses": [self._public_recurring_expense(x)',
        '"recurring_total": recurring_total',
        '"recurring_next_month"',
        '"recurring_monthly_equivalent"',
        '"installment_remaining_total"',
        '"recurring_expenses": self.recurring_expenses',
        '"recurring_occurrences": self.recurring_occurrences',
        'def _migrate_recurring_expenses',
        'def _migrate_recurring_occurrences',
    ):
        assert token in source


def test_recurring_websocket_crud_is_registered():
    source = INIT.read_text(encoding="utf-8")
    for token in (
        '"bill_tracker/recurring/add"',
        '"bill_tracker/recurring/update"',
        '"bill_tracker/recurring/set_active"',
        '"bill_tracker/recurring/set_reimbursement"',
        '"bill_tracker/recurring/delete"',
        'ws_recurring_add',
        'ws_recurring_update',
        'ws_recurring_set_active',
        'ws_recurring_set_reimbursement',
        'ws_recurring_delete',
    ):
        assert token in source


def test_sidebar_has_native_recurring_management_and_custom_parser_editor():
    panel = PANEL.read_text(encoding="utf-8")
    parser_panel = (
        ROOT
        / "custom_components"
        / "bill_tracker"
        / "frontend"
        / "billy-parser-manager.js"
    ).read_text(encoding="utf-8")
    for token in (
        "class BillyRecurring",
        '<billy-recurring id="recurring-panel">',
        'data-view="recurring"',
        "bill_tracker/recurring/add",
        "bill_tracker/recurring/update",
        "bill_tracker/recurring/set_active",
        "bill_tracker/recurring/set_reimbursement",
        "bill_tracker/recurring/delete",
        "recurringOverview",
        "recurring_monthly_equivalent",
        'id="recurring-reimbursement"',
        "data-recurring-reimbursements",
        "recurring-split-input",
    ):
        assert token in panel
    for token in (
        'id="new-custom"',
        "bill_tracker/parser/custom/save",
        "bill_tracker/parser/custom/export",
        "bill_tracker/parser/test",
    ):
        assert token in parser_panel


def _recurring_split_harness_class():
    tree = ast.parse(MANAGER.read_text(encoding="utf-8"))
    source_cls = next(
        node for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "BillTrackerManager"
    )
    names = {
        "payer",
        "active_payers",
        "default_split",
        "_validate_optional_payer",
        "_resolve_expense_split",
        "_normalize_split",
        "_normalize_optional_iso_date",
        "_normalize_optional_text",
        "_normalize_color",
        "_normalize_recurring_payload",
        "_add_months_date",
        "_recurring_occurrence",
        "_next_recurring_due",
        "_recurring_occurrences_between",
        "_recurring_tracking_start",
        "_sync_recurring_occurrences",
        "_sort",
    }
    methods = [
        node for node in source_cls.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in names
    ]
    cls = ast.ClassDef(
        name="RecurringSplitHarness",
        bases=[],
        keywords=[],
        body=methods,
        decorator_list=[],
    )
    module = ast.Module(body=[cls], type_ignores=[])
    ast.fix_missing_locations(module)
    ns = {
        "Any": object,
        "date": date,
        "datetime": __import__("datetime").datetime,
        "monthrange": monthrange,
        "isfinite": isfinite,
        "defaultdict": defaultdict,
        "RECURRING_KINDS": ("subscription", "mortgage", "installment", "recurring"),
        "RECURRING_INTERVALS": (1, 2, 3, 4, 6, 12),
        "FALLBACK_COLORS": ("#5B8FF9", "#5AD8A6", "#5D7092", "#F6BD16"),
    }
    exec(compile(module, str(MANAGER), "exec"), ns)
    return ns["RecurringSplitHarness"]


def test_recurring_split_materialization_starts_from_latest_due_not_full_history():
    manager = _recurring_split_harness_class()()
    manager.payers = [
        {"id": "a", "name": "A", "share_percent": 50, "enabled": True},
        {"id": "b", "name": "B", "share_percent": 50, "enabled": True},
    ]
    manager.expenses = []
    manager.settlements = []
    manager.recurring_occurrences = []
    item = manager._normalize_recurring_payload(
        name="Mortgage",
        kind="mortgage",
        amount=800,
        interval_months=1,
        start_date="2024-01-15",
        end_date=None,
        auto_renew=False,
        renewal_interval_months=12,
        installment_count=None,
        payer_id="a",
        split=[
            {"payer_id": "a", "percentage": 50},
            {"payer_id": "b", "percentage": 50},
        ],
    )
    item["id"] = "mortgage"
    item["created_at"] = "2026-08-26T00:00:00+02:00"
    item["reimbursement_tracking_start_date"] = manager._recurring_tracking_start(
        item, on_or_after=date(2026, 8, 1)
    )
    manager.recurring_expenses = [item]

    assert item["reimbursement_tracking_start_date"] == "2026-08-15"
    assert manager._sync_recurring_occurrences(date(2026, 8, 26)) is True
    assert [x["due_date"] for x in manager.recurring_occurrences] == ["2026-08-15"]
    assert manager.recurring_occurrences[0]["payer_id"] == "a"
    assert manager.recurring_occurrences[0]["split"][1]["payer_id"] == "b"

    assert manager._sync_recurring_occurrences(date(2026, 9, 20)) is True
    assert {x["due_date"] for x in manager.recurring_occurrences} == {
        "2026-08-15",
        "2026-09-15",
    }
