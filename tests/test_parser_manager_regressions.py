from pathlib import Path
import ast
import asyncio
import hashlib
import re
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
MANAGER = ROOT / "custom_components" / "bill_tracker" / "parser" / "manager.py"
CATALOG = ROOT / "custom_components" / "bill_tracker" / "parser" / "catalog.py"


@dataclass
class MailPart:
    part: str
    content_type: str = ""
    filename: str = ""
    content_transfer_encoding: str = ""


def _load_method(name: str):
    tree = ast.parse(MANAGER.read_text(encoding="utf-8"))
    cls = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "ParserManager")
    fn = next(
        node
        for node in cls.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name
    )
    fn.decorator_list = []
    module = ast.Module(body=[fn], type_ignores=[])
    ast.fix_missing_locations(module)
    ns = {
        "Any": Any,
        "MailPart": MailPart,
        "hashlib": hashlib,
        "re": re,
        "datetime": __import__("datetime").datetime,
        "CatalogError": RuntimeError,
        "validate_parser": lambda _parser: None,
        "FEEDBACK_SOURCE_UNKNOWN": (
            "Unable to submit feedback because the parser source revision is unknown. "
            "Update or reinstall the parser first."
        ),
        "_LOGGER": SimpleNamespace(warning=lambda *_args, **_kwargs: None),
    }
    exec(compile(module, str(MANAGER), "exec"), ns)
    return ns[name]


def _load_catalog_normalizer():
    tree = ast.parse(CATALOG.read_text(encoding="utf-8"))
    cls = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "ParserCatalogClient")
    fn = next(node for node in cls.body if isinstance(node, ast.FunctionDef) and node.name == "_normalize_catalog_item")
    fn.decorator_list = []
    module = ast.Module(body=[fn], type_ignores=[])
    ast.fix_missing_locations(module)
    ns = {"Any": Any}
    exec(compile(module, str(CATALOG), "exec"), ns)
    return ns["_normalize_catalog_item"]


class _CatalogClientHarness:
    def __init__(self):
        self._normalize = _load_catalog_normalizer()

    def _normalize_catalog_item(self, item):
        return self._normalize(item)


class _StorageHarness:
    def __init__(self, catalog, installed=None, custom=None):
        self.data = {
            "catalog": catalog,
            "community_id": "test-community-installation",
            "installed": installed or {},
            "custom": custom or {},
        }


class _ManagerHarness:
    def __init__(self, catalog, installed=None, custom=None):
        self.storage = _StorageHarness(catalog, installed, custom)
        self.catalog_client = _CatalogClientHarness()
        self.parsers = {}

    @staticmethod
    def catalog_country():
        return "IT"

    def _stored_catalog_for_country(self, _country):
        return dict(self.storage.data["catalog"])

    @staticmethod
    def _version_supported(_minimum):
        return True

    def community_fingerprint(self, parser_id, version):
        return f"fingerprint:{parser_id}:{version}"


class _InstallStorageHarness:
    def __init__(self, catalog):
        self.data = {
            "catalog": catalog,
            "installed": {},
            "custom": {},
            "community_id": "install-community",
        }
        self.saved = 0
        self.deleted = []

    async def async_write_official(self, parser_id, _content):
        return f"/tmp/{parser_id}.yaml"

    async def async_save(self):
        self.saved += 1

    async def async_delete_file(self, path):
        self.deleted.append(path)


class _InstallCatalogHarness:
    async def async_fetch_parser(self, _catalog, item):
        return {"id": item["id"], "version": int(item["version"])}, "schema: 1\n"


def _official_catalog(parser_id="it.example.energy", version=1, commit="commit-one", sha="abc"):
    return {
        "schema_version": 2,
        "country": "IT",
        "source_commit": commit,
        "parsers": [
            {
                "id": parser_id,
                "version": version,
                "sha256": sha,
                "min_billy_version": "0.0.0",
                "catalog_status": "experimental",
            }
        ],
    }


