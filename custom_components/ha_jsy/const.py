"""Constants for the JSY-MK-194 integration."""

from __future__ import annotations

DOMAIN = "ha_jsy"
VERSION = "1.1.1"

MANUFACTURER = "Shenzhen Jiansiyan Technologies (JSY)"

# hass.data[DOMAIN] keys
COORDINATOR = "coordinator"
SERIAL_LOCK = "_serial_lock"

# Config entry keys
CONF_PORT = "port"
CONF_DEVICE_ID = "device_id"
CONF_BAUDRATE = "baudrate"
CONF_SCAN_INTERVAL = "scan_interval"
CONF_NAME = "name"
CONF_USB_VID = "usb_vid"
CONF_USB_PID = "usb_pid"
CONF_AUTO_RELOCATE = "auto_relocate"
CONF_MONITORED_PARAMETERS = "monitored_parameters"
CONF_CH1_NAME = "channel_1_name"
CONF_CH2_NAME = "channel_2_name"
CONF_CH1_CIRCUIT = "channel_1_circuit"
CONF_CH2_CIRCUIT = "channel_2_circuit"
# Config flow only (never stored)
CONF_NEW_DEVICE_ID = "new_device_id"

# Defaults
DEFAULT_DEVICE_ID = 1          # factory Modbus ID of every JSY module
DEFAULT_BAUDRATE = 4800        # factory baud rate
DEFAULT_SCAN_INTERVAL = 10     # seconds
MIN_SCAN_INTERVAL = 2
MAX_SCAN_INTERVAL = 3600
DEFAULT_NAME = "JSY-MK-194"
DEFAULT_AUTO_RELOCATE = True

# Modbus IDs handed out by the config flow: 10 for the first module, then
# 11, 12, ... The factory ID (1) is left free so a brand-new module can always
# be told apart from the ones that are already configured.
FIRST_ASSIGNED_ID = 10
MIN_DEVICE_ID = 1
MAX_DEVICE_ID = 255

# Dictionary keys behind the editable entities (number / select). They are
# always monitored so their current value is available as a sensor too.
WRITABLE_PARAMETER_KEYS: list[str] = [
    "EnergyPositive1",
    "EnergyNegative1",
    "EnergyPositive2",
    "EnergyNegative2",
    "DeviceID",
    "BaudRate",
]

# Parameters pre-selected at installation
DEFAULT_PARAMETERS: list[str] = [
    "Voltage1",
    "Current1",
    "PowerSigned1",
    "Voltage2",
    "Current2",
    "PowerSigned2",
    *WRITABLE_PARAMETER_KEYS,
]

# --------------------------------------------------------------------------- #
# Per-channel settings
# --------------------------------------------------------------------------- #
CHANNELS = (1, 2)
CONF_CHANNEL_NAME = {1: CONF_CH1_NAME, 2: CONF_CH2_NAME}
CONF_CHANNEL_CIRCUIT = {1: CONF_CH1_CIRCUIT, 2: CONF_CH2_CIRCUIT}

# Circuit the current sensor (CT) of a channel is clamped on.
#
# The module has ONE voltage input and uses it for both channels. On a
# split-phase panel (240 V between L1 and L2, 120 V from each to neutral) that
# input is normally wired line-neutral, so the module computes
# P = 120 V x I x PF. For a load fed line-to-line (240 V, no neutral current)
# the real figures are twice that: voltage, power and energy are multiplied by
# the factor below. Current and power factor are already right.
CIRCUIT_LINE_NEUTRAL = "line_neutral"
CIRCUIT_LINE_LINE = "line_line"
DEFAULT_CIRCUIT = CIRCUIT_LINE_NEUTRAL
CIRCUIT_MULTIPLIER: dict[str, int] = {
    CIRCUIT_LINE_NEUTRAL: 1,
    CIRCUIT_LINE_LINE: 2,
}

# Dictionary keys (without the channel digit) scaled by the circuit multiplier
SCALED_CHANNEL_KEYS = (
    "Voltage",
    "Power",
    "PowerSigned",
    "EnergyPositive",
    "EnergyNegative",
    "EnergyNet",
)

# Manual Table 1 — low byte of register 0004H
BAUD_RATE_CODES: dict[int, int] = {
    1200: 3,
    2400: 4,
    4800: 5,
    9600: 6,
    19200: 7,
    38400: 8,
}

# --------------------------------------------------------------------------- #
# Register addresses (manual Tables 1 and 3). In Table 3 one address is one
# 4-byte value; a write sends 2 x 16-bit words to that address (manual 4.4.2).
# --------------------------------------------------------------------------- #
REG_ID_BAUD = 0x0004
REG_CLEAR_ALL_ENERGY = 0x000C

# Writable energy counters: dictionary key -> register address
WRITABLE_ENERGY_REGISTERS: dict[str, int] = {
    "EnergyPositive1": 0x004B,
    "EnergyNegative1": 0x004D,
    "EnergyPositive2": 0x0053,
    "EnergyNegative2": 0x0055,
}
ENERGY_SCALE = 10000                      # raw = kWh x 10000
# Measured on a JSY-MK-194G: a written counter is stored in steps of 0.01 kWh
# (raw value truncated to a multiple of 100), although it then counts and
# reads back in steps of 0.001 kWh.
ENERGY_WRITE_STEP_RAW = 100
ENERGY_WRITE_STEP_KWH = ENERGY_WRITE_STEP_RAW / ENERGY_SCALE   # 0.01 kWh
ENERGY_MAX_KWH = 0xFFFFFFFF / ENERGY_SCALE  # 429496.7295 kWh

