"""Base entity for ha_jsy — one HA device per JSY module."""

from __future__ import annotations

import re

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import slugify

from .const import DOMAIN, MANUFACTURER
from .coordinator import JsyCoordinator


class JsyEntity(CoordinatorEntity[JsyCoordinator]):
    """Common device info and unique-id scheme."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: JsyCoordinator, key: str) -> None:
        super().__init__(coordinator)
        self._key = key
        # Based on the config entry, not on the port or the Modbus ID, so the
        # entities survive a port change or an ID change.
        self._attr_unique_id = f"{DOMAIN}_{coordinator.entry.entry_id}_{key}"

    def _set_name(self, domain: str, name: str, channel: int | None = None) -> None:
        """Set the entity name and its entity ID.

        The entity ID is imposed here so that it never depends on the area the
        device is placed in:

        * channel WITH a user name ("Heat pump"): the entity stands on its own.
          "Power 1 (signed)" becomes "Heat pump Power (signed)", with the ID
          ``sensor.heat_pump_power_signed`` — no device name, because a module
          often measures two unrelated circuits.
        * otherwise: the usual "<device> <name>", with the ID
          ``sensor.<device>_<name>``.

        An entity that already exists keeps the ID stored in the registry.
        """
        custom = self.coordinator.channel_names.get(channel or 0, "")
        if custom:
            stripped = re.sub(rf"\s(?:Channel\s)?{channel}\b", "", name, count=1)
            self._attr_has_entity_name = False
            self._attr_name = f"{custom} {stripped}"
            self.entity_id = f"{domain}.{slugify(self._attr_name)}"
        else:
            self._attr_name = name
            self.entity_id = (
                f"{domain}.{slugify(self.coordinator.device_name)}_{slugify(name)}"
            )

    @property
    def device_info(self) -> DeviceInfo:
        data = self.coordinator.data or {}
        model = data.get("Model1txt")
        return DeviceInfo(
            identifiers={(DOMAIN, self.coordinator.entry.entry_id)},
            name=self.coordinator.device_name,
            manufacturer=MANUFACTURER,
            model=f"JSY-MK-{model}" if model else "JSY-MK-194",
        )
