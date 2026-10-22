"""Carrier SmartHome integration constants.

A thermostat's normal controls live in the climate entity, not config options.
"""
from datetime import timedelta

DOMAIN = "carrier_smarthome"
POLL_INTERVAL = timedelta(seconds=60)
# Keep the last confirmed online state visible through one short API interruption.
# All HVAC commands still require a freshly successful cloud read.
TRANSIENT_GRACE_SECONDS = 90
MAX_POLL_BACKOFF_SECONDS = 600
SUPPORTED_MODEL = "TSTATCCEWF-01"
PLATFORMS = ["climate", "sensor", "binary_sensor"]
