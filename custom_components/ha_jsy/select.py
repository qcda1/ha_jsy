"""Select platform for ha_jsy — baud rate (register 0004H, low byte).

"Baud Rate (Set)" writes the new speed to the module; the integration then
talks to it at that speed and updates its own configuration.
"""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import BAUD_RATE_CODES, COORDINATOR, DOMAIN
from .coordinator import JsyCoordinator
from .entity import JsyEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the baud-rate select of one JSY module."""
    coordinator: JsyCoordinator = hass.data[DOMAIN][entry.entry_id][COORDINATOR]
    async_add_entities([JsyBaudRateSelect(coordinator)])


class JsyBaudRateSelect(JsyEntity, SelectEntity):
    """Editable baud rate."""

    _attr_entity_category = EntityCategory.CONFIG
    _attr_icon = "mdi:pencil-outline"
    _attr_name = "Baud Rate (Set)"
    _attr_options = [str(baud) for baud in BAUD_RATE_CODES]

    def __init__(self, coordinator: JsyCoordinator) -> None:
        super().__init__(coordinator, "BaudRate_set")

    @property
    def current_option(self) -> str | None:
        if self.coordinator.data is None:
            return None
        baud = self.coordinator.data.get("BaudRate")
        return str(baud) if baud is not None else None

    async def async_select_option(self, option: str) -> None:
        await self.coordinator.async_change_comm_settings(new_baudrate=int(option))
