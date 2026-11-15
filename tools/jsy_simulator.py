#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""JSY-MK-194 simulator — a fake module behind a pseudo serial port.

Lets you exercise jsy_modbusdecoder.py and the ha_jsy integration without
the hardware (Linux / macOS):

    python jsy_simulator.py                 # prints the port to use
    python jsy_simulator.py --id 10 --link /tmp/ttyJSY0

then, in another terminal:

    python jsy_modbusdecoder.py /tmp/ttyJSY0

It reproduces what was observed on a real JSY-MK-194G:
  * function 03H at 0000H (4 words), 0004H (1 word) and 0048H (count 14 ->
    56 data bytes); anything else answers exception 82H
  * function 10H at 0004H (ID / baud), 004BH 004DH 0053H 0055H (energies)
    and 000CH (clear both channels)
  * it only answers frames addressed to its own Modbus ID

It also reproduces two behaviours seen on the real module:
  * a write to 0004H applies at once and is NOT acknowledged
  * after any write the module stays silent for a moment (--deaf, default
    0.8 s; the real duration can be measured with jsy_write_test.py)

Baud-rate changes are stored but meaningless on a pseudo terminal.
"""

import argparse
import os
import pty
import select
import struct
import termios
import time
import tty


def crc16(data: bytes) -> bytes:
    crc = 0xFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            crc = (crc >> 1) ^ 0xA001 if crc & 1 else crc >> 1
    return struct.pack("<H", crc)


class JsySimulator:
    def __init__(self, device_id=1, baud_code=5, deaf=0.8):
        self.device_id = device_id
        self.deaf = deaf
        self.deaf_until = 0.0
        self.baud_code = baud_code
        self.started = time.monotonic()
        # raw 32-bit energy counters (kWh x 10000)
        self.energy = {0x004B: 54360, 0x004D: 0, 0x0053: 0, 0x0055: 80650}

    # -- measurement block: 14 values of 4 bytes --------------------------- #
    def measurements(self) -> bytes:
        wobble = int((time.monotonic() - self.started) * 10) % 50
        values = [
            1206397 + wobble * 10,       # voltage 1      /10000 V
            11751 + wobble,              # current 1      /10000 A
            750507 + wobble * 60,        # power 1        /10000 W
            self.energy[0x004B],         # energy + 1     /10000 kWh
            529,                         # power factor 1 /1000
            self.energy[0x004D],         # energy - 1
            0x00010000,                  # direction: ch1 positive, ch2 negative
            6000,                        # frequency      /100 Hz
            1206397 + wobble * 10,       # voltage 2
            1841,                        # current 2
            222195,                      # power 2
            self.energy[0x0053],         # energy + 2
            1000,                        # power factor 2
            self.energy[0x0055],         # energy - 2
        ]
        return b"".join(struct.pack(">I", v & 0xFFFFFFFF) for v in values)

    def exception(self, function, code=0x82) -> bytes:
        return bytes([self.device_id, function | 0x80, code])

    def handle(self, frame: bytes) -> bytes | None:
        """Return the reply PDU (without CRC) for one request frame."""
        if len(frame) < 8 or crc16(frame[:-2]) != frame[-2:]:
            return None
        unit, function = frame[0], frame[1]
        if unit != self.device_id:
            return None                     # not for us: stay silent
        if time.monotonic() < self.deaf_until:
            return None                     # busy after a write
        address, count = struct.unpack(">HH", frame[2:6])

        if function == 0x03:
            if address == 0x0000 and count == 4:
                data = struct.pack(">4H", 0x0194, 0x0115, 250, 800)
            elif address == 0x0004 and count == 1:
                data = bytes([self.device_id, self.baud_code])
            elif address == 0x0048 and count == 14:
                data = self.measurements()
            else:
                return self.exception(function)
            return bytes([unit, function, len(data)]) + data

        if function == 0x10:
            nbytes = frame[6]
            payload = frame[7:7 + nbytes]
            if address == 0x0004 and count == 1 and nbytes == 2:
                new_id, new_code = payload[0], payload[1]
                if not 1 <= new_id <= 255 or not 3 <= new_code <= 8:
                    return self.exception(function, 0x83)
                print(f"  ID {self.device_id} -> {new_id}, baud code {self.baud_code} -> {new_code}")
                self.device_id, self.baud_code = new_id, new_code
                self.deaf_until = time.monotonic() + self.deaf
                return None                 # applied, but never acknowledged
            elif address in self.energy and count == 2 and nbytes == 4:
                self.energy[address] = struct.unpack(">I", payload)[0]
                print(f"  energy 0x{address:04X} = {self.energy[address] / 10000} kWh")
            elif address == 0x000C and count == 2 and nbytes == 4:
                for key in self.energy:
                    self.energy[key] = 0
                print("  all energy counters cleared")
            else:
                return self.exception(function)
            self.deaf_until = time.monotonic() + self.deaf
            return frame[:6]            # acknowledgement

        return self.exception(function, 0x81)


def expected_length(buf: bytes) -> int | None:
    """Length of the request frame at the start of ``buf`` (None = need more)."""
    if len(buf) < 2:
        return None
    if buf[1] == 0x03:
        return 8
    if buf[1] == 0x10:
        return None if len(buf) < 7 else 9 + buf[6]
    return 8


def main():
    parser = argparse.ArgumentParser(description="JSY-MK-194 simulator")
    parser.add_argument("--id", type=int, default=1, help="Modbus ID (default 1)")
    parser.add_argument("--link", help="create this symlink to the pseudo port")
    parser.add_argument("--deaf", type=float, default=0.8,
                        help="seconds of silence after a write (default 0.8)")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()

    master, slave = pty.openpty()
    tty.setraw(slave)
    attrs = termios.tcgetattr(slave)
    attrs[3] &= ~termios.ECHO
    termios.tcsetattr(slave, termios.TCSANOW, attrs)
    port = os.ttyname(slave)

    if args.link:
        if os.path.islink(args.link):
            os.unlink(args.link)
        os.symlink(port, args.link)
        port = args.link

    sim = JsySimulator(device_id=args.id, deaf=args.deaf)
    print(f"JSY simulator, Modbus ID {sim.device_id}, listening on {port}", flush=True)

    buf = b""
    last_rx = time.monotonic()
    try:
        while True:
            ready, _, _ = select.select([master], [], [], 0.2)
            now = time.monotonic()
            if not ready:
                if buf and now - last_rx > 0.2:
                    buf = b""               # drop an incomplete frame
                continue
            buf += os.read(master, 256)
            last_rx = now
            while True:
                length = expected_length(buf)
                if length is None or len(buf) < length:
                    break
                frame, buf = buf[:length], buf[length:]
                reply = sim.handle(frame)
                if not args.quiet:
                    print(f"rx {frame.hex(' ')}  ->  " + (
                        (reply + crc16(reply)).hex(" ") if reply else "(silent)"), flush=True)
                if reply:
                    os.write(master, reply + crc16(reply))
    except KeyboardInterrupt:
        pass
    finally:
        if args.link and os.path.islink(args.link):
            os.unlink(args.link)


if __name__ == "__main__":
    main()
