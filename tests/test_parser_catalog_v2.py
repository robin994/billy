import ast
import asyncio
import hashlib
import json
from pathlib import Path
from types import MethodType, SimpleNamespace
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "custom_components" / "bill_tracker" / "parser" / "catalog.py"


def _catalog_module():
    tree = ast.parse(CATALOG.read_text(encoding="utf-8"))
    wanted = {"CatalogError", "CatalogNotFound", "CatalogV2Unavailable", "ParserCatalogClient"}
    classes = [
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name in wanted
    ]
    future = ast.ImportFrom(
        module="__future__",
        names=[ast.alias(name="annotations")],
        level=0,
    )
    module = ast.Module(body=[future, *classes], type_ignores=[])
    ast.fix_missing_locations(module)
    ns = {
        "Any": Any,
        "json": json,
        "hashlib": hashlib,
        "HomeAssistant": object,
        "ClientError": Exception,
        "ClientTimeout": object,
        "async_get_clientsession": None,
        "load_parser_yaml": lambda _content: {},
        "DEFAULT_CATALOG_ROOT": "https://example.test/main",
        "DEFAULT_CATALOG_INDEX_URL": "https://example.test/main/catalog/index.json",
        "DEFAULT_CATALOG_URL": "https://example.test/main/parser.json",
        "DEFAULT_RAW_BASE": "https://example.test",
        "MAX_CATALOG_INDEX_BYTES": 256_000,
        "MAX_CATALOG_BYTES": 1_000_000,
        "MAX_PARSER_BYTES": 256_000,
    }
    exec(compile(module, str(CATALOG), "exec"), ns)
    return SimpleNamespace(**{name: ns[name] for name in wanted})


def _client(responses):
    module = _catalog_module()
    client = module.ParserCatalogClient(
        None,
        catalog_url="https://example.test/main/parser.json",
        catalog_root="https://example.test/main",
        index_url="https://example.test/main/catalog/index.json",
    )
    calls = []

    async def fake_get_cached(self, url, _max_bytes, *, etag=None):
        calls.append((url, etag))
        response = responses[url]
        if isinstance(response, Exception):
            raise response
        if callable(response):
            response = response(etag)
        if isinstance(response, tuple) and len(response) == 3:
            return response
        return json.dumps(response).encode(), f'etag-{len(calls)}', False

    client._get_cached = MethodType(fake_get_cached, client)
    return module, client, calls


def _index():
    return {
        "schema_version": 2,
        "countries": {
            "IT": {"path": "catalog/it.json", "parsers": 2},
            "FR": {"path": "catalog/fr.json", "parsers": 1},
        },
    }


def _it_shard():
    return {
        "schema_version": 2,
        "country": "IT",
        "source_commit": "abc123",
        "parsers": [
            {
                "id": "it.eon.electricity",
                "version": 2,
                "provider": "E.ON Energia",
                "bill_type": "electricity",
                "status": "verified",
                "path": "parsers/it/eon/electricity.yaml",
                "replacement": None,
            },
            {
                "id": "it.enel.energy",
                "version": 1,
                "provider": "Enel Energia",
                "bill_type": "electricity",
                "status": "experimental",
                "path": "parsers/it/enelenergia/energy.yaml",
            },
        ],
    }


def test_catalog_v2_loads_index_and_only_requested_it_shard():
    index_url = "https://example.test/main/catalog/index.json"
    it_url = "https://example.test/main/catalog/it.json"
    module, client, calls = _client({index_url: _index(), it_url: _it_shard()})

    catalog, cache, stale = asyncio.run(client.async_fetch_catalog("it", {}))

    assert catalog["schema_version"] == 2
    assert catalog["country"] == "IT"
    assert catalog["catalog_mode"] == "v2"
    assert catalog["source_commit"] == "abc123"
    assert {row["id"] for row in catalog["parsers"]} == {
        "it.eon.electricity",
        "it.enel.energy",
    }
    assert catalog["parsers"][0]["catalog_status"] == "verified"
    assert catalog["parsers"][1]["catalog_status"] == "experimental"
    assert [url for url, _etag in calls] == [index_url, it_url]
    assert "https://example.test/main/catalog/fr.json" not in {url for url, _etag in calls}
    assert cache["country"] == "IT"
    assert stale is False
    assert module.ParserCatalogClient.normalize_country(" it ") == "IT"


