"""Standard Home Assistant climate control for Carrier SmartHome.

No configuration switch is required to see or operate HVAC modes. The climate
entity owns Off / Heat / Cool / Auto / Fan Only, fan Auto / On, and setpoints.
No parallel power switch or redundant select entity exists.
"""
from __future__ import annotations

from homeassistant.components.climate import ClimateEntity, ClimateEntityFeature, HVACMode
from homeassistant.exceptions import HomeAssistantError

from .const import DOMAIN
from .control import async_set_mode_verified, async_set_fan_verified, async_set_setpoints_verified
from .entity import CarrierEntity
from .models import connectivity_state, temperature_unit, zone_indices, zone_values
from .matter_protocol import CLOUD_ONLY, MATTER_ONLY, MatterNotReady, MatterWriteUncertain
from .matter_runtime import degrees_from_c, degrees_to_c

_TO_HA = {
    "off": HVACMode.OFF, "heat": HVACMode.HEAT,
    "cool": HVACMode.COOL, "auto": HVACMode.HEAT_COOL,
    "fanonly": HVACMode.FAN_ONLY,
}
_FROM_HA = {value: key for key, value in _TO_HA.items()}
_HVAC_MODES = [HVACMode.OFF, HVACMode.HEAT, HVACMode.COOL,
               HVACMode.HEAT_COOL, HVACMode.FAN_ONLY]
_FAN_MODES = ["auto", "on"]  # Circulation API value is unverified.


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = hass.data[DOMAIN][entry.entry_id]
    seen: set[tuple[str, int]] = set()

    def add_new_zones():
        fresh = []
        for serial, system in coordinator.data.items():
            for index in zone_indices(system):
                key = (serial, index)
                if key not in seen:
                    seen.add(key)
                    fresh.append(CarrierClimate(coordinator, serial, index))
        if fresh:
            async_add_entities(fresh)

    add_new_zones()
    entry.async_on_unload(coordinator.async_add_listener(add_new_zones))


