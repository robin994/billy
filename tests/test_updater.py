"""Tests for Billy's self-update helpers (issue #6)."""
import ast
import io
import json
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMPONENT = ROOT / "custom_components" / "bill_tracker"
UPDATER = COMPONENT / "updater.py"


def _updater_helpers():
    """Load the pure helpers from updater.py without importing Home Assistant."""
    tree = ast.parse(UPDATER.read_text(encoding="utf-8"))
    wanted = {"version_tuple", "changelog_since", "_apply_zipball"}
    nodes = [
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name in wanted
    ]
    assign = [
        node
        for node in tree.body
        if isinstance(node, ast.Assign)
        and getattr(node.targets[0], "id", "") == "_COMPONENT_DIR"
    ]
    future = ast.ImportFrom("__future__", [ast.alias("annotations")], 0)
    module = ast.Module(body=[future, *assign, *nodes], type_ignores=[])
    ast.fix_missing_locations(module)
    ns = {"re": __import__("re"), "io": io, "json": json, "zipfile": zipfile,
          "shutil": __import__("shutil"), "Path": Path, "Any": object,
          "__file__": str(UPDATER)}
    exec(compile(module, str(UPDATER), "exec"), ns)  # noqa: S102
    return ns


HELPERS = _updater_helpers()


def test_version_tuple_parses_and_tolerates_junk():
    vt = HELPERS["version_tuple"]
    assert vt("0.11.10") == (0, 11, 10)
    assert vt("v0.9.1") == (0, 9, 1)
    assert vt("garbage") == (0, 0, 0)
    assert vt("0.12.0") > vt("0.11.10")


def test_changelog_since_returns_only_newer_sections():
    cs = HELPERS["changelog_since"]
    changelog = (
        "# Changelog\n\n"
        "## 0.11.10\n\n- new stuff\n\n"
        "## 0.11.9\n\n- old stuff\n\n"
        "## 0.11.3\n\n- ancient\n"
    )
    since_119 = cs(changelog, "0.11.9")
    assert "## 0.11.10" in since_119
    assert "0.11.9" not in since_119
    assert cs(changelog, "0.11.10") == ""
    assert cs(changelog, "0.0.0").count("## ") == 3


def test_real_changelog_top_section_is_current_version():
    cs = HELPERS["changelog_since"]
    manifest = json.loads((COMPONENT / "manifest.json").read_text())
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    assert f"## {manifest['version']}" in changelog
    # nothing newer than the shipped version
    assert cs(changelog, manifest["version"]) == ""


def test_apply_zipball_swaps_the_component_dir(tmp_path, monkeypatch):
    apply = HELPERS["_apply_zipball"]
    # fake an installed component dir
    parent = tmp_path / "custom_components"
    component = parent / "bill_tracker"
    component.mkdir(parents=True)
    (component / "manifest.json").write_text('{"version": "0.11.10"}')
    (component / "old_only.py").write_text("# gone after update")
    monkeypatch.setitem(HELPERS, "_COMPONENT_DIR", component)

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        base = "billy-main/custom_components/bill_tracker/"
        archive.writestr(base + "manifest.json", '{"version": "0.11.11"}')
        archive.writestr(base + "__init__.py", "# new code")
        archive.writestr("billy-main/README.md", "ignored")
    apply(buffer.getvalue(), "0.11.11")

    assert json.loads((component / "manifest.json").read_text())["version"] == "0.11.11"
    assert (component / "__init__.py").read_text() == "# new code"
    assert not (component / "old_only.py").exists()
    assert not (parent / "bill_tracker.bak").exists()
    assert not (parent / "bill_tracker.new").exists()


def test_update_platform_is_wired_up():
    init = (COMPONENT / "__init__.py").read_text(encoding="utf-8")
    assert '"update"' in init and 'PLATFORMS = ["sensor", "update"]' in init
    assert "ws_update_status" in init and "ws_update_install" in init
    assert 'hass.data[DOMAIN].setdefault(\n        "updater"' in init

    update = (COMPONENT / "update.py").read_text(encoding="utf-8")
    assert "class BillyUpdateEntity(UpdateEntity)" in update
    assert "UpdateEntityFeature.INSTALL" in update
    assert "UpdateEntityFeature.RELEASE_NOTES" in update

    panel = (ROOT / "custom_components" / "bill_tracker" / "frontend" / "billy-panel.js").read_text(
        encoding="utf-8"
    )
    assert "bill_tracker/update/status" in panel
    assert "bill_tracker/update/install" in panel
    assert "_updateCard()" in panel


def test_apply_zipball_rejects_a_version_mismatch(tmp_path, monkeypatch):
    apply = HELPERS["_apply_zipball"]
    parent = tmp_path / "custom_components"
    component = parent / "bill_tracker"
    component.mkdir(parents=True)
    (component / "manifest.json").write_text('{"version": "0.11.10"}')
    monkeypatch.setitem(HELPERS, "_COMPONENT_DIR", component)

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        base = "billy-main/custom_components/bill_tracker/"
        archive.writestr(base + "manifest.json", '{"version": "0.11.99"}')
    try:
        apply(buffer.getvalue(), "0.12.0")
        raised = False
    except RuntimeError:
        raised = True
    assert raised
    # the running install is untouched
    assert json.loads((component / "manifest.json").read_text())["version"] == "0.11.10"