def _install_manager(catalog):
    storage = _InstallStorageHarness(catalog)
    manager = SimpleNamespace(
        storage=storage,
        catalog_client=_InstallCatalogHarness(),
        parsers={},
        _ensure_category=lambda _category_id: None,
        _normalize_payment_defaults=lambda payer, split: (payer or None, list(split or [])),
        catalog_country=lambda: "IT",
        _stored_catalog_for_country=lambda _country: storage.data["catalog"],
        _version_supported=lambda _minimum: True,
    )
    return manager


def test_official_install_promotes_same_id_custom_parser():
    install = _load_method("async_install")
    manager = _install_manager(_official_catalog())
    manager.storage.data["custom"]["it.example.energy"] = {
        "id": "it.example.energy",
        "version": 1,
        "path": "/tmp/custom-it.example.energy.yaml",
        "category_id": "electricity",
        "enabled": True,
        "auto_import": False,
        "default_payer_id": "payer-a",
        "default_split": [{"payer_id": "payer-a", "percentage": 100}],
    }

    state = asyncio.run(
        install(
            manager,
            "it.example.energy",
            category_id="electricity",
            default_payer_id="payer-a",
            default_split=[{"payer_id": "payer-a", "percentage": 100}],
        )
    )

    assert state["source"] == "official"
    assert "it.example.energy" not in manager.storage.data["custom"]
    assert manager.storage.data["installed"]["it.example.energy"] == state
    assert "/tmp/custom-it.example.energy.yaml" in manager.storage.deleted


def test_catalog_official_row_inherits_same_id_custom_configuration():
    snapshot = _load_method("catalog_snapshot")
    custom = {
        "it.example.energy": {
            "id": "it.example.energy",
            "version": 1,
            "category_id": "electricity",
            "enabled": False,
            "auto_import": True,
            "default_payer_id": "payer-a",
            "default_split": [{"payer_id": "payer-a", "percentage": 100}],
        }
    }
    row = snapshot(_ManagerHarness(_official_catalog(), custom=custom))["parsers"][0]

    assert row["installed"] is False
    assert row["replaces_custom"] is True
    assert row["category_id"] == "electricity"
    assert row["enabled"] is False
    assert row["auto_import"] is True
    assert row["default_payer_id"] == "payer-a"
    assert row["default_split"] == [{"payer_id": "payer-a", "percentage": 100}]


def test_generic_binary_pdf_matches_restrictive_pdf_parser_by_filename():
    find_part = _load_method("_find_part")
    document = {
        "mime_types": ["application/pdf"],
        "filename_regex": r"(?i)^FATTURA_.*\.pdf$",
    }
    parts = [
        MailPart(
            part="1",
            content_type="application/octet-stream",
            filename="FATTURA_2026_41_TEST.pdf",
            content_transfer_encoding="base64",
        )
    ]
    assert find_part(document, parts) == parts[0]


def test_wrong_filename_does_not_bypass_mime_filter():
    find_part = _load_method("_find_part")
    document = {
        "mime_types": ["application/pdf"],
        "filename_regex": r"(?i)^FATTURA_.*\.pdf$",
    }
    parts = [MailPart(part="1", content_type="application/octet-stream", filename="image.bin")]
    assert find_part(document, parts) is None


def test_error_source_fingerprint_retries_once_per_runtime_without_log_loop():
    source = MANAGER.read_text(encoding="utf-8")
    assert "self._runtime_failed_fingerprints: set[str] = set()" in source
    assert "prefetch_key in self._runtime_failed_fingerprints" in source
    assert "existing_source = self._source_fingerprint_row(prefetch_key)" in source
    assert 'row.get("status") != "error"' in source
    assert "Persisted errors are deliberately excluded" in source
    assert "self._runtime_failed_fingerprints.add(source_fingerprint)" in source
    assert "self._runtime_failed_fingerprints.discard(source_fingerprint)" in source


