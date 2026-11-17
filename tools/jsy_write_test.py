#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""JSY-MK-194 write tests — raw Modbus frames, no pymodbus.

Shows exactly what the module answers to each write, and measures how long it
stays silent afterwards. Needs only pyserial. Stop Home Assistant's use of the
port first (or move the adapter to another machine).

    python jsy_write_test.py                       # read-only check
    python jsy_write_test.py --energy              # one energy counter +0.01 kWh, and back
    python jsy_write_test.py --new-id 11           # ID -> 11, then back
    python jsy_write_test.py --new-baud 9600       # speed -> 9600, then back
    python jsy_write_test.py --energy --new-id 11 --new-baud 9600   # everything

Options: --port /dev/ttyUSB0  --id 10  --baud 4800

Every test puts the module back the way it found it. If a test is interrupted
half-way, run with --scan to find the ID and speed the module ended up with.
"""

import argparse
import struct
import sys
import time

import serial

BAUD_CODES = {1200: 3, 2400: 4, 4800: 5, 9600: 6, 19200: 7, 38400: 8}
REG_ID_BAUD = 0x0004
REG_ENERGY_NEG_1 = 0x004D


def crc16(data: bytes) -> bytes:
    crc = 0xFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            crc = (crc >> 1) ^ 0xA001 if crc & 1 else crc >> 1
    return struct.pack("<H", crc)


def hx(data: bytes) -> str:
    return data.hex(" ").upper() if data else "(nothing)"


class Link:
    def __init__(self, port, baud):
        self.port, self.baud = port, baud
        self.ser = serial.Serial(port, baud, bytesize=8, parity="N", stopbits=1, timeout=0.05)

    def set_baud(self, baud):
        self.ser.close()
        self.baud = baud
        self.ser = serial.Serial(self.port, baud, bytesize=8, parity="N", stopbits=1, timeout=0.05)

    def exchange(self, frame: bytes, wait=0.6, show=True) -> bytes:
        """Send one frame, return everything received within ``wait`` seconds."""
        self.ser.reset_input_buffer()
        self.ser.write(frame)
        self.ser.flush()
        reply, deadline, last = b"", time.monotonic() + wait, None
        while time.monotonic() < deadline:
            chunk = self.ser.read(64)
            if chunk:
                reply += chunk
                last = time.monotonic()
            elif reply and time.monotonic() - last > 0.1:
                break
        if show:
            print(f"    tx {hx(frame)}")
            print(f"    rx {hx(reply)}")
        return reply

    def read_cmd(self, unit, address, count):
        pdu = struct.pack(">BBHH", unit, 0x03, address, count)
        return pdu + crc16(pdu)

    def write_cmd(self, unit, address, words):
        payload = b"".join(struct.pack(">H", w) for w in words)
        pdu = struct.pack(">BBHHB", unit, 0x10, address, len(words), len(payload)) + payload
        return pdu + crc16(pdu)

    def read_id_baud(self, unit, show=False, wait=0.25):
        """Return (id, baud_code) from register 0004H, or None."""
        reply = self.exchange(self.read_cmd(unit, REG_ID_BAUD, 1), wait=wait, show=show)
        if len(reply) >= 7 and reply[1] == 0x03 and crc16(reply[:5]) == reply[5:7]:
            return reply[3], reply[4]
        return None

    def read_u32(self, unit, table_address):
        """Read one 4-byte value of Table 3 through the 0048H block."""
        reply = self.exchange(self.read_cmd(unit, 0x0048, 14), wait=1.0, show=False)
        if len(reply) < 61 or reply[1] != 0x03:
            return None
        offset = 3 + 4 * (table_address - 0x0048)
        return struct.unpack(">I", reply[offset:offset + 4])[0]

    def silence_after(self, unit, limit=10.0):
        """Poll 0004H until the module answers; return the delay in seconds."""
        start = time.monotonic()
        while time.monotonic() - start < limit:
            if self.read_id_baud(unit) is not None:
                return time.monotonic() - start
        return None


def test_energy(link, unit):
    """Write the counter 0.01 kWh higher, then back.

    The module stores a written counter in steps of 0.01 kWh (raw 100) and
    keeps counting meanwhile, so the read-back is compared at that step.
    """
    print("\n== Energy counter: EnergyNegative1 (004DH) + 0.01 kWh, then back ==")
    raw = link.read_u32(unit, REG_ENERGY_NEG_1)
    if raw is None:
        print("  could not read the measurement block — skipped")
        return
    print(f"  current value: {raw} ({raw / 10000} kWh)")
    base = raw - raw % 100
    for label, value in (("value + 0.01 kWh", base + 100), ("original value", base)):
        print(f"  write {label}:")
        link.exchange(link.write_cmd(unit, REG_ENERGY_NEG_1, [value >> 16, value & 0xFFFF]))
        delay = link.silence_after(unit)
        print(f"    answers again after: {'%.2f s' % delay if delay is not None else 'NO ANSWER in 10 s'}")
        back = link.read_u32(unit, REG_ENERGY_NEG_1)
        ok = back is not None and 0 <= back - value < 100
        print(f"    wrote {value}, read back {back}  ->  {'OK' if ok else 'DIFFERENT'}")


def change_comm(link, unit, baud, new_unit, new_baud):
    """Write 0004H and report where the module answers afterwards."""
    word = (new_unit << 8) | BAUD_CODES[new_baud]
    print(f"  write 0004H = 0x{word:04X}  (ID {unit} -> {new_unit}, {baud} -> {new_baud} baud):")
    link.exchange(link.write_cmd(unit, REG_ID_BAUD, [word]), wait=1.0)
    start = time.monotonic()
    while time.monotonic() - start < 6.0:
        for u, b, tag in ((new_unit, new_baud, "NEW"), (unit, baud, "OLD")):
            if link.baud != b:
                link.set_baud(b)
            if link.read_id_baud(u) is not None:
                print(f"    answers with the {tag} settings (ID {u}, {b} baud) "
                      f"after {time.monotonic() - start:.2f} s")
                return u, b
    print("    NO ANSWER with the old or the new settings within 6 s")
    print("    -> power-cycle the module, then run:  --scan")
    return None


def test_comm(link, unit, baud, new_unit, new_baud, title):
    print(f"\n== {title} ==")
    where = change_comm(link, unit, baud, new_unit, new_baud)
    if where is None:
        sys.exit(1)
    if where == (unit, baud):
        print("  the change did not apply (maybe after a power cycle?) — nothing to restore")
        return
    print("  restoring:")
    back = change_comm(link, new_unit, new_baud, unit, baud)
    if back != (unit, baud):
        print(f"  !! module left with {back} — set it in the integration options")
        sys.exit(1)


def scan(port):
    print("Scanning every baud rate and ID 1..255 (about 3 minutes worst case)...")
    for baud in (4800, 9600, 2400, 19200, 38400, 1200):
        link = Link(port, baud)
        for unit in range(1, 256):
            reply = link.exchange(link.read_cmd(unit, REG_ID_BAUD, 1), wait=0.12, show=False)
            if len(reply) >= 7 and reply[1] == 0x03:
                print(f"FOUND: ID {reply[3]} at {baud} baud (code {reply[4]})")
                return
        link.ser.close()
    print("Nothing found.")


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--port", default="/dev/ttyUSB0")
    parser.add_argument("--id", type=int, default=10, help="current Modbus ID (default 10)")
    parser.add_argument("--baud", type=int, default=4800, help="current baud rate")
    parser.add_argument("--energy", action="store_true", help="energy write test")
    parser.add_argument("--new-id", type=int, help="ID change test (and back)")
    parser.add_argument("--new-baud", type=int, choices=sorted(BAUD_CODES), help="baud change test (and back)")
    parser.add_argument("--scan", action="store_true", help="find the module's ID and speed")
    args = parser.parse_args()

    if args.scan:
        scan(args.port)
        return

    link = Link(args.port, args.baud)
    print(f"== Module ID {args.id} on {args.port} at {args.baud} baud ==")
    print("  read 0004H:")
    link.exchange(link.read_cmd(args.id, REG_ID_BAUD, 1))
    if link.read_id_baud(args.id) is None:
        sys.exit("  no answer — check --port / --id / --baud, or run with --scan")

    if args.energy:
        test_energy(link, args.id)
    if args.new_id:
        test_comm(link, args.id, args.baud, args.new_id, args.baud, f"Modbus ID {args.id} -> {args.new_id}")
    if args.new_baud:
        test_comm(link, args.id, args.baud, args.id, args.new_baud, f"Baud rate {args.baud} -> {args.new_baud}")
    print("\nDone.")


if __name__ == "__main__":
    main()
