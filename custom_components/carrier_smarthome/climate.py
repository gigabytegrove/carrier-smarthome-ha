"""Carrier SmartHome climate devices; writes are opt-in experimental."""
from __future__ import annotations

from homeassistant.components.climate import ClimateEntity, ClimateEntityFeature, HVACMode
from homeassistant.exceptions import HomeAssistantError

from .api import CarrierError
from .const import CONF_ENABLE_CONTROL, DEFAULT_ENABLE_CONTROL, DOMAIN
from .entity import CarrierEntity
from .models import temperature_unit, zone_indices, zone_values

_TO_HA = {
    "off": HVACMode.OFF, "heat": HVACMode.HEAT,
    "cool": HVACMode.COOL, "auto": HVACMode.HEAT_COOL,
    "fanonly": HVACMode.FAN_ONLY,
}
_FROM_HA = {value: key for key, value in _TO_HA.items()}


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = hass.data[DOMAIN][entry.entry_id]
    devices = []
    for serial, system in coordinator.data.items():
        for index in zone_indices(system):
            devices.append(CarrierClimate(coordinator, entry, serial, index))
    async_add_entities(devices)
    # Carrier can add a thermostat to the account after integration setup.
    # Existing entities are stable; only newly discovered zones are added.
    seen = {(item.serial, item.zone) for item in devices}

    def add_new_zones():
        fresh = []
        for serial, system in coordinator.data.items():
            for index in zone_indices(system):
                key = (serial, index)
                if key not in seen:
                    seen.add(key)
                    fresh.append(CarrierClimate(coordinator, entry, serial, index))
        if fresh:
            async_add_entities(fresh)

    entry.async_on_unload(coordinator.async_add_listener(add_new_zones))


class CarrierClimate(CarrierEntity, ClimateEntity):
    """Native Carrier Smart Thermostat climate entity."""

    _attr_name = None

    def __init__(self, coordinator, entry, serial, zone):
        super().__init__(coordinator, serial, zone)
        self.entry = entry
        self._attr_unique_id = f"{serial}_zone_{zone}_climate"

    @property
    def hvac_modes(self):
        # Do not offer mode-change controls before explicit opt-in.
        if not self.entry.options.get(CONF_ENABLE_CONTROL, DEFAULT_ENABLE_CONTROL):
            return [self.hvac_mode] if self.hvac_mode else [HVACMode.OFF]
        return [HVACMode.OFF, HVACMode.HEAT, HVACMode.COOL, HVACMode.HEAT_COOL]

    @property
    def _state(self):
        return zone_values(self.zone_data)

    @property
    def temperature_unit(self):
        return temperature_unit(self.system.get("temp_unit_format")) or self.hass.config.units.temperature_unit

    @property
    def current_temperature(self):
        return self._state["temperature"]

    @property
    def current_humidity(self):
        return self._state["humidity"]

    @property
    def hvac_mode(self):
        raw = self._state["mode"]
        return _TO_HA.get(raw.lower()) if isinstance(raw, str) else None

    @property
    def supported_features(self):
        if not self.entry.options.get(CONF_ENABLE_CONTROL, DEFAULT_ENABLE_CONTROL):
            return ClimateEntityFeature(0)
        state = self._state
        if state["heat_setpoint"] is None or state["cool_setpoint"] is None:
            return ClimateEntityFeature(0)
        if self.hvac_mode == HVACMode.HEAT_COOL:
            return ClimateEntityFeature.TARGET_TEMPERATURE_RANGE
        if self.hvac_mode in (HVACMode.HEAT, HVACMode.COOL):
            return ClimateEntityFeature.TARGET_TEMPERATURE
        return ClimateEntityFeature(0)

    @property
    def target_temperature(self):
        mode = self.hvac_mode
        if mode == HVACMode.HEAT:
            return self._state["heat_setpoint"]
        if mode == HVACMode.COOL:
            return self._state["cool_setpoint"]
        return None

    @property
    def target_temperature_low(self):
        return self._state["heat_setpoint"] if self.hvac_mode == HVACMode.HEAT_COOL else None

    @property
    def target_temperature_high(self):
        return self._state["cool_setpoint"] if self.hvac_mode == HVACMode.HEAT_COOL else None

    @property
    def extra_state_attributes(self):
        data = self._state
        # No account or network identifiers in attributes.
        return {"schedule_enabled": data["schedule_enabled"],
                "fan_mode_reported": data["fan_mode"],
                "stage_status": data["stage_status"],
                "experimental_control_enabled": bool(self.entry.options.get(CONF_ENABLE_CONTROL, False))}

    def _require_control(self):
        if not self.entry.options.get(CONF_ENABLE_CONTROL, DEFAULT_ENABLE_CONTROL):
            raise HomeAssistantError("Enable experimental control in Carrier SmartHome options first")
        if not self.available:
            raise HomeAssistantError("Carrier thermostat is unavailable")

    async def async_set_hvac_mode(self, hvac_mode):
        self._require_control()
        if hvac_mode not in _FROM_HA or hvac_mode not in self.hvac_modes:
            raise HomeAssistantError("Unsupported thermostat mode")
        try:
            await self.coordinator.client.async_update_zone(self.serial, self.zone,
                                                             mode=_FROM_HA[hvac_mode])
            await self.coordinator.async_request_refresh()
        except CarrierError as exc:
            raise HomeAssistantError("Carrier rejected the HVAC mode change") from exc

    async def async_set_temperature(self, **kwargs):
        self._require_control()
        state = self._state
        heat, cool = state["heat_setpoint"], state["cool_setpoint"]
        if heat is None or cool is None:
            raise HomeAssistantError("Carrier has not reported both setpoints")
        if self.hvac_mode == HVACMode.HEAT_COOL:
            if "target_temp_low" not in kwargs or "target_temp_high" not in kwargs:
                raise HomeAssistantError("Automatic mode requires both heating and cooling targets")
            heat, cool = kwargs["target_temp_low"], kwargs["target_temp_high"]
        elif self.hvac_mode == HVACMode.HEAT:
            if "temperature" not in kwargs:
                raise HomeAssistantError("Heating target is required")
            heat = kwargs["temperature"]
        elif self.hvac_mode == HVACMode.COOL:
            if "temperature" not in kwargs:
                raise HomeAssistantError("Cooling target is required")
            cool = kwargs["temperature"]
        else:
            raise HomeAssistantError("Change to Heat, Cool or Heat/Cool before setting a target")
        if state["heat_max"] is not None and heat > state["heat_max"]:
            raise HomeAssistantError("Heating target exceeds Carrier's reported maximum")
        if state["cool_min"] is not None and cool < state["cool_min"]:
            raise HomeAssistantError("Cooling target is below Carrier's reported minimum")
        try:
            await self.coordinator.client.async_update_zone(self.serial, self.zone,
                                                             heat=heat, cool=cool)
            await self.coordinator.async_request_refresh()
        except (CarrierError, ValueError) as exc:
            raise HomeAssistantError("Carrier rejected the temperature change") from exc
