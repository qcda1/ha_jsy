# JSY-MK-194 Energy Meter — Home Assistant Integration

---

## Custom integration for the **JSY-MK-194 (T/G)** single-phase, two-channel energy metering module. Communicates with the module over **Modbus RTU** through a USB/TTL serial adapter

## Features

- Periodic polling of every register of the module (voltage, current, power, power factor, energy in both directions, frequency, for both channels)
- Every value of the `jsy_modbusdecoder.py` dictionary is exposed as a sensor
- Configurable polling interval from **2 to 3,600 seconds**
- Read/write registers can be changed from HA: the four energy counters, the Modbus ID and the baud rate
- Buttons to reset the energy counters, per channel or all at once
- Multi-module support, one USB/TTL adapter per module
- Each module is identified by its **Modbus ID**, so a module keeps its entities even if `/dev/ttyUSB0` and `/dev/ttyUSB1` are swapped after a reboot
- Options flow (⚙️ icon) to change the port, ID, baud rate and interval without reconfiguring
- Downloadable diagnostics report

## Requirements

| Component | Description |
|---|---|
| Home Assistant | 2026.2 or later |
| Module | JSY-MK-194T / JSY-MK-194G (TTL interface) |
| Adapter | One USB/TTL adapter per module (tested with an FT232R), plugged into the Home Assistant host |
| Python packages | `pymodbus` and `pyserial`, installed automatically by Home Assistant |

The module's TTL interface is point to point: each module needs its own adapter.

## Installation

### 1 - Install HACS (if not already done)

See <https://hacs.xyz/docs/use/>.

### 2 - Add the repository as a Custom repository

HACS → ⋮ → **Custom repositories** → Repository `https://github.com/qcda1/ha_jsy`, Type **Integration** → **Add**.

### 3 - Add the integration through HACS

Search for **JSY-MK-194 Energy Meter** in HACS, download it, then restart Home Assistant.

### Manual installation (without HACS)

Copy the `custom_components/ha_jsy` folder into the `custom_components` folder of your Home Assistant configuration, then restart Home Assistant.

```
config/
└── custom_components/
    └── ha_jsy/
        ├── __init__.py
        ├── manifest.json
        ├── jsy_modbusdecoder.py
        └── ...
```

### 4 - Add the integration

Settings → Devices & Services → **Add integration** → **JSY-MK-194 Energy Meter**.

## Configuration

### Step 1 — Connection

| Field | Description |
|---|---|
| Serial port | Port of the USB/TTL adapter. Detected ports are listed under their stable name (`/dev/serial/by-id/...`) when the system provides one; a path can also be typed |
| Current Modbus ID | The ID the module has **now**: `1` on a new module |
| Baud rate | `4800` on a new module |
| Polling interval | Seconds between two reads (default 10) |
| Device name | Name of the device in Home Assistant |

The integration reads the module to validate the connection.

### Step 2 — Modbus ID

The integration proposes the ID the module will keep: **10** for the first module, then 11, 12, and so on (highest configured ID + 1). If the proposed ID differs from the current one, it is written to the module (register 0004H) and verified before the device is created.

Keeping the factory ID (1) free means a new module can always be added without clashing with one that is already configured.

## How a module is identified

Linux names USB serial ports in the order they are detected, so `/dev/ttyUSB0` and `/dev/ttyUSB1` can be swapped after a reboot. The integration protects against this in two ways:

1. **Stable port name.** The port is stored as `/dev/serial/by-id/usb-FTDI_FT232R_USB_UART_<serial>-if00-port0` when that name exists. It is derived from the serial number of the adapter and does not change with the detection order.
2. **Modbus ID.** The ID assigned in step 2 is the identity of the module (it is the unique id of the config entry). A module only answers requests carrying its own ID, so reading the wrong module is not possible: the request simply gets no answer. When that happens, the integration probes the other adapters for the expected ID, moves the configuration to the port where it answers, and logs a warning.

The second mechanism matters when the stable name is not usable, which is the case with adapters that all report the same serial number (frequent with FT232R clones) or systems without `/dev/serial/by-id`.

Only adapters of the **same USB model** (VID:PID) as the one selected at setup are probed, so no Modbus frame is ever sent to an unrelated serial device such as a Zigbee stick. The search can be turned off in the options.

Entities are tied to the config entry, not to the port or the ID: they keep their history through a port change or an ID change.

## Created entities

Entity names are prefixed with the device name, for example `sensor.jsy_mk_194_10_power_1`.

### Sensors

| Entity | Unit | Dictionary key |
|---|---|---|
| Voltage 1 / 2 | V | `Voltage1`, `Voltage2` |
| Current 1 / 2 | A | `Current1`, `Current2` |
| Power 1 / 2 | W | `Power1`, `Power2` (unsigned, as sent by the module) |
| Power 1 / 2 (signed) | W | `PowerSigned1`, `PowerSigned2` (negative when the direction is negative) |
| Power Factor 1 / 2 | | `PowerFactor1`, `PowerFactor2` |
| Energy Positive 1 / 2 | kWh | `EnergyPositive1`, `EnergyPositive2` |
| Energy Negative 1 / 2 | kWh | `EnergyNegative1`, `EnergyNegative2` |
| Energy Net 1 / 2 | kWh | `EnergyNet1`, `EnergyNet2` (positive minus negative) |
| Power Direction 1 / 2 | | `PowerDirection1Text`, `PowerDirection2Text` (`positive` / `negative`) |
| Frequency | Hz | `Frequency` |

