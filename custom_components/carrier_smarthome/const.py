"""Carrier SmartHome alpha integration configuration."""
from datetime import timedelta

DOMAIN = "carrier_smarthome"
CONF_ENABLE_CONTROL = "enable_control"
DEFAULT_ENABLE_CONTROL = False
POLL_INTERVAL = timedelta(seconds=60)
SUPPORTED_MODEL = "TSTATCCEWF-01"
PLATFORMS = ["climate", "sensor", "binary_sensor"]
