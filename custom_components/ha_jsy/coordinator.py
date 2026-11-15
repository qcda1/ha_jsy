"""DataUpdateCoordinator for one JSY-MK-194 module."""

from __future__ import annotations

import asyncio
import logging
import os
from collections import deque
from datetime import datetime, timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from . import jsy_reader, jsy_writer
from .const import (
    BAUD_RATE_CODES,
    CHANNELS,
    CIRCUIT_MULTIPLIER,
    CONF_AUTO_RELOCATE,
    CONF_BAUDRATE,
    CONF_CHANNEL_CIRCUIT,
    CONF_CHANNEL_NAME,
    CONF_DEVICE_ID,
    CONF_PORT,
    CONF_SCAN_INTERVAL,
    CONF_USB_PID,
    CONF_USB_VID,
    DEFAULT_AUTO_RELOCATE,
    DEFAULT_BAUDRATE,
    DEFAULT_CIRCUIT,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    SCALED_CHANNEL_KEYS,
    channel_of,
)
from .jsy_reader import JsyConnectionError, JsyModuleNotFoundError
from .jsy_writer import WriteResult

_LOGGER = logging.getLogger(__name__)

#: How many past failures to keep for the diagnostics download.
ERROR_HISTORY_SIZE = 20

#: Pause between a write to 0004H and the first request with the new settings.
COMM_CHANGE_SETTLE = 0.5


def entry_unique_id(device_id: int) -> str:
    """Config-entry unique id: the Modbus ID is the identity of a module."""
    return f"jsy_id_{device_id}"


class JsyCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinator that polls one JSY-MK-194 module."""

    def __init__(
        self, hass: HomeAssistant, entry: ConfigEntry, serial_lock: asyncio.Lock
    ) -> None:
        data = entry.data
        self.entry = entry
        self.port: str = data[CONF_PORT]
        self.device_id: int = int(data[CONF_DEVICE_ID])
        self.baudrate: int = int(data.get(CONF_BAUDRATE, DEFAULT_BAUDRATE))
        self.usb_vid: int | None = data.get(CONF_USB_VID)
        self.usb_pid: int | None = data.get(CONF_USB_PID)
        self.auto_relocate: bool = bool(
            data.get(CONF_AUTO_RELOCATE, DEFAULT_AUTO_RELOCATE)
        )
        self.device_name: str = entry.title
        # Per-channel settings: custom name ("" = none) and circuit multiplier
        self.channel_names: dict[int, str] = {
            n: str(data.get(CONF_CHANNEL_NAME[n], "") or "").strip() for n in CHANNELS
        }
        self.channel_multipliers: dict[int, int] = {
            n: CIRCUIT_MULTIPLIER.get(
                data.get(CONF_CHANNEL_CIRCUIT[n], DEFAULT_CIRCUIT), 1
            )
            for n in CHANNELS
        }
        self._lock = serial_lock
        self._internal_update = False

        # Health counters, surfaced by diagnostics.py
        self.consecutive_errors: int = 0
        self.total_errors: int = 0
        self.total_reads: int = 0
        self.relocations: int = 0
        self.last_success: datetime | None = None
        self.last_error: str | None = None
        self.last_error_at: datetime | None = None
        self.error_history: deque[dict[str, Any]] = deque(maxlen=ERROR_HISTORY_SIZE)

        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN}_{self.device_id}",
            update_interval=timedelta(
                seconds=int(data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL))
            ),
        )

    # ------------------------------------------------------------------
    # Config entry bookkeeping
    # ------------------------------------------------------------------

    def consume_internal_update(self) -> bool:
        """True (once) when the last entry update came from this coordinator."""
        flag, self._internal_update = self._internal_update, False
        return flag

    def _save_entry(self, **changes: Any) -> None:
        """Persist connection changes without reloading the entry."""
        new_data = {**self.entry.data, **changes}
        if new_data == dict(self.entry.data):
            return
        kwargs: dict[str, Any] = {"data": new_data}
        if CONF_DEVICE_ID in changes:
            kwargs["unique_id"] = entry_unique_id(int(changes[CONF_DEVICE_ID]))
        self._internal_update = True
        if not self.hass.config_entries.async_update_entry(self.entry, **kwargs):
            self._internal_update = False

    # ------------------------------------------------------------------
    # Polling
    # ------------------------------------------------------------------

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data from the module, looking for it on another port if needed."""
        self.total_reads += 1
        async with self._lock:
            try:
                data = await self.hass.async_add_executor_job(
                    jsy_reader.read_device, self.port, self.baudrate, self.device_id
                )
            except JsyModuleNotFoundError as err:
                raise UpdateFailed(str(err)) from err
            except JsyConnectionError as err:
                data = await self._async_relocate_and_read(str(err))
            except Exception as err:  # noqa: BLE001
                self._record_failure(f"{type(err).__name__}: {err}")
                raise UpdateFailed(f"JSY read failed: {err}") from err

        if self.consecutive_errors:
            _LOGGER.info(
                "JSY %s (ID %s on %s): recovered after %d consecutive failure(s)",
                self.device_name, self.device_id, self.port, self.consecutive_errors,
            )
        self.consecutive_errors = 0
        self.last_success = dt_util.utcnow()
        return self._apply_circuit_multipliers(data)

    def _apply_circuit_multipliers(self, data: dict[str, Any]) -> dict[str, Any]:
        """Scale voltage, power and energy of the channels on a 240 V circuit.

        Done here, on the decoded dictionary, so jsy_modbusdecoder.py stays
        untouched. See CIRCUIT_MULTIPLIER in const.py for the rationale.
        """
        for channel, factor in self.channel_multipliers.items():
            if factor == 1:
                continue
            for base in SCALED_CHANNEL_KEYS:
                key = f"{base}{channel}"
                if isinstance(data.get(key), (int, float)):
                    data[key] = round(data[key] * factor, 4)
        return data

    async def _async_relocate_and_read(self, first_error: str) -> dict[str, Any]:
        """The module did not answer on its port: look for its ID elsewhere.

        Called with the serial lock held. Raises UpdateFailed when the module
        cannot be found.
        """
        if self.auto_relocate:
            candidates = await self._async_relocation_candidates()
            if candidates:
                found = await self.hass.async_add_executor_job(
                    jsy_reader.locate_device, candidates, self.baudrate, self.device_id
                )
                if found:
                    new_port = await self.hass.async_add_executor_job(
                        jsy_reader.stable_path_for, found
                    )
                    try:
                        data = await self.hass.async_add_executor_job(
                            jsy_reader.read_device,
                            new_port, self.baudrate, self.device_id,
                        )
                    except (JsyConnectionError, JsyModuleNotFoundError) as err:
                        first_error = f"{first_error}; found on {new_port} but {err}"
                    else:
                        _LOGGER.warning(
                            "JSY %s (ID %s) moved from %s to %s — configuration updated",
                            self.device_name, self.device_id, self.port, new_port,
                        )
                        self.port = new_port
                        self.relocations += 1
                        self._save_entry(**{CONF_PORT: new_port})
                        return data

        self._record_failure(first_error)
        raise UpdateFailed(
            f"JSY {self.device_name} (ID {self.device_id}) not reachable — {first_error}"
        )

    async def _async_relocation_candidates(self) -> list[str]:
        """Ports worth probing for this module's Modbus ID.

        Only adapters of the same USB model (VID:PID) as the one chosen at
        setup are probed, so the integration never sends Modbus frames to an
        unrelated serial device (Zigbee stick, GPS...). A port used by another
        JSY module is probed too: that module ignores a request for another
        ID, and the serial lock keeps the two from talking at the same time.
        """
        if self.usb_vid is None or self.usb_pid is None:
            return []

        ports = await self.hass.async_add_executor_job(jsy_reader.list_serial_ports)
        current = os.path.realpath(self.port)
        return [
            info.device
            for info in ports
            if info.vid == self.usb_vid
            and info.pid == self.usb_pid
            and os.path.realpath(info.device) != current
        ]

    def _record_failure(self, message: str) -> None:
        now = dt_util.utcnow()
        self.consecutive_errors += 1
        self.total_errors += 1
        self.last_error = message
        self.last_error_at = now
        self.error_history.append(
            {"at": now.isoformat(), "port": self.port, "error": message}
        )
        _LOGGER.warning(
            "JSY %s (ID %s on %s): failure #%d — %s",
            self.device_name, self.device_id, self.port,
            self.consecutive_errors, message,
        )

    # ------------------------------------------------------------------
    # Health reporting
    # ------------------------------------------------------------------

    def diagnostic_snapshot(self) -> dict[str, Any]:
        """Health summary — consumed by diagnostics.py."""
        return {
            "device_name": self.device_name,
            "port": self.port,
            "device_id": self.device_id,
            "baudrate": self.baudrate,
            "usb_vid": self.usb_vid,
            "usb_pid": self.usb_pid,
            "auto_relocate": self.auto_relocate,
            "channel_names": self.channel_names,
            "channel_multipliers": self.channel_multipliers,
            "scan_interval_s": (
                self.update_interval.total_seconds() if self.update_interval else None
            ),
            "total_reads": self.total_reads,
            "total_errors": self.total_errors,
            "consecutive_errors": self.consecutive_errors,
            "relocations": self.relocations,
            "last_success": self.last_success.isoformat() if self.last_success else None,
            "last_error": self.last_error,
            "last_error_at": (
                self.last_error_at.isoformat() if self.last_error_at else None
            ),
            "last_update_success": self.last_update_success,
            "error_history": list(self.error_history),
            "data": self.data,
        }

    # ------------------------------------------------------------------
    # Writes
    # ------------------------------------------------------------------

    async def _async_write(self, func, *args: Any) -> WriteResult:
        """Run one jsy_writer function under the serial lock, then refresh."""
        async with self._lock:
            result: WriteResult = await self.hass.async_add_executor_job(
                func, self.port, self.baudrate, self.device_id, *args
            )
        if not result.success:
            raise HomeAssistantError(
                f"{self.device_name}: {result.what} failed — {result.error}"
            )
        await self.async_refresh()
        return result

    async def async_write_energy(self, key: str, kwh: float) -> WriteResult:
        """Set one energy counter.

        ``kwh`` is the value as shown in HA; the module stores it divided by
        the circuit multiplier of the channel.
        """
        factor = self.channel_multipliers.get(channel_of(key) or 0, 1)
        return await self._async_write(jsy_writer.write_energy, key, kwh / factor)

    async def async_clear_energy(self, channel: int) -> WriteResult:
        """Zero the energy counters of channel 1, 2, or both (0)."""
        return await self._async_write(jsy_writer.clear_energy, channel)

    def _ids_in_use_elsewhere(self) -> set[int]:
        return {
            int(entry.data[CONF_DEVICE_ID])
            for entry in self.hass.config_entries.async_entries(DOMAIN)
            if entry.entry_id != self.entry.entry_id and CONF_DEVICE_ID in entry.data
        }

    async def async_change_comm_settings(
        self, new_device_id: int | None = None, new_baudrate: int | None = None
    ) -> None:
        """Write register 0004H and follow the module to its new settings.

        The write result alone is not trusted: depending on the firmware the
        acknowledgement may come back with the new ID or at the new speed. The
        module is therefore probed with the new settings, then with the old
        ones, and the configuration follows whichever answers.
        """
        new_device_id = self.device_id if new_device_id is None else int(new_device_id)
        new_baudrate = self.baudrate if new_baudrate is None else int(new_baudrate)

        if (new_device_id, new_baudrate) == (self.device_id, self.baudrate):
            return
        if new_baudrate not in BAUD_RATE_CODES:
            raise HomeAssistantError(f"Unsupported baud rate {new_baudrate}")
        if new_device_id != self.device_id and new_device_id in self._ids_in_use_elsewhere():
            raise HomeAssistantError(
                f"Modbus ID {new_device_id} is already used by another JSY module"
            )

        async with self._lock:
            result: WriteResult = await self.hass.async_add_executor_job(
                jsy_writer.write_comm_settings,
                self.port, self.baudrate, self.device_id, new_device_id, new_baudrate,
            )
            await asyncio.sleep(COMM_CHANGE_SETTLE)
            new_ok = await self.hass.async_add_executor_job(
                jsy_reader.probe_device, self.port, new_baudrate, new_device_id
            )
            old_ok = None
            if new_ok is None:
                old_ok = await self.hass.async_add_executor_job(
                    jsy_reader.probe_device, self.port, self.baudrate, self.device_id
                )

        if new_ok is not None:
            _LOGGER.warning(
                "JSY %s: now Modbus ID %s at %s baud (was ID %s at %s baud)",
                self.device_name, new_device_id, new_baudrate,
                self.device_id, self.baudrate,
            )
            self.device_id = new_device_id
            self.baudrate = new_baudrate
            self._save_entry(
                **{CONF_DEVICE_ID: new_device_id, CONF_BAUDRATE: new_baudrate}
            )
            await self.async_refresh()
            return

        if old_ok is not None:
            raise HomeAssistantError(
                f"{self.device_name}: the module still answers with its previous "
                f"settings (ID {self.device_id}, {self.baudrate} baud). "
                f"Write result: {result.error or 'acknowledged'}. If the change only "
                "applies after a power cycle, power-cycle the module and then set the "
                "new ID / baud rate in the integration options."
            )
        raise HomeAssistantError(
            f"{self.device_name}: the module no longer answers with the old or the "
            "new settings. Power-cycle it, then check the ID / baud rate in the "
            "integration options."
        )