The energy sensors use the `energy` device class and can be used in the Energy dashboard.

### Diagnostic sensors

`Model 1`, `Model 2` (`Model1txt`, `Model2txt`), `Model 1 (raw)`, `Model 2 (raw)`, `Voltage Range`, `Current Range`, `Modbus Device ID`, `Baud Rate`, `Baud Rate Code`, `Power Direction 1 / 2 (raw)`, `Serial Port`.

A key added later to `jsy_modbusdecoder.py` appears automatically as a plain sensor.

## Read/write registers

These are the registers the manual documents as writable. The editable entities carry the suffix **(Set)** and are listed under *Configuration* on the device page.

| Entity | Register | Effect |
|---|---|---|
| Energy Positive 1 (Set) | 004BH | Presets the counter, in kWh |
| Energy Negative 1 (Set) | 004DH | Presets the counter, in kWh |
| Energy Positive 2 (Set) | 0053H | Presets the counter, in kWh |
| Energy Negative 2 (Set) | 0055H | Presets the counter, in kWh |
| Modbus Device ID (Set) | 0004H, high byte | Changes the module's ID (1–255) |
| Baud Rate (Set) | 0004H, low byte | Changes the module's speed (1200–38400) |
| Reset Energy Channel 1 (button) | 004BH, 004DH | Zeroes both counters of channel 1 |
| Reset Energy Channel 2 (button) | 0053H, 0055H | Zeroes both counters of channel 2 |
| Reset Energy (All) (button) | 000CH | Zeroes the four counters |

After a write the module is read again immediately, so the entities show the value confirmed by the module. A failed write is reported as an error in the Home Assistant UI.

When the ID or the baud rate is changed, the integration checks that the module answers with the new settings and updates its own configuration. If the module still answers with the old settings, nothing is changed and an error explains what to do.

### Notes

- Writing a smaller value to an energy counter is seen by Home Assistant as a meter reset, which the `total_increasing` statistics handle.
- An ID already used by another configured module is refused.
- Keep 4800 baud unless you have a reason to change it: a full read takes about 0.3 s at that speed.

## Options

Settings → Devices & Services → JSY-MK-194 → ⚙️. The options describe **how Home Assistant reaches the module** (port, Modbus ID, baud rate, polling interval, search on other ports). Nothing is written to the module from this screen. Use it, for instance, after replacing an adapter or after changing the module's settings with another tool.

## Multiple modules

Add the integration once per module. Plug the new module in, add it with its current ID (1 if new), and accept the proposed ID. Each module becomes a separate device with its own entities.

All serial accesses of the integration are serialised, so several modules never talk at the same time.

## Files

| File | Role |
|---|---|
| `jsy_modbusdecoder.py` | Reads and decodes the registers into a dictionary. Standalone: `python jsy_modbusdecoder.py [port]` |
| `jsy_reader.py` | Port discovery, fast probe, wrapper around the decoder |
| `jsy_writer.py` | Writes to the read/write registers |
| `coordinator.py` | Polling, port relocation, writes, health counters |
| `config_flow.py` | Setup and options screens |
| `entity.py`, `sensor.py`, `number.py`, `select.py`, `button.py` | Entities |
| `diagnostics.py` | Diagnostics report |
| `tools/jsy_simulator.py` | Fake module on a pseudo serial port, to test without hardware |

## Register addressing

The manual numbers the measurements one address per **4-byte value** (0048H, 0049H, ...), not per 16-bit Modbus register:

- Reading: request **14** values at 0048H; the module returns 56 data bytes (28 words). Requests for 20 or 28 are refused with exception 82H.
- Writing: two 16-bit words are sent to the address of the value, for example `01 10 00 4B 00 02 04 00 00 00 00` to clear the positive energy of channel 1.

## Troubleshooting

| Symptom | Check |
|---|---|
| *No answer from the module* during setup | Port, current ID (1 on a new module), baud rate, TX/RX crossed, module powered |
| No port in the list | The adapter must be plugged into the Home Assistant host. On Home Assistant OS, see Settings → System → Hardware → All hardware |
| Entities unavailable after a reboot | Read the log: a warning tells whether the module was found on another port. Check that *Look for the module on other ports* is enabled in the options |
| Module unreachable after an ID or baud rate change | Power-cycle the module, then set the right ID / baud rate in the options |

Debug logging:

```yaml
logger:
  logs:
    custom_components.ha_jsy: debug
    jsy_modbusdecoder: debug
```

Diagnostics: Settings → Devices & Services → JSY-MK-194 → ⋮ → **Download diagnostics**. The report lists the connection settings, the last failures, the last decoded values and the serial ports seen by the host.

## Status of the write functions

Reading has been validated on a real JSY-MK-194G. The write functions follow the manual and have been validated against the simulator only. To confirm on hardware:

- whether a new Modbus ID or baud rate applies immediately or after a power cycle;
- whether register 0004H accepts a single-word write;
- presetting an energy counter to a non-zero value.

## License

MIT
