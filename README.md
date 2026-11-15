# JSY-MK-194 Energy Meter — Home Assistant Integration

---

## Custom integration for the **JSY-MK-194 (T/G)** single-phase, two-channel energy metering module. Communicates with the module over **Modbus RTU** through a USB/TTL serial adapter

## Features

- Periodic polling of every register of the module (voltage, current, power, power factor, energy in both directions, frequency, for both channels)
- Every value of the `jsy_modbusdecoder.py` dictionary is available; select which ones to expose as HA entities via the UI
- Configurable polling interval from **2 to 3,600 seconds**
- Read/write registers can be changed from HA: the four energy counters, the Modbus ID and the baud rate
- Buttons to reset the energy counters, per channel or all at once
- Multi-module support, one USB/TTL adapter per module
- Each channel can be named after what it measures (`Heat pump`, `Furnace`) and the name is used in its entities
- Split-phase support: a channel on a 240 V line-to-line circuit gets its voltage, power and energy corrected
- Each module is identified by its **Modbus ID**, so a module keeps its entities even if `/dev/ttyUSB0` and `/dev/ttyUSB1` are swapped after a reboot
- Options flow (⚙️ icon) to change the port, ID, baud rate, interval and monitored parameters without reconfiguring
- Downloadable diagnostics report

## Requirements

| Component | Description |
|---|---|
| Home Assistant | 2026.2 or later (tested on 2026.2 and used on 2026.11) |
| Module | JSY-MK-194T / JSY-MK-194G (TTL interface) |
| Adapter | One USB/TTL adapter per module (tested with an FT232R), plugged into the Home Assistant host |
| Python packages | `pymodbus` and `pyserial`, installed automatically by Home Assistant |

The module's TTL interface is point to point: each module needs its own adapter.

## Installation

### Home Assistant 2026.11 or later — Marketplace

Since Home Assistant 2026.11, HACS is built into Home Assistant as the **Marketplace** (Settings → Marketplace). Nothing has to be installed first.

1. Go to **Settings → Marketplace**. On first use, accept the community-content notice.
2. Select **Add from link** in the upper-right corner.
3. Under **GitHub link**, enter `https://github.com/qcda1/ha_jsy` (or `qcda1/ha_jsy`) and select **Add**. Home Assistant asks you to connect your GitHub account the first time you add a custom repository. If the content type is not detected, choose **Integration** under **Type** and select **Add** again.
4. Open **JSY-MK-194 Energy Meter**, select **Install**, confirm the version and select **Install** again.
5. If a restart is requested, use the repair under **Settings → System → Repairs**.
6. Go to **Settings → Devices & Services → Add integration** and search for **JSY-MK-194 Energy Meter**.

Updates then appear under **Settings → Updates**. Updating the integration requires a restart of Home Assistant.

### Home Assistant 2026.10 or earlier — HACS

