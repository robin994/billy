"""Sensor platform for Bill Tracker."""
from __future__ import annotations

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import DOMAIN, EVENT_UPDATED, FRONTEND_VERSION
from .manager import BillTrackerManager
from .parser.manager import EVENT_IMPORT_UPDATED, ParserManager
from .parser_api import register_parser_websockets
from .parser_http import register_parser_http


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the Bill Tracker sensor and the optional parser subsystem."""
    manager: BillTrackerManager = hass.data[DOMAIN][entry.entry_id]
    parser_manager = ParserManager(
        hass,
        manager,
        billy_version=hass.data[DOMAIN].get("version", FRONTEND_VERSION),
        config_entry=entry,
    )
    await parser_manager.async_load()
    await parser_manager.async_start()
    hass.data[DOMAIN]["parser_manager"] = parser_manager
    register_parser_websockets(hass)
    register_parser_http(hass)
    async_add_entities([BillTrackerSensor(manager, parser_manager)])


class BillTrackerSensor(SensorEntity):
    """Expose the current month's bill total as a sensor."""

    _attr_translation_key = "total_bills"
    _attr_unique_id = "bill_tracker_total"
    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_icon = "mdi:receipt-text"

    def __init__(self, manager: BillTrackerManager, parser_manager: ParserManager) -> None:
        self.manager = manager
        self.parser_manager = parser_manager

    async def async_added_to_hass(self) -> None:
        """Subscribe to Bill Tracker updates."""
        self.async_on_remove(self.hass.bus.async_listen(EVENT_UPDATED, self._on_update))
        self.async_on_remove(
            self.hass.bus.async_listen(EVENT_IMPORT_UPDATED, self._on_update)
        )

    async def async_will_remove_from_hass(self) -> None:
        await self.parser_manager.async_stop()
        domain_data = self.hass.data.get(DOMAIN, {})
        if domain_data.get("parser_manager") is self.parser_manager:
            domain_data.pop("parser_manager", None)

    @callback
    def _on_update(self, _event) -> None:
        self.async_write_ha_state()

    @property
    def native_unit_of_measurement(self):
        """Use the currency configured in Home Assistant."""
        return self.manager.currency

    @property
    def native_value(self):
        """Return the current month's total."""
        return self.manager.summary()["current_month"]

    @property
    def extra_state_attributes(self):
        """Expose compact summary data without duplicating the full database in Recorder."""
        summary = self.manager.summary()
        summary["automatic_import_pending"] = len(self.parser_manager.imports_snapshot("pending", 500))
        return summary
