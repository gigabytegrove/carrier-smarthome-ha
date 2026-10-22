"""Read-only Carrier temperature/humidity telemetry sensors."""
from __future__ import annotations

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.const import PERCENTAGE

from .const import DOMAIN
from .entity import CarrierEntity
from .models import temperature_unit, zone_indices, zone_values

_SENSORS = {
    "humidity": ("Humidity", SensorDeviceClass.HUMIDITY, PERCENTAGE),
    "outside_temperature": ("Outside temperature", SensorDeviceClass.TEMPERATURE, None),
}


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([CarrierSensor(coordinator, serial, index, key)
                        for serial, system in coordinator.data.items()
                        for index in zone_indices(system)
                        for key in _SENSORS])


class CarrierSensor(CarrierEntity, SensorEntity):
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator, serial, index, key):
        super().__init__(coordinator, serial, index)
        self.key = key
        label, device_class, unit = _SENSORS[key]
        self._attr_name = label
        self._attr_unique_id = f"{serial}_zone_{index}_{key}"
        self._attr_device_class = device_class
        if unit:
            self._attr_native_unit_of_measurement = unit

    @property
    def native_unit_of_measurement(self):
        if self.key == "outside_temperature":
            return temperature_unit(self.system.get("temp_unit_format")) or self.hass.config.units.temperature_unit
        return PERCENTAGE

    @property
    def native_value(self):
        return zone_values(self.zone_data)[self.key]
