"""Constants for the JSY-MK-194 integration."""

DOMAIN = "ha_jsy"
VERSION = "0.1.0"

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
ENERGY_MAX_KWH = 0xFFFFFFFF / ENERGY_SCALE  # 429496.7295 kWh

# --------------------------------------------------------------------------- #
# Every key returned by jsy_modbusdecoder.getRegisters(), with its metadata.
# Format: key -> (friendly_name, unit, device_class, state_class, icon,
#                 precision, diagnostic)
#
# precision  : digits shown by default in HA (None for text values)
# diagnostic : True = shown under "Diagnostic" on the device page
# Keys returned by the decoder but missing here still get a plain sensor.
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
