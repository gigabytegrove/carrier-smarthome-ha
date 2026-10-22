"""Carrier cloud-reported device online status (not a LAN ping)."""
from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .models import connectivity_state


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = hass.data[DOMAIN][entry.entry_id]
    seen: set[str] = set()

    def add_new_devices():
        fresh = []
        for serial in coordinator.data:
            if serial not in seen:
                seen.add(serial)
                fresh.append(CarrierCloudConnectivity(coordinator, serial))
                fresh.append(CarrierApiReadable(coordinator, serial))
        if fresh:
            async_add_entities(fresh)

    add_new_devices()
    entry.async_on_unload(coordinator.async_add_listener(add_new_devices))


class CarrierCloudConnectivity(CoordinatorEntity, BinarySensorEntity):
    _attr_has_entity_name = True
    _attr_name = "Carrier-reported device connection"
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
        # An absent/malformed connection field is unknown, not disconnected.
        return (self.coordinator.last_update_success and
                self.serial in self.coordinator.data and
                connectivity_state(self.coordinator.data[self.serial]) != "unknown")

    @property
    def is_on(self):
        connection = self.coordinator.data.get(self.serial, {}).get("connection") or {}
        return connection.get("isConnected") is True

    @property
    def extra_state_attributes(self):
        return {
            "status_source": "Carrier native GraphQL connection.isConnected",
            "carrier_reported_connection": connectivity_state(
                self.coordinator.data.get(self.serial, {})
            ),
            "local_network_reachability": "not_checked",
            "status_reliability": "unverified_for_this_thermostat_model",
            "interpretation": "Phone-app control may work even when Carrier reports disconnected",
        }


class CarrierApiReadable(CoordinatorEntity, BinarySensorEntity):
    """Carrier GraphQL polling succeeded; NOT physical device online status."""

    _attr_has_entity_name = True
    _attr_name = "Native cloud API readable"
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY

    def __init__(self, coordinator, serial):
        super().__init__(coordinator)
        self.serial = serial
        self._attr_unique_id = f"{serial}_native_cloud_api_readable"

    @property
    def device_info(self):
        system = self.coordinator.data.get(self.serial, {})
        return {"identifiers": {(DOMAIN, self.serial)},
                "manufacturer": "Carrier", "name": system.get("name") or "Carrier Smart Thermostat",
                "model": system.get("model") or "Smart Thermostat"}

    @property
    def available(self):
        return self.coordinator.last_update_success

    @property
    def is_on(self):
        return self.coordinator.last_update_success and self.serial in self.coordinator.data

    @property
    def extra_state_attributes(self):
        return {"meaning": "Carrier API returned a device record; physical connectivity unverified",
                "physical_device_online": "not_established"}
