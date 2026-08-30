"""Update entity for Billy — surfaces new versions in Settings > Updates."""
from __future__ import annotations

from typing import Any

from homeassistant.components.update import UpdateEntity, UpdateEntityFeature
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.event import async_track_time_interval

from .const import DOMAIN
from .updater import CHANGELOG_URL, CHECK_INTERVAL, BillyUpdater


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the Billy update entity."""
    updater: BillyUpdater = hass.data[DOMAIN]["updater"]
    async_add_entities([BillyUpdateEntity(updater)])


class BillyUpdateEntity(UpdateEntity):
    """Reports and installs Billy updates tracked against the main branch."""

    _attr_has_entity_name = True
    _attr_translation_key = "billy"
    _attr_unique_id = "bill_tracker_update"
    _attr_title = "Billy"
    _attr_release_url = CHANGELOG_URL
    _attr_supported_features = (
        UpdateEntityFeature.INSTALL | UpdateEntityFeature.RELEASE_NOTES
    )

    def __init__(self, updater: BillyUpdater) -> None:
        self._updater = updater

    @property
    def installed_version(self) -> str:
        return self._updater.installed_version

    @property
    def latest_version(self) -> str:
        return self._updater.latest_version or self._updater.installed_version

    @property
    def in_progress(self) -> bool:
        return self._updater.installing

    def release_notes(self) -> str | None:
        return self._updater.release_notes

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(self._updater.add_listener(self.async_write_ha_state))
        self.async_on_remove(
            async_track_time_interval(
                self.hass, self._async_scheduled_check, CHECK_INTERVAL
            )
        )
        self.hass.async_create_background_task(
            self._updater.async_check(), "billy_update_check"
        )

    async def _async_scheduled_check(self, _now: Any) -> None:
        await self._updater.async_check()

    async def async_update(self) -> None:
        await self._updater.async_check()

    async def async_install(
        self, version: str | None, backup: bool, **kwargs: Any
    ) -> None:
        await self._updater.async_install()