1. Install HACS if not already done (<https://hacs.xyz/docs/use/>).
2. HACS → ⋮ → **Custom repositories** → Repository `https://github.com/qcda1/ha_jsy`, Type **Integration** → **Add**.
3. Search for **JSY-MK-194 Energy Meter** in HACS, download it, then restart Home Assistant.
4. Settings → Devices & Services → **Add integration** → **JSY-MK-194 Energy Meter**.

### Manual installation

Copy the `custom_components/ha_jsy` folder into the `custom_components` folder of your Home Assistant configuration, restart Home Assistant, then add the integration from Settings → Devices & Services.

```
config/
└── custom_components/
    └── ha_jsy/
        ├── __init__.py
        ├── manifest.json
        ├── jsy_modbusdecoder.py
        └── ...
```

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

### Step 3 — Channels

| Field | Description |
|---|---|
| Name of channel 1 / 2 | Optional. What the channel measures, for example `Heat pump` or `Furnace`. Used in the entity names |
| Circuit measured by channel 1 / 2 | **Line–neutral** (values as measured) or **Line–line, split-phase** (voltage, power and energy ×2). See [Split-phase panels](#split-phase-panels-120--240-v) |

### Step 4 — Monitored parameters

Tick the values to expose as sensors. Pre-selected:

- `Voltage1`, `Current1`, `PowerSigned1`, `Voltage2`, `Current2`, `PowerSigned2`
- the read/write registers: `EnergyPositive1`, `EnergyNegative1`, `EnergyPositive2`, `EnergyNegative2`, `DeviceID`, `BaudRate`

The read/write registers are always included, even if un-ticked, because the editable entities rely on them. The selection can be changed later in the options.

## Channel names

By default the entities are named after the registers: `Voltage 1`, `Power 2 (signed)`, and so on. When a channel has a name, it replaces the channel number:

| Without a name | Channel 1 named `Heat pump` |
|---|---|
| Voltage 1 | Heat pump Voltage |
| Power 1 (signed) | Heat pump Power (signed) |
| Energy Positive 1 (Set) | Heat pump Energy Positive (Set) |
| Reset Energy Channel 1 | Heat pump Reset Energy |

Entities common to both channels (frequency, module information) keep their names.

### Entity IDs

The integration sets the entity IDs itself, so they do not depend on the area the device is placed in:

| Entity | Displayed name | Entity ID |
|---|---|---|
| Named channel | `Heat pump Voltage` | `sensor.heat_pump_voltage` |
| Channel without a name | `<device> Voltage 1` | `sensor.<device>_voltage_1` |
| Common to both channels | `<device> Frequency` | `sensor.<device>_frequency` |

Entities of a named channel do not carry the device name. A module often measures two unrelated circuits (a water heater and a refrigerator, say), so the channel name identifies them better than any device name would. The device name is then only used for the common entities and for the device page: a neutral name such as the default `JSY-MK-194 #10`, or the panel the module is installed in, works well.

An entity that already exists keeps the ID stored in Home Assistant. Naming a channel later, in the options, changes the displayed names but not the existing entity IDs, so history, dashboards and automations are unaffected. To get entity IDs that match, name the channels when the module is added.

## Split-phase panels (120 / 240 V)

The module has **one** voltage input, shared by both channels. On a North American split-phase panel there are 240 V between L1 and L2 and 120 V from each to neutral, and the voltage input is normally wired line–neutral (120 V).

For a load on a single-pole breaker (120 V) this is exactly right. For a load on a double-pole breaker fed line-to-line (240 V with no neutral: furnace, heat pump, water heater), the current sensor sees the full load current but the module multiplies it by 120 V instead of 240 V. Power and energy come out at **half** their real value.

Set the circuit of the channel to **Line–line, split-phase** to correct this. For that channel:

| Value | Correction |
|---|---|
| Voltage | ×2 |
| Power, Power (signed) | ×2 |
| Energy Positive, Negative, Net | ×2 |
| Current, Power Factor | unchanged |

The correction is applied to the decoded dictionary, per channel; the module's own counters are not modified. The *(Set)* energy entities take and show corrected values and convert them when writing.

Notes:

- The correction assumes a pure 240 V load. If part of the load returns through the neutral (a 120 V control circuit, for example), that part is over-counted.
- `Voltage Range` (module information) stays as reported by the module.
- **Reset the energy counters of the channel before changing the circuit type** (*Reset Energy* button). Otherwise the energy sensors double at once and Home Assistant's statistics record the jump as consumption.

## How a module is identified

Linux names USB serial ports in the order they are detected, so `/dev/ttyUSB0` and `/dev/ttyUSB1` can be swapped after a reboot. The integration protects against this in two ways:

1. **Stable port name.** The port is stored as `/dev/serial/by-id/usb-FTDI_FT232R_USB_UART_<serial>-if00-port0` when that name exists. It is derived from the serial number of the adapter and does not change with the detection order.
2. **Modbus ID.** The ID assigned in step 2 is the identity of the module (it is the unique id of the config entry). A module only answers requests carrying its own ID, so reading the wrong module is not possible: the request simply gets no answer. When that happens, the integration probes the other adapters for the expected ID, moves the configuration to the port where it answers, and logs a warning.

The second mechanism matters when the stable name is not usable, which is the case with adapters that all report the same serial number (frequent with FT232R clones) or systems without `/dev/serial/by-id`.

Only adapters of the **same USB model** (VID:PID) as the one selected at setup are probed, so no Modbus frame is ever sent to an unrelated serial device such as a Zigbee stick. The search can be turned off in the options.

Entities are tied to the config entry, not to the port or the ID: they keep their history through a port change or an ID change.

## Created entities

See [Entity IDs](#entity-ids) for how entities are named. A sensor is created for each parameter selected in step 4; the tables below list everything that can be selected.

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

A key added later to `jsy_modbusdecoder.py` appears automatically in the selection list and gets a plain sensor.

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

The ID and baud rate fields of the **options** screen are a different thing: they tell Home Assistant which settings the module already has, and write nothing to it. Settings the module does not answer to are refused there.

### Notes

- Writing a smaller value to an energy counter is seen by Home Assistant as a meter reset, which the `total_increasing` statistics handle.
- An ID already used by another configured module is refused.
- Keep 4800 baud unless you have a reason to change it: a full read takes about 0.3 s at that speed.

## Options

Settings → Devices & Services → JSY-MK-194 → ⚙️. The options describe **how Home Assistant reaches the module** (port, Modbus ID, baud rate, polling interval, search on other ports), the **channel names and circuit types**, and **which parameters are monitored**. Nothing is written to the module from this screen. Use it, for instance, after replacing an adapter or after changing the module's settings with another tool.

A sensor whose parameter is un-ticked is removed from Home Assistant. Its long-term statistics are kept and are picked up again if the parameter is re-selected.

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
| `tools/jsy_write_test.py` | Raw-frame write tests against a real module (energy, ID, baud rate) |
| `docs/Notes_v110.md` | Release notes (French) |

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

Validated on a real JSY-MK-194G:

- **Modbus ID** (register 0004H, single-word write): applies immediately. The module does not acknowledge this write, so the integration checks the result by questioning the module with its new ID.
- **Energy counters**: zero and non-zero values are written and acknowledged.
- After a write the module stays silent for a moment. The integration waits, then reads the value back, retrying a few times; the entities keep their state meanwhile.

Still to confirm on hardware: the **baud rate** change. `tools/jsy_write_test.py` runs each of these tests with raw frames and measures the silence after a write.

## License

MIT
