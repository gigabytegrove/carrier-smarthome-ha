"""Carrier SmartHome live and explicitly labeled last cloud-reported sensors.

Live sensors disappear when Carrier reports the thermostat offline. Additional
"Last cloud-reported" sensors preserve visibility into the values returned by
Carrier, but must NEVER be interpreted as fresh or safe for control loops.
Carrier does not provide a trustworthy sample timestamp in the query used here.
"""
from __future__ import annotations

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.const import PERCENTAGE

from .const import DOMAIN
from .entity import CarrierEntity
from .models import connectivity_state, temperature_unit, zone_indices, zone_values

_LIVE_SENSORS = {
    "humidity": ("Humidity", SensorDeviceClass.HUMIDITY, PERCENTAGE),
    "outside_temperature": ("Outside temperature", SensorDeviceClass.TEMPERATURE, None),
}

# Distinct entities, rather than making the existing live measurements look
# available while the thermostat itself is not connected to Carrier.
_LAST_REPORTED_SENSORS = {
    "temperature": ("Last cloud-reported room temperature", SensorDeviceClass.TEMPERATURE, None),
    "humidity": ("Last cloud-reported humidity", SensorDeviceClass.HUMIDITY, PERCENTAGE),
    "outside_temperature": ("Last cloud-reported outdoor temperature", SensorDeviceClass.TEMPERATURE, None),
    "heat_setpoint": ("Last cloud-reported heating target", SensorDeviceClass.TEMPERATURE, None),
    "cool_setpoint": ("Last cloud-reported cooling target", SensorDeviceClass.TEMPERATURE, None),
    "heat_max": ("Last cloud-reported heating limit", SensorDeviceClass.TEMPERATURE, None),
    "cool_min": ("Last cloud-reported cooling limit", SensorDeviceClass.TEMPERATURE, None),
    "mode": ("Last cloud-reported HVAC mode", None, None),
    "fan_mode": ("Last cloud-reported fan setting", None, None),
    "stage_status": ("Last cloud-reported equipment status", None, None),
    "schedule_enabled": ("Last cloud-reported schedule state", None, None),
    "current_scene": ("Last cloud-reported comfort profile", None, None),
}


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = hass.data[DOMAIN][entry.entry_id]
    seen: set[tuple[str, int, str, str]] = set()

    def add_new_sensors():
        fresh = []
        for serial, system in coordinator.data.items():
            for index in zone_indices(system):
                for key in _LIVE_SENSORS:
                    identity = (serial, index, "live", key)
                    if identity not in seen:
                        seen.add(identity)
                        fresh.append(CarrierSensor(coordinator, serial, index, key))
                for key in _LAST_REPORTED_SENSORS:
                    identity = (serial, index, "last_reported", key)
                    if identity not in seen:
                        seen.add(identity)
                        fresh.append(CarrierLastReportedSensor(coordinator, serial, index, key))
        if fresh:
            async_add_entities(fresh)

    add_new_sensors()
    entry.async_on_unload(coordinator.async_add_listener(add_new_sensors))


class CarrierSensor(CarrierEntity, SensorEntity):
    """Live measurement; intentionally unavailable when Carrier says offline."""

    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator, serial, index, key):
        super().__init__(coordinator, serial, index)
        self.key = key
        label, device_class, unit = _LIVE_SENSORS[key]
        self._attr_name = label
        self._attr_unique_id = f"{serial}_zone_{index}_{key}"
        self._attr_device_class = device_class
        if unit:
            self._attr_native_unit_of_measurement = unit

    @property
    def available(self):
        # Like the live climate entity, humidity and outside temperature stay
        # unavailable when the physical device is Carrier-reported offline.
        # Separate diagnostic entities retain optional cached readings.
        return super().available and connectivity_state(self.system) == "online"

    @property
    def native_unit_of_measurement(self):
        if self.key != "humidity":
            return temperature_unit(self.system.get("temp_unit_format")) or self.hass.config.units.temperature_unit
        return PERCENTAGE

    @property
    def native_value(self):
        return zone_values(self.zone_data)[self.key]

    @property
    def extra_state_attributes(self):
        return {
            "last_successful_poll_utc": getattr(self.coordinator, "last_poll_utc", None),
            "cloud_poll_succeeded": self.coordinator.last_update_success,
            "brief_grace_period_data": getattr(self.coordinator, "telemetry_in_grace", False),
        }


class CarrierLastReportedSensor(CarrierEntity, SensorEntity):
    """Last value returned by Carrier's cloud; freshness cannot be asserted.

    This is NOT a live measurement, even if the API is responding. Never use
    these values in HVAC automations or Home Assistant long-term statistics.
    """

    _attr_state_class = None  # A cached/offline value is not a measurement event.

    def __init__(self, coordinator, serial, index, key):
        super().__init__(coordinator, serial, index)
        self.key = key
        label, device_class, unit = _LAST_REPORTED_SENSORS[key]
        self._attr_name = label
        # Diagnostic entities are opt-in in the HA UI to avoid flooding dashboards.
        from homeassistant.helpers.entity import EntityCategory
        self._attr_entity_category = EntityCategory.DIAGNOSTIC
        # Keep the device page uncluttered by default; these are explicitly
        # potentially stale readings and can be enabled by the owner.
        self._attr_entity_registry_enabled_default = False
        self._attr_unique_id = f"{serial}_zone_{index}_last_cloud_reported_{key}"
        self._attr_device_class = device_class
        if unit:
            self._attr_native_unit_of_measurement = unit

    @property
    def available(self):
        # Require a successful, CURRENT API poll and a numeric value in its
        # response, but NOT cloud-reported online status. The value itself may
        # have been cached by Carrier for an unknown length of time.
        # Last-known readings are intentionally still readable when the cloud
        # is unavailable, and explicitly marked as potentially stale.
        return bool(self.serial in self.coordinator.data and
                    self.zone_data and self.native_value is not None)

    @property
    def native_unit_of_measurement(self):
        if self.key == "humidity":
            return PERCENTAGE
        if self.key in {"temperature", "outside_temperature", "heat_setpoint", "cool_setpoint", "heat_max", "cool_min"}:
            return temperature_unit(self.system.get("temp_unit_format")) or self.hass.config.units.temperature_unit
        # Never label HVAC mode / fan / stage / schedule status as degrees.
        return None

    @property
    def native_value(self):
        value = zone_values(self.zone_data)[self.key]
        if self.key == "schedule_enabled":
            return "enabled" if value is True else "disabled" if value is False else None
        return value

    @property
    def extra_state_attributes(self):
        return {
            "carrier_reported_connection": connectivity_state(self.system),
            "value_freshness": "unverified_may_be_stale",
            "device_sample_timestamp": "not_provided_by_api",
            "not_for_hvac_automations": True,
            "last_successful_poll_utc": getattr(self.coordinator, "last_poll_utc", None),
            "cloud_poll_succeeded": self.coordinator.last_update_success,
        }
