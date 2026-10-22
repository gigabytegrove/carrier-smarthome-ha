"""Shared device identity and data access for Carrier entities."""
from __future__ import annotations

from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .models import get_zone


class CarrierEntity(CoordinatorEntity):
    _attr_has_entity_name = True

    def __init__(self, coordinator, serial: str, zone: int):
        super().__init__(coordinator)
        self.serial = serial
        self.zone = zone

    @property
    def system(self) -> dict:
        return self.coordinator.data.get(self.serial, {})

    @property
    def zone_data(self) -> dict:
        return get_zone(self.system, self.zone) or {}

    @property
    def device_info(self) -> dict:
        system = self.system
        result = {
            "identifiers": {("carrier_smarthome", self.serial)},
            "name": system.get("name") or "Carrier Smart Thermostat",
            "manufacturer": "Carrier",
            "model": system.get("model") or "Smart Thermostat",
        }
        if firmware := system.get("firmware"):
            result["sw_version"] = str(firmware)
        return result

    @property
    def available(self) -> bool:
        # Base availability means GraphQL returned this record. Live climate
        # and sensor entities ALSO check for Carrier-reported online status;
        # explicitly labeled last-reported diagnostics use this base value.
        return bool(self.coordinator.last_update_success and
                    self.serial in self.coordinator.data and self.zone_data)
