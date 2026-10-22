"""Single guarded Carrier entry-level thermostat command path.

Every command is preflighted against a new cloud poll, submitted EXACTLY once,
and read back with bounded retries. Failed readback never triggers a second write.
Writes are opt-in and the mutation remains unverified on physical hardware.
"""
from __future__ import annotations

import asyncio
import math
from typing import Any

from homeassistant.exceptions import HomeAssistantError

from .api import CarrierError
from .const import (
    CONF_ENABLE_CONTROL, DEFAULT_ENABLE_CONTROL,
    CONF_ENABLE_FAN_CONTROL, DEFAULT_ENABLE_FAN_CONTROL,
    CONF_ENABLE_SETPOINT_CONTROL, DEFAULT_ENABLE_SETPOINT_CONTROL,
)
from .models import connectivity_state, get_zone, zone_values

MODES = frozenset({"off", "heat", "cool", "auto", "fanonly"})
FANS = frozenset({"auto", "on"})  # On unverified; Circulate enum is unknown.
READBACK_ATTEMPTS = 3
READBACK_INTERVAL = 3


def _state(coordinator: Any, serial: str, index: int) -> dict:
    if not coordinator.last_update_success:
        raise HomeAssistantError("Carrier cloud data unavailable; no command sent")
    system = coordinator.data.get(serial, {})
    if connectivity_state(system) != "online":
        raise HomeAssistantError("Carrier thermostat disconnected; command blocked")
    zone = get_zone(system, index)
    if zone is None:
        raise HomeAssistantError("Carrier thermostat zone not found; command blocked")
    return zone_values(zone)


def _enabled(options: dict, kind: str) -> None:
    name, default = {
        "mode": (CONF_ENABLE_CONTROL, DEFAULT_ENABLE_CONTROL),
        "fan": (CONF_ENABLE_FAN_CONTROL, DEFAULT_ENABLE_FAN_CONTROL),
        "setpoints": (CONF_ENABLE_SETPOINT_CONTROL, DEFAULT_ENABLE_SETPOINT_CONTROL),
    }[kind]
    if not options.get(name, default):
        raise HomeAssistantError(f"Enable experimental Carrier {kind} control in integration options first")


def _target_ok(kind: str, current: dict, desired: dict) -> bool:
    return all(current.get(key) == value for key, value in desired.items())


async def _write_verified(coordinator, options: dict, serial: str, index: int,
                          kind: str, desired: dict, payload: dict) -> None:
    _enabled(options, kind)
    # This lock is scoped to the HA config entry and shared across climate and
    # switch entities; no overlapping writes to one thermostat/account.
    async with coordinator.write_lock:
        _state(coordinator, serial, index)
        try:
            await coordinator.async_request_refresh()
        except Exception as exc:
            raise HomeAssistantError("Unable to refresh Carrier status before sending command") from exc
        current = _state(coordinator, serial, index)
        if kind == "setpoints":
            heat, cool = desired["heat_setpoint"], desired["cool_setpoint"]
            if (not all(isinstance(x, (int, float)) and not isinstance(x, bool)
                        and math.isfinite(x) for x in (heat, cool))
                    or not 0 <= heat <= cool <= 120):
                raise HomeAssistantError("Invalid heating/cooling setpoint pair")
            if current["heat_max"] is not None and heat > current["heat_max"]:
                raise HomeAssistantError("Heat target exceeds current Carrier limit")
            if current["cool_min"] is not None and cool < current["cool_min"]:
                raise HomeAssistantError("Cool target is below current Carrier limit")
        if _target_ok(kind, current, desired):
            return  # Idempotent. Never write an unchanged state.
        try:
            await coordinator.client.async_update_zone(serial, index, **payload)
        except (CarrierError, ValueError) as exc:
            raise HomeAssistantError("Carrier did not accept the thermostat command") from exc
        for attempt in range(READBACK_ATTEMPTS):
            if attempt:
                await asyncio.sleep(READBACK_INTERVAL)
            try:
                await coordinator.async_request_refresh()
                latest = _state(coordinator, serial, index)
            except Exception as exc:
                raise HomeAssistantError(
                    "Carrier acknowledged command but status confirmation failed; check official app"
                ) from exc
            if _target_ok(kind, latest, desired):
                return
        raise HomeAssistantError(
            "Carrier acknowledged command but state not confirmed; verify in the official app before retrying"
        )


async def async_set_mode_verified(coordinator, options: dict, serial: str, index: int, mode: str) -> None:
    if mode not in MODES:
        raise HomeAssistantError("Unsupported Carrier HVAC mode")
    await _write_verified(coordinator, options, serial, index, "mode",
                          {"mode": mode}, {"mode": mode})


async def async_set_fan_verified(coordinator, options: dict, serial: str, index: int, fan: str) -> None:
    if fan not in FANS:
        raise HomeAssistantError("Unverified Carrier fan mode: only Auto and On are available for testing")
    await _write_verified(coordinator, options, serial, index, "fan",
                          {"fan_mode": fan}, {"fan": fan})


async def async_set_setpoints_verified(coordinator, options: dict, serial: str,
                                      index: int, heat: float, cool: float) -> None:
    _enabled(options, "mode")  # Setpoints also require master control opt-in.
    await _write_verified(coordinator, options, serial, index, "setpoints",
                          {"heat_setpoint": heat, "cool_setpoint": cool},
                          {"heat": heat, "cool": cool})
