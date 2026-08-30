"""Guards for issue #7: one installed version, shown consistently everywhere."""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMPONENT = ROOT / "custom_components" / "bill_tracker"
FRONTEND = COMPONENT / "frontend"


def _manifest_version() -> str:
    return json.loads((COMPONENT / "manifest.json").read_text(encoding="utf-8"))["version"]


def test_every_version_constant_matches_the_manifest():
    """All the hardcoded version strings must agree with manifest.json."""
    expected = _manifest_version()
    found: dict[str, str] = {}

    const = (COMPONENT / "const.py").read_text(encoding="utf-8")
    found["const.FRONTEND_VERSION"] = re.search(
        r'FRONTEND_VERSION = "([^"]+)"', const
    ).group(1)
    found["const.FRONTEND_CACHE_VERSION"] = re.search(
        r'FRONTEND_CACHE_VERSION = "([^"]+)"', const
    ).group(1).split("-")[0]

    js_consts = {
        "bill-tracker-card.js": "BILLY_FRONTEND_VERSION",
        "bill-tracker-card-impl.js": "BILL_TRACKER_VERSION",
        "billy-panel.js": "BILLY_PANEL_VERSION",
        "billy-parser-manager.js": "BILLY_PARSER_MANAGER_VERSION",
        "billy-widgets.js": "BILLY_WIDGETS_VERSION",
    }
    for filename, const_name in js_consts.items():
        source = (FRONTEND / filename).read_text(encoding="utf-8")
        found[f"{filename}:{const_name}"] = re.search(
            rf"{const_name} = '([^']+)'", source
        ).group(1)

    mismatches = {k: v for k, v in found.items() if v != expected}
    assert not mismatches, f"expected {expected}, got mismatches: {mismatches}"


def test_backend_reports_the_installed_version_to_the_frontend():
    init = (COMPONENT / "__init__.py").read_text(encoding="utf-8")
    # version is derived from the loaded integration (manifest), not a constant
    assert "async_get_integration" in init
    assert '["version"]' in init
    # ws_list must expose it so a stale cached panel still shows the real version
    assert re.search(r'result\["version"\] = ', init)
    # the custom panel is registered with the runtime version
    assert 'config={"version": version}' in init


def test_panel_displays_the_backend_version_not_only_the_bundled_constant():
    panel = (FRONTEND / "billy-panel.js").read_text(encoding="utf-8")
    # top-right badge + System card both go through the runtime value
    assert "this._billyVersion()" in panel
    assert "this._data?.version || BILLY_PANEL_VERSION" in panel
    assert "v${BILLY_PANEL_VERSION}" not in panel

    parser = (FRONTEND / "billy-parser-manager.js").read_text(encoding="utf-8")
    assert "this._billData?.version || BILLY_PARSER_MANAGER_VERSION" in parser
