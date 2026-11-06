"""Persistent parser configuration and parser file storage."""
from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import uuid4

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .validator import load_parser_yaml

PARSER_STORAGE_VERSION = 1
PARSER_STORAGE_KEY = "bill_tracker.parsers"


class ParserStorage:
    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass
        self._store: Store[dict[str, Any]] = Store(hass, PARSER_STORAGE_VERSION, PARSER_STORAGE_KEY)
        self.root = Path(hass.config.path("billy", "parsers"))
        self.official_dir = self.root / "official"
        self.custom_dir = self.root / "custom"
        self.data: dict[str, Any] = self.defaults()

    @staticmethod
    def defaults() -> dict[str, Any]:
        return {
            "schema_version": 1,
            "catalog": {},
            "catalog_cache": {"index": {}, "country": "", "path": "", "shard": {}},
            "catalog_other_countries": {},
            "catalog_other_caches": {},
            "community_id": "",
            "installed": {},
            "custom": {},
            "source_entry_ids": [],
            "imports": [],
        }

    async def async_load(self) -> dict[str, Any]:
        loaded = await self._store.async_load() or {}
        data = self.defaults()
        for key in data:
            if key in loaded:
                data[key] = loaded[key]
        if not isinstance(data["installed"], dict):
            data["installed"] = {}
        if not isinstance(data["custom"], dict):
            data["custom"] = {}
        if not isinstance(data["catalog_other_countries"], dict):
            data["catalog_other_countries"] = {}
        if not isinstance(data["catalog_other_caches"], dict):
            data["catalog_other_caches"] = {}
        if not isinstance(data["catalog_cache"], dict):
            data["catalog_cache"] = {
                "index": {},
                "country": "",
                "path": "",
                "shard": {},
            }
        else:
            cache = data["catalog_cache"]
            if not isinstance(cache.get("index"), dict):
                cache["index"] = {}
            if not isinstance(cache.get("shard"), dict):
                cache["shard"] = {}
            cache["country"] = str(cache.get("country") or "")
            cache["path"] = str(cache.get("path") or "")
        community_id = str(data.get("community_id") or "").strip()
        generated_community_id = not community_id
        if not community_id:
            community_id = uuid4().hex
        data["community_id"] = community_id
        if not isinstance(data["source_entry_ids"], list):
            data["source_entry_ids"] = []
        if not isinstance(data["imports"], list):
            data["imports"] = []
        self.data = data
        if generated_community_id:
            await self._store.async_save(self.data)
        await self.hass.async_add_executor_job(self._ensure_dirs)
        return self.data

    async def async_save(self) -> None:
        await self._store.async_save(self.data)

    async def async_write_official(self, parser_id: str, content: str) -> str:
        path = self.official_dir / f"{self._safe_name(parser_id)}.yaml"
        await self.hass.async_add_executor_job(path.write_text, content, "utf-8")
        return str(path)

    async def async_write_custom(self, parser_id: str, content: str) -> str:
        path = self.custom_dir / f"{self._safe_name(parser_id)}.yaml"
        await self.hass.async_add_executor_job(path.write_text, content, "utf-8")
        return str(path)

    async def async_delete_file(self, path_value: str) -> None:
        path = Path(path_value)
        if not self._is_under_root(path):
            return
        await self.hass.async_add_executor_job(path.unlink, True)

    async def async_load_parser_file(self, path_value: str) -> tuple[dict[str, Any], str]:
        path = Path(path_value)
        if not self._is_under_root(path):
            raise ValueError("Parser path is outside Billy's parser directory")
        content = await self.hass.async_add_executor_job(path.read_text, "utf-8")
        return load_parser_yaml(content), content

    def _ensure_dirs(self) -> None:
        self.official_dir.mkdir(parents=True, exist_ok=True)
        self.custom_dir.mkdir(parents=True, exist_ok=True)

    def _is_under_root(self, path: Path) -> bool:
        try:
            path.resolve().relative_to(self.root.resolve())
            return True
        except ValueError:
            return False

    @staticmethod
    def _safe_name(parser_id: str) -> str:
        return "".join(char if char.isalnum() or char in "._-" else "_" for char in parser_id)
