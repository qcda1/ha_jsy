"""Serial-port discovery and read wrapper around jsy_modbusdecoder.py.

jsy_modbusdecoder.py is used untouched: this module only adds what Home
Assistant needs around it.

1. ``list_serial_ports()`` — what is plugged in, with the *stable* name of
   each port (``/dev/serial/by-id/...``) next to the kernel name
   (``/dev/ttyUSB0``), which can change between reboots.
2. ``probe_device()`` — a fast "is module ID n behind this port?" check
   (one register, no retries, short timeout).
3. ``read_device()`` — probe, then ``getRegisters()``. The probe keeps a dead
   or wrong port from blocking the serial lock for the decoder's full
   timeout x retries.
4. ``locate_device()`` — find which port a given Modbus ID is on.

Everything here is synchronous; callers run it in the executor.
"""

from __future__ import annotations

import glob
import logging
import os
import time
from dataclasses import asdict, dataclass
from typing import Any

from .const import REG_ID_BAUD

_LOGGER = logging.getLogger(__name__)

PROBE_TIMEOUT = 0.5   # seconds — a JSY answers in ~100 ms at 4800 baud
PROBE_RETRY_DELAY = 0.3
READ_PROBE_ATTEMPTS = 2   # one lost frame must not make the entities unavailable
BY_ID_DIR = "/dev/serial/by-id"


class JsyModuleNotFoundError(Exception):
    """Raised when jsy_modbusdecoder.py is missing from the integration folder."""


class JsyConnectionError(Exception):
    """Raised when the module does not answer on the serial port."""


@dataclass
class SerialPortInfo:
    """One serial port as seen by the host."""

    device: str                     # kernel name, e.g. /dev/ttyUSB0
    stable_path: str                # /dev/serial/by-id/... when it exists, else device
    description: str = ""
    manufacturer: str | None = None
    serial_number: str | None = None
    vid: int | None = None
    pid: int | None = None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    @property
    def label(self) -> str:
        """Text shown in the config-flow drop-down."""
        parts = [self.device]
        if self.description and self.description != "n/a":
            parts.append(self.description)
        if self.serial_number:
            parts.append(f"S/N {self.serial_number}")
        return " — ".join(parts)


# --------------------------------------------------------------------------- #
# Port discovery
# --------------------------------------------------------------------------- #
def _by_id_links() -> dict[str, str]:
    """Map real device path -> /dev/serial/by-id link."""
    links: dict[str, str] = {}
    for link in sorted(glob.glob(os.path.join(BY_ID_DIR, "*"))):
        links.setdefault(os.path.realpath(link), link)
    return links


def stable_path_for(path: str) -> str:
    """Return the /dev/serial/by-id name of a port when there is one."""
    if not path or path.startswith(BY_ID_DIR):
        return path
    return _by_id_links().get(os.path.realpath(path), path)


def list_serial_ports() -> list[SerialPortInfo]:
    """List the serial ports of the host, USB adapters first."""
    from serial.tools import list_ports

    links = _by_id_links()
    ports: list[SerialPortInfo] = []
    for port in list_ports.comports():
        real = os.path.realpath(port.device)
        ports.append(
            SerialPortInfo(
                device=port.device,
                stable_path=links.get(real, port.device),
                description=port.description or "",
                manufacturer=port.manufacturer,
                serial_number=port.serial_number,
                vid=port.vid,
                pid=port.pid,
            )
        )
    ports.sort(key=lambda p: (p.vid is None, p.device))
    return ports


def find_port_info(path: str) -> SerialPortInfo | None:
    """Return the SerialPortInfo behind ``path`` (kernel name or by-id link)."""
    if not path:
        return None
    real = os.path.realpath(path)
    for info in list_serial_ports():
        if os.path.realpath(info.device) == real:
            return info
    return None


# --------------------------------------------------------------------------- #
# Modbus helpers
# --------------------------------------------------------------------------- #
def modbus_call(method, *args, device_id: int, **kwargs):
    """Call a pymodbus client method with the right unit-id keyword.

    pymodbus >= 3.10 names it ``device_id``; older releases name it ``slave``.
    """
    try:
        return method(*args, device_id=device_id, **kwargs)
    except TypeError:
        return method(*args, slave=device_id, **kwargs)