def test_repeated_error_for_same_source_updates_existing_queue_row():
    source = MANAGER.read_text(encoding="utf-8")
    assert 'item.get("status") == "error"' in source
    assert "== source_fingerprint" in source
    assert "self._remove_source_errors(prefetch_key)" in source


def test_imap_ingestion_exposes_early_exit_diagnostics():
    source = MANAGER.read_text(encoding="utf-8")
    api = (ROOT / "custom_components" / "bill_tracker" / "parser_api.py").read_text(
        encoding="utf-8"
    )
    assert "self._last_ingestion" in source
    assert "IMAP source '" in source
    assert "No enabled Billy parser matched the email prefilter" in source
    assert "This IMAP message is already stored as" in source
    assert "import_id=" in source
    assert '"diagnostic": manager.ingestion_diagnostic()' in api


def test_stale_source_fingerprint_rows_are_removed_before_retry():
    source = MANAGER.read_text(encoding="utf-8")
    assert 'status == "pending" and (not parser_id or not data)' in source
    assert 'status == "imported" and not expense_id' in source
    assert "Billy removed stale import" in source
    assert "self._remove_import(existing_id)" in source


def test_empty_parser_split_falls_back_to_default_payer_at_100_percent():
    normalize = _load_method("_normalize_payment_defaults")

    class BillManager:
        @staticmethod
        def _validate_optional_payer(value):
            return value or None

        @staticmethod
        def default_split():
            return []

        @staticmethod
        def _normalize_split(split):
            return split

    manager = SimpleNamespace(bill_manager=BillManager())
    payer, split = normalize(manager, "payer-a", [])
    assert payer == "payer-a"
    assert split == [{"payer_id": "payer-a", "percentage": 100.0}]


def test_imap_fetches_retry_once_on_transient_home_assistant_errors():
    source = (ROOT / "custom_components" / "bill_tracker" / "sources" / "imap.py").read_text(
        encoding="utf-8"
    )
    assert "for attempt in range(2):" in source
    assert "await asyncio.sleep(0.25)" in source


def test_parser_can_continue_when_full_imap_fetch_fails_but_event_metadata_is_available():
    source = MANAGER.read_text(encoding="utf-8")
    assert "except ImapSourceError as err:" in source
    assert 'email_text = ""' in source
    assert "continuing with event metadata" in source
    assert "scored.append((score, threshold, parser_id, parser, config))" in source


def test_optional_attachment_fetch_failure_does_not_abort_parser():
    source = MANAGER.read_text(encoding="utf-8")
    assert "except (ImapSourceError, PdfExtractionError) as err:" in source
    assert "Billy skipped optional attachment" in source
    assert "continue" in source


def test_failed_import_retry_has_uuid_and_reprocesses_original_imap_uid():
    source = MANAGER.read_text(encoding="utf-8")
    api = (ROOT / "custom_components" / "bill_tracker" / "parser_api.py").read_text(
        encoding="utf-8"
    )
    assert "from uuid import uuid4" in source
    assert "async def async_retry" in source
    assert '"entry_id": source.get("entry_id")' in source
    assert '"uid": source.get("uid")' in source
    assert "retry_import_id=import_id" in source
    assert '"bill_tracker/parser/import/retry"' in api
    assert 'row.get("status") not in {"error", "rejected"}' in source


def test_candidate_uuid_generator_is_imported():
    tree = ast.parse(MANAGER.read_text(encoding="utf-8"))
    imports = {
        alias.name
        for node in tree.body
        if isinstance(node, ast.ImportFrom) and node.module == "uuid"
        for alias in node.names
    }
    assert "uuid4" in imports


def test_fetched_parts_preserve_original_metadata():
    source = MANAGER.read_text(encoding="utf-8")
    assert "merged: dict[str, MailPart] = {part.part: part for part in envelope.parts}" in source
    assert "previous.filename if previous else" in source