# --------------------------------------------------------------------------- #
# Every key returned by jsy_modbusdecoder.getRegisters(), with its metadata.
# Format: key -> (friendly_name, unit, device_class, state_class, icon,
#                 precision, diagnostic)
#
# precision  : digits shown by default in HA (None for text values)
# diagnostic : True = shown under "Diagnostic" on the device page
# Keys returned by the decoder but missing here can still be selected; they
# get a plain sensor.
# --------------------------------------------------------------------------- #
PARAMETER_META: dict[str, tuple] = {
    # --- Channel 1 ---------------------------------------------------------
    "Voltage1":            ("Voltage 1",              "V",   "voltage",      "measurement",      "mdi:sine-wave",              1,    False),
    "Current1":            ("Current 1",              "A",   "current",      "measurement",      "mdi:current-ac",             3,    False),
    "Power1":              ("Power 1",                "W",   "power",        "measurement",      "mdi:flash",                  1,    False),
    "PowerSigned1":        ("Power 1 (signed)",       "W",   "power",        "measurement",      "mdi:flash-outline",          1,    False),
    "PowerFactor1":        ("Power Factor 1",         None,  "power_factor", "measurement",      "mdi:angle-acute",            3,    False),
    "EnergyPositive1":     ("Energy Positive 1",      "kWh", "energy",       "total_increasing", "mdi:transmission-tower-import", 3, False),
    "EnergyNegative1":     ("Energy Negative 1",      "kWh", "energy",       "total_increasing", "mdi:transmission-tower-export", 3, False),
    "EnergyNet1":          ("Energy Net 1",           "kWh", "energy",       "total",            "mdi:scale-balance",          3,    False),
    "PowerDirection1":     ("Power Direction 1 (raw)", None, None,           None,               "mdi:swap-horizontal",        None, True),
    "PowerDirection1Text": ("Power Direction 1",      None,  None,           None,               "mdi:swap-horizontal",        None, False),
    # --- Channel 2 ---------------------------------------------------------
    "Voltage2":            ("Voltage 2",              "V",   "voltage",      "measurement",      "mdi:sine-wave",              1,    False),
    "Current2":            ("Current 2",              "A",   "current",      "measurement",      "mdi:current-ac",             3,    False),
    "Power2":              ("Power 2",                "W",   "power",        "measurement",      "mdi:flash",                  1,    False),
    "PowerSigned2":        ("Power 2 (signed)",       "W",   "power",        "measurement",      "mdi:flash-outline",          1,    False),
    "PowerFactor2":        ("Power Factor 2",         None,  "power_factor", "measurement",      "mdi:angle-acute",            3,    False),
    "EnergyPositive2":     ("Energy Positive 2",      "kWh", "energy",       "total_increasing", "mdi:transmission-tower-import", 3, False),
    "EnergyNegative2":     ("Energy Negative 2",      "kWh", "energy",       "total_increasing", "mdi:transmission-tower-export", 3, False),
    "EnergyNet2":          ("Energy Net 2",           "kWh", "energy",       "total",            "mdi:scale-balance",          3,    False),
    "PowerDirection2":     ("Power Direction 2 (raw)", None, None,           None,               "mdi:swap-horizontal",        None, True),
    "PowerDirection2Text": ("Power Direction 2",      None,  None,           None,               "mdi:swap-horizontal",        None, False),
    # --- Common ------------------------------------------------------------
    "Frequency":           ("Frequency",              "Hz",  "frequency",    "measurement",      "mdi:waveform",               2,    False),
    # --- Module information / configuration ----------------------------------
    "Model1":              ("Model 1 (raw)",          None,  None,           None,               "mdi:chip",                   None, True),
    "Model2":              ("Model 2 (raw)",          None,  None,           None,               "mdi:chip",                   None, True),
    "Model1txt":           ("Model 1",                None,  None,           None,               "mdi:chip",                   None, True),
    "Model2txt":           ("Model 2",                None,  None,           None,               "mdi:chip",                   None, True),
    "VoltageRange":        ("Voltage Range",          "V",   "voltage",      None,               "mdi:arrow-expand-vertical",  0,    True),
    "CurrentRange":        ("Current Range",          "A",   "current",      None,               "mdi:arrow-expand-vertical",  0,    True),
    "DeviceID":            ("Modbus Device ID",       None,  None,           None,               "mdi:identifier",             None, True),
    "BaudRateCode":        ("Baud Rate Code",         None,  None,           None,               "mdi:speedometer",            None, True),
    "BaudRate":            ("Baud Rate",              "Bd",  None,           None,               "mdi:speedometer",            None, True),
    "Port":                ("Serial Port",            None,  None,           None,               "mdi:usb-port",               None, True),
}


def channel_of(key: str) -> int | None:
    """Channel (1 or 2) a dictionary key belongs to, None for common keys."""
    if key.startswith("Model"):
        return None
    for channel in CHANNELS:
        for suffix in ("", "Text", "_set"):
            if key.endswith(f"{channel}{suffix}"):
                return channel
    return None
