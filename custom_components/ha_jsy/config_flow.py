"""Config flow for the JSY-MK-194 energy meter (ha_jsy).

Adding a module is a two-step flow:

1. ``user``      — pick the serial port, give the module's CURRENT Modbus ID
                   (1 on a new module) and baud rate. The module is probed.
2. ``assign_id`` — choose the ID the module will keep. The flow proposes the
                   next free one starting at 10 and writes it to the module.

The Modbus ID is then the identity of the module: it is the config entry's
unique id, and it is what the coordinator looks for if the adapter shows up
under another port name after a reboot.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.config_entries import ConfigFlowResult, OptionsFlow
from homeassistant.core import callback
from homeassistant.helpers import selector

from . import get_serial_lock, jsy_reader, jsy_writer
from .const import (
    BAUD_RATE_CODES,
    CONF_AUTO_RELOCATE,
    CONF_BAUDRATE,
    CONF_DEVICE_ID,
    CONF_NAME,
    CONF_NEW_DEVICE_ID,
    CONF_PORT,
    CONF_SCAN_INTERVAL,
    CONF_USB_PID,
    CONF_USB_VID,
    DEFAULT_AUTO_RELOCATE,
    DEFAULT_BAUDRATE,
    DEFAULT_DEVICE_ID,
    DEFAULT_NAME,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    FIRST_ASSIGNED_ID,
    MAX_DEVICE_ID,
    MAX_SCAN_INTERVAL,
    MIN_DEVICE_ID,
    MIN_SCAN_INTERVAL,
)
from .coordinator import COMM_CHANGE_SETTLE, entry_unique_id

_LOGGER = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# Schema helpers
# --------------------------------------------------------------------------- #
def _port_selector(ports: list[jsy_reader.SerialPortInfo]) -> Any:
    """Drop-down of detected ports; free text is always allowed."""
    if not ports:
        return selector.TextSelector()
    return selector.SelectSelector(
        selector.SelectSelectorConfig(
            options=[
                selector.SelectOptionDict(value=p.stable_path, label=p.label)
                for p in ports
            ],
            custom_value=True,
            mode=selector.SelectSelectorMode.DROPDOWN,
        )
    )


def _id_selector() -> Any:
    return selector.NumberSelector(
        selector.NumberSelectorConfig(
            min=MIN_DEVICE_ID, max=MAX_DEVICE_ID, step=1,
            mode=selector.NumberSelectorMode.BOX,
        )
    )


def _baud_selector() -> Any:
    return selector.SelectSelector(
        selector.SelectSelectorConfig(
            options=[str(b) for b in BAUD_RATE_CODES],
            mode=selector.SelectSelectorMode.DROPDOWN,
        )
    )


def _interval_selector() -> Any:
    return selector.NumberSelector(
        selector.NumberSelectorConfig(
            min=MIN_SCAN_INTERVAL, max=MAX_SCAN_INTERVAL, step=1,
            unit_of_measurement="s",
            mode=selector.NumberSelectorMode.BOX,
        )
    )


def _default_port(ports: list[jsy_reader.SerialPortInfo], used: set[str]) -> str:
    """First USB port not already used by a configured module."""
    for info in ports:
        if info.vid is not None and info.stable_path not in used:
            return info.stable_path
    return ports[0].stable_path if ports else ""


class JsyConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for ha_jsy."""

    VERSION = 1

    def __init__(self) -> None:
        self._port: str = ""
        self._device_id: int = DEFAULT_DEVICE_ID
        self._baudrate: int = DEFAULT_BAUDRATE
        self._scan_interval: int = DEFAULT_SCAN_INTERVAL
        self._name: str = DEFAULT_NAME
        self._usb_vid: int | None = None
        self._usb_pid: int | None = None

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _ids_in_use(self) -> set[int]:
        return {
            int(entry.data[CONF_DEVICE_ID])
            for entry in self._async_current_entries()
            if CONF_DEVICE_ID in entry.data
        }

    def _suggest_id(self) -> int:
        """Next free ID: 10 for the first module, then highest + 1."""
        used = self._ids_in_use()
        if self._device_id >= FIRST_ASSIGNED_ID and self._device_id not in used:
            return self._device_id       # already carries a managed ID: keep it
        candidate = max([i for i in used if i >= FIRST_ASSIGNED_ID], default=FIRST_ASSIGNED_ID - 1) + 1
        while candidate in used and candidate < MAX_DEVICE_ID:
            candidate += 1
        return candidate

    # ------------------------------------------------------------------
    # Step 1 — serial port and current settings of the module
    # ------------------------------------------------------------------
    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        ports = await self.hass.async_add_executor_job(jsy_reader.list_serial_ports)

        if user_input is not None:
            port = str(user_input[CONF_PORT]).strip()
            device_id = int(user_input[CONF_DEVICE_ID])
            baudrate = int(user_input[CONF_BAUDRATE])
            self._scan_interval = int(user_input[CONF_SCAN_INTERVAL])
            self._name = str(user_input[CONF_NAME]).strip() or DEFAULT_NAME

            port = await self.hass.async_add_executor_job(
                jsy_reader.stable_path_for, port
            )
            try:
                async with get_serial_lock(self.hass):
                    await self.hass.async_add_executor_job(
                        jsy_reader.read_device, port, baudrate, device_id
                    )
            except jsy_reader.JsyModuleNotFoundError:
                errors["base"] = "module_not_found"
            except jsy_reader.JsyConnectionError as err:
                _LOGGER.warning("JSY config flow: %s", err)
                errors["base"] = "cannot_connect"

            self._port, self._device_id, self._baudrate = port, device_id, baudrate
            if not errors:
                info = await self.hass.async_add_executor_job(
                    jsy_reader.find_port_info, port
                )
                self._usb_vid = info.vid if info else None
                self._usb_pid = info.pid if info else None
                return await self.async_step_assign_id()

        used_ports = {e.data.get(CONF_PORT, "") for e in self._async_current_entries()}
        schema = vol.Schema(
            {
                vol.Required(
                    CONF_PORT, default=self._port or _default_port(ports, used_ports)
                ): _port_selector(ports),
                vol.Required(CONF_DEVICE_ID, default=self._device_id): _id_selector(),
                vol.Required(CONF_BAUDRATE, default=str(self._baudrate)): _baud_selector(),
                vol.Required(
                    CONF_SCAN_INTERVAL, default=self._scan_interval
                ): _interval_selector(),
                vol.Required(CONF_NAME, default=self._name): selector.TextSelector(),
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    # ------------------------------------------------------------------
    # Step 2 — give the module its permanent Modbus ID
    # ------------------------------------------------------------------
    async def async_step_assign_id(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            new_id = int(user_input[CONF_NEW_DEVICE_ID])

            if new_id in self._ids_in_use():
                errors["base"] = "id_in_use"
            elif new_id != self._device_id:
                if not await self._async_change_id(new_id):
                    errors["base"] = "id_write_failed"

            if not errors:
                self._device_id = new_id
                await self.async_set_unique_id(entry_unique_id(new_id))
                self._abort_if_unique_id_configured()
                title = self._name
                if title == DEFAULT_NAME:
                    title = f"{DEFAULT_NAME} #{new_id}"
                return self.async_create_entry(
                    title=title,
                    data={
                        CONF_PORT: self._port,
                        CONF_DEVICE_ID: new_id,
                        CONF_BAUDRATE: self._baudrate,
                        CONF_SCAN_INTERVAL: self._scan_interval,
                        CONF_USB_VID: self._usb_vid,
                        CONF_USB_PID: self._usb_pid,
                        CONF_AUTO_RELOCATE: DEFAULT_AUTO_RELOCATE,
                    },
                )

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_NEW_DEVICE_ID, default=self._suggest_id()
                ): _id_selector(),
            }
        )
        return self.async_show_form(
            step_id="assign_id",
            data_schema=schema,
            errors=errors,
            description_placeholders={
                "current_id": str(self._device_id),
                "port": self._port,
                "used_ids": ", ".join(str(i) for i in sorted(self._ids_in_use())) or "—",
            },
        )

    async def _async_change_id(self, new_id: int) -> bool:
        """Write the new ID to the module and check that it answers with it."""
        async with get_serial_lock(self.hass):
            await self.hass.async_add_executor_job(
                jsy_writer.write_comm_settings,
                self._port, self._baudrate, self._device_id, new_id, self._baudrate,
            )
            await asyncio.sleep(COMM_CHANGE_SETTLE)
            answer = await self.hass.async_add_executor_job(
                jsy_reader.probe_device, self._port, self._baudrate, new_id
            )
        return answer is not None

    # ------------------------------------------------------------------
    # Options flow
    # ------------------------------------------------------------------
    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> OptionsFlow:
        return JsyOptionsFlowHandler()


