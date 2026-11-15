"""Diagnostics support for ha_jsy.

Settings → Devices & Services → JSY-MK-194 → ⋮ → Download diagnostics.
The report holds the connection settings, the health counters, the last
failures, the last decoded dictionary and the serial ports seen by the host.
"""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from . import jsy_reader
from .const import COORDINATOR, DOMAIN


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    stored = hass.data.get(DOMAIN, {}).get(entry.entry_id) or {}
    coordinator = stored.get(COORDINATOR)
    ports = await hass.async_add_executor_job(jsy_reader.list_serial_ports)

    return {
        "entry": {
            "title": entry.title,
            "version": entry.version,
            "unique_id": entry.unique_id,
            "data": dict(entry.data),
            "options": dict(entry.options),
        },
        "coordinator": coordinator.diagnostic_snapshot() if coordinator else None,
        "serial_ports": [port.as_dict() for port in ports],
    }
