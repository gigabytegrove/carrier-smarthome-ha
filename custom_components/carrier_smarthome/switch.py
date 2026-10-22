"""Native Carrier cloud HVAC power switch, opt-in and guarded."""
from __future__ import annotations

from homeassistant.components.switch import SwitchEntity
from homeassistant.exceptions import HomeAssistantError

from .const import (CONF_ENABLE_CONTROL, CONF_POWER_ON_MODE,
                    DEFAULT_ENABLE_CONTROL, DEFAULT_POWER_ON_MODE, DOMAIN)
from .control import async_set_mode_verified
from .entity import CarrierEntity
from .models import connectivity_state, zone_indices, zone_values


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = hass.data[DOMAIN][entry.entry_id]
    seen = set()

    def add_new_switches():
        fresh = []
        for serial, system in coordinator.data.items():
            for index in zone_indices(system):
                key = (serial, index)
                if key not in seen:
                    seen.add(key)
                    fresh.append(CarrierPowerSwitch(coordinator, entry, serial, index))
        if fresh:
            async_add_entities(fresh)

    add_new_switches()
    entry.async_on_unload(coordinator.async_add_listener(add_new_switches))


class CarrierPowerSwitch(CarrierEntity, SwitchEntity):
    """Off is explicit; On requires the user-selected Heat/Cool/Auto mode."""

    _attr_name = "HVAC power"

    def __init__(self, coordinator, entry, serial: str, index: int):
        super().__init__(coordinator, serial, index)
        self.entry = entry
        self._attr_unique_id = f"{serial}_zone_{index}_hvac_power"

    @property
    def available(self):
        return (super().available
                and connectivity_state(self.system) == "online"
                and bool(self.entry.options.get(CONF_ENABLE_CONTROL, DEFAULT_ENABLE_CONTROL)))

    @property
    def is_on(self):
        mode = zone_values(self.zone_data)["mode"]
        return mode is not None and mode != "off"

    @property
    def extra_state_attributes(self):
        return {
            "power_on_mode": self.entry.options.get(CONF_POWER_ON_MODE, DEFAULT_POWER_ON_MODE),
            "carrier_reported_connection": connectivity_state(self.system),
        }

    async def async_turn_off(self, **kwargs):
        await async_set_mode_verified(self.coordinator, self.entry.options,
                                      self.serial, self.zone, "off")

    async def async_turn_on(self, **kwargs):
        mode = self.entry.options.get(CONF_POWER_ON_MODE, DEFAULT_POWER_ON_MODE)
        if mode not in ("heat", "cool", "auto"):
            raise HomeAssistantError("Choose Heat, Cool or Auto as Turn On mode in Carrier SmartHome options")
        await async_set_mode_verified(self.coordinator, self.entry.options,
                                      self.serial, self.zone, mode)