def test_catalog_snapshot_marks_outdated_and_removed_parsers():
    source = MANAGER.read_text(encoding="utf-8")
    assert 'status = "outdated"' in source
    assert '"removed_from_catalog": True' in source
    assert "installed_country != country" in source
    assert '"outdated": sum(1 for row in rows if row.get("status") == "outdated")' in source
    assert '"compatible": compatible' in source


def test_catalog_status_fallback_from_legacy_quality():
    normalize = _load_catalog_normalizer()
    assert normalize({"quality": "experimental"})["catalog_status"] == "experimental"
    assert normalize({"quality": "verified"})["catalog_status"] == "verified"
    assert normalize({"quality": "tested"})["catalog_status"] == "verified"
    assert normalize({"catalog_status": "verified"})["catalog_status"] == "verified"
    assert normalize({})["catalog_status"] == "experimental"


def test_catalog_refresh_uses_etag_cache_validation():
    source = CATALOG.read_text(encoding="utf-8")
    assert 'headers = {"If-None-Match": etag} if etag else None' in source
    assert "response.status == 304" in source
    assert '"catalog_cache"' in (
        ROOT / "custom_components" / "bill_tracker" / "parser" / "storage.py"
    ).read_text(encoding="utf-8")


def test_parser_catalog_country_prefers_explicit_option_then_home_assistant_then_it():
    resolve = _load_method("catalog_country")

    class Client:
        @staticmethod
        def normalize_country(value):
            text = str(value or "").strip().upper()
            return text if len(text) == 2 and text.isalpha() else None

    explicit = SimpleNamespace(
        config_entry=SimpleNamespace(options={"parser_country": "fr"}, data={}),
        hass=SimpleNamespace(config=SimpleNamespace(country="IT")),
        catalog_client=Client(),
    )
    assert resolve(explicit) == "FR"

    home_assistant = SimpleNamespace(
        config_entry=SimpleNamespace(options={}, data={}),
        hass=SimpleNamespace(config=SimpleNamespace(country="de")),
        catalog_client=Client(),
    )
    assert resolve(home_assistant) == "DE"

    fallback = SimpleNamespace(
        config_entry=None,
        hass=SimpleNamespace(config=SimpleNamespace(country=None)),
        catalog_client=Client(),
    )
    assert resolve(fallback) == "IT"


def test_catalog_status_is_preserved_after_runtime_merge():
    snapshot = _load_method("catalog_snapshot")
    catalog = {
        "parsers": [
            {"id": "it.enel.energy", "version": 1, "status": "experimental"},
            {"id": "it.eon.energy", "version": 1, "status": "verified"},
            {
                "id": "it.tim.generic",
                "version": 2,
                "status": "outdated",
                "replacement": "it.tim.internet",
            },
        ]
    }
    manager = _ManagerHarness(catalog)
    rows = {row["id"]: row for row in snapshot(manager)["parsers"]}
    assert rows["it.enel.energy"]["catalog_status"] == "experimental"
    assert rows["it.enel.energy"]["status"] == "available"
    assert rows["it.eon.energy"]["catalog_status"] == "verified"
    assert rows["it.eon.energy"]["status"] == "available"
    assert rows["it.tim.generic"]["catalog_status"] == "outdated"
    assert rows["it.tim.generic"]["status"] == "available"
    assert rows["it.tim.generic"]["replacement"] == "it.tim.internet"


def test_catalog_outdated_does_not_collide_with_runtime_update_available():
    snapshot = _load_method("catalog_snapshot")
    catalog = {
        "parsers": [
            {
                "id": "it.tim.generic",
                "version": 3,
                "status": "outdated",
                "replacement": "it.tim.internet",
            }
        ]
    }
    installed = {
        "it.tim.generic": {
            "id": "it.tim.generic",
            "version": 2,
            "enabled": True,
        }
    }
    row = snapshot(_ManagerHarness(catalog, installed))["parsers"][0]
    assert row["catalog_status"] == "outdated"
    assert row["status"] == "outdated"
    assert row["update_available"] is True
    assert row["replacement"] == "it.tim.internet"


