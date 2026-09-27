import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LOCALIZATION = ROOT / "custom_components" / "bill_tracker" / "localization.py"


def _load_localization():
    spec = importlib.util.spec_from_file_location("billy_localization_test", LOCALIZATION)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_builtin_category_name_is_localized_while_untouched():
    localization = _load_localization()
    category = {"id": "condominium", "name": "Condominio"}

    assert localization.category_label("en", category) == "Condominium"
    assert localization.category_label("de", category) == "Hausverwaltung"


def test_custom_category_rename_wins_over_builtin_id_label():
    localization = _load_localization()
    category = {"id": "condominium", "name": "Credit Card"}

    assert localization.category_label("en", category) == "Credit Card"
    assert localization.category_label("it", category) == "Credit Card"
