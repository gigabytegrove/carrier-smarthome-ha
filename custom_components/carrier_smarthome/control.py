"""One guarded native Carrier thermostat command path.

Every requested command gets a fresh cloud preflight, one mutation at most,
and bounded readback. Never retry a write following uncertain confirmation.
"""
from __future__ import annotations

import asyncio
import math
from typing import Any

from homeassistant.exceptions import HomeAssistantError

from .api import CarrierError, CarrierRateLimitError
from .models import connectivity_state, get_zone, zone_values

MODES = frozenset({"off", "heat", "cool", "auto", "fanonly"})
FANS = frozenset({"auto", "on"})  # 'on' unverified on physical hardware.
READBACK_ATTEMPTS = 9
READBACK_INTERVAL = 8
# Carrier app-to-cloud changes previously took up to the second 20-second
# observation; HA's normal async_request_refresh() is DEBOUNCED (10s cooldown).
# Always use async_refresh() for *actual* fresh reads in the write path.
# After one mutation, check for up to 64 seconds; NEVER repeat the mutation.



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
            await coordinator.async_refresh()
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
        require_detail_confirmation = False
        if _target_ok(current, desired):
            # A matching summary can be stale even after a fresh HTTP read.
            # For mode changes, inspect the independent detail GraphQL view
            # before claiming an already-applied command. If it disagrees,
            # the explicit requested mode still receives exactly one write.
            if "mode" in desired and hasattr(coordinator.client, "async_get_system_detail"):
                try:
                    detail = await coordinator.client.async_get_system_detail(serial)
                    detail_zone = get_zone(detail, index) if detail.get("serial") == serial else None
                except CarrierRateLimitError as exc:
                    raise HomeAssistantError(
                        "Carrier rate-limited mode verification; no command sent"
                    ) from exc
                except (CarrierError, ValueError, TypeError, AttributeError):
                    detail_zone = None
                if (detail_zone is None or
                        _target_ok(zone_values(detail_zone), desired)):
                    return
                # Summary was already at target BEFORE the write; that same
                # unchanged value cannot independently confirm this command.
                # Require the detail view to converge, or report uncertainty.
                require_detail_confirmation = True
            else:
                return
        try:
            await coordinator.client.async_update_zone(serial, index, **payload)
        except (CarrierError, ValueError) as exc:
            raise HomeAssistantError("Carrier mutation was not confirmed; check the official app before attempting another command") from exc
        # One write only. Carrier cloud propagation may lag tens of seconds.
        # Readbacks remain read-only; the dedicated detail query is an
        # independent cross-check of the *same serial and zone*.
        detail_confirmed = False
        last_read_error = False
        for attempt in range(READBACK_ATTEMPTS):
            if attempt:
                await asyncio.sleep(READBACK_INTERVAL)
            try:
                await coordinator.async_refresh()
                latest = _state(coordinator, serial, index)
                if _target_ok(latest, desired) and not require_detail_confirmation:
                    return
            except Exception:
                # A transient failed read must not trigger another write or
                # prematurely erase the possibility the first write succeeded.
                last_read_error = True
                # Carrier may impose a rate-limit; do not keep probing after it.
                failure = getattr(coordinator, "last_exception", None)
                if getattr(failure, "retry_after", None) is not None:
                    raise HomeAssistantError(
                        "Carrier acknowledged the command but rate-limited verification; "
                        "check the official app before sending another command"
                    ) from (failure if isinstance(failure, BaseException) else None)
            # Consult the independent APK-derived detail view after the
            # initial short wait. Never accept a mismatched serial or zone.
            if attempt in (2, 4, 6, 8) and hasattr(coordinator.client, "async_get_system_detail"):
                try:
                    detail = await coordinator.client.async_get_system_detail(serial)
                    if (detail.get("serial") == serial
                            and connectivity_state(detail) == "online"):
                        detail_zone = get_zone(detail, index)
                        if detail_zone is not None and _target_ok(zone_values(detail_zone), desired):
                            detail_confirmed = True
                            break
                except CarrierRateLimitError as exc:
                    raise HomeAssistantError(
                        "Carrier acknowledged the command but rate-limited confirmation; "
                        "check the official app before sending another command"
                    ) from exc
                except (CarrierError, ValueError, TypeError, AttributeError):
                    # Some accounts reject the detail query. The account list
                    # remains authoritative if it becomes current later.
                    pass
        if detail_confirmed:
            # The detailed GraphQL query confirmed the actual requested state;
            # HA's regular coordinator polling will reconcile its summary.
            # Do not synthesize a state or issue another mutation.
            return
        if last_read_error:
            raise HomeAssistantError(
                "Carrier acknowledged the command, but cloud verification is incomplete; "
                "check actual mode in the official app before sending another command"
            )
        raise HomeAssistantError(
            "Carrier acknowledged the command; the requested state was not confirmed "
            "within the 64-second cloud observation window. The command may have worked. "
            "Check the official app before sending another command"
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