def test_custom_parser_uses_custom_catalog_status():
    source = MANAGER.read_text(encoding="utf-8")
    assert '"catalog_status": "custom"' in source
    panel = (ROOT / "custom_components" / "bill_tracker" / "frontend" / "billy-parser-manager.js").read_text(encoding="utf-8")
    assert "catalog_status: 'custom'" in panel


def test_installed_and_available_runtime_status_remain_distinct():
    snapshot = _load_method("catalog_snapshot")
    catalog = {
        "parsers": [
            {"id": "it.eon.energy", "version": 1, "status": "verified"},
            {"id": "it.enel.energy", "version": 1, "status": "experimental"},
        ]
    }
    installed = {"it.eon.energy": {"id": "it.eon.energy", "version": 1, "enabled": True}}
    rows = {row["id"]: row for row in snapshot(_ManagerHarness(catalog, installed))["parsers"]}
    assert rows["it.eon.energy"]["status"] == "installed"
    assert rows["it.eon.energy"]["catalog_status"] == "verified"
    assert rows["it.enel.energy"]["status"] == "available"
    assert rows["it.enel.energy"]["catalog_status"] == "experimental"


def test_installed_parser_exposes_anonymous_version_scoped_feedback_fingerprint():
    snapshot = _load_method("catalog_snapshot")
    catalog = {
        "parsers": [
            {"id": "it.enel.energy", "version": 3, "status": "experimental"},
        ]
    }
    installed = {"it.enel.energy": {"id": "it.enel.energy", "version": 3, "enabled": True}}
    row = snapshot(_ManagerHarness(catalog, installed))["parsers"][0]
    assert row["feedback_fingerprint"] == "fingerprint:it.enel.energy:3"


def test_install_parser_persists_catalog_source_commit():
    install = _load_method("async_install")
    catalog = _official_catalog(commit="source-install")
    manager = _install_manager(catalog)

    state = asyncio.run(
        install(
            manager,
            "it.example.energy",
            category_id="electricity",
        )
    )

    assert state["source_commit"] == "source-install"
    assert manager.storage.data["installed"]["it.example.energy"]["source_commit"] == "source-install"


def test_update_parser_replaces_source_commit_with_new_installed_snapshot():
    install = _load_method("async_install")
    catalog = _official_catalog(version=1, commit="source-v1", sha="sha-v1")
    manager = _install_manager(catalog)
    asyncio.run(install(manager, "it.example.energy", category_id="electricity"))

    manager.storage.data["catalog"] = _official_catalog(
        version=2,
        commit="source-v2",
        sha="sha-v2",
    )
    state = asyncio.run(
        install(manager, "it.example.energy", category_id="electricity")
    )

    assert state["version"] == 2
    assert state["source_commit"] == "source-v2"


def test_reinstall_parser_persists_source_commit_from_new_snapshot():
    install = _load_method("async_install")
    uninstall = _load_method("async_uninstall")
    manager = _install_manager(
        _official_catalog(version=3, commit="source-first", sha="same-sha")
    )
    asyncio.run(install(manager, "it.example.energy", category_id="electricity"))
    assert asyncio.run(uninstall(manager, "it.example.energy")) is True

    manager.storage.data["catalog"] = _official_catalog(
        version=3,
        commit="source-reinstall",
        sha="same-sha",
    )
    state = asyncio.run(
        install(manager, "it.example.energy", category_id="electricity")
    )

    assert state["source_commit"] == "source-reinstall"


def test_feedback_payload_uses_installed_source_commit_and_never_remote_commit():
    payload = _load_method("community_feedback_payload")
    manager = SimpleNamespace(
        storage=SimpleNamespace(
            data={
                "installed": {
                    "it.example.energy": {
                        "version": 4,
                        "source_commit": "installed-source",
                    }
                },
                "custom": {},
            }
        ),
        billy_version="0.11.9",
        community_fingerprint=lambda parser_id, version: f"fp:{parser_id}:{version}",
    )

    result = payload(manager, "it.example.energy", "working")

    assert result == {
        "schema_version": 1,
        "parser_id": "it.example.energy",
        "version": 4,
        "result": "working",
        "installation_fingerprint": "fp:it.example.energy:4",
        "billy_version": "0.11.9",
        "source_commit": "installed-source",
    }


