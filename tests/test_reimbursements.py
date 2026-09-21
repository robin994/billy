from collections import defaultdict
from pathlib import Path
import ast
from types import MethodType

ROOT = Path(__file__).resolve().parents[1]
MANAGER = ROOT / "custom_components" / "bill_tracker" / "manager.py"


def _load_pairwise_debts():
    tree = ast.parse(MANAGER.read_text(encoding="utf-8"))
    cls = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "BillTrackerManager")
    fn = next(node for node in cls.body if isinstance(node, ast.FunctionDef) and node.name == "_pairwise_debts")
    module = ast.Module(body=[fn], type_ignores=[])
    ast.fix_missing_locations(module)
    ns = {"Any": object, "defaultdict": defaultdict}
    exec(compile(module, str(MANAGER), "exec"), ns)
    return ns["_pairwise_debts"]


def _load_public_settlement():
    tree = ast.parse(MANAGER.read_text(encoding="utf-8"))
    cls = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "BillTrackerManager"
    )
    fn = next(
        node
        for node in cls.body
        if isinstance(node, ast.FunctionDef) and node.name == "_public_settlement"
    )
    module = ast.Module(body=[fn], type_ignores=[])
    ast.fix_missing_locations(module)
    ns = {"Any": object}
    exec(compile(module, str(MANAGER), "exec"), ns)
    return ns["_public_settlement"]


class DummyManager:
    def __init__(self):
        self.payers = [
            {"id": "a", "name": "A", "paypal_me": "payerA"},
            {"id": "b", "name": "B", "paypal_me": "payerB"},
        ]
        self.expenses = []
        self.recurring_occurrences = []
        self.recurring_expenses = []
        self.categories = []
        self.settlements = []
        self.currency = "EUR"

    def payer(self, payer_id):
        return next((row for row in self.payers if row["id"] == payer_id), None)

    def category(self, category_id):
        return next(
            (row for row in self.categories if row["id"] == category_id), None
        )

    def recurring_expense(self, recurring_id):
        return next(
            (row for row in self.recurring_expenses if row["id"] == recurring_id),
            None,
        )

    @staticmethod
    def _preferred_payment(payer, amount, currency):
        handle = payer.get("paypal_me", "")
        return {
            "method": "paypal" if handle else "",
            "handle": handle,
            "url": f"https://paypal.me/{handle}/{amount:.2f}{currency}" if handle else "",
        }

    def _sync_recurring_occurrences(self):
        return False


def test_reimbursements_are_independent_from_provider_bill_payment():
    manager = DummyManager()
    manager._pairwise_debts = MethodType(_load_pairwise_debts(), manager)
    manager.expenses = [
        {
            "id": "bill-1",
            "payer_id": "a",
            "amount": 100.0,
            "paid": True,
            "split": [
                {"payer_id": "a", "percentage": 50.0},
                {"payer_id": "b", "percentage": 50.0},
            ],
        }
    ]
    debts = manager._pairwise_debts()
    assert len(debts) == 1
    assert debts[0]["from_payer_id"] == "b"
    assert debts[0]["to_payer_id"] == "a"
    assert debts[0]["amount"] == 50.0
    assert debts[0]["items"] == [
        {
            "kind": "expense",
            "id": "bill-1",
            "amount": 50.0,
            "label": "Bill",
            "date": "",
        }
    ]
    assert debts[0]["payment_method"] == "paypal"
    assert debts[0]["payment_url"] == "https://paypal.me/payerA/50.00EUR"

    manager.settlements = [
        {"from_payer_id": "b", "to_payer_id": "a", "amount": 50.0}
    ]
    assert manager._pairwise_debts() == []
    assert manager.expenses[0]["paid"] is True


def test_settlement_methods_do_not_mutate_bill_paid_status():
    source = MANAGER.read_text(encoding="utf-8")
    start = source.index("    async def async_add_settlement(")
    end = source.index("    def _pairwise_debts", start)
    settlement_source = source[start:end]
    assert 'expense["paid"]' not in settlement_source
    assert "without touching bill status" in settlement_source
    assert "Bill payment and payer reimbursements are deliberately independent" in settlement_source


def test_manual_bill_reimbursement_flag_removes_it_from_open_debts():
    manager = DummyManager()
    manager._pairwise_debts = MethodType(_load_pairwise_debts(), manager)
    manager.expenses = [
        {
            "id": "bill-manual",
            "payer_id": "a",
            "amount": 100.0,
            "paid": False,
            "reimbursement_manual_done": True,
            "split": [
                {"payer_id": "a", "percentage": 50.0},
                {"payer_id": "b", "percentage": 50.0},
            ],
        }
    ]
    assert manager._pairwise_debts() == []
    assert manager.expenses[0]["paid"] is False


def test_due_recurring_occurrence_uses_the_same_split_debt_logic():
    manager = DummyManager()
    manager._pairwise_debts = MethodType(_load_pairwise_debts(), manager)
    manager.recurring_occurrences = [
        {
            "id": "rec-1@2026-08-15",
            "recurring_id": "rec-1",
            "payer_id": "a",
            "amount": 40.0,
            "split": [
                {"payer_id": "a", "percentage": 50.0},
                {"payer_id": "b", "percentage": 50.0},
            ],
            "reimbursement_manual_done": False,
        }
    ]
    debts = manager._pairwise_debts()
    assert len(debts) == 1
    assert debts[0]["from_payer_id"] == "b"
    assert debts[0]["to_payer_id"] == "a"
    assert debts[0]["amount"] == 20.0
    assert debts[0]["recurring_count"] == 1
    assert debts[0]["item_count"] == 1
    assert debts[0]["recurring_occurrence_ids"] == ["rec-1@2026-08-15"]
    assert debts[0]["items"][0]["kind"] == "recurring"
    assert debts[0]["items"][0]["id"] == "rec-1@2026-08-15"
    assert debts[0]["items"][0]["amount"] == 20.0

    manager.recurring_occurrences[0]["reimbursement_manual_done"] = True
    assert manager._pairwise_debts() == []


