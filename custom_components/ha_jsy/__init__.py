"""JSY-MK-194 energy meter — ha_jsy integration."""

from __future__ import annotations

import asyncio
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .const import COORDINATOR, DOMAIN, SERIAL_LOCK
from .coordinator import JsyCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.SENSOR,
    Platform.NUMBER,
    Platform.BUTTON,
    Platform.SELECT,
]


def get_serial_lock(hass: HomeAssistant) -> asyncio.Lock:
    """One lock for every serial access of the integration.

    Reads, writes and port scans of all configured modules are serialised so
    two of them never talk on the same port at the same time.
    """
    return hass.data.setdefault(DOMAIN, {}).setdefault(SERIAL_LOCK, asyncio.Lock())


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up ha_jsy from a config entry."""
    coordinator = JsyCoordinator(hass, entry, get_serial_lock(hass))

    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {COORDINATOR: coordinator}

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    # A port relocation during the first refresh happened before the listener
    # existed: clear the flag so it does not swallow the next user change.
    coordinator.consume_internal_update()
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    return True


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the entry when the user changes it (options flow).

    Changes the coordinator makes on its own (port relocation, new Modbus ID
    or baud rate) are already applied in memory and must not trigger a reload.
    """
    stored = hass.data.get(DOMAIN, {}).get(entry.entry_id)
    coordinator: JsyCoordinator | None = stored.get(COORDINATOR) if stored else None
    if coordinator is not None and coordinator.consume_internal_update():
        return
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unload_ok
