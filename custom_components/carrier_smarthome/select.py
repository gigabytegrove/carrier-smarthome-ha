"""Explicit Carrier thermostat mode and fan selectors in HA device Controls.

Mode and fan writes are off by default. The selectors remain registered, but
unavailable until their individual opt-in is enabled and Carrier reports online.
"""
from __future__ import annotations

from homeassistant.components.select import SelectEntity

from .const import (DOMAIN, CONF_ENABLE_CONTROL, DEFAULT_ENABLE_CONTROL,
                    CONF_ENABLE_FAN_CONTROL, DEFAULT_ENABLE_FAN_CONTROL)
from .control import async_set_mode_verified, async_set_fan_verified
from .entity import CarrierEntity
from .models import connectivity_state, zone_indices, zone_values

MODES = {"Off": "off", "Heat": "heat", "Cool": "cool", "Auto": "auto", "Fan Only": "fanonly"}
FANS = {"Auto": "auto", "On": "on"}

async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = hass.data[DOMAIN][entry.entry_id]
    seen = set()

    def add_new():
        fresh = []
        for serial, system in coordinator.data.items():
            for index in zone_indices(system):
                for kind in ("mode", "fan"):
                    key = (serial, index, kind)
                    if key not in seen:
                        seen.add(key)
                        fresh.append(CarrierControlSelect(coordinator, entry, serial, index, kind))
        if fresh:
            async_add_entities(fresh)

    add_new()
    entry.async_on_unload(coordinator.async_add_listener(add_new))


class CarrierControlSelect(CarrierEntity, SelectEntity):
    """One device page selector for mode; another for Auto/On fan commands."""

    def __init__(self, coordinator, entry, serial, zone, kind):
        super().__init__(coordinator, serial, zone)
        self.entry = entry
        self.kind = kind
        self._attr_name = "HVAC mode" if kind == "mode" else "Fan setting"
        self._attr_unique_id = f"{serial}_zone_{zone}_{kind}_control"
        self._attr_options = list((MODES if kind == "mode" else FANS).keys())

    @property
    def available(self):
        enabled = (self.entry.options.get(CONF_ENABLE_CONTROL, DEFAULT_ENABLE_CONTROL)
                   if self.kind == "mode" else
                   self.entry.options.get(CONF_ENABLE_FAN_CONTROL, DEFAULT_ENABLE_FAN_CONTROL))
        return bool(super().available and connectivity_state(self.system) == "online" and enabled)

    @property
    def current_option(self):
        state = zone_values(self.zone_data)
        current = state["mode"] if self.kind == "mode" else state["fan_mode"]
        mapping = MODES if self.kind == "mode" else FANS
        return next((label for label, value in mapping.items() if current == value), None)

    async def async_select_option(self, option: str):
        mapping = MODES if self.kind == "mode" else FANS
        if option not in mapping:
            raise ValueError("Unsupported Carrier control choice")
        if self.kind == "mode":
            await async_set_mode_verified(self.coordinator, self.entry.options,
                                          self.serial, self.zone, mapping[option])
        else:
            await async_set_fan_verified(self.coordinator, self.entry.options,
                                         self.serial, self.zone, mapping[option])
