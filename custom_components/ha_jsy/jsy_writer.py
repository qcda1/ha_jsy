"""Modbus write logic for the writable JSY-MK-194 registers.

Kept separate from jsy_reader.py and jsy_modbusdecoder.py so that reading
(acquisition) and writing (control) stay isolated — jsy_modbusdecoder.py is
not modified.

Writable registers (manual Tables 1 and 3, function code 10H)
--------------------------------------------------------------
0004H  ID and baud rate      high byte = Modbus ID (1-255),
                             low byte  = baud-rate code (3..8)
004BH  Positive energy ch 1  4-byte unsigned, kWh x 10000
004DH  Negative energy ch 1
0053H  Positive energy ch 2
0055H  Negative energy ch 2
000CH  Clear both channels   (manual 4.4.2, write 0)

Note on the 4-byte values: Table 3 gives ONE address per 4-byte value, but a
write still sends two 16-bit words to that address, high word first. This is
the frame the manual gives to clear channel 1:

    01 10 00 4B 00 02 04 00 00 00 00  ->  write_registers(0x004B, [0, 0])

Everything here is synchronous; callers run it in the executor and get a
``WriteResult`` back, with no Home Assistant import in this module.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from .const import (
    BAUD_RATE_CODES,
    ENERGY_MAX_KWH,
    ENERGY_SCALE,
    MAX_DEVICE_ID,
    MIN_DEVICE_ID,
    REG_CLEAR_ALL_ENERGY,
    REG_ID_BAUD,
    WRITABLE_ENERGY_REGISTERS,
)
from .jsy_reader import modbus_call, open_client

_LOGGER = logging.getLogger(__name__)

WRITE_TIMEOUT = 2.0
WRITE_RETRIES = 1

# Error codes returned by the module (manual section 4.3)
EXCEPTION_TEXT = {
    0x81: "illegal function code",
    0x82: "illegal data address",
    0x83: "illegal data value",
}


@dataclass
class WriteResult:
    """Outcome of one write attempt."""

    success: bool
    what: str                 # what was written, for logs and messages
    values: list[int]         # the 16-bit words actually sent
    error: str | None = None


def _write(
    port: str,
    baudrate: int,
    device_id: int,
    address: int,
    values: list[int],
    what: str,
) -> WriteResult:
    """Write ``values`` (16-bit words) at ``address`` with function code 10H."""
    client = None
    try:
        client = open_client(port, baudrate, WRITE_TIMEOUT, WRITE_RETRIES)
        if not client.connect():
            return WriteResult(False, what, values, f"unable to open {port}")

        result = modbus_call(
            client.write_registers, address, values, device_id=device_id
        )
        if result.isError():
            code = getattr(result, "exception_code", None)
            text = EXCEPTION_TEXT.get(code, str(result))
            error = f"module refused the write at 0x{address:04X}: {text}"
            _LOGGER.error("%s — %s", what, error)
            return WriteResult(False, what, values, error)

    except Exception as err:  # noqa: BLE001
        error = f"{type(err).__name__}: {err}"
        _LOGGER.error("%s — write at 0x%04X failed: %s", what, address, error)
        return WriteResult(False, what, values, error)
    finally:
        if client is not None:
            try:
                client.close()
            except Exception:  # noqa: BLE001
                pass

    _LOGGER.info(
        "%s — wrote %s at 0x%04X (ID %s on %s)",
        what, [f"0x{v:04X}" for v in values], address, device_id, port,
    )
    return WriteResult(True, what, values)


def _u32_words(raw: int) -> list[int]:
    """Split an unsigned 32-bit value into [high word, low word]."""
    return [(raw >> 16) & 0xFFFF, raw & 0xFFFF]


# --------------------------------------------------------------------------- #
# Energy counters
# --------------------------------------------------------------------------- #
def write_energy(
    port: str, baudrate: int, device_id: int, key: str, kwh: float
) -> WriteResult:
    """Set one energy counter (``key`` from WRITABLE_ENERGY_REGISTERS) in kWh."""
    what = f"{key} = {kwh} kWh"
    address = WRITABLE_ENERGY_REGISTERS.get(key)
    if address is None:
        return WriteResult(False, what, [], f"{key} is not a writable register")
    if not 0 <= kwh <= ENERGY_MAX_KWH:
        return WriteResult(
            False, what, [], f"value out of range 0..{ENERGY_MAX_KWH} kWh"
        )
    raw = round(kwh * ENERGY_SCALE)
    return _write(port, baudrate, device_id, address, _u32_words(raw), what)


def clear_energy(
    port: str, baudrate: int, device_id: int, channel: int
) -> WriteResult:
    """Zero the energy counters.

    channel 1 or 2 : positive and negative counters of that channel
    channel 0      : both channels at once (register 000CH)
    """
    if channel == 0:
        return _write(
            port, baudrate, device_id, REG_CLEAR_ALL_ENERGY, [0, 0],
            "clear energy, both channels",
        )
    if channel not in (1, 2):
        return WriteResult(False, "clear energy", [], f"unknown channel {channel}")

    result = WriteResult(True, f"clear energy, channel {channel}", [0, 0])
    for key in (f"EnergyPositive{channel}", f"EnergyNegative{channel}"):
        result = _write(
            port, baudrate, device_id, WRITABLE_ENERGY_REGISTERS[key], [0, 0],
            f"clear {key}",
        )
        if not result.success:
            break
    return result


# --------------------------------------------------------------------------- #
# Modbus ID and baud rate
# --------------------------------------------------------------------------- #
def write_comm_settings(
    port: str,
    baudrate: int,
    device_id: int,
    new_device_id: int,
    new_baudrate: int,
) -> WriteResult:
    """Write register 0004H: new Modbus ID (high byte) and baud code (low byte).

    ``baudrate`` / ``device_id`` are the CURRENT settings, used to reach the
    module. After a successful write the module answers with the new ones.
    """
    what = f"Modbus ID {device_id} -> {new_device_id}, {baudrate} -> {new_baudrate} baud"
    if not MIN_DEVICE_ID <= new_device_id <= MAX_DEVICE_ID:
        return WriteResult(False, what, [], f"ID {new_device_id} out of range 1..255")
    code = BAUD_RATE_CODES.get(new_baudrate)
    if code is None:
        return WriteResult(False, what, [], f"unsupported baud rate {new_baudrate}")

    word = (new_device_id << 8) | code
    return _write(port, baudrate, device_id, REG_ID_BAUD, [word], what)