def open_client(port: str, baudrate: int, timeout: float, retries: int = 0):
    """Build a ModbusSerialClient with the JSY line settings (8N1)."""
    from pymodbus.client import ModbusSerialClient

    return ModbusSerialClient(
        port=port,
        baudrate=baudrate,
        bytesize=8,
        parity="N",
        stopbits=1,
        timeout=timeout,
        retries=retries,
    )


def probe_device(
    port: str,
    baudrate: int,
    device_id: int,
    timeout: float = PROBE_TIMEOUT,
    attempts: int = 1,
) -> tuple[int, int] | None:
    """Ask register 0004H of module ``device_id`` on ``port``.

    ``attempts`` > 1 repeats the question, for the cases where the module is
    known to be there but may be momentarily deaf (it does not answer for a
    short while after a write).
    """
    for attempt in range(max(1, attempts)):
        if attempt:
            time.sleep(PROBE_RETRY_DELAY)
        answer = _probe_once(port, baudrate, device_id, timeout)
        if answer is not None:
            return answer
    return None


def _probe_once(
    port: str, baudrate: int, device_id: int, timeout: float
) -> tuple[int, int] | None:
    """One request for register 0004H.

    Returns ``(device_id, baud_rate_code)`` as reported by the module, or
    ``None`` when nothing with that ID answers. A module with another ID
    stays silent, which is what makes this usable to tell modules apart.
    """
    client = None
    try:
        client = open_client(port, baudrate, timeout)
        if not client.connect():
            return None
        result = modbus_call(
            client.read_holding_registers, REG_ID_BAUD, count=1, device_id=device_id
        )
        if result.isError() or not result.registers:
            return None
        word = result.registers[0]
        reported_id, baud_code = word >> 8, word & 0xFF
        if reported_id != device_id:
            _LOGGER.debug(
                "%s answered ID %s but reports ID %s — ignored",
                port, device_id, reported_id,
            )
            return None
        return reported_id, baud_code
    except Exception as err:  # noqa: BLE001 — any serial/modbus failure = no answer
        _LOGGER.debug("Probe of %s (ID %s) failed: %s", port, device_id, err)
        return None
    finally:
        if client is not None:
            try:
                client.close()
            except Exception:  # noqa: BLE001
                pass


def read_device(
    port: str, baudrate: int, device_id: int, attempts: int = READ_PROBE_ATTEMPTS
) -> dict[str, Any]:
    """Read every register of one module through jsy_modbusdecoder.

    Raises:
        JsyModuleNotFoundError — jsy_modbusdecoder.py is missing.
        JsyConnectionError     — the module does not answer / returns nothing.
    """
    try:
        from .jsy_modbusdecoder import getRegisters  # type: ignore[import]
    except ImportError as exc:
        raise JsyModuleNotFoundError(
            "jsy_modbusdecoder.py not found in custom_components/ha_jsy/ "
            f"(or one of its imports failed: {exc})"
        ) from exc

    if probe_device(port, baudrate, device_id, attempts=attempts) is None:
        raise JsyConnectionError(
            f"no answer from Modbus ID {device_id} on {port} at {baudrate} baud"
        )

    data = getRegisters(port=port, baudrate=baudrate, device_id=device_id)
    if not data:
        raise JsyConnectionError(
            f"getRegisters returned empty data for ID {device_id} on {port}"
        )
    if "Voltage1" not in data:
        raise JsyConnectionError(
            f"measurement block missing for ID {device_id} on {port} "
            "(see the jsy_modbusdecoder log line above)"
        )
    return data


def locate_device(
    candidates: list[str], baudrate: int, device_id: int
) -> str | None:
    """Return the first port of ``candidates`` where ``device_id`` answers."""
    for port in candidates:
        if probe_device(port, baudrate, device_id) is not None:
            return port
        time.sleep(0.05)
    return None