def test_manual_reimbursement_state_is_migrated_and_kept_separate_from_paid():
    source = MANAGER.read_text(encoding="utf-8")
    assert '"reimbursement_manual_done": bool(item.get("reimbursement_manual_done", False))' in source
    assert '"reimbursement_manual_at"' in source
    assert 'if bool(item.get("reimbursement_manual_done", False)):' in source
    assert 'item["paid"]' not in source[source.index("    async def async_set_reimbursement_done("):source.index("    async def async_delete(")]


def test_itemized_settlement_only_removes_selected_reimbursement_items():
    manager = DummyManager()
    manager._pairwise_debts = MethodType(_load_pairwise_debts(), manager)
    manager.expenses = [
        {
            "id": "bill-small",
            "payer_id": "a",
            "amount": 40.0,
            "split": [
                {"payer_id": "a", "percentage": 50.0},
                {"payer_id": "b", "percentage": 50.0},
            ],
        },
        {
            "id": "bill-large",
            "payer_id": "a",
            "amount": 60.0,
            "split": [
                {"payer_id": "a", "percentage": 50.0},
                {"payer_id": "b", "percentage": 50.0},
            ],
        },
    ]
    before = manager._pairwise_debts()
    assert before[0]["amount"] == 50.0
    assert [(row["id"], row["amount"]) for row in before[0]["items"]] == [
        ("bill-small", 20.0),
        ("bill-large", 30.0),
    ]

    manager.settlements = [
        {
            "from_payer_id": "b",
            "to_payer_id": "a",
            "amount": 20.0,
            "expense_ids": ["bill-small"],
            "line_items": [
                {"kind": "expense", "id": "bill-small", "amount": 20.0}
            ],
        }
    ]
    after = manager._pairwise_debts()
    assert after[0]["amount"] == 30.0
    assert after[0]["expense_ids"] == ["bill-large"]
    assert after[0]["item_count"] == 1
    assert [(row["id"], row["amount"]) for row in after[0]["items"]] == [
        ("bill-large", 30.0)
    ]


def test_partial_settlement_contract_accepts_selected_line_items():
    source = MANAGER.read_text(encoding="utf-8")
    init = (ROOT / "custom_components" / "bill_tracker" / "__init__.py").read_text(
        encoding="utf-8"
    )
    settlement = source[
        source.index("    async def async_add_settlement("):
        source.index("    async def async_delete_settlement(")
    ]
    assert 'line_items: list[dict[str, Any]] | None = None' in settlement
    assert '"settlement_invalid_selection"' in settlement
    assert '"line_items": [' in settlement
    assert 'vol.Optional("line_items", default=[]): [dict]' in init


def test_public_settlement_exposes_itemized_history_details_and_legacy_fallback():
    manager = DummyManager()
    manager._public_settlement = MethodType(_load_public_settlement(), manager)
    manager.categories = [{"id": "power", "name": "Electricity"}]
    manager.expenses = [
        {
            "id": "bill-1",
            "category_id": "power",
            "provider": "Example Energy",
            "contract": "Home",
            "amount": 100.0,
            "due_date": "2026-09-10",
        }
    ]
    manager.recurring_expenses = [
        {
            "id": "rent",
            "name": "Rent",
            "provider": "Landlord",
            "contract": "Apartment",
        }
    ]
    manager.recurring_occurrences = [
        {
            "id": "rent@2026-09-01",
            "recurring_id": "rent",
            "name": "Rent",
            "amount": 800.0,
            "due_date": "2026-09-01",
        }
    ]
    current = manager._public_settlement(
        {
            "id": "settlement-1",
            "from_payer_id": "b",
            "to_payer_id": "a",
            "amount": 70.0,
            "expense_ids": ["bill-1"],
            "recurring_occurrence_ids": ["rent@2026-09-01"],
            "line_items": [
                {"kind": "expense", "id": "bill-1", "amount": 20.0},
                {
                    "kind": "recurring",
                    "id": "rent@2026-09-01",
                    "amount": 50.0,
                },
            ],
        }
    )
    assert current["status"] == "done"
    assert current["item_count"] == 2
    assert current["items"][0]["label"] == "Example Energy"
    assert current["items"][0]["amount"] == 20.0
    assert current["items"][0]["legacy_amount_unknown"] is False
    assert current["items"][1]["label"] == "Rent"
    assert current["items"][1]["amount"] == 50.0

    legacy = manager._public_settlement(
        {
            "id": "settlement-legacy",
            "from_payer_id": "b",
            "to_payer_id": "a",
            "amount": 20.0,
            "expense_ids": ["bill-1"],
            "recurring_occurrence_ids": [],
        }
    )
    assert legacy["items"][0]["amount"] is None
    assert legacy["items"][0]["legacy_amount_unknown"] is True


def test_payers_support_multiple_payment_methods_with_legacy_paypal_migration():
    source = MANAGER.read_text(encoding="utf-8")
    for token in (
        '"payment_methods": methods',
        '"preferred_payment_method": preferred',
        'raw["paypal"] = legacy_paypal',
        'for method in ("paypal", "revolut", "venmo", "cashapp")',
        'return f"https://revolut.me/{safe}"',
        'return f"https://venmo.com/u/{safe}"',
        'return f"https://cash.app/${safe}"',
        '"payment_method": payment["method"]',
        '"payment_url": payment["url"]',
    ):
        assert token in source
