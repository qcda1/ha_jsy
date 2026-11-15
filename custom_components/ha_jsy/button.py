"""Button platform for ha_jsy — energy counter resets.

  "Reset Energy Channel 1"   zeroes 004BH and 004DH
  "Reset Energy Channel 2"   zeroes 0053H and 0055H
  "Reset Energy (All)"       writes 0 to 000CH (manual 4.4.2)
"""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import COORDINATOR, DOMAIN
from .coordinator import JsyCoordinator
from .entity import JsyEntity

# key -> (name, channel)   channel 0 = both
_BUTTONS: dict[str, tuple[str, int]] = {
    "reset_energy_1":   ("Reset Energy Channel 1", 1),
    "reset_energy_2":   ("Reset Energy Channel 2", 2),
    "reset_energy_all": ("Reset Energy (All)", 0),
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the reset buttons of one JSY module."""
    coordinator: JsyCoordinator = hass.data[DOMAIN][entry.entry_id][COORDINATOR]
    async_add_entities(
        JsyResetEnergyButton(coordinator, key, name, channel)
        for key, (name, channel) in _BUTTONS.items()
    )


class JsyResetEnergyButton(JsyEntity, ButtonEntity):
    """Zero the energy counters of one channel, or of both."""

    _attr_entity_category = EntityCategory.CONFIG
    _attr_icon = "mdi:counter"

    def __init__(
        self, coordinator: JsyCoordinator, key: str, name: str, channel: int
    ) -> None:
        super().__init__(coordinator, key)
        self._attr_name = self._channel_name(name, channel or None)
        self._channel = channel

    async def async_press(self) -> None:
        """A failure surfaces as an error in the HA UI."""
        await self.coordinator.async_clear_energy(self._channel)
