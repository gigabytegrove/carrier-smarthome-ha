"""Carrier SmartHome alpha integration configuration."""
from datetime import timedelta

DOMAIN = "carrier_smarthome"
CONF_ENABLE_CONTROL = "enable_control"
DEFAULT_ENABLE_CONTROL = False
CONF_ENABLE_SETPOINT_CONTROL = "enable_setpoint_control"
DEFAULT_ENABLE_SETPOINT_CONTROL = False
CONF_ENABLE_FAN_CONTROL = "enable_fan_control"
DEFAULT_ENABLE_FAN_CONTROL = False
CONF_POWER_ON_MODE = "power_on_mode"
DEFAULT_POWER_ON_MODE = "unset"
POWER_ON_MODES = ("unset", "heat", "cool", "auto", "fanonly")
POLL_INTERVAL = timedelta(seconds=60)
SUPPORTED_MODEL = "TSTATCCEWF-01"
PLATFORMS = ["climate", "sensor", "binary_sensor", "switch", "select"]
