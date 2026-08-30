"""Self-update support for Billy.

Billy is distributed as a HACS/custom integration and has no GitHub releases, so
updates are tracked against the ``main`` branch: the remote ``manifest.json``
gives the latest version and ``CHANGELOG.md`` the release notes. Installing an
update downloads the branch zipball and swaps it in over the running copy; Home
Assistant must be restarted afterwards to load the new code.
"""
from __future__ import annotations

import asyncio
import io
import json
import logging
import re
import shutil
import zipfile
from collections.abc import Callable
from datetime import timedelta
from pathlib import Path
from typing import Any

from aiohttp import ClientError, ClientTimeout

from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

_REPO = "robin994/billy"
_BRANCH = "main"
_RAW_BASE = f"https://raw.githubusercontent.com/{_REPO}/{_BRANCH}"
REMOTE_MANIFEST_URL = f"{_RAW_BASE}/custom_components/bill_tracker/manifest.json"
REMOTE_CHANGELOG_URL = f"{_RAW_BASE}/CHANGELOG.md"
ZIPBALL_URL = f"https://codeload.github.com/{_REPO}/zip/refs/heads/{_BRANCH}"
CHANGELOG_URL = f"https://github.com/{_REPO}/blob/{_BRANCH}/CHANGELOG.md"

CHECK_INTERVAL = timedelta(hours=6)
_HTTP_TIMEOUT = ClientTimeout(total=30)
_DOWNLOAD_TIMEOUT = ClientTimeout(total=180)
_MAX_MANIFEST_BYTES = 64_000
_MAX_CHANGELOG_BYTES = 512_000
_MAX_ZIP_BYTES = 40_000_000

_COMPONENT_DIR = Path(__file__).parent


def version_tuple(value: str) -> tuple[int, int, int]:
    """Best-effort ``MAJOR.MINOR.PATCH`` tuple for comparing Billy versions."""
    match = re.match(r"\s*v?(\d+)\.(\d+)\.(\d+)", str(value or ""))
    return tuple(map(int, match.groups())) if match else (0, 0, 0)


def changelog_since(changelog: str, installed: str) -> str:
    """Return the ``## x.y.z`` sections of CHANGELOG.md newer than ``installed``."""
    installed_key = version_tuple(installed)
    sections = re.split(r"^## +", changelog, flags=re.MULTILINE)
    picked: list[str] = []
    for section in sections[1:]:
        heading = section.splitlines()[0].strip()
        if version_tuple(heading) > installed_key:
            picked.append(f"## {section.strip()}")
    return "\n\n".join(picked).strip()


