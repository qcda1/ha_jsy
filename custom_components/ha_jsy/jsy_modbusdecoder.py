#!/usr/bin/env python
# -*- coding: utf-8 -*-

# --------------------------------------------------------------------------- #
# Handle the Modbus-RTU data from a JSY-MK-194 (T/G) two-channel energy meter.
# The only function meant to be called from outside is getRegisters().
# It opens the serial port, reads everything, closes the port and returns one
# flat dict. It does not keep the link open.
#
# Register map taken from the manufacturer documentation:
# "JSY-MK-194T Single-phase two-way electric energy measurement module,
#  Product manual V1.0" (Shenzhen Jiansiyan Technologies Co., Ltd.)
#
# Note on addresses: in Table 3 of the manual every measurement is a 4-byte
# value and the table numbers them one address per VALUE (0048H, 0049H, ...).
# On the wire each value takes two 16-bit Modbus registers, so value N of the
# table sits at registers[2*N] and registers[2*N + 1] of the response
# (high word first).
# --------------------------------------------------------------------------- #

from collections import OrderedDict
import logging

from serial.tools import list_ports
from pymodbus.client import ModbusSerialClient

log = logging.getLogger("jsy_modbusdecoder")


# --------------------------------------------------------------------------- #
# Register blocks: start address -> number of 16-bit registers to request
# --------------------------------------------------------------------------- #
ADDR_SYSTEM = 0x0000   # Table 2 - model, voltage range, current range
ADDR_CONFIG = 0x0004   # Table 1 - device ID + baud rate
ADDR_MEASURE = 0x0048  # Table 3 - electrical measurements, both channels

# The module counts in 4-byte VALUES, not in 16-bit registers: requesting 14
# (as in the manual's example, 01 03 00 48 00 0E) returns 56 data bytes, which
# pymodbus hands back as 28 registers. Requesting 20 or 28 is rejected with
# exception 0x82 (verified on real hardware).
MEASURE_COUNT = 14

REGISTER_BLOCKS = OrderedDict(
    [
        (ADDR_SYSTEM, 4),
        (ADDR_CONFIG, 1),
        (ADDR_MEASURE, MEASURE_COUNT),
    ]
)

# Table 1 - low byte of register 0004H
BAUD_RATE = {
    3: 1200,
    4: 2400,
    5: 4800,
    6: 9600,
    7: 19200,
    8: 38400,
}

# Table 3, value 7 - power direction, one byte per channel
POWER_DIRECTION_TEXT = {
    0: "positive",
    1: "negative",
}

# Error codes returned by the module (manual section 4.3)
EXCEPTION_TEXT = {
    0x81: "Illegal function code",
    0x82: "Illegal data address (outside the readable/writable range)",
    0x83: "Illegal data value",
}

DEFAULT_USB_NAME = "FT232R USB UART"


# --------------------------------------------------------------------------- #
# Find the serial port of the USB/TTL adapter by its description
# --------------------------------------------------------------------------- #
def findPort(name=DEFAULT_USB_NAME):
    for port in list_ports.comports(include_links=True):
        if name in (port.description or ""):
            return port.device
    return None


# --------------------------------------------------------------------------- #
# Read holding registers from an already-connected client
# --------------------------------------------------------------------------- #
def _readRegisters(theClient, addr, cnt, device_id=1):
    try:
        try:
            result = theClient.read_holding_registers(
                addr, count=cnt, device_id=device_id
            )
        except TypeError:
            # pymodbus < 3.10 names this argument "slave"
            result = theClient.read_holding_registers(addr, count=cnt, slave=device_id)

        if result.isError():
            code = getattr(result, "exception_code", None)
            log.error(
                "error getting addr=0x%04X cnt=%s: %s (%s)",
                addr,
                cnt,
                result,
                EXCEPTION_TEXT.get(code, "unknown error code"),
            )
            return []
    except Exception as ex:
        log.error("Error getting addr=0x%04X cnt=%s, exception: %s", addr, cnt, ex)
        return []
    return result.registers


# --------------------------------------------------------------------------- #
# Combine two 16-bit registers into one unsigned 32-bit value (high word first)
# --------------------------------------------------------------------------- #
def _u32(registers, index):
    return (registers[index] << 16) | registers[index + 1]


def _decodeChannel(registers, base, n):
    """Decode the 6 values of one channel starting at registers[base]."""
    return [
        (f"Voltage{n}", _u32(registers, base + 0) / 10000.0),          # V
        (f"Current{n}", _u32(registers, base + 2) / 10000.0),          # A
        (f"Power{n}", _u32(registers, base + 4) / 10000.0),            # W
        (f"EnergyPositive{n}", _u32(registers, base + 6) / 10000.0),   # kWh
        (f"PowerFactor{n}", _u32(registers, base + 8) / 1000.0),
        (f"EnergyNegative{n}", _u32(registers, base + 10) / 10000.0),  # kWh
    ]