class JsyOptionsFlowHandler(OptionsFlow):
    """Options flow — tell the integration where the module is and how to poll.

    Nothing is written to the module here: these fields describe how to reach
    it. To CHANGE the module's ID or baud rate, use the "Modbus ID (Set)" and
    "Baud Rate (Set)" entities, which write register 0004H.
    """

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        entry = self.config_entry
        data = dict(entry.data)
        ports = await self.hass.async_add_executor_job(jsy_reader.list_serial_ports)

        if user_input is not None:
            port = await self.hass.async_add_executor_job(
                jsy_reader.stable_path_for, str(user_input[CONF_PORT]).strip()
            )
            device_id = int(user_input[CONF_DEVICE_ID])
            others = {
                int(e.data[CONF_DEVICE_ID])
                for e in self.hass.config_entries.async_entries(DOMAIN)
                if e.entry_id != entry.entry_id and CONF_DEVICE_ID in e.data
            }
            if device_id in others:
                errors["base"] = "id_in_use"
            else:
                info = await self.hass.async_add_executor_job(
                    jsy_reader.find_port_info, port
                )
                data.update(
                    {
                        CONF_PORT: port,
                        CONF_DEVICE_ID: device_id,
                        CONF_BAUDRATE: int(user_input[CONF_BAUDRATE]),
                        CONF_SCAN_INTERVAL: int(user_input[CONF_SCAN_INTERVAL]),
                        CONF_AUTO_RELOCATE: bool(user_input[CONF_AUTO_RELOCATE]),
                    }
                )
                if info is not None:
                    data[CONF_USB_VID], data[CONF_USB_PID] = info.vid, info.pid
                # The connection settings live in entry.data; the update
                # listener reloads the entry.
                self.hass.config_entries.async_update_entry(
                    entry, data=data, unique_id=entry_unique_id(device_id)
                )
                return self.async_create_entry(title="", data={})

        schema = vol.Schema(
            {
                vol.Required(CONF_PORT, default=data[CONF_PORT]): _port_selector(ports),
                vol.Required(
                    CONF_DEVICE_ID, default=int(data[CONF_DEVICE_ID])
                ): _id_selector(),
                vol.Required(
                    CONF_BAUDRATE, default=str(data.get(CONF_BAUDRATE, DEFAULT_BAUDRATE))
                ): _baud_selector(),
                vol.Required(
                    CONF_SCAN_INTERVAL,
                    default=int(data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)),
                ): _interval_selector(),
                vol.Required(
                    CONF_AUTO_RELOCATE,
                    default=bool(data.get(CONF_AUTO_RELOCATE, DEFAULT_AUTO_RELOCATE)),
                ): selector.BooleanSelector(),
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema, errors=errors)