def test_feedback_payload_never_emits_empty_source_commit():
    payload = _load_method("community_feedback_payload")
    manager = SimpleNamespace(
        storage=SimpleNamespace(
            data={
                "installed": {"it.example.energy": {"version": 1, "source_commit": ""}},
                "custom": {},
            }
        ),
        billy_version="0.11.9",
        community_fingerprint=lambda _parser_id, _version: "unused",
    )

    try:
        payload(manager, "it.example.energy", "working")
    except ValueError as err:
        assert "source revision is unknown" in str(err)
    else:
        raise AssertionError("Feedback without source_commit must be blocked")


def test_legacy_install_backfills_source_commit_on_exact_id_version_match():
    backfill = _load_method("_backfill_installed_source_commits")
    catalog = _official_catalog(version=3, commit="legacy-backfill", sha="same-sha")
    storage = SimpleNamespace(
        data={
            "catalog": catalog,
            "installed": {
                "it.example.energy": {
                    "id": "it.example.energy",
                    "version": 3,
                    "sha256": "same-sha",
                }
            },
        }
    )
    manager = SimpleNamespace(
        storage=storage,
        catalog_country=lambda: "IT",
        _stored_catalog_for_country=lambda _country: storage.data["catalog"],
    )

    assert backfill(manager) is True
    assert storage.data["installed"]["it.example.energy"]["source_commit"] == "legacy-backfill"


def test_legacy_install_does_not_backfill_from_different_remote_version():
    backfill = _load_method("_backfill_installed_source_commits")
    catalog = _official_catalog(version=4, commit="remote-v4", sha="sha-v4")
    storage = SimpleNamespace(
        data={
            "catalog": catalog,
            "installed": {
                "it.example.energy": {
                    "id": "it.example.energy",
                    "version": 3,
                    "sha256": "sha-v3",
                }
            },
        }
    )
    manager = SimpleNamespace(
        storage=storage,
        catalog_country=lambda: "IT",
        _stored_catalog_for_country=lambda _country: storage.data["catalog"],
    )

    assert backfill(manager) is False
    assert "source_commit" not in storage.data["installed"]["it.example.energy"]


def test_legacy_install_with_different_remote_version_blocks_feedback():
    backfill = _load_method("_backfill_installed_source_commits")
    payload = _load_method("community_feedback_payload")
    catalog = _official_catalog(version=4, commit="remote-v4", sha="sha-v4")
    storage = SimpleNamespace(
        data={
            "catalog": catalog,
            "installed": {
                "it.example.energy": {
                    "id": "it.example.energy",
                    "version": 3,
                    "sha256": "sha-v3",
                }
            },
            "custom": {},
        }
    )
    manager = SimpleNamespace(
        storage=storage,
        catalog_country=lambda: "IT",
        _stored_catalog_for_country=lambda _country: storage.data["catalog"],
        billy_version="0.11.9",
        community_fingerprint=lambda _parser_id, _version: "unused",
    )

    assert backfill(manager) is False
    try:
        payload(manager, "it.example.energy", "working")
    except ValueError as err:
        assert "source revision is unknown" in str(err)
    else:
        raise AssertionError("Legacy feedback must be blocked when catalog version differs")


def test_catalog_refresh_backfill_never_overwrites_installed_source_commit():
    backfill = _load_method("_backfill_installed_source_commits")
    catalog = _official_catalog(version=5, commit="remote-source", sha="remote-sha")
    storage = SimpleNamespace(
        data={
            "installed": {
                "it.example.energy": {
                    "id": "it.example.energy",
                    "version": 4,
                    "sha256": "installed-sha",
                    "source_commit": "installed-source",
                }
            }
        }
    )
    manager = SimpleNamespace(storage=storage)

    assert backfill(manager, catalog) is False
    assert storage.data["installed"]["it.example.energy"]["source_commit"] == "installed-source"


