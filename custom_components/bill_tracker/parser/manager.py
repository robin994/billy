"""Parser catalog, installation and automatic IMAP processing coordinator."""
from __future__ import annotations

import hashlib
import logging
import re
from datetime import datetime
from typing import Any
from uuid import uuid4

import yaml
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers.event import async_track_time_change

from ..extractors import PdfExtractionError, extract_pdf_text
from ..importers import BillImportCoordinator
from ..sources import ImapSource, ImapSourceError
from .catalog import CatalogError, ParserCatalogClient
from .engine import ParserEngine, ParserError
from .models import BillCandidate, DocumentBundle, MailEnvelope, MailPart
from .storage import ParserStorage
from .validator import ParserValidationError, load_parser_yaml, validate_parser

_LOGGER = logging.getLogger(__name__)
EVENT_IMPORT_UPDATED = "bill_tracker_import_updated"
MAX_IMPORT_HISTORY = 500
FEEDBACK_SOURCE_UNKNOWN = (
    "Unable to submit feedback because the parser source revision is unknown. "
    "Update or reinstall the parser first."
)


class ParserManager:
    """Own parser state while BillTrackerManager remains the owner of expenses."""

    def __init__(
        self,
        hass: HomeAssistant,
        bill_manager,
        billy_version: str = "0.9.1",
        config_entry: ConfigEntry | None = None,
    ) -> None:
        self.hass = hass
        self.bill_manager = bill_manager
        self.billy_version = billy_version
        self.config_entry = config_entry
        self.storage = ParserStorage(hass)
        self.catalog_client = ParserCatalogClient(hass)
        self.engine = ParserEngine()
        self.imap = ImapSource(hass)
        self.importer = BillImportCoordinator(bill_manager)
        self.parsers: dict[str, dict[str, Any]] = {}
        self._runtime_failed_fingerprints: set[str] = set()
        self._last_ingestion: dict[str, Any] | None = None
        self._unsubscribe = None
        self._unsubscribe_catalog_refresh = None

    async def async_load(self) -> None:
        await self.storage.async_load()
        dirty = self._normalize_cached_catalog_country()
        dirty |= self._backfill_installed_source_commits()
        if dirty:
            await self.storage.async_save()
        await self._reload_installed()

    async def async_start(self) -> None:
        if self._unsubscribe is None:
            self._unsubscribe = self.hass.bus.async_listen("imap_content", self._handle_imap_event)
        if self._unsubscribe_catalog_refresh is None:
            self._unsubscribe_catalog_refresh = async_track_time_change(
                self.hass,
                self._handle_catalog_refresh,
                hour=0,
                minute=0,
                second=0,
            )

    async def async_stop(self) -> None:
        if self._unsubscribe is not None:
            self._unsubscribe()
            self._unsubscribe = None
        if self._unsubscribe_catalog_refresh is not None:
            self._unsubscribe_catalog_refresh()
            self._unsubscribe_catalog_refresh = None

    @callback
    def _handle_imap_event(self, event: Event) -> None:
        self.hass.async_create_task(self.async_process_imap_event(dict(event.data)))

    @callback
    def _handle_catalog_refresh(self, _now) -> None:
        """Refresh the country catalog every day without updating installed parsers."""
        self.hass.async_create_task(self._async_scheduled_catalog_refresh())

    async def _async_scheduled_catalog_refresh(self) -> None:
        try:
            await self.async_refresh_catalog()
        except Exception as err:  # noqa: BLE001 - keep the last good catalog on network failures
            _LOGGER.warning("Billy daily parser catalog refresh failed: %s", err)

    async def async_process_imap_event(
        self,
        event_data: dict[str, Any],
        *,
        retry_import_id: str | None = None,
    ) -> dict[str, Any] | None:
        envelope = self.imap.envelope(event_data)
        if not envelope.entry_id or not envelope.uid:
            self._set_ingestion_diagnostic(
                envelope,
                "ignored",
                "IMAP event is missing entry_id or uid",
            )
            return None
        enabled_entries = set(self.storage.data.get("source_entry_ids", []))
        if not enabled_entries or envelope.entry_id not in enabled_entries:
            detail = (
                f"IMAP source '{envelope.entry_id}' is not enabled in Billy; "
                f"selected sources: {', '.join(sorted(enabled_entries)) or 'none'}"
            )
            self._set_ingestion_diagnostic(envelope, "ignored", detail)
            _LOGGER.warning("Billy ignored IMAP UID %s: %s", envelope.uid, detail)
            return None

        prefiltered: list[tuple[str, dict[str, Any], dict[str, Any]]] = []
        for parser_id, parser in self.parsers.items():
            config = self.storage.data.get("installed", {}).get(parser_id) or self.storage.data.get("custom", {}).get(parser_id)
            if not config or not config.get("enabled", True):
                continue
            if self.engine.prefilter(parser, envelope):
                prefiltered.append((parser_id, parser, config))
        if not prefiltered:
            enabled_parser_ids = sorted(
                parser_id
                for parser_id in self.parsers
                if (
                    self.storage.data.get("installed", {}).get(parser_id)
                    or self.storage.data.get("custom", {}).get(parser_id)
                    or {}
                ).get("enabled", True)
            )
            detail = (
                "No enabled Billy parser matched the email prefilter; "
                f"enabled parsers: {', '.join(enabled_parser_ids) or 'none'}"
            )
            self._set_ingestion_diagnostic(envelope, "ignored", detail)
            return None

        prefetch_key = self._prefetch_fingerprint(envelope)
        if not retry_import_id and prefetch_key in self._runtime_failed_fingerprints:
            self._set_ingestion_diagnostic(
                envelope,
                "ignored",
                "This IMAP message already failed during the current Billy runtime; use Retry or reload the integration",
            )
            return None
        if not retry_import_id:
            existing_source = self._source_fingerprint_row(prefetch_key)
            if existing_source is not None:
                status = str(existing_source.get("status") or "unknown")
                existing_id = str(existing_source.get("id") or "")
                parser_id = str(existing_source.get("parser_id") or "")
                data = existing_source.get("data") or {}
                expense_id = str(existing_source.get("expense_id") or "")
                stale = (
                    status == "pending" and (not parser_id or not data)
                ) or (status == "imported" and not expense_id)
                if stale:
                    _LOGGER.warning(
                        "Billy removed stale import %s (%s) for IMAP UID %s and will retry it",
                        existing_id or "unknown",
                        status,
                        envelope.uid,
                    )
                    self._remove_import(existing_id)
                else:
                    detail = (
                        f"This IMAP message is already stored as {status}; "
                        f"import_id={existing_id or 'unknown'}"
                    )
                    if parser_id:
                        detail += f"; parser={parser_id}"
                    if expense_id:
                        detail += f"; expense_id={expense_id}"
                    self._set_ingestion_diagnostic(
                        envelope,
                        "duplicate",
                        detail,
                        parser_id=parser_id or None,
                    )
                    return None

        try:
            fetch_error: str | None = None
            email_text = ""
            try:
                fetched = await self.imap.async_fetch(envelope)
                envelope = self._merge_fetched_envelope(envelope, fetched)
                email_text = str(fetched.get("text") or "")
            except ImapSourceError as err:
                fetch_error = str(err)
                _LOGGER.debug(
                    "Billy could not fetch full IMAP message UID %s; continuing with event metadata: %s",
                    envelope.uid,
                    err,
                )
            base_documents = DocumentBundle(email=email_text)

            matches: list[tuple[int, int, str, dict[str, Any], dict[str, Any]]] = []
            scored: list[tuple[int, int, str, dict[str, Any], dict[str, Any]]] = []
            for parser_id, parser, config in prefiltered:
                matched, score, threshold = self.engine.detect(parser, envelope, base_documents)
                scored.append((score, threshold, parser_id, parser, config))
                if matched:
                    matches.append((score, threshold, parser_id, parser, config))
            if not matches:
                score, threshold, parser_id, _parser, config = max(
                    scored,
                    key=lambda item: (item[0] / max(1, item[1]), item[0]),
                )
                detail = (
                    f"Parser '{parser_id}' matched the email prefilter but detection scored "
                    f"{score}/{threshold}"
                )
                if fetch_error:
                    detail += f"; full IMAP fetch failed: {fetch_error}"
                _LOGGER.warning("Billy automatic parsing skipped IMAP UID %s: %s", envelope.uid, detail)
                self._set_ingestion_diagnostic(
                    envelope,
                    "error",
                    detail,
                    parser_id=parser_id,
                )
                await self._record_error(
                    envelope,
                    prefetch_key,
                    detail,
                    import_id=retry_import_id,
                    parser_id=parser_id,
                    category_id=str(config.get("category_id") or ""),
                )
                return None
            matches.sort(key=lambda item: (item[0] / max(1, item[1]), item[0]), reverse=True)
            score, threshold, parser_id, parser, config = matches[0]
            documents, attachment_hashes = await self._documents_for(parser, envelope, email_text)
            matched, score, threshold = self.engine.detect(parser, envelope, documents)
            if not matched:
                detail = f"Parser '{parser_id}' detection dropped below threshold after document loading ({score}/{threshold})"
                _LOGGER.warning("Billy automatic parsing skipped IMAP UID %s: %s", envelope.uid, detail)
                self._set_ingestion_diagnostic(
                    envelope,
                    "error",
                    detail,
                    parser_id=parser_id,
                )
                await self._record_error(
                    envelope,
                    prefetch_key,
                    detail,
                    import_id=retry_import_id,
                    parser_id=parser_id,
                    category_id=str(config.get("category_id") or ""),
                )
                return None
            parsed = self.engine.parse(parser, envelope, documents)
            verification = self.engine.verification(parser, documents)
            candidate = self._candidate(
                parser_id=parser_id,
                parser=parser,
                config=config,
                envelope=envelope,
                parsed=parsed,
                score=score,
                threshold=threshold,
                verification=verification,
                source_fingerprint=prefetch_key,
                attachment_hashes=attachment_hashes,
            )
            if self._is_duplicate_candidate(candidate):
                self._remove_source_errors(prefetch_key)
                self._runtime_failed_fingerprints.discard(prefetch_key)
                self._set_ingestion_diagnostic(
                    envelope,
                    "duplicate",
                    f"Parser '{parser_id}' produced a bill already known to Billy",
                    parser_id=parser_id,
                )
                return None
            if retry_import_id:
                self._remove_import(retry_import_id)
            self._remove_source_errors(prefetch_key)
            self._runtime_failed_fingerprints.discard(prefetch_key)
            await self._record_candidate(candidate)
            self._set_ingestion_diagnostic(
                envelope,
                "pending",
                f"Parser '{parser_id}' created import candidate {candidate.id}",
                parser_id=parser_id,
            )
            expected_checks = len(parser.get("verification", []) or [])
            verification_complete = (
                expected_checks == 0
                or (
                    len(verification) == expected_checks
                    and all(item.get("match", False) for item in verification)
                )
            )
            if (
                config.get("auto_import", False)
                and verification_complete
                and candidate.confidence >= 90
            ):
                await self.async_approve(candidate.id)
                self._set_ingestion_diagnostic(
                    envelope,
                    "imported",
                    f"Parser '{parser_id}' automatically imported candidate {candidate.id}",
                    parser_id=parser_id,
                )
            return self.get_import(candidate.id)
        except (ParserError, ParserValidationError, PdfExtractionError, ValueError, RuntimeError) as err:
            _LOGGER.warning("Billy automatic parsing failed for IMAP UID %s: %s", envelope.uid, err)
            self._set_ingestion_diagnostic(envelope, "error", str(err))
            await self._record_error(
                envelope,
                prefetch_key,
                str(err),
                import_id=retry_import_id,
            )
            return None
        except Exception as err:  # noqa: BLE001 - source events must never break HA
            _LOGGER.exception("Unexpected Billy parser error")
            self._set_ingestion_diagnostic(
                envelope,
                "error",
                f"Unexpected error: {err}",
            )
            await self._record_error(
                envelope,
                prefetch_key,
                f"Unexpected error: {err}",
                import_id=retry_import_id,
            )
            return None

    def catalog_country(self) -> str:
        """Resolve the parser country from options, HA config, then legacy IT fallback."""
        candidates: list[Any] = []
        if self.config_entry is not None:
            options = getattr(self.config_entry, "options", {}) or {}
            data = getattr(self.config_entry, "data", {}) or {}
            candidates.extend(
                (
                    options.get("parser_country"),
                    options.get("country"),
                    data.get("parser_country"),
                    data.get("country"),
                )
            )
        candidates.append(getattr(self.hass.config, "country", None))
        for candidate in candidates:
            country = self.catalog_client.normalize_country(candidate)
            if country:
                return country
        return "IT"

    def _normalize_cached_catalog_country(self) -> bool:
        """Migrate the persisted global v1 catalog to the currently selected country."""
        country = self.catalog_country()
        changed = False
        catalog = self.storage.data.get("catalog")
        if isinstance(catalog, dict) and catalog.get("schema_version") in {1, 2}:
            try:
                normalized = self.catalog_client.normalize_stored_catalog(catalog, country)
            except CatalogError:
                normalized = {"country": country, "parsers": []}
            if normalized != catalog:
                self.storage.data["catalog"] = normalized
                changed = True

        cache = self.storage.data.get("catalog_cache")
        if isinstance(cache, dict):
            cached_country = self.catalog_client.normalize_country(cache.get("country"))
            if cached_country and cached_country != country:
                self.storage.data["catalog_cache"] = {
                    "index": cache.get("index") if isinstance(cache.get("index"), dict) else {},
                    "country": "",
                    "path": "",
                    "shard": {},
                }
                changed = True
        return changed

    def _stored_catalog_for_country(self, country: str) -> dict[str, Any]:
        catalog = self.storage.data.get("catalog")
        if not isinstance(catalog, dict) or not catalog.get("parsers"):
            return {"country": country, "parsers": []}
        try:
            return self.catalog_client.normalize_stored_catalog(catalog, country)
        except CatalogError:
            return {"country": country, "parsers": []}

    async def async_refresh_catalog(self) -> dict[str, Any]:
        country = self.catalog_country()
        cache = self.storage.data.get("catalog_cache")
        cache = cache if isinstance(cache, dict) else {}
        previous = self._stored_catalog_for_country(country)
        try:
            catalog, next_cache, using_cache = await self.catalog_client.async_fetch_catalog(
                country,
                cache,
            )
        except CatalogError as err:
            if previous.get("parsers"):
                previous["using_cache"] = True
                previous["refresh_error"] = str(err)
                self.storage.data["catalog"] = previous
                await self.storage.async_save()
                return self.catalog_snapshot()
            raise

        catalog["using_cache"] = bool(using_cache)
        catalog["refresh_error"] = (
            "Remote catalog refresh failed; using cached catalog data"
            if using_cache
            else ""
        )
        self.storage.data["catalog"] = {
            **catalog,
            "updated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        }
        self.storage.data["catalog_cache"] = next_cache
        self._backfill_installed_source_commits(self.storage.data["catalog"])
        await self.storage.async_save()
        return self.catalog_snapshot()

    def catalog_snapshot(self) -> dict[str, Any]:
        """Return the remote catalog enriched with local installation state."""
        country = self.catalog_country()
        catalog = self._stored_catalog_for_country(country)
        installed = self.storage.data.get("installed", {})
        custom = self.storage.data.get("custom", {})
        rows: list[dict[str, Any]] = []
        catalog_ids: set[str] = set()

        for item in catalog.get("parsers", []) or []:
            row = self.catalog_client._normalize_catalog_item(item)
            parser_id = str(item.get("id") or "")
            catalog_ids.add(parser_id)
            state = installed.get(parser_id)
            custom_state = custom.get(parser_id)
            remote_version = int(item.get("version", 0) or 0)
            installed_version = int(state.get("version", 0) or 0) if state else None
            minimum = str(item.get("min_billy_version") or "0.0.0")
            compatible = self._version_supported(minimum)
            deprecated = bool(item.get("deprecated", False))
            update_available = bool(
                state and remote_version > int(installed_version or 0)
            )
            load_error = str(state.get("load_error") or "") if state else ""
            installed_catalog_status = (
                str(state.get("catalog_status") or "")
                if state
                else ""
            )
            if (
                state
                and not installed_catalog_status
                and installed_version == remote_version
            ):
                installed_catalog_status = str(
                    row.get("catalog_status") or "experimental"
                )
            installed_source_commit = (
                str(state.get("source_commit") or "").strip()
                if state
                else ""
            )
            feedback_eligible = bool(
                state and installed_catalog_status == "experimental"
            )

            if load_error:
                status = "error"
            elif state and update_available:
                status = "outdated"
            elif state:
                status = "installed"
            elif deprecated:
                status = "deprecated"
            elif not compatible:
                status = "incompatible"
            else:
                status = "available"

            row.update(
                {
                    "installed": bool(state),
                    "installed_version": installed_version,
                    "update_available": update_available,
                    "compatible": compatible,
                    "deprecated": deprecated,
                    "catalog_status": str(row.get("catalog_status") or "experimental"),
                    "replacement": row.get("replacement"),
                    "feedback_fingerprint": (
                        self.community_fingerprint(
                            parser_id, int(installed_version or remote_version)
                        )
                        if state
                        else ""
                    ),
                    "source_commit": installed_source_commit,
                    "installed_catalog_status": installed_catalog_status,
                    "feedback_available": bool(
                        feedback_eligible and installed_source_commit
                    ),
                    "feedback_block_reason": (
                        "source_commit_unavailable"
                        if state and not installed_source_commit
                        else ""
                    ),
                    "status": status,
                    "load_error": load_error,
                    "source": "official",
                    # A parser can begin life as a local custom parser and later
                    # be accepted into the community catalog with the same ID.
                    # Surface the local configuration on the official row so
                    # installing it is a seamless promotion rather than forcing
                    # users to delete/reconfigure the custom parser first.
                    "replaces_custom": bool(custom_state and not state),
                    "category_id": (
                        state.get("category_id")
                        if state
                        else custom_state.get("category_id")
                        if custom_state
                        else None
                    ),
                    "enabled": (
                        bool(state.get("enabled", True))
                        if state
                        else bool(custom_state.get("enabled", True))
                        if custom_state
                        else False
                    ),
                    "auto_import": (
                        bool(state.get("auto_import", False))
                        if state
                        else bool(custom_state.get("auto_import", False))
                        if custom_state
                        else False
                    ),
                    "default_payer_id": (
                        state.get("default_payer_id")
                        if state
                        else custom_state.get("default_payer_id")
                        if custom_state
                        else None
                    ),
                    "default_split": (
                        list(state.get("default_split") or [])
                        if state
                        else list(custom_state.get("default_split") or [])
                        if custom_state
                        else []
                    ),
                }
            )
            rows.append(row)

        # Keep locally installed parsers visible even if a catalog refresh removes them.
        for parser_id, state in installed.items():
            if parser_id in catalog_ids:
                continue
            parser = self.parsers.get(parser_id, {})
            metadata = parser.get("metadata", {}) if isinstance(parser, dict) else {}
            installed_country = self.catalog_client.normalize_country(metadata.get("country"))
            if installed_country and installed_country != country:
                # Keep the parser installed and active, but do not mix another
                # country's local parser into the selected catalog view.
                continue
            load_error = str(state.get("load_error") or "")
            installed_catalog_status = str(
                state.get("catalog_status")
                or metadata.get("status")
                or "experimental"
            )
            installed_source_commit = str(
                state.get("source_commit") or ""
            ).strip()
            rows.append(
                {
                    "id": parser_id,
                    "version": int(state.get("version", 0) or 0),
                    "name": metadata.get("name", parser_id),
                    "country": metadata.get("country", ""),
                    "language": metadata.get("language", ""),
                    "provider": metadata.get("provider", ""),
                    "bill_type": metadata.get("bill_type", ""),
                    "min_billy_version": metadata.get("min_billy_version", ""),
                    "installed": True,
                    "installed_version": int(state.get("version", 0) or 0),
                    "update_available": False,
                    "compatible": True,
                    "deprecated": False,
                    "catalog_status": str(
                        state.get("catalog_status")
                        or metadata.get("status")
                        or "experimental"
                    ),
                    "replacement": state.get("replacement"),
                    "source_commit": installed_source_commit,
                    "installed_catalog_status": installed_catalog_status,
                    "feedback_available": bool(
                        installed_catalog_status == "experimental"
                        and installed_source_commit
                    ),
                    "feedback_block_reason": (
                        "source_commit_unavailable"
                        if not installed_source_commit
                        else ""
                    ),
                    "removed_from_catalog": True,
                    "status": "error" if load_error else "removed",
                    "enabled": bool(state.get("enabled", True)),
                    "category_id": state.get("category_id"),
                    "auto_import": bool(state.get("auto_import", False)),
                    "load_error": load_error,
                    "source": "official",
                }
            )

        counts = {
            "total": len(rows),
            "installed": sum(1 for row in rows if row.get("installed")),
            "available": sum(1 for row in rows if row.get("status") == "available"),
            "outdated": sum(1 for row in rows if row.get("status") == "outdated"),
            "catalog_outdated": sum(
                1 for row in rows if row.get("catalog_status") == "outdated"
            ),
            "incompatible": sum(1 for row in rows if not row.get("compatible", True)),
            "deprecated": sum(1 for row in rows if row.get("deprecated")),
            "errors": sum(1 for row in rows if row.get("status") == "error"),
            "removed": sum(1 for row in rows if row.get("status") == "removed"),
        }
        catalog["parsers"] = rows
        catalog["counts"] = counts
        catalog["custom_count"] = len(custom)
        catalog["country"] = country
        return catalog

    def community_fingerprint(self, parser_id: str, version: int) -> str:
        """Return a parser-version-scoped anonymous installation fingerprint."""
        community_id = str(self.storage.data.get("community_id") or "")
        payload = f"{community_id}:{parser_id}:{int(version)}".encode()
        return hashlib.sha256(payload).hexdigest()

    def _backfill_installed_source_commits(
        self,
        catalog: dict[str, Any] | None = None,
    ) -> bool:
        """Backfill legacy installs only from an exact catalog id/version match."""
        if catalog is None:
            catalog = self._stored_catalog_for_country(self.catalog_country())
        if not isinstance(catalog, dict):
            return False
        source_commit = str(catalog.get("source_commit") or "").strip()
        if not source_commit:
            return False

        catalog_rows = {
            str(row.get("id") or ""): row
            for row in catalog.get("parsers", []) or []
            if isinstance(row, dict) and row.get("id")
        }
        changed = False
        for parser_id, state in self.storage.data.get("installed", {}).items():
            if str(state.get("source_commit") or "").strip():
                continue
            item = catalog_rows.get(str(parser_id))
            if item is None:
                continue
            try:
                installed_version = int(state.get("version", 0) or 0)
                catalog_version = int(item.get("version", 0) or 0)
            except (TypeError, ValueError):
                continue
            if installed_version < 1 or installed_version != catalog_version:
                continue

            installed_sha = str(state.get("sha256") or "").strip().lower()
            catalog_sha = str(item.get("sha256") or "").strip().lower()
            if installed_sha and catalog_sha and installed_sha != catalog_sha:
                continue

            state["source_commit"] = source_commit
            changed = True
        return changed

    def community_feedback_payload(
        self,
        parser_id: str,
        result: str,
    ) -> dict[str, Any]:
        """Build a feedback payload from the immutable installed parser state."""
        if result not in {"working", "partial", "failed"}:
            raise ValueError("Unsupported parser feedback result")
        if parser_id in self.storage.data.get("custom", {}):
            raise ValueError("Community feedback is not available for custom parsers")
        state = self.storage.data.get("installed", {}).get(parser_id)
        if state is None:
            raise ValueError("Parser is not installed")
        version = int(state.get("version", 0) or 0)
        if version < 1:
            raise ValueError("Installed parser version is invalid")
        source_commit = str(state.get("source_commit") or "").strip()
        if not source_commit:
            _LOGGER.warning(
                "Billy parser feedback skipped for %s v%s: source_commit unavailable",
                parser_id,
                version,
            )
            raise ValueError(FEEDBACK_SOURCE_UNKNOWN)
        return {
            "schema_version": 1,
            "parser_id": parser_id,
            "version": version,
            "result": result,
            "installation_fingerprint": self.community_fingerprint(
                parser_id, version
            ),
            "billy_version": self.billy_version,
            "source_commit": source_commit,
        }

    async def async_install(
        self,
        parser_id: str,
        *,
        category_id: str,
        expected_parser_id: str | None = None,
        enabled: bool = True,
        auto_import: bool = False,
        default_payer_id: str | None = None,
        default_split: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        self._ensure_category(category_id)
        payer_id, split = self._normalize_payment_defaults(default_payer_id, default_split)
        custom_state = self.storage.data.get("custom", {}).get(parser_id)
        country = self.catalog_country()
        catalog = self._stored_catalog_for_country(country)
        if not catalog.get("parsers"):
            await self.async_refresh_catalog()
            catalog = self._stored_catalog_for_country(country)
        item = next((row for row in catalog.get("parsers", []) if row.get("id") == parser_id), None)
        if item is None:
            raise CatalogError("Parser not found in the remote catalog")
        if not self._version_supported(str(item.get("min_billy_version") or "0.0.0")):
            raise CatalogError("This parser requires a newer Billy version")
        source_commit = str(catalog.get("source_commit") or "").strip()
        if not source_commit:
            raise CatalogError("Parser catalog has no source_commit")
        parser, content = await self.catalog_client.async_fetch_parser(catalog, item)
        validate_parser(parser)
        path = await self.storage.async_write_official(parser_id, content)
        self.storage.data["installed"][parser_id] = {
            "id": parser_id,
            "version": int(parser["version"]),
            "sha256": str(item.get("sha256") or ""),
            "source_commit": source_commit,
            "path": path,
            "enabled": bool(enabled),
            "category_id": category_id,
            "auto_import": bool(auto_import),
            "default_payer_id": payer_id,
            "default_split": split,
            "catalog_status": str(item.get("catalog_status") or "experimental"),
            "replacement": item.get("replacement"),
            "source": "official",
            "installed_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        }
        # Promotion path: once the official parser has been fetched, validated
        # and written successfully, retire the same-ID custom parser. Keep this
        # after the official write so a failed catalog fetch never destroys the
        # user's working custom parser.
        if custom_state is not None:
            self.storage.data.get("custom", {}).pop(parser_id, None)
        await self.storage.async_save()
        self.parsers[parser_id] = parser
        if custom_state and custom_state.get("path"):
            try:
                await self.storage.async_delete_file(str(custom_state["path"]))
            except Exception:  # noqa: BLE001
                _LOGGER.warning(
                    "Billy promoted custom parser %s to official but could not delete the old custom file",
                    parser_id,
                    exc_info=True,
                )
        return dict(self.storage.data["installed"][parser_id])

    async def async_uninstall(self, parser_id: str) -> bool:
        state = self.storage.data.get("installed", {}).pop(parser_id, None)
        if state is None:
            return False
        if state.get("path"):
            await self.storage.async_delete_file(str(state["path"]))
        self.parsers.pop(parser_id, None)
        await self.storage.async_save()
        return True

    async def async_configure(
        self,
        parser_id: str,
        *,
        category_id: str,
        enabled: bool,
        auto_import: bool,
        default_payer_id: str | None = None,
        default_split: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        self._ensure_category(category_id)
        state = self.storage.data.get("installed", {}).get(parser_id)
        if state is None:
            state = self.storage.data.get("custom", {}).get(parser_id)
        if state is None:
            raise ValueError("Parser is not installed")
        if default_payer_id is None and default_split is None:
            payer_id = state.get("default_payer_id")
            split = list(state.get("default_split") or [])
        else:
            payer_id, split = self._normalize_payment_defaults(default_payer_id, default_split)
        state.update(
            {
                "category_id": category_id,
                "enabled": bool(enabled),
                "auto_import": bool(auto_import),
                "default_payer_id": payer_id,
                "default_split": split,
            }
        )
        await self.storage.async_save()
        return dict(state)

    async def async_save_custom(
        self,
        content: str,
        *,
        category_id: str,
        enabled: bool = True,
        auto_import: bool = False,
        default_payer_id: str | None = None,
        default_split: list[dict[str, Any]] | None = None,
        expected_parser_id: str | None = None,
    ) -> dict[str, Any]:
        self._ensure_category(category_id)
        parser = load_parser_yaml(content)
        parser_id = str(parser["id"])
        if expected_parser_id is not None and parser_id != expected_parser_id:
            raise ValueError("Custom parser ID cannot be changed while editing")
        if parser_id in self.storage.data.get("installed", {}):
            raise ValueError(
                "An official parser with this ID is installed; uninstall it before saving the custom parser"
            )
        existing = self.storage.data.get("custom", {}).get(parser_id, {})
        if default_payer_id is None and default_split is None:
            payer_id = existing.get("default_payer_id")
            split = list(existing.get("default_split") or [])
        else:
            payer_id, split = self._normalize_payment_defaults(default_payer_id, default_split)
        path = await self.storage.async_write_custom(parser_id, content)
        self.storage.data["custom"][parser_id] = {
            "id": parser_id,
            "version": int(parser["version"]),
            "path": path,
            "enabled": bool(enabled),
            "category_id": category_id,
            "auto_import": bool(auto_import),
            "default_payer_id": payer_id,
            "default_split": split,
            "catalog_status": "custom",
            "source": "custom",
            "saved_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        }
        await self.storage.async_save()
        self.parsers[parser_id] = parser
        return dict(self.storage.data["custom"][parser_id])

    async def async_delete_custom(self, parser_id: str) -> bool:
        state = self.storage.data.get("custom", {}).pop(parser_id, None)
        if state is None:
            return False
        if state.get("path"):
            await self.storage.async_delete_file(str(state["path"]))
        self.parsers.pop(parser_id, None)
        await self.storage.async_save()
        return True

    async def async_export_custom(self, parser_id: str) -> tuple[str, str]:
        state = self.storage.data.get("custom", {}).get(parser_id)
        if state is None:
            raise ValueError("Custom parser not found")
        _parser, content = await self.storage.async_load_parser_file(str(state["path"]))
        return f"{parser_id}.yaml", content

    async def async_set_sources(self, entry_ids: list[str]) -> list[str]:
        known = {entry.entry_id for entry in self.hass.config_entries.async_entries("imap")}
        selected = sorted({str(value) for value in entry_ids if str(value) in known})
        self.storage.data["source_entry_ids"] = selected
        await self.storage.async_save()
        return selected

    def sources_snapshot(self) -> list[dict[str, Any]]:
        selected = set(self.storage.data.get("source_entry_ids", []))
        return [
            {
                "entry_id": entry.entry_id,
                "title": entry.title,
                "selected": entry.entry_id in selected,
            }
            for entry in self.hass.config_entries.async_entries("imap")
        ]

    def ingestion_diagnostic(self) -> dict[str, Any] | None:
        return dict(self._last_ingestion) if self._last_ingestion else None

    def installed_snapshot(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for source_name in ("installed", "custom"):
            for parser_id, state in self.storage.data.get(source_name, {}).items():
                parser = self.parsers.get(parser_id, {})
                metadata = parser.get("metadata", {}) if isinstance(parser, dict) else {}
                rows.append(
                    {
                        **dict(state),
                        "name": metadata.get("name", parser_id),
                        "provider": metadata.get("provider", ""),
                        "bill_type": metadata.get("bill_type", ""),
                        "country": metadata.get("country", ""),
                        "catalog_status": (
                            "custom"
                            if source_name == "custom"
                            else str(
                                state.get("catalog_status")
                                or metadata.get("status")
                                or "experimental"
                            )
                        ),
                        "replacement": state.get("replacement"),
                    }
                )
        return sorted(rows, key=lambda row: str(row.get("name", "")).casefold())

    def imports_snapshot(self, status: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        rows = self.storage.data.get("imports", [])
        if status:
            rows = [row for row in rows if row.get("status") == status]
        return [dict(row) for row in rows[: max(1, min(int(limit), 500))]]

    def get_import(self, import_id: str) -> dict[str, Any] | None:
        row = next((row for row in self.storage.data.get("imports", []) if row.get("id") == import_id), None)
        return dict(row) if row else None

    async def async_approve(self, import_id: str) -> dict[str, Any]:
        row = next((row for row in self.storage.data.get("imports", []) if row.get("id") == import_id), None)
        if row is None:
            raise ValueError("Import candidate not found")
        if row.get("status") == "imported":
            return dict(row)
        if row.get("status") != "pending":
            raise ValueError("Import candidate cannot be approved")
        try:
            candidate = dict(row)
            config = self.storage.data.get("installed", {}).get(str(row.get("parser_id") or ""))
            if config is None:
                config = self.storage.data.get("custom", {}).get(str(row.get("parser_id") or ""))
            if config:
                candidate["default_payer_id"] = config.get("default_payer_id")
                candidate["default_split"] = list(config.get("default_split") or [])
            expense = await self.importer.async_import(candidate)
        except Exception as err:
            row["status"] = "error"
            row["error"] = str(err)
            await self.storage.async_save()
            self._notify_import_updated()
            raise
        row["status"] = "imported"
        row["expense_id"] = expense.get("id")
        row["error"] = ""
        row["imported_at"] = datetime.now().astimezone().isoformat(timespec="seconds")
        await self.storage.async_save()
        self._notify_import_updated()
        return dict(row)

    def _normalize_payment_defaults(
        self,
        payer_id: str | None,
        split: list[dict[str, Any]] | None,
    ) -> tuple[str | None, list[dict[str, Any]]]:
        normalized_payer = self.bill_manager._validate_optional_payer(payer_id)
        if normalized_payer is None:
            return None, []
        if split is None:
            split = self.bill_manager.default_split()
        if not split:
            split = [{"payer_id": normalized_payer, "percentage": 100.0}]
        return normalized_payer, self.bill_manager._normalize_split(split)

    async def async_reject(self, import_id: str) -> dict[str, Any]:
        row = next((row for row in self.storage.data.get("imports", []) if row.get("id") == import_id), None)
        if row is None:
            raise ValueError("Import candidate not found")
        if row.get("status") == "imported":
            raise ValueError("Imported candidates cannot be rejected")
        row["status"] = "rejected"
        row["rejected_at"] = datetime.now().astimezone().isoformat(timespec="seconds")
        await self.storage.async_save()
        self._notify_import_updated()
        return dict(row)

    async def async_retry(self, import_id: str) -> dict[str, Any]:
        row = next(
            (
                row
                for row in self.storage.data.get("imports", [])
                if row.get("id") == import_id
            ),
            None,
        )
        if row is None:
            raise ValueError("Import candidate not found")
        if row.get("status") not in {"error", "rejected"}:
            raise ValueError("Only failed or rejected imports can be retried")
        source = dict(row.get("source") or {})
        if not source.get("entry_id") or not source.get("uid"):
            raise ValueError("Import does not contain enough IMAP source data")
        source_fingerprint = str(source.get("source_fingerprint") or "")
        if source_fingerprint:
            self._runtime_failed_fingerprints.discard(source_fingerprint)
        result = await self.async_process_imap_event(
            {
                "entry_id": source.get("entry_id"),
                "uid": source.get("uid"),
                "sender": source.get("sender"),
                "subject": source.get("subject"),
                "date": source.get("date"),
                "folder": source.get("folder"),
                "initial": False,
            },
            retry_import_id=import_id,
        )
        if result is not None:
            return result
        current = next(
            (
                item
                for item in self.storage.data.get("imports", [])
                if item.get("id") == import_id
            ),
            None,
        )
        if current is not None:
            current["error"] = current.get("error") or "Retry did not produce an import candidate"
            current["retried_at"] = datetime.now().astimezone().isoformat(timespec="seconds")
            await self.storage.async_save()
            self._notify_import_updated()
            return dict(current)
        raise ValueError("Retry did not produce an import candidate")

    async def async_test(
        self,
        content: str,
        *,
        sender: str,
        subject: str,
        email_text: str,
        documents: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        parser = load_parser_yaml(content)
        envelope = MailEnvelope(entry_id="test", uid="test", sender=sender, subject=subject)
        bundle = DocumentBundle(email=email_text, documents=dict(documents or {}))
        prefilter = self.engine.prefilter(parser, envelope)
        matched, score, threshold = self.engine.detect(parser, envelope, bundle)
        parsed = self.engine.parse(parser, envelope, bundle) if matched else {"data": {}, "provenance": {}}
        return {
            "prefilter": prefilter,
            "matched": matched,
            "score": score,
            "threshold": threshold,
            "data": parsed["data"],
            "provenance": parsed["provenance"],
            "verification": self.engine.verification(parser, bundle) if matched else [],
        }

    async def _reload_installed(self) -> None:
        self.parsers = {}
        dirty = False
        for source_name in ("installed", "custom"):
            states = self.storage.data.get(source_name, {})
            for parser_id, state in list(states.items()):
                try:
                    parser, _content = await self.storage.async_load_parser_file(str(state.get("path") or ""))
                    if str(parser.get("id")) != parser_id:
                        raise ValueError("Parser ID does not match its stored identity")
                    self.parsers[parser_id] = parser
                except Exception as err:
                    _LOGGER.warning("Unable to load Billy parser %s: %s", parser_id, err)
                    state["enabled"] = False
                    state["load_error"] = str(err)
                    dirty = True
        if dirty:
            await self.storage.async_save()

    async def _documents_for(
        self,
        parser: dict[str, Any],
        envelope: MailEnvelope,
        email_text: str,
    ) -> tuple[DocumentBundle, list[str]]:
        bundle = DocumentBundle(email=email_text)
        hashes: list[str] = []
        for document in parser.get("documents", {}).get("attachments", []) or []:
            document_id = str(document.get("id") or "")
            part = self._find_part(document, envelope.parts)
            if part is None:
                if document.get("required", False):
                    available = ", ".join(
                        f"{item.part}:{item.content_type}:{item.filename or '-'}"
                        for item in envelope.parts
                    ) or "none"
                    raise ParserError(
                        f"Required attachment '{document_id}' was not found; "
                        f"available parts: {available}"
                    )
                continue
            try:
                content = await self.imap.async_fetch_part(envelope, part)
                hashes.append(hashlib.sha256(content).hexdigest())
                extractor = document.get("extractor")
                if extractor == "pdf_text":
                    text = await self.hass.async_add_executor_job(extract_pdf_text, content)
                elif extractor == "text":
                    text = content.decode("utf-8", errors="replace")
                else:
                    raise ParserError(f"Unsupported extractor '{extractor}'")
            except (ImapSourceError, PdfExtractionError) as err:
                if document.get("required", False):
                    raise
                _LOGGER.warning(
                    "Billy skipped optional attachment '%s' for IMAP UID %s: %s",
                    document_id,
                    envelope.uid,
                    err,
                )
                continue
            bundle.documents[document_id] = text
        return bundle, hashes

    @staticmethod
    def _find_part(document: dict[str, Any], parts: list[MailPart]) -> MailPart | None:
        mime_types = {
            str(value).casefold().split(";", 1)[0].strip()
            for value in document.get("mime_types", []) or []
        }
        filename_regex = str(document.get("filename_regex") or "")
        generic_binary_types = {"", "application/octet-stream", "binary/octet-stream"}
        for part in parts:
            filename = part.filename or ""
            if filename_regex and not re.search(filename_regex, filename):
                continue

            content_type = part.content_type.casefold().split(";", 1)[0].strip()
            if mime_types and content_type not in mime_types:
                # Some providers (including TIM via Gmail) expose a real PDF as
                # application/octet-stream. If the parser supplied a restrictive
                # filename regex and it matches, treat a generic binary MIME as
                # unknown rather than rejecting the attachment.
                if not (filename_regex and content_type in generic_binary_types):
                    continue
            return part
        return None

    @staticmethod
    def _merge_fetched_envelope(envelope: MailEnvelope, fetched: dict[str, Any]) -> MailEnvelope:
        # Preserve attachment metadata already present on imap_content. The IMAP
        # fetch action normally returns the same metadata, but providers can omit
        # or downgrade MIME/filename information on a second parse. Never discard
        # metadata that was good enough to prefilter the original event.
        merged: dict[str, MailPart] = {part.part: part for part in envelope.parts}
        for part_id, metadata in (fetched.get("parts") or {}).items():
            if not isinstance(metadata, dict):
                continue
            key = str(part_id)
            previous = merged.get(key)
            merged[key] = MailPart(
                part=key,
                content_type=str(
                    metadata.get("content_type")
                    or (previous.content_type if previous else "")
                ),
                filename=str(
                    metadata.get("filename")
                    or (previous.filename if previous else "")
                ),
                content_transfer_encoding=str(
                    metadata.get("content_transfer_encoding")
                    or (previous.content_transfer_encoding if previous else "")
                ),
            )
        if merged:
            envelope.parts = list(merged.values())
        envelope.sender = str(fetched.get("sender") or envelope.sender)
        envelope.subject = str(fetched.get("subject") or envelope.subject)
        return envelope

    def _candidate(
        self,
        *,
        parser_id: str,
        parser: dict[str, Any],
        config: dict[str, Any],
        envelope: MailEnvelope,
        parsed: dict[str, Any],
        score: int,
        threshold: int,
        verification: list[dict[str, Any]],
        source_fingerprint: str,
        attachment_hashes: list[str],
    ) -> BillCandidate:
        data = dict(parsed.get("data") or {})
        verified = [item for item in verification if item.get("match")]
        conflicts = [item for item in verification if not item.get("match")]
        confidence = min(90, round(score / max(threshold, 1) * 80))
        if verification:
            confidence += round(10 * len(verified) / len(verification))
        if conflicts:
            confidence = min(confidence, 79)
        semantic = self._semantic_fingerprint(parser_id, data)
        fingerprint = hashlib.sha256(
            "|".join([source_fingerprint, semantic, *attachment_hashes]).encode("utf-8")
        ).hexdigest()
        source = {
            "type": "imap",
            "entry_id": envelope.entry_id,
            "uid": envelope.uid,
            "sender": envelope.sender,
            "subject": envelope.subject,
            "date": envelope.date,
            "folder": envelope.folder,
            "source_fingerprint": source_fingerprint,
            "semantic_fingerprint": semantic,
        }
        return BillCandidate(
            id=uuid4().hex,
            parser_id=parser_id,
            parser_version=int(parser.get("version", 1)),
            category_id=str(config.get("category_id") or ""),
            data=data,
            confidence=confidence,
            matched_score=score,
            matched_threshold=threshold,
            verification=verification,
            source=source,
            fingerprint=fingerprint,
            created_at=datetime.now().astimezone().isoformat(timespec="seconds"),
        )

    async def _record_candidate(self, candidate: BillCandidate) -> None:
        imports = self.storage.data.setdefault("imports", [])
        imports.insert(0, candidate.as_dict())
        del imports[MAX_IMPORT_HISTORY:]
        await self.storage.async_save()
        self._notify_import_updated()

    async def _record_error(
        self,
        envelope: MailEnvelope,
        source_fingerprint: str,
        error: str,
        *,
        import_id: str | None = None,
        parser_id: str | None = None,
        category_id: str | None = None,
    ) -> None:
        row = next(
            (
                item
                for item in self.storage.data.get("imports", [])
                if (import_id and item.get("id") == import_id)
                or (
                    not import_id
                    and item.get("status") == "error"
                    and item.get("source", {}).get("source_fingerprint")
                    == source_fingerprint
                )
            ),
            None,
        )
        stored_parser_id = parser_id or (str(row.get("parser_id") or "") if row else "")
        stored_category_id = category_id or (str(row.get("category_id") or "") if row else "")
        payload = {
            "id": uuid4().hex,
            "parser_id": stored_parser_id,
            "parser_version": 0,
            "category_id": stored_category_id,
            "data": {},
            "confidence": 0,
            "matched_score": 0,
            "matched_threshold": 0,
            "verification": [],
            "source": {
                "type": "imap",
                "entry_id": envelope.entry_id,
                "uid": envelope.uid,
                "sender": envelope.sender,
                "subject": envelope.subject,
                "date": envelope.date,
                "folder": envelope.folder,
                "source_fingerprint": source_fingerprint,
            },
            "fingerprint": source_fingerprint,
            "status": "error",
            "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "expense_id": None,
            "error": error[:500],
        }
        imports = self.storage.data.setdefault("imports", [])
        if row is not None:
            payload["id"] = str(row.get("id") or import_id)
            payload["created_at"] = str(row.get("created_at") or payload["created_at"])
            payload["retried_at"] = datetime.now().astimezone().isoformat(timespec="seconds")
            row.clear()
            row.update(payload)
        else:
            imports.insert(0, payload)
        del imports[MAX_IMPORT_HISTORY:]
        self._runtime_failed_fingerprints.add(source_fingerprint)
        await self.storage.async_save()
        self._notify_import_updated()

    def _remove_import(self, import_id: str) -> None:
        imports = self.storage.data.setdefault("imports", [])
        imports[:] = [row for row in imports if row.get("id") != import_id]

    def _remove_source_errors(self, source_fingerprint: str) -> None:
        imports = self.storage.data.setdefault("imports", [])
        imports[:] = [
            row
            for row in imports
            if not (
                row.get("status") == "error"
                and row.get("source", {}).get("source_fingerprint")
                == source_fingerprint
            )
        ]

    def _source_fingerprint_row(self, fingerprint: str) -> dict[str, Any] | None:
        # Persisted errors are deliberately excluded so a new integration/HA
        # runtime can retry them after code or parser fixes. A runtime-local set
        # suppresses repeated imap_content events after the first failure.
        return next(
            (
                row
                for row in self.storage.data.get("imports", [])
                if row.get("status") != "error"
                and row.get("source", {}).get("source_fingerprint") == fingerprint
            ),
            None,
        )

    def _has_source_fingerprint(self, fingerprint: str) -> bool:
        return self._source_fingerprint_row(fingerprint) is not None

    def _is_duplicate_candidate(self, candidate: BillCandidate) -> bool:
        semantic = candidate.source.get("semantic_fingerprint")
        for row in self.storage.data.get("imports", []):
            if row.get("fingerprint") == candidate.fingerprint:
                return True
            if semantic and row.get("source", {}).get("semantic_fingerprint") == semantic:
                return True
        return False

    @staticmethod
    def _prefetch_fingerprint(envelope: MailEnvelope) -> str:
        payload = f"imap|{envelope.entry_id}|{envelope.uid}|{envelope.sender}|{envelope.subject}"
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    @staticmethod
    def _semantic_fingerprint(parser_id: str, data: dict[str, Any]) -> str:
        invoice = str(data.get("invoice_number") or "").strip()
        if invoice:
            payload = f"{parser_id}|invoice|{invoice}"
        else:
            payload = "|".join(
                [
                    parser_id,
                    str(data.get("provider") or ""),
                    str(data.get("amount") or ""),
                    str(data.get("period_start") or ""),
                    str(data.get("period_end") or ""),
                    str(data.get("due_date") or ""),
                ]
            )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def _ensure_category(self, category_id: str) -> None:
        if self.bill_manager.category(category_id) is None:
            raise ValueError("Billy bill type does not exist")

    def _version_supported(self, minimum: str) -> bool:
        def parts(value: str) -> tuple[int, int, int]:
            match = re.match(r"^(\d+)\.(\d+)\.(\d+)", value)
            return tuple(map(int, match.groups())) if match else (0, 0, 0)

        return parts(self.billy_version) >= parts(minimum)

    def _notify_import_updated(self) -> None:
        self.hass.bus.async_fire(EVENT_IMPORT_UPDATED)

    def _set_ingestion_diagnostic(
        self,
        envelope: MailEnvelope,
        outcome: str,
        detail: str,
        *,
        parser_id: str | None = None,
    ) -> None:
        self._last_ingestion = {
            "uid": envelope.uid,
            "entry_id": envelope.entry_id,
            "sender": envelope.sender,
            "subject": envelope.subject,
            "outcome": outcome,
            "detail": detail,
            "parser_id": parser_id or "",
            "at": datetime.now().astimezone().isoformat(timespec="seconds"),
        }
