"""Carrier cloud-reported device online status (not a LAN ping)."""
from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = hass.data[DOMAIN][entry.entry_id]
    seen: set[str] = set()

    def add_new_devices():
        fresh = []
        for serial in coordinator.data:
            if serial not in seen:
                seen.add(serial)
                fresh.append(CarrierCloudConnectivity(coordinator, serial))
        if fresh:
            async_add_entities(fresh)

    add_new_devices()
    entry.async_on_unload(coordinator.async_add_listener(add_new_devices))


class CarrierCloudConnectivity(CoordinatorEntity, BinarySensorEntity):
    _attr_has_entity_name = True
    _attr_name = "Carrier cloud connection"
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY

    def __init__(self, coordinator, serial):
        super().__init__(coordinator)
        self.serial = serial
        self._attr_unique_id = f"{serial}_carrier_cloud_connection"

    @property
    def device_info(self):
        system = self.coordinator.data.get(self.serial, {})
        return {"identifiers": {(DOMAIN, self.serial)},
                "manufacturer": "Carrier", "name": system.get("name") or "Carrier Smart Thermostat",
                "model": system.get("model") or "Smart Thermostat"}

    @property
    def available(self):
        return self.coordinator.last_update_success and self.serial in self.coordinator.data

    @property
    def is_on(self):
        connection = self.coordinator.data.get(self.serial, {}).get("connection") or {}
        return connection.get("isConnected") is True
