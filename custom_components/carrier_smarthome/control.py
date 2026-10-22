"""One guarded native Carrier thermostat command path.

Every requested command gets a fresh cloud preflight, one mutation at most,
and bounded readback. Never retry a write following uncertain confirmation.
"""
from __future__ import annotations

import asyncio
import math
from typing import Any

from homeassistant.exceptions import HomeAssistantError

from .api import CarrierError
from .models import connectivity_state, get_zone, zone_values

MODES = frozenset({"off", "heat", "cool", "auto", "fanonly"})
FANS = frozenset({"auto", "on"})  # 'on' unverified on physical hardware.
READBACK_ATTEMPTS = 3
READBACK_INTERVAL = 3


def _state(coordinator: Any, serial: str, index: int) -> dict:
    if not coordinator.last_update_success:
        raise HomeAssistantError("Carrier cloud unavailable; no command sent")
    system = coordinator.data.get(serial, {})
    if connectivity_state(system) != "online":
        raise HomeAssistantError("Carrier thermostat disconnected; command blocked")
    zone = get_zone(system, index)
    if zone is None:
        raise HomeAssistantError("Carrier thermostat zone not found; command blocked")
    return zone_values(zone)


def _target_ok(current: dict, desired: dict) -> bool:
    return all(current.get(key) == value for key, value in desired.items())


async def _write_verified(coordinator, serial: str, index: int,
                          desired: dict, payload: dict) -> None:
    # One per-account write lock; the same thermostat cannot receive racing
    # mode, target, and fan updates from concurrent HA service calls.
    async with coordinator.write_lock:
        _state(coordinator, serial, index)
        try:
            await coordinator.async_request_refresh()
        except Exception as exc:
            raise HomeAssistantError("Could not refresh Carrier status; no command sent") from exc
        current = _state(coordinator, serial, index)
        if "heat_setpoint" in desired:
            heat, cool = desired["heat_setpoint"], desired["cool_setpoint"]
            if (not all(isinstance(x, (int, float)) and not isinstance(x, bool)
                        and math.isfinite(x) for x in (heat, cool))
                    or not 0 <= heat <= cool <= 120):
                raise HomeAssistantError("Invalid heating/cooling setpoint pair")
            if current["heat_max"] is not None and heat > current["heat_max"]:
                raise HomeAssistantError("Heat target exceeds current Carrier limit")
            if current["cool_min"] is not None and cool < current["cool_min"]:
                raise HomeAssistantError("Cool target is below current Carrier limit")
        if _target_ok(current, desired):
            return
        try:
            await coordinator.client.async_update_zone(serial, index, **payload)
        except (CarrierError, ValueError) as exc:
            raise HomeAssistantError("Carrier did not accept thermostat command") from exc
        # Never send the same mutation again, even if response is delayed.
        for attempt in range(READBACK_ATTEMPTS):
            if attempt:
                await asyncio.sleep(READBACK_INTERVAL)
            try:
                await coordinator.async_request_refresh()
                latest = _state(coordinator, serial, index)
            except Exception as exc:
                raise HomeAssistantError(
                    "Carrier accepted command but verification failed; check official app"
                ) from exc
            if _target_ok(latest, desired):
                return
        raise HomeAssistantError(
            "Carrier accepted command but state not confirmed; check official app before retrying"
        )


async def async_set_mode_verified(coordinator, serial: str, index: int, mode: str) -> None:
    if mode not in MODES:
        raise HomeAssistantError("Unsupported Carrier HVAC mode")
    await _write_verified(coordinator, serial, index, {"mode": mode}, {"mode": mode})


async def async_set_fan_verified(coordinator, serial: str, index: int, fan: str) -> None:
    if fan not in FANS:
        raise HomeAssistantError("Only Carrier fan Auto and On are supported; Circulate is not verified")
    await _write_verified(coordinator, serial, index, {"fan_mode": fan}, {"fan": fan})


async def async_set_setpoints_verified(coordinator, serial: str,
                                      index: int, heat: float, cool: float) -> None:
    await _write_verified(coordinator, serial, index,
                          {"heat_setpoint": heat, "cool_setpoint": cool},
                          {"heat": heat, "cool": cool})
