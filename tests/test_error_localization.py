"""Guards for issue #5: backend errors must be localizable, not hardcoded Italian."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMPONENT = ROOT / "custom_components" / "bill_tracker"
FRONTEND = COMPONENT / "frontend"

ITALIAN_MARKERS = re.compile(
    r"\b(bolletta|pagante|pagatore|spesa|rimborso|competenza|valuta|obbligatori\w*|"
    r"sconosciut\w*|mancante|già|non valid\w*|non trovat\w*|righe|storico)\b",
    re.IGNORECASE,
)


def _string_literals(source: str) -> list[str]:
    return re.findall(r'"([^"\n]{4,})"', source) + re.findall(r"'([^'\n]{4,})'", source)


def test_backend_user_facing_errors_are_not_hardcoded_italian():
    offenders = []
    for name in ("manager.py", "exporter.py", "__init__.py"):
        source = (COMPONENT / name).read_text(encoding="utf-8")
        for line in source.splitlines():
            if "raise " not in line and "send_error" not in line:
                continue
            for literal in _string_literals(line):
                if ITALIAN_MARKERS.search(literal):
                    offenders.append(f"{name}: {literal}")
    assert not offenders, offenders


def test_billy_error_codes_have_english_messages():
    errors = (COMPONENT / "errors.py").read_text(encoding="utf-8")
    used = set(re.findall(r'billy_error\("([a-z0-9_]+)"', errors))
    for name in ("manager.py", "exporter.py"):
        used |= set(
            re.findall(r'billy_error\("([a-z0-9_]+)"', (COMPONENT / name).read_text("utf-8"))
        )
    defined = set(re.findall(r'^\s{4}"([a-z0-9_]+)":', errors, re.MULTILINE))
    assert used <= defined, sorted(used - defined)


def test_frontend_error_table_covers_the_websocket_error_codes():
    extra = (FRONTEND / "billy-extra-i18n.js").read_text(encoding="utf-8")
    init = (COMPONENT / "__init__.py").read_text(encoding="utf-8")
    block = extra.split("BILLY_ERROR_TEXT")[1].split("\n}")[0]
    languages = re.findall(r"\n  ([a-z]{2}): \{", block)
    assert set(languages) == {"en", "it", "es", "fr", "de", "pt"}

    english_keys = set(re.findall(r"\n    ([a-z0-9_]+): '", block.split("it: {")[0]))
    # every non-parameterized code that the websocket layer can emit is translated
    codes = set(re.findall(r'send_error\(msg\["id"\], "([a-z0-9_]+)"', init))
    codes |= set(re.findall(r'_ws_error\(connection, msg, err, "([a-z0-9_]+)"', init))
    missing = sorted(code for code in codes if code not in english_keys)
    assert not missing, missing

    # each language defines exactly the same keys as English
    for language in ("it", "es", "fr", "de", "pt"):
        section = block.split(f"{language}: {{")[1]
        keys = set(re.findall(r"\n    ([a-z0-9_]+): '", section.split("\n  }")[0]))
        assert keys == english_keys, (language, english_keys ^ keys)
