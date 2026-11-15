"""Number platform for ha_jsy — writable registers.

Energy counters (004BH, 004DH, 0053H, 0055H)
    "Energy Positive 1 (Set)" ... let you preset a counter, e.g. to line the
    module up with a utility meter. Writing 0 clears it.

Modbus ID (0004H, high byte)
    "Modbus ID (Set)" changes the ID stored in the module. The integration
    follows the module to its new ID and updates its own configuration.

The "(Set)" suffix separates these editable entities from the read-only
sensors that show the same register.
"""

from __future__ import annotations

import logging

from homeassistant.components.number import NumberDeviceClass, NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory, UnitOfEnergy
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    COORDINATOR,
    DOMAIN,
    ENERGY_MAX_KWH,
    MAX_DEVICE_ID,
    MIN_DEVICE_ID,
    PARAMETER_META,
    WRITABLE_ENERGY_REGISTERS,
    channel_of,
)
from .coordinator import JsyCoordinator
from .entity import JsyEntity

_LOGGER = logging.getLogger(__name__)

_EDITABLE_SUFFIX = " (Set)"
_EDITABLE_ICON = "mdi:pencil-outline"


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the editable registers of one JSY module."""
    coordinator: JsyCoordinator = hass.data[DOMAIN][entry.entry_id][COORDINATOR]

    entities: list[NumberEntity] = [
        JsyEnergyNumber(coordinator, key) for key in WRITABLE_ENERGY_REGISTERS
    ]
    entities.append(JsyDeviceIdNumber(coordinator))
    async_add_entities(entities)


class JsyEnergyNumber(JsyEntity, NumberEntity):
    """Editable energy counter (kWh)."""

    _attr_entity_category = EntityCategory.CONFIG
    _attr_mode = NumberMode.BOX
    _attr_icon = _EDITABLE_ICON
    _attr_device_class = NumberDeviceClass.ENERGY
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_native_min_value = 0
    _attr_native_step = 0.0001

    def __init__(self, coordinator: JsyCoordinator, key: str) -> None:
        super().__init__(coordinator, f"{key}_set")
        self._data_key = key
        channel = channel_of(key)
        self._attr_name = self._channel_name(
            f"{PARAMETER_META[key][0]}{_EDITABLE_SUFFIX}", channel
        )
        # The value shown is the module counter x the circuit multiplier
        self._attr_native_max_value = (
            ENERGY_MAX_KWH * coordinator.channel_multipliers.get(channel or 0, 1)
        )

    @property
    def native_value(self) -> float | None:
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.get(self._data_key)

    async def async_set_native_value(self, value: float) -> None:
        """Write the counter; a failure surfaces as an error in the HA UI."""
        await self.coordinator.async_write_energy(self._data_key, value)


class JsyDeviceIdNumber(JsyEntity, NumberEntity):
    """Editable Modbus ID (register 0004H, high byte)."""

    _attr_entity_category = EntityCategory.CONFIG
    _attr_mode = NumberMode.BOX
    _attr_icon = _EDITABLE_ICON
    _attr_native_min_value = MIN_DEVICE_ID
    _attr_native_max_value = MAX_DEVICE_ID
    _attr_native_step = 1

    def __init__(self, coordinator: JsyCoordinator) -> None:
        super().__init__(coordinator, "DeviceID_set")
        self._attr_name = f"{PARAMETER_META['DeviceID'][0]}{_EDITABLE_SUFFIX}"

    @property
    def native_value(self) -> int | None:
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.get("DeviceID")

    async def async_set_native_value(self, value: float) -> None:
        await self.coordinator.async_change_comm_settings(new_device_id=int(value))
