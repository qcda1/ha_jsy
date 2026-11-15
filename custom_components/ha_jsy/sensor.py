"""Sensor platform for ha_jsy — one sensor per key of the decoder dictionary."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import COORDINATOR, DOMAIN, PARAMETER_META
from .coordinator import JsyCoordinator
from .entity import JsyEntity

_LOGGER = logging.getLogger(__name__)

_DEVICE_CLASS_MAP: dict[str, SensorDeviceClass] = {
    "voltage":      SensorDeviceClass.VOLTAGE,
    "current":      SensorDeviceClass.CURRENT,
    "power":        SensorDeviceClass.POWER,
    "energy":       SensorDeviceClass.ENERGY,
    "power_factor": SensorDeviceClass.POWER_FACTOR,
    "frequency":    SensorDeviceClass.FREQUENCY,
}

_STATE_CLASS_MAP: dict[str, SensorStateClass] = {
    "measurement":      SensorStateClass.MEASUREMENT,
    "total":            SensorStateClass.TOTAL,
    "total_increasing": SensorStateClass.TOTAL_INCREASING,
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Create a sensor for every value returned by jsy_modbusdecoder."""
    coordinator: JsyCoordinator = hass.data[DOMAIN][entry.entry_id][COORDINATOR]

    # Documented keys first (in PARAMETER_META order), then anything else the
    # decoder returns, so a key added to jsy_modbusdecoder.py shows up in HA
    # without touching the integration.
    keys = list(PARAMETER_META)
    for key in coordinator.data or {}:
        if key not in PARAMETER_META:
            _LOGGER.info("Key %s has no PARAMETER_META entry — plain sensor", key)
            keys.append(key)

    async_add_entities(JsySensor(coordinator, key) for key in keys)


class JsySensor(JsyEntity, SensorEntity):
    """One sensor entity per dictionary key."""

    def __init__(self, coordinator: JsyCoordinator, key: str) -> None:
        super().__init__(coordinator, key)
        meta = PARAMETER_META.get(key)
        if meta is None:
            self._attr_name = key
            return

        friendly_name, unit, dc_str, sc_str, icon, precision, diagnostic = meta
        self._attr_name = friendly_name
        self._attr_native_unit_of_measurement = unit
        self._attr_device_class = _DEVICE_CLASS_MAP.get(dc_str) if dc_str else None
        self._attr_state_class = _STATE_CLASS_MAP.get(sc_str) if sc_str else None
        self._attr_icon = icon
        if precision is not None:
            self._attr_suggested_display_precision = precision
        if diagnostic:
            self._attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def native_value(self) -> Any:
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.get(self._key)
