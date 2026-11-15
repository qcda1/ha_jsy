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