class BillyUpdater:
    """Checks for and installs Billy updates from the ``main`` branch."""

    def __init__(self, hass: HomeAssistant, installed_version: str) -> None:
        self.hass = hass
        self.installed_version = installed_version
        self.latest_version: str | None = None
        self.release_notes: str | None = None
        self.last_error: str | None = None
        self.installing = False
        # An in-place install cannot hot-swap the running code: the new files are
        # on disk but Home Assistant keeps executing the old modules (and the
        # cached frontend bundle) until it is restarted.
        self.restart_required = False
        self.pending_version: str | None = None
        self._listeners: list[Callable[[], None]] = []
        self._lock = asyncio.Lock()

    # -- state -----------------------------------------------------------------
    @property
    def update_available(self) -> bool:
        if self.restart_required or not self.latest_version:
            return False
        return version_tuple(self.latest_version) > version_tuple(self.installed_version)

    def add_listener(self, listener: Callable[[], None]) -> Callable[[], None]:
        self._listeners.append(listener)

        def _remove() -> None:
            if listener in self._listeners:
                self._listeners.remove(listener)

        return _remove

    def _notify(self) -> None:
        for listener in list(self._listeners):
            listener()

    def as_dict(self) -> dict[str, Any]:
        return {
            "installed_version": self.installed_version,
            "latest_version": self.latest_version or self.installed_version,
            "update_available": self.update_available,
            "restart_required": self.restart_required,
            "pending_version": self.pending_version or "",
            "release_notes": self.release_notes or "",
            "release_url": CHANGELOG_URL,
            "installing": self.installing,
            "last_error": self.last_error,
        }

    # -- check ---------------------------------------------------------------
    async def _fetch(self, url: str, max_bytes: int) -> bytes:
        session = async_get_clientsession(self.hass)
        async with session.get(url, timeout=_HTTP_TIMEOUT) as resp:
            resp.raise_for_status()
            length = resp.content_length
            if length is not None and length > max_bytes:
                raise ValueError(f"{url} is unexpectedly large ({length} bytes)")
            raw = await resp.read()
        if len(raw) > max_bytes:
            raise ValueError(f"{url} is unexpectedly large")
        return raw

    async def _local_manifest_version(self) -> str:
        """Version currently written to disk (may be ahead of the running code)."""
        try:
            raw = await self.hass.async_add_executor_job(
                (_COMPONENT_DIR / "manifest.json").read_text
            )
            return str(json.loads(raw).get("version") or "").strip()
        except Exception:  # noqa: BLE001
            return self.installed_version

    async def async_check(self) -> None:
        # New files on disk (from this updater or from HACS / a manual copy) do
        # not take effect until Home Assistant restarts. Detect that so the UI
        # can say so instead of just showing a stale version number.
        on_disk = await self._local_manifest_version()
        if on_disk and version_tuple(on_disk) > version_tuple(self.installed_version):
            self.restart_required = True
            self.pending_version = on_disk

        try:
            raw = await self._fetch(REMOTE_MANIFEST_URL, _MAX_MANIFEST_BYTES)
            latest = str(json.loads(raw).get("version") or "").strip()
            self.latest_version = latest or None

            notes = ""
            if self.update_available:
                text = (
                    await self._fetch(REMOTE_CHANGELOG_URL, _MAX_CHANGELOG_BYTES)
                ).decode("utf-8", "replace")
                notes = changelog_since(text, self.installed_version)
            self.release_notes = notes or None
            self.last_error = None
        except (ClientError, TimeoutError) as err:
            self.last_error = str(err)
            _LOGGER.debug("Billy update check failed: %s", err)
        except Exception as err:  # noqa: BLE001
            self.last_error = str(err)
            _LOGGER.debug("Billy update check failed unexpectedly: %s", err)
        self._notify()

    # -- install -----------------------------------------------------------
    async def async_install(self) -> None:
        async with self._lock:
            if self.restart_required:
                raise RuntimeError(
                    f"Billy {self.pending_version} is installed — "
                    "restart Home Assistant to apply it"
                )
            if not self.update_available:
                await self.async_check()
                if not self.update_available:
                    raise RuntimeError("Billy is already up to date")
            self.installing = True
            self.last_error = None
            self._notify()
            target = self.latest_version
            try:
                session = async_get_clientsession(self.hass)
                async with session.get(
                    ZIPBALL_URL, timeout=_DOWNLOAD_TIMEOUT
                ) as resp:
                    resp.raise_for_status()
                    payload = await resp.read()
                if len(payload) > _MAX_ZIP_BYTES:
                    raise RuntimeError("downloaded archive is too large")
                await self.hass.async_add_executor_job(
                    _apply_zipball, payload, str(target)
                )
            except Exception as err:  # noqa: BLE001
                self.last_error = str(err)
                self.installing = False
                self._notify()
                _LOGGER.exception("Billy update install failed")
                raise
            self.pending_version = str(target)
            self.restart_required = True
            self.installing = False
            self._notify()

        from homeassistant.components import persistent_notification

        persistent_notification.async_create(
            self.hass,
            (
                f"Billy has been updated to {target}. "
                "Restart Home Assistant to load the new version."
            ),
            title="Billy update installed",
            notification_id=f"{DOMAIN}_update_restart",
        )


def _apply_zipball(payload: bytes, expected_version: str) -> None:
    """Extract the branch zipball and swap it in over the running component dir."""
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        marker = "/custom_components/bill_tracker/manifest.json"
        entry = next(
            (name for name in archive.namelist() if name.endswith(marker)), None
        )
        if entry is None:
            raise RuntimeError("downloaded archive is not a Billy build")
        prefix = entry[: -len("manifest.json")]

        staging = _COMPONENT_DIR.parent / "bill_tracker.new"
        backup = _COMPONENT_DIR.parent / "bill_tracker.bak"
        for path in (staging, backup):
            if path.exists():
                shutil.rmtree(path)

        for name in archive.namelist():
            if not name.startswith(prefix) or name.endswith("/"):
                continue
            relative = name[len(prefix) :]
            if not relative or relative.startswith("/") or ".." in relative:
                continue
            destination = staging / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(name) as source, open(destination, "wb") as out:
                shutil.copyfileobj(source, out)

    manifest = staging / "manifest.json"
    if not manifest.is_file():
        shutil.rmtree(staging, ignore_errors=True)
        raise RuntimeError("downloaded archive is incomplete")
    if str(json.loads(manifest.read_text("utf-8")).get("version") or "") != expected_version:
        shutil.rmtree(staging, ignore_errors=True)
        raise RuntimeError("downloaded archive version does not match the update")

    _COMPONENT_DIR.rename(backup)
    try:
        staging.rename(_COMPONENT_DIR)
    except Exception:
        if not _COMPONENT_DIR.exists():
            backup.rename(_COMPONENT_DIR)
        raise
    shutil.rmtree(backup, ignore_errors=True)