def test_configure_preserves_installed_source_commit():
    source = MANAGER.read_text(encoding="utf-8")
    configure_start = source.index("    async def async_configure(")
    configure_end = source.index("    async def async_save_custom(", configure_start)
    configure = source[configure_start:configure_end]
    assert 'state.update(' in configure
    assert '"source_commit"' not in configure


def test_real_anthropic_v3_legacy_install_backfills_current_catalog_snapshot_commit():
    backfill = _load_method("_backfill_installed_source_commits")
    catalog = _official_catalog(
        parser_id="it.anthropic.subscription",
        version=3,
        commit="a622b4eeab53637ddb18e59e287eee8676d3a743",
        sha="47656a25650aaed70dc887b8e03602e084eecc61885425d967be700768b5e6d2",
    )
    storage = SimpleNamespace(
        data={
            "catalog": catalog,
            "installed": {
                "it.anthropic.subscription": {
                    "id": "it.anthropic.subscription",
                    "version": 3,
                    "sha256": "47656a25650aaed70dc887b8e03602e084eecc61885425d967be700768b5e6d2",
                }
            },
        }
    )
    manager = SimpleNamespace(
        storage=storage,
        catalog_country=lambda: "IT",
        _stored_catalog_for_country=lambda _country: storage.data["catalog"],
    )

    assert backfill(manager) is True
    assert (
        storage.data["installed"]["it.anthropic.subscription"]["source_commit"]
        == "a622b4eeab53637ddb18e59e287eee8676d3a743"
    )


def test_custom_parser_feedback_is_rejected_without_fake_source_commit():
    payload = _load_method("community_feedback_payload")
    manager = SimpleNamespace(
        storage=SimpleNamespace(
            data={
                "installed": {},
                "custom": {"it.local.custom": {"version": 1}},
            }
        ),
        billy_version="0.11.9",
        community_fingerprint=lambda _parser_id, _version: "unused",
    )

    try:
        payload(manager, "it.local.custom", "working")
    except ValueError as err:
        assert "custom parsers" in str(err)
    else:
        raise AssertionError("Custom parser feedback must not be generated")


def test_parser_storage_generates_persistent_community_id():
    storage = (
        ROOT / "custom_components" / "bill_tracker" / "parser" / "storage.py"
    ).read_text(encoding="utf-8")
    assert '"community_id": ""' in storage
    assert "community_id = uuid4().hex" in storage
    assert "await self._store.async_save(self.data)" in storage


def test_community_fingerprint_is_anonymous_and_version_scoped():
    fingerprint = _load_method("community_fingerprint")
    manager = SimpleNamespace(
        storage=SimpleNamespace(data={"community_id": "local-secret-installation-id"})
    )
    version_one = fingerprint(manager, "it.heracomm.energy", 1)
    version_two = fingerprint(manager, "it.heracomm.energy", 2)
    assert len(version_one) == 64
    assert version_one != version_two
    assert "local-secret-installation-id" not in version_one


def test_catalog_refresh_is_scheduled_daily_at_midnight():
    source = MANAGER.read_text(encoding="utf-8")
    assert "async_track_time_change" in source
    assert "self._handle_catalog_refresh" in source
    assert "hour=0" in source
    assert "minute=0" in source
    assert "second=0" in source
    assert "self._unsubscribe_catalog_refresh()" in source
    assert "daily parser catalog refresh failed" in source


def test_custom_parser_edit_locks_existing_parser_id():
    source = MANAGER.read_text(encoding="utf-8")
    assert "expected_parser_id: str | None = None" in source
    assert "if expected_parser_id is not None and parser_id != expected_parser_id" in source
    assert 'raise ValueError("Custom parser ID cannot be changed while editing")' in source