# --------------------------------------------------------------------------- #
# Based on the block start address, return the decoded OrderedDict
# --------------------------------------------------------------------------- #
def doDecode(addr, registers):
    if addr == ADDR_SYSTEM:
        # Model1txt / Model2txt are the hex digits of the register as a string.
        # Model2 is "Reserved" in the manual; on real hardware it holds 0x0115,
        # which looks like the nominal voltage type (115).
        if len(registers) < 4:
            log.warning("doDecode: block 0x%04X too short (%s)", addr, len(registers))
            return {}
        decoded = OrderedDict(
            [
                ("Model1", registers[0]),              # 0000H  raw (0x0194 = 404)
                ("Model2", registers[1]),              # 0001H  raw (0x0115 = 277)
                ("Model1txt", f"{registers[0]:X}"),    # "194" - model number
                ("Model2txt", f"{registers[1]:X}"),    # "115" - see note below
                ("VoltageRange", registers[2]),        # 0002H  V
                ("CurrentRange", registers[3] / 10.0),  # 0003H  800 -> 80 A
            ]
        )
    elif addr == ADDR_CONFIG:
        if len(registers) < 1:
            log.warning("doDecode: block 0x%04X too short (%s)", addr, len(registers))
            return {}
        decoded = OrderedDict(
            [
                ("DeviceID", registers[0] >> 8),          # 0004H high byte
                ("BaudRateCode", registers[0] & 0xFF),    # 0004H low byte
            ]
        )
    elif addr == ADDR_MEASURE:
        if len(registers) < 28:
            log.warning("doDecode: block 0x%04X too short (%s)", addr, len(registers))
            return {}
        decoded = OrderedDict(
            _decodeChannel(registers, 0, 1)                         # 0048H-004DH
            + [
                ("PowerDirection1", registers[12] >> 8),            # 004EH byte 1
                ("PowerDirection2", registers[12] & 0xFF),          # 004EH byte 2
                ("Frequency", _u32(registers, 14) / 100.0),         # 004FH  Hz
            ]
            + _decodeChannel(registers, 16, 2)                      # 0050H-0055H
        )
    else:
        log.warning("doDecode: unknown address 0x%04X - ignored", addr)
        return {}

    return decoded


# --------------------------------------------------------------------------- #
# Public entry point
# Opens the serial port, reads all register blocks, closes it, returns a dict
# --------------------------------------------------------------------------- #
def getRegisters(port=None, baudrate=4800, device_id=1, timeout=2) -> dict:
    """Connect to the JSY-MK-194, read all registers and return a decoded dict.

    port      : serial device (e.g. "/dev/ttyUSB0"). When None, the first port
                whose description contains "FT232R USB UART" is used.
    Returns an empty dict when the module cannot be reached.
    """
    if not port:
        port = findPort()
        if not port:
            log.error("No USB serial adapter matching '%s' found", DEFAULT_USB_NAME)
            return {}

    client = ModbusSerialClient(
        port=port,
        baudrate=baudrate,
        bytesize=8,
        parity="N",
        stopbits=1,
        timeout=timeout,
    )
    raw = {}
    try:
        if not client.connect():
            log.error("Unable to open %s", port)
            return {}

        for addr, cnt in REGISTER_BLOCKS.items():
            raw[addr] = _readRegisters(client, addr, cnt, device_id)

    except Exception as ex:
        log.error("Modbus error on %s - %s", port, ex)
        return {}
    finally:
        client.close()

    # Decode all register blocks into one flat dict
    decoded: dict = {}
    for addr, registers in raw.items():
        if registers:
            decoded.update(doDecode(addr, registers))

    if not decoded:
        return {}

    # ------------------------------------------------------------------ #
    # Post-processing
    # ------------------------------------------------------------------ #
    decoded["Port"] = port

    if "BaudRateCode" in decoded:
        decoded["BaudRate"] = BAUD_RATE.get(decoded["BaudRateCode"])

    for n in (1, 2):
        direction = decoded.get(f"PowerDirection{n}")
        if direction is None:
            continue
        decoded[f"PowerDirection{n}Text"] = POWER_DIRECTION_TEXT.get(
            direction, f"No text defined for this value...{direction}"
        )
        # Power is unsigned on the wire; apply the direction flag
        power = decoded[f"Power{n}"]
        decoded[f"PowerSigned{n}"] = -power if direction == 1 else power
        # Net energy: positive (import) minus negative (export)
        decoded[f"EnergyNet{n}"] = round(
            decoded[f"EnergyPositive{n}"] - decoded[f"EnergyNegative{n}"], 4
        )

    return decoded


if __name__ == "__main__":
    import sys

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(module)s:%(lineno)s %(message)s",
    )
    data = getRegisters(sys.argv[1] if len(sys.argv) > 1 else None)
    if not data:
        sys.exit("No data read from the JSY-MK-194")
    for key, value in data.items():
        print(f"{key:20s} {value}")
