"""Sensor platform for ha_jsy — one sensor per monitored dictionary key."""

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
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    CONF_MONITORED_PARAMETERS,
    COORDINATOR,
    DEFAULT_PARAMETERS,
    DOMAIN,
    PARAMETER_META,
    channel_of,
)
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
    """Create a sensor for every monitored key of the decoder dictionary."""
    coordinator: JsyCoordinator = hass.data[DOMAIN][entry.entry_id][COORDINATOR]

    monitored: list[str] = entry.data.get(
        CONF_MONITORED_PARAMETERS, DEFAULT_PARAMETERS
    )

    entities: list[JsySensor] = []
    for key in monitored:
        if coordinator.data and key not in coordinator.data:
            _LOGGER.warning("Parameter %s not in JSY data — skipping", key)
            continue
        entities.append(JsySensor(coordinator, key))

    # Sensors that were un-ticked in the options are removed from the entity
    # registry instead of lingering as "unavailable". Their statistics stay in
    # the recorder and are picked up again if the parameter is re-selected.
    wanted = {entity.unique_id for entity in entities}
    registry = er.async_get(hass)
    for reg_entry in er.async_entries_for_config_entry(registry, entry.entry_id):
        if reg_entry.domain == "sensor" and reg_entry.unique_id not in wanted:
            registry.async_remove(reg_entry.entity_id)

    async_add_entities(entities)


class JsySensor(JsyEntity, SensorEntity):
    """One sensor entity per dictionary key."""

    def __init__(self, coordinator: JsyCoordinator, key: str) -> None:
        super().__init__(coordinator, key)
        meta = PARAMETER_META.get(key)
        if meta is None:
            self._attr_name = key
            return

        friendly_name, unit, dc_str, sc_str, icon, precision, diagnostic = meta
        self._attr_name = self._channel_name(friendly_name, channel_of(key))
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