def test_other_country_rows_never_enter_requested_shard():
    index_url = "https://example.test/main/catalog/index.json"
    it_url = "https://example.test/main/catalog/it.json"
    shard = _it_shard()
    shard["parsers"].append(
        {
            "id": "fr.example.energy",
            "version": 1,
            "country": "FR",
            "provider": "Example FR",
            "bill_type": "electricity",
            "status": "verified",
            "path": "parsers/fr/example/energy.yaml",
        }
    )
    _module, client, _calls = _client({index_url: _index(), it_url: shard})

    catalog, _cache, _stale = asyncio.run(client.async_fetch_catalog("IT", {}))

    assert all(row["country"] == "IT" for row in catalog["parsers"])
    assert "fr.example.energy" not in {row["id"] for row in catalog["parsers"]}


def test_catalog_v2_preserves_lifecycle_and_replacement():
    index_url = "https://example.test/main/catalog/index.json"
    it_url = "https://example.test/main/catalog/it.json"
    shard = _it_shard()
    shard["parsers"][0]["status"] = "outdated"
    shard["parsers"][0]["replacement"] = "it.eon.electricity.v2"
    _module, client, _calls = _client({index_url: _index(), it_url: shard})

    catalog, _cache, _stale = asyncio.run(client.async_fetch_catalog("IT", {}))
    row = catalog["parsers"][0]

    assert row["catalog_status"] == "outdated"
    assert "status" not in row
    assert row["replacement"] == "it.eon.electricity.v2"


def test_legacy_parser_json_is_used_when_v2_index_is_missing():
    module = _catalog_module()
    index_url = "https://example.test/main/catalog/index.json"
    legacy_url = "https://example.test/main/parser.json"
    legacy = {
        "schema_version": 1,
        "source_commit": "legacy123",
        "parsers": [
            {
                "id": "it.legacy.energy",
                "version": 1,
                "country": "IT",
                "quality": "tested",
                "path": "parsers/it/legacy/energy.yaml",
            },
            {
                "id": "fr.legacy.energy",
                "version": 1,
                "country": "FR",
                "quality": "experimental",
                "path": "parsers/fr/legacy/energy.yaml",
            },
        ],
    }
    client, calls = None, []
    client = module.ParserCatalogClient(
        None,
        catalog_url=legacy_url,
        catalog_root="https://example.test/main",
        index_url=index_url,
    )

    async def fake_get_cached(self, url, _max_bytes, *, etag=None):
        calls.append(url)
        if url == index_url:
            raise module.CatalogNotFound("missing")
        return json.dumps(legacy).encode(), "legacy-etag", False

    client._get_cached = MethodType(fake_get_cached, client)
    catalog, _cache, stale = asyncio.run(client.async_fetch_catalog("IT", {}))

    assert calls == [index_url, legacy_url]
    assert catalog["catalog_mode"] == "legacy"
    assert [row["id"] for row in catalog["parsers"]] == ["it.legacy.energy"]
    assert catalog["parsers"][0]["catalog_status"] == "verified"
    assert stale is False


def test_unsupported_index_schema_falls_back_to_legacy_catalog():
    index_url = "https://example.test/main/catalog/index.json"
    legacy_url = "https://example.test/main/parser.json"
    legacy = {
        "schema_version": 1,
        "source_commit": "legacy123",
        "parsers": [],
    }
    _module, client, calls = _client(
        {
            index_url: {"schema_version": 99, "countries": {}},
            legacy_url: legacy,
        }
    )
    catalog, _cache, _stale = asyncio.run(client.async_fetch_catalog("IT", {}))
    assert catalog["catalog_mode"] == "legacy"
    assert [url for url, _etag in calls] == [index_url, legacy_url]


def test_cached_index_and_shard_are_used_when_remote_is_offline():
    index_url = "https://example.test/main/catalog/index.json"
    it_url = "https://example.test/main/catalog/it.json"
    module = _catalog_module()
    client = module.ParserCatalogClient(
        None,
        catalog_url="https://example.test/main/parser.json",
        catalog_root="https://example.test/main",
        index_url=index_url,
    )
    calls = []

    async def offline(self, url, _max_bytes, *, etag=None):
        calls.append((url, etag))
        raise module.CatalogError("offline")

    client._get_cached = MethodType(offline, client)
    cache = {
        "index": {"etag": "index-old", "payload": _index()},
        "country": "IT",
        "path": "catalog/it.json",
        "shard": {"etag": "it-old", "payload": _it_shard()},
    }

    catalog, next_cache, stale = asyncio.run(client.async_fetch_catalog("IT", cache))

    assert catalog["country"] == "IT"
    assert stale is True
    assert next_cache == cache
    assert calls == [(index_url, "index-old"), (it_url, "it-old")]


