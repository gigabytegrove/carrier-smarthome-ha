"""Carrier SmartHome integration constants.

A thermostat's normal controls live in the climate entity, not config options.
"""
from datetime import timedelta

DOMAIN = "carrier_smarthome"
POLL_INTERVAL = timedelta(seconds=30)
SUPPORTED_MODEL = "TSTATCCEWF-01"
PLATFORMS = ["climate", "sensor", "binary_sensor"]