class CarrierClimate(CarrierEntity, ClimateEntity):
    """One UI entity for all HVAC controls, with cloud preflight/readback."""

    _attr_name = None

    def __init__(self, coordinator, serial, zone):
        super().__init__(coordinator, serial, zone)
        # Keep existing unique ID so HACS updates do not duplicate climate.
        self._attr_unique_id = f"{serial}_zone_{zone}_climate"

    @property
    def _matter(self):
        return getattr(self.coordinator, "matter", None)

    @property
    def _policy(self):
        return self._matter.policy(self.serial, self.zone) if self._matter else CLOUD_ONLY

    @property
    def _local(self):
        return self._matter.state(self.serial, self.zone) if self._matter else None

    @property
    def available(self):
        if self._policy != CLOUD_ONLY:
            if self._local is not None:
                return True
            if self._policy == MATTER_ONLY:
                return False
        return super().available and connectivity_state(self.system) == "online"

    @property
    def _state(self):
        values = zone_values(self.zone_data)
        local = self._local if self._policy != CLOUD_ONLY else None
        if local is not None:
            unit = self.temperature_unit
            values.update({
                "mode": local.mode,
                "temperature": degrees_from_c(local.temperature_c, unit),
                "heat_setpoint": degrees_from_c(local.heat_target_c, unit),
                "cool_setpoint": degrees_from_c(local.cool_target_c, unit),
                "heat_max": degrees_from_c(local.max_heat_c, unit),
                "cool_min": degrees_from_c(local.min_cool_c, unit),
            })
        return values

    async def _execute(self, cloud_write, matter_write):
        if self._matter is None or self._policy == CLOUD_ONLY:
            await cloud_write()
            return
        try:
            await self._matter.execute(self.serial, self.zone,
                                       cloud_write, matter_write)
        except (MatterNotReady, MatterWriteUncertain) as exc:
            raise HomeAssistantError(str(exc)) from exc

    @property
    def hvac_modes(self):
        # Independent fan-only mode has not yet been verified over Matter.
        if self._policy == MATTER_ONLY:
            return [mode for mode in _HVAC_MODES if mode != HVACMode.FAN_ONLY]
        return _HVAC_MODES

    @property
    def hvac_mode(self):
        mode = self._state["mode"]
        return _TO_HA.get(mode)

    @property
    def supported_features(self):
        features = ClimateEntityFeature.TURN_OFF
        if self._policy != MATTER_ONLY:
            features |= ClimateEntityFeature.FAN_MODE
        # A power-on service needs an established previous mode. We never
        # silently choose Heat or Cool when one cannot be established.
        if self.coordinator.last_non_off_mode(self.serial, self.zone) is not None:
            features |= ClimateEntityFeature.TURN_ON
        if (self._state["heat_setpoint"] is not None
                and self._state["cool_setpoint"] is not None):
            if self.hvac_mode == HVACMode.HEAT_COOL:
                features |= ClimateEntityFeature.TARGET_TEMPERATURE_RANGE
            elif self.hvac_mode in (HVACMode.HEAT, HVACMode.COOL):
                features |= ClimateEntityFeature.TARGET_TEMPERATURE
        return features

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
    def fan_mode(self):
        return self._state["fan_mode"]

    @property
    def fan_modes(self):
        return [] if self._policy == MATTER_ONLY else _FAN_MODES

    @property
    def target_temperature(self):
        if self.hvac_mode == HVACMode.HEAT:
            return self._state["heat_setpoint"]
        if self.hvac_mode == HVACMode.COOL:
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
        state = self._state
        return {
            "schedule_enabled": state["schedule_enabled"],
            "stage_status": state["stage_status"],
            "carrier_reported_connection": connectivity_state(self.system),
            "control_transport": (
                "local_matter" if self._policy != CLOUD_ONLY and self._local is not None
                else "carrier_native_cloud_graphql"
            ),
            "transport_policy": self._policy,
            "telemetry_freshness": (
                "local_matter_poll_within_45_seconds"
                if self._policy != CLOUD_ONLY and self._local is not None
                else "brief_cloud_recovery_grace_may_be_stale"
                if getattr(self.coordinator, "telemetry_in_grace", False)
                else "carrier_online_without_device_sample_timestamp"
            ),
        }

    def _require_online(self):
        if not self.available:
            raise HomeAssistantError("Carrier thermostat disconnected or cloud unavailable; no command sent")

    async def async_set_hvac_mode(self, hvac_mode):
        self._require_online()
        if hvac_mode not in _FROM_HA:
            raise HomeAssistantError("Unsupported thermostat mode")
        mode = _FROM_HA[hvac_mode]
        await self._execute(
            lambda: async_set_mode_verified(self.coordinator, self.serial, self.zone, mode),
            lambda client: client.write(mode=mode),
        )

    async def async_turn_off(self):
        await self.async_set_hvac_mode(HVACMode.OFF)

    async def async_turn_on(self):
        self._require_online()
        previous = self.coordinator.last_non_off_mode(self.serial, self.zone)
        if previous not in ("heat", "cool", "auto", "fanonly"):
            raise HomeAssistantError("Choose Heat, Cool, Auto or Fan Only in the mode selector first")
        await self._execute(
            lambda: async_set_mode_verified(self.coordinator, self.serial, self.zone, previous),
            lambda client: client.write(mode=previous),
        )

    async def async_set_fan_mode(self, fan_mode):
        self._require_online()
        if self._policy == MATTER_ONLY:
            raise HomeAssistantError("Independent fan mode is not verified via Matter; no command sent")
        # Prefer Matter falls back to cloud for fan control: the thermostat
        # cluster does not prove that an independent FanControl command exists.
        await async_set_fan_verified(self.coordinator, self.serial, self.zone, fan_mode)

    async def async_set_temperature(self, **kwargs):
        self._require_online()
        state = self._state
        heat, cool = state["heat_setpoint"], state["cool_setpoint"]
        if heat is None or cool is None:
            raise HomeAssistantError("Carrier has not reported both setpoints")
        if self.hvac_mode == HVACMode.HEAT_COOL:
            if "target_temp_low" not in kwargs or "target_temp_high" not in kwargs:
                raise HomeAssistantError("Automatic mode requires both heat and cool targets")
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
            raise HomeAssistantError("Select Heat, Cool or Auto before setting temperature")
        async def local_setpoint(client):
            if not isinstance(heat, (int, float)) or not isinstance(cool, (int, float)):
                raise MatterNotReady("Setpoint values must be numeric")
            if isinstance(heat, bool) or isinstance(cool, bool):
                raise MatterNotReady("Boolean temperature rejected")
            old_heat, old_cool = state["heat_setpoint"], state["cool_setpoint"]
            # A single Matter write is atomic; do not partially apply both
            # targets or pretend that two separate writes are transactional.
            changed = []
            if abs(heat - old_heat) >= 0.01:
                changed.append(("heat", heat))
            if abs(cool - old_cool) >= 0.01:
                changed.append(("cool", cool))
            if len(changed) > 1:
                raise MatterNotReady(
                    "Two simultaneous Matter targets are not yet verified; "
                    "change one setpoint at a time"
                )
            if not changed:
                return {"confirmed": True}
            kind, value = changed[0]
            return await client.write(setpoint_kind=kind,
                                      setpoint_c=degrees_to_c(value, self.temperature_unit))

        await self._execute(
            lambda: async_set_setpoints_verified(
                self.coordinator, self.serial, self.zone, heat, cool),
            local_setpoint,
        )
