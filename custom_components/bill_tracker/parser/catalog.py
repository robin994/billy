"""Remote parser catalog client."""
from __future__ import annotations

import hashlib
import json
from typing import Any

from aiohttp import ClientError, ClientTimeout
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .validator import load_parser_yaml

DEFAULT_CATALOG_ROOT = "https://raw.githubusercontent.com/robin994/billy-parser/main"
DEFAULT_CATALOG_INDEX_URL = f"{DEFAULT_CATALOG_ROOT}/catalog/index.json"
DEFAULT_CATALOG_URL = f"{DEFAULT_CATALOG_ROOT}/parser.json"
DEFAULT_RAW_BASE = "https://raw.githubusercontent.com/robin994/billy-parser"
MAX_CATALOG_INDEX_BYTES = 256_000
MAX_CATALOG_BYTES = 1_000_000
MAX_PARSER_BYTES = 256_000


class CatalogError(RuntimeError):
    """Unable to fetch or validate the remote catalog."""


class CatalogNotFound(CatalogError):
    """Requested catalog resource does not exist."""


class CatalogV2Unavailable(CatalogError):
    """Catalog v2 index is unavailable or unsupported; legacy fallback is allowed."""


class ParserCatalogClient:
    def __init__(
        self,
        hass: HomeAssistant,
        catalog_url: str = DEFAULT_CATALOG_URL,
        catalog_root: str = DEFAULT_CATALOG_ROOT,
        index_url: str = DEFAULT_CATALOG_INDEX_URL,
    ) -> None:
        self.hass = hass
        self.catalog_url = catalog_url
        self.catalog_root = catalog_root.rstrip("/")
        self.index_url = index_url

    async def async_fetch_catalog(
        self,
        country: str,
        cache: dict[str, Any] | None = None,
    ) -> tuple[dict[str, Any], dict[str, Any], bool]:
        """Fetch only the requested country shard, falling back to parser.json."""
        normalized_country = self.normalize_country(country) or "IT"
        cache = cache if isinstance(cache, dict) else {}
        index_cache = cache.get("index") if isinstance(cache.get("index"), dict) else {}

        try:
            index, next_index_cache, index_stale = await self._fetch_index(index_cache)
        except CatalogV2Unavailable:
            catalog = await self._fetch_legacy_catalog(normalized_country)
            return (
                catalog,
                {
                    "index": index_cache,
                    "country": normalized_country,
                    "path": "",
                    "shard": {},
                },
                False,
            )

        descriptor = (index.get("countries") or {}).get(normalized_country)
        if not isinstance(descriptor, dict):
            return (
                {"country": normalized_country, "parsers": [], "catalog_unavailable": True},
                {"index": next_index_cache, "country": normalized_country, "path": "", "shard": {}},
                bool(index_stale),
            )
        shard_path = self._safe_repo_path(descriptor.get("path"))
        if not shard_path:
            raise CatalogError(f"Parser catalog shard for {normalized_country} has no valid path")

        same_country_cache = self.normalize_country(cache.get("country")) == normalized_country
        same_shard_cache = same_country_cache and str(cache.get("path") or "") == shard_path
        shard_cache = (
            cache.get("shard")
            if same_shard_cache and isinstance(cache.get("shard"), dict)
            else {}
        )
        shard_url = f"{self.catalog_root}/{shard_path}"
        catalog, next_shard_cache, shard_stale = await self._fetch_shard(
            shard_url,
            normalized_country,
            shard_cache,
        )
        return (
            catalog,
            {
                "index": next_index_cache,
                "country": normalized_country,
                "path": shard_path,
                "shard": next_shard_cache,
            },
            bool(index_stale or shard_stale),
        )

    async def _fetch_index(
        self, cache: dict[str, Any]
    ) -> tuple[dict[str, Any], dict[str, Any], bool]:
        etag = str(cache.get("etag") or "") or None
        cached_payload = cache.get("payload") if isinstance(cache.get("payload"), dict) else None
        try:
            raw, response_etag, not_modified = await self._get_cached(
                self.index_url,
                MAX_CATALOG_INDEX_BYTES,
                etag=etag,
            )
        except CatalogNotFound as err:
            raise CatalogV2Unavailable("Catalog v2 index does not exist") from err
        except CatalogError:
            if cached_payload is None:
                raise
            index = self._validate_index(cached_payload)
            return index, dict(cache), True

        if not_modified:
            if cached_payload is None:
                raise CatalogError("Catalog index returned 304 without a local cache")
            return self._validate_index(cached_payload), dict(cache), False
        if raw is None:
            raise CatalogError("Catalog index response is empty")
        try:
            payload = self._decode_json(raw, "parser catalog index")
            index = self._validate_index(payload)
        except CatalogV2Unavailable:
            raise
        return index, {"etag": response_etag or "", "payload": index}, False

    async def _fetch_shard(
        self,
        url: str,
        country: str,
        cache: dict[str, Any],
    ) -> tuple[dict[str, Any], dict[str, Any], bool]:
        etag = str(cache.get("etag") or "") or None
        cached_payload = cache.get("payload") if isinstance(cache.get("payload"), dict) else None
        try:
            raw, response_etag, not_modified = await self._get_cached(
                url,
                MAX_CATALOG_BYTES,
                etag=etag,
            )
            if not_modified:
                if cached_payload is None:
                    raise CatalogError("Catalog shard returned 304 without a local cache")
                return self._validate_shard(cached_payload, country), dict(cache), False
            if raw is None:
                raise CatalogError("Catalog shard response is empty")
            payload = self._decode_json(raw, "parser catalog shard")
            shard = self._validate_shard(payload, country)
            return shard, {"etag": response_etag or "", "payload": shard}, False
        except CatalogError:
            if cached_payload is None:
                raise
            shard = self._validate_shard(cached_payload, country)
            return shard, dict(cache), True

    async def _fetch_legacy_catalog(self, country: str) -> dict[str, Any]:
        raw = await self._get(self.catalog_url, MAX_CATALOG_BYTES)
        catalog = self._decode_json(raw, "legacy parser catalog")
        return self._validate_legacy_catalog(catalog, country)

    @classmethod
    def normalize_stored_catalog(
        cls, catalog: dict[str, Any], country: str
    ) -> dict[str, Any]:
        """Normalize a persisted v1/v2 catalog without any network access."""
        normalized_country = cls.normalize_country(country) or "IT"
        schema = catalog.get("schema_version") if isinstance(catalog, dict) else None
        if schema == 1:
            normalized = cls._validate_legacy_catalog(catalog, normalized_country)
        elif schema == 2:
            normalized = cls._validate_shard(catalog, normalized_country)
        else:
            raise CatalogError("Unsupported cached parser catalog schema")
        for key in ("updated_at", "refresh_error", "using_cache"):
            if key in catalog:
                normalized[key] = catalog[key]
        return normalized

    @staticmethod
    def normalize_country(value: Any) -> str | None:
        """Return a normalized ISO 3166 alpha-2 code when possible."""
        country = str(value or "").strip().upper()
        if len(country) != 2 or not country.isascii() or not country.isalpha():
            return None
        return country

    @classmethod
    def _validate_index(cls, payload: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(payload, dict) or payload.get("schema_version") != 2:
            raise CatalogV2Unavailable("Unsupported parser catalog index schema")
        countries = payload.get("countries")
        if not isinstance(countries, dict):
            raise CatalogV2Unavailable("Parser catalog index is malformed")
        normalized: dict[str, dict[str, Any]] = {}
        for raw_country, raw_descriptor in countries.items():
            country = cls.normalize_country(raw_country)
            if country is None or not isinstance(raw_descriptor, dict):
                raise CatalogV2Unavailable("Parser catalog index contains an invalid country")
            path = cls._safe_repo_path(raw_descriptor.get("path"))
            if not path:
                raise CatalogV2Unavailable("Parser catalog index contains an invalid shard path")
            descriptor = dict(raw_descriptor)
            descriptor["path"] = path
            normalized[country] = descriptor
        result = dict(payload)
        result["countries"] = normalized
        return result

    @classmethod
    def _validate_shard(cls, payload: dict[str, Any], country: str) -> dict[str, Any]:
        if not isinstance(payload, dict) or payload.get("schema_version") != 2:
            raise CatalogError("Unsupported parser catalog shard schema")
        shard_country = cls.normalize_country(payload.get("country"))
        if shard_country != country:
            raise CatalogError("Parser catalog shard country does not match the requested country")
        source_commit = str(payload.get("source_commit") or "").strip()
        if not source_commit:
            raise CatalogError("Parser catalog shard has no source_commit")
        raw_parsers = payload.get("parsers")
        if not isinstance(raw_parsers, list):
            raise CatalogError("Parser catalog shard is malformed")
        parsers: list[dict[str, Any]] = []
        for item in raw_parsers:
            if not isinstance(item, dict):
                raise CatalogError("Parser catalog shard contains an invalid parser row")
            row = cls._normalize_catalog_item(item)
            parser_id = str(row.get("id") or "").strip()
            path = cls._safe_repo_path(row.get("path"))
            try:
                version = int(row.get("version", 0) or 0)
            except (TypeError, ValueError) as err:
                raise CatalogError("Parser catalog shard contains an invalid parser version") from err
            if not parser_id or version < 1 or not path:
                raise CatalogError("Parser catalog shard contains an incomplete parser row")
            row["version"] = version
            row_country = cls._item_country(row)
            if row_country and row_country != country:
                continue
            row["country"] = country
            row["path"] = path
            parsers.append(row)
        result = dict(payload)
        result.update(
            {
                "schema_version": 2,
                "country": country,
                "source_commit": source_commit,
                "parsers": parsers,
                "catalog_mode": "v2",
            }
        )
        return result

    @classmethod
    def _validate_legacy_catalog(
        cls, payload: dict[str, Any], country: str
    ) -> dict[str, Any]:
        if not isinstance(payload, dict) or payload.get("schema_version") != 1:
            raise CatalogError("Unsupported legacy parser catalog schema")
        if not isinstance(payload.get("parsers"), list):
            raise CatalogError("Legacy parser catalog is malformed")
        source_commit = str(payload.get("source_commit") or "").strip()
        if not source_commit:
            raise CatalogError("Legacy parser catalog has no source_commit")
        parsers: list[dict[str, Any]] = []
        for item in payload.get("parsers", []):
            if not isinstance(item, dict):
                continue
            row = cls._normalize_catalog_item(item)
            if cls._item_country(row) != country:
                continue
            row["country"] = country
            parsers.append(row)
        result = dict(payload)
        result.update(
            {
                "country": country,
                "source_commit": source_commit,
                "parsers": parsers,
                "catalog_mode": "legacy",
            }
        )
        return result

    @classmethod
    def _item_country(cls, item: dict[str, Any]) -> str | None:
        explicit = cls.normalize_country(item.get("country"))
        if explicit:
            return explicit
        parser_id = str(item.get("id") or "")
        prefix = parser_id.split(".", 1)[0] if "." in parser_id else ""
        return cls.normalize_country(prefix)

    @staticmethod
    def _safe_repo_path(value: Any) -> str:
        path = str(value or "").strip().lstrip("/")
        if not path or ".." in path.split("/"):
            return ""
        return path

    @staticmethod
    def _decode_json(raw: bytes, label: str) -> dict[str, Any]:
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as err:
            if label == "parser catalog index":
                raise CatalogV2Unavailable("Remote parser catalog index is not valid JSON") from err
            raise CatalogError(f"Remote {label} is not valid JSON") from err
        if not isinstance(payload, dict):
            if label == "parser catalog index":
                raise CatalogV2Unavailable("Remote parser catalog index is malformed")
            raise CatalogError(f"Remote {label} is malformed")
        return payload

    @staticmethod
    def _normalize_catalog_item(item: dict[str, Any]) -> dict[str, Any]:
        """Normalize upstream lifecycle without colliding with Billy runtime state."""
        row = dict(item)
        existing_catalog_status = str(row.get("catalog_status") or "").strip().lower()
        upstream_status = str(row.get("status") or "").strip().lower()
        quality = str(row.get("quality") or "").strip().lower()
        if existing_catalog_status in {"experimental", "verified", "outdated", "custom"}:
            catalog_status = existing_catalog_status
        elif upstream_status in {"experimental", "verified", "outdated"}:
            catalog_status = upstream_status
        elif quality == "experimental":
            catalog_status = "experimental"
        elif quality in {"verified", "tested"}:
            catalog_status = "verified"
        else:
            # Unknown old catalogs should never be presented as verified by default.
            catalog_status = "experimental"
        row["catalog_status"] = catalog_status
        row.pop("status", None)
        return row

    async def async_fetch_parser(
        self,
        catalog: dict[str, Any],
        item: dict[str, Any],
    ) -> tuple[dict[str, Any], str]:
        source_commit = str(catalog.get("source_commit") or "").strip()
        path = self._safe_repo_path(item.get("path"))
        if not source_commit or not path:
            raise CatalogError("Invalid parser catalog path")
        url = f"{DEFAULT_RAW_BASE}/{source_commit}/{path}"
        raw = await self._get(url, MAX_PARSER_BYTES)
        expected_size = int(item.get("size") or 0)
        if expected_size and len(raw) != expected_size:
            raise CatalogError("Downloaded parser size does not match the catalog")
        digest = hashlib.sha256(raw).hexdigest()
        expected_digest = str(item.get("sha256") or "").lower()
        if expected_digest and digest != expected_digest:
            raise CatalogError("Downloaded parser checksum does not match the catalog")
        try:
            content = raw.decode("utf-8")
        except UnicodeDecodeError as err:
            raise CatalogError("Downloaded parser is not UTF-8") from err
        parser = load_parser_yaml(content)
        if parser.get("id") != item.get("id") or int(parser.get("version", 0)) != int(item.get("version", -1)):
            raise CatalogError("Downloaded parser identity does not match the catalog")
        return parser, content

    async def _get(self, url: str, max_bytes: int) -> bytes:
        raw, _etag, not_modified = await self._get_cached(url, max_bytes)
        if not_modified or raw is None:
            raise CatalogError("Unexpected empty parser repository response")
        return raw

    async def _get_cached(
        self,
        url: str,
        max_bytes: int,
        *,
        etag: str | None = None,
    ) -> tuple[bytes | None, str | None, bool]:
        session = async_get_clientsession(self.hass)
        headers = {"If-None-Match": etag} if etag else None
        try:
            async with session.get(
                url,
                timeout=ClientTimeout(total=20),
                headers=headers,
            ) as response:
                if response.status == 304:
                    return None, response.headers.get("ETag") or etag, True
                if response.status == 404:
                    raise CatalogNotFound(f"HTTP 404 while downloading {url}")
                if response.status != 200:
                    raise CatalogError(f"HTTP {response.status} while downloading parser data")
                length = response.content_length
                if length is not None and length > max_bytes:
                    raise CatalogError("Remote parser data is too large")
                raw = await response.read()
                response_etag = response.headers.get("ETag")
        except (ClientError, TimeoutError) as err:
            raise CatalogError("Unable to reach the parser repository") from err
        if len(raw) > max_bytes:
            raise CatalogError("Remote parser data is too large")
        return raw, response_etag, False