def test_etag_304_reuses_cached_payload_without_redownloading_json():
    index_url = "https://example.test/main/catalog/index.json"
    it_url = "https://example.test/main/catalog/it.json"
    _module, client, calls = _client(
        {
            index_url: lambda etag: (None, etag, True),
            it_url: lambda etag: (None, etag, True),
        }
    )
    cache = {
        "index": {"etag": "index-etag", "payload": _index()},
        "country": "IT",
        "path": "catalog/it.json",
        "shard": {"etag": "it-etag", "payload": _it_shard()},
    }

    catalog, next_cache, stale = asyncio.run(client.async_fetch_catalog("IT", cache))

    assert catalog["parsers"]
    assert next_cache == cache
    assert stale is False
    assert calls == [(index_url, "index-etag"), (it_url, "it-etag")]


def test_index_without_requested_country_fails_without_loading_another_shard():
    index_url = "https://example.test/main/catalog/index.json"
    module, client, calls = _client(
        {
            index_url: {
                "schema_version": 2,
                "countries": {"FR": {"path": "catalog/fr.json", "parsers": 1}},
            }
        }
    )

    try:
        asyncio.run(client.async_fetch_catalog("IT", {}))
    except module.CatalogError as err:
        assert "country IT" in str(err)
    else:
        raise AssertionError("Missing country should fail")
    assert [url for url, _etag in calls] == [index_url]


def test_malformed_or_unsupported_shard_is_rejected_without_cache():
    index_url = "https://example.test/main/catalog/index.json"
    it_url = "https://example.test/main/catalog/it.json"
    module, client, _calls = _client(
        {
            index_url: _index(),
            it_url: {"schema_version": 2, "country": "IT", "source_commit": "abc", "parsers": {}},
        }
    )
    try:
        asyncio.run(client.async_fetch_catalog("IT", {}))
    except module.CatalogError as err:
        assert "malformed" in str(err)
    else:
        raise AssertionError("Malformed shard should fail")

    second_module, client, _calls = _client(
        {
            index_url: _index(),
            it_url: {"schema_version": 3, "country": "IT", "source_commit": "abc", "parsers": []},
        }
    )
    try:
        asyncio.run(client.async_fetch_catalog("IT", {}))
    except second_module.CatalogError as err:
        assert "shard schema" in str(err)
    else:
        raise AssertionError("Unsupported shard schema should fail")


def test_changed_shard_path_does_not_reuse_previous_shard_cache():
    index_url = "https://example.test/main/catalog/index.json"
    new_shard_url = "https://example.test/main/catalog/it-v2.json"
    index = {
        "schema_version": 2,
        "countries": {"IT": {"path": "catalog/it-v2.json", "parsers": 2}},
    }
    _module, client, calls = _client({index_url: index, new_shard_url: _it_shard()})
    cache = {
        "index": {"etag": "old-index", "payload": _index()},
        "country": "IT",
        "path": "catalog/it.json",
        "shard": {"etag": "old-it", "payload": _it_shard()},
    }

    _catalog, next_cache, _stale = asyncio.run(client.async_fetch_catalog("IT", cache))

    assert calls[1] == (new_shard_url, None)
    assert next_cache["path"] == "catalog/it-v2.json"


def test_country_change_reuses_index_but_not_previous_country_shard():
    index_url = "https://example.test/main/catalog/index.json"
    fr_url = "https://example.test/main/catalog/fr.json"
    fr_shard = {
        "schema_version": 2,
        "country": "FR",
        "source_commit": "fr123",
        "parsers": [
            {
                "id": "fr.example.energy",
                "version": 1,
                "provider": "Example FR",
                "bill_type": "electricity",
                "status": "verified",
                "path": "parsers/fr/example/energy.yaml",
            }
        ],
    }
    _module, client, calls = _client(
        {
            index_url: lambda etag: (None, etag, True),
            fr_url: fr_shard,
        }
    )
    cache = {
        "index": {"etag": "index-etag", "payload": _index()},
        "country": "IT",
        "path": "catalog/it.json",
        "shard": {"etag": "it-etag", "payload": _it_shard()},
    }

    catalog, next_cache, stale = asyncio.run(client.async_fetch_catalog("FR", cache))

    assert [url for url, _etag in calls] == [index_url, fr_url]
    assert calls[1][1] is None
    assert catalog["country"] == "FR"
    assert [row["id"] for row in catalog["parsers"]] == ["fr.example.energy"]
    assert next_cache["country"] == "FR"
    assert next_cache["path"] == "catalog/fr.json"
    assert stale is False


def test_country_normalization_rejects_non_alpha2_values():
    module = _catalog_module()
    normalize = module.ParserCatalogClient.normalize_country
    assert normalize("it") == "IT"
    assert normalize(" Fr ") == "FR"
    assert normalize("ITA") is None
    assert normalize("1T") is None
