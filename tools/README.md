# Tools

## jsy_simulator.py

A fake JSY-MK-194 behind a pseudo serial port (Linux / macOS, standard library
only). Use it to try `jsy_modbusdecoder.py` or the integration without the
hardware.

```bash
python jsy_simulator.py --id 1 --link /tmp/ttyJSY0
# in another terminal
python ../custom_components/ha_jsy/jsy_modbusdecoder.py /tmp/ttyJSY0
```

In Home Assistant, type the link path (`/tmp/ttyJSY0`) in the *Serial port*
field of the config flow. Start a second simulator with another `--link` to
test several modules.

The simulator answers the way a real JSY-MK-194G was observed to answer for
reads. For writes it follows the manual; see the assumptions listed at the top
of the script.

## jsy_write_test.py

Write tests against a **real** module, with raw Modbus frames (pyserial only,
no pymodbus). It prints every frame sent and received, and measures how long
the module stays silent after a write. Free the serial port first: disable the
integration in Home Assistant, or move the adapter to another machine.

```bash
python jsy_write_test.py --port /dev/ttyUSB0 --id 10              # read-only check
python jsy_write_test.py --port /dev/ttyUSB0 --id 10 --energy     # energy counter
python jsy_write_test.py --port /dev/ttyUSB0 --id 10 --new-id 11  # ID, and back
python jsy_write_test.py --port /dev/ttyUSB0 --id 10 --new-baud 9600   # speed, and back
python jsy_write_test.py --port /dev/ttyUSB0 --scan               # find a lost module
```

Each test restores the module to its initial state. `--scan` tries every baud
rate and every ID, for a module whose settings are no longer known.
