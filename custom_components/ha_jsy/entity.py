"""Base entity for ha_jsy — one HA device per JSY module."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

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
