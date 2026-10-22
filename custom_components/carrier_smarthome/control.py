"""Shared guarded Carrier cloud mode control for climate and power switch.

Mode mutations have not been owner-verified yet; never blindly retry a mutation.
A fresh cloud read is mandatory before any write, and a post-write comparison
reports whether Carrier's device state has actually converged.
"""
from __future__ import annotations

import asyncio

from homeassistant.exceptions import HomeAssistantError

from .api import CarrierError
from .const import CONF_ENABLE_CONTROL, DEFAULT_ENABLE_CONTROL
from .models import connectivity_state, get_zone, zone_values

MODES = frozenset({"off", "heat", "cool", "auto", "fanonly"})


def assert_control_ready(coordinator, options: dict, serial: str, index: int) -> None:
    if not options.get(CONF_ENABLE_CONTROL, DEFAULT_ENABLE_CONTROL):
        raise HomeAssistantError("Enable experimental Carrier control in integration options first")
    if not coordinator.last_update_success:
        raise HomeAssistantError("Carrier cloud data are unavailable; no HVAC command sent")
    system = coordinator.data.get(serial, {})
    if connectivity_state(system) != "online" or get_zone(system, index) is None:
        raise HomeAssistantError("Carrier reports the thermostat disconnected; command blocked")


async def async_set_mode_verified(coordinator, options: dict, serial: str, index: int, mode: str) -> None:
    """One mode mutation, then bounded read-back. No retries of the mutation."""
    if mode not in MODES:
        raise HomeAssistantError("Unsupported Carrier HVAC mode")
    assert_control_ready(coordinator, options, serial, index)
    try:
        # Preflight refresh prevents writes using an old 'online' state.
        await coordinator.async_request_refresh()
    except Exception as exc:
        raise HomeAssistantError("Could not verify a fresh Carrier connection before the command") from exc
    assert_control_ready(coordinator, options, serial, index)
    state = zone_values(get_zone(coordinator.data[serial], index) or {})
    if state["mode"] == mode:
        return  # Idempotent, do not submit an unnecessary mutation.
    try:
        await coordinator.client.async_update_zone(serial, index, mode=mode)
    except CarrierError as exc:
        raise HomeAssistantError("Carrier rejected the HVAC mode command") from exc
    # GraphQL writes may be eventually consistent. Give the read path bounded
    # time to catch up; never resend the command automatically.
    for attempt in range(3):
        if attempt:
            await asyncio.sleep(3)
        try:
            await coordinator.async_request_refresh()
        except Exception as exc:
            raise HomeAssistantError(
                "Carrier acknowledged the command, but confirmation polling failed; check the phone app"
            ) from exc
        system = coordinator.data.get(serial, {})
        if connectivity_state(system) != "online":
            raise HomeAssistantError(
                "Carrier acknowledged the command but the thermostat went offline; verify in the phone app"
            )
        current = zone_values(get_zone(system, index) or {}).get("mode")
        if current == mode:
            return
    raise HomeAssistantError(
        "Carrier acknowledged the command but the requested mode was not confirmed; check the phone app before retrying"
    )


async def async_set_fan_verified(coordinator, options: dict, serial: str, index: int, fan: str) -> None:
    """One native fan mutation, then bounded readback; NEVER retry the write.

    Carrier hardware provides Auto, On, Circulation. The backend's Circulation
    string has not been verified so this alpha limits writes to Auto and On.
    """
    from .const import CONF_ENABLE_FAN_CONTROL, DEFAULT_ENABLE_FAN_CONTROL
    if not options.get(CONF_ENABLE_FAN_CONTROL, DEFAULT_ENABLE_FAN_CONTROL):
        raise HomeAssistantError("Enable experimental Carrier fan control in integration options first")
    if fan not in ("auto", "on"):
        raise HomeAssistantError("Unverified Carrier fan mode; only Auto and On can be tested")
    if not coordinator.last_update_success:
        raise HomeAssistantError("Carrier cloud is unavailable; no fan command sent")
    system = coordinator.data.get(serial, {})
    if connectivity_state(system) != "online" or get_zone(system, index) is None:
        raise HomeAssistantError("Carrier thermostat disconnected; no fan command sent")
    try:
        await coordinator.async_request_refresh()
    except Exception as exc:
        raise HomeAssistantError("Could not verify fresh Carrier status before fan change") from exc
    if not coordinator.last_update_success or connectivity_state(coordinator.data.get(serial, {})) != "online":
        raise HomeAssistantError("Carrier thermostat is not currently online; fan command blocked")
    actual = zone_values(get_zone(coordinator.data[serial], index) or {}).get("fan_mode")
    if actual == fan:
        return
    try:
        await coordinator.client.async_update_zone(serial, index, fan=fan)
    except (CarrierError, ValueError) as exc:
        raise HomeAssistantError("Carrier rejected experimental fan mode change") from exc
    for attempt in range(3):
        if attempt:
            await asyncio.sleep(3)
        try:
            await coordinator.async_request_refresh()
        except Exception as exc:
            raise HomeAssistantError("Carrier accepted fan write, but cloud readback failed; check the app") from exc
        system = coordinator.data.get(serial, {})
        if connectivity_state(system) != "online":
            raise HomeAssistantError("Carrier thermostat disconnected after fan change; check the app")
        observed = zone_values(get_zone(system, index) or {}).get("fan_mode")
        if observed == fan:
            return
    raise HomeAssistantError("Carrier accepted fan change, but the device did not confirm it; check the official app")


async def async_set_setpoints_verified(coordinator, options: dict, serial: str,
                                      index: int, heat: float, cool: float) -> None:
    """Send a single pair of targets after preflight and verify both on readback.

    The backend is eventually consistent; a failed confirmation does NOT mean the
    mutation was rejected. Do not retry the actual command automatically.
    """
    from .const import CONF_ENABLE_SETPOINT_CONTROL, DEFAULT_ENABLE_SETPOINT_CONTROL
    if not options.get(CONF_ENABLE_SETPOINT_CONTROL, DEFAULT_ENABLE_SETPOINT_CONTROL):
        raise HomeAssistantError("Enable experimental setpoint changes in Carrier SmartHome options first")
    assert_control_ready(coordinator, options, serial, index)
    try:
        await coordinator.async_request_refresh()
    except Exception as exc:
        raise HomeAssistantError("Carrier data could not be refreshed before changing targets") from exc
    assert_control_ready(coordinator, options, serial, index)
    zone = zone_values(get_zone(coordinator.data[serial], index) or {})
    if zone["heat_setpoint"] == heat and zone["cool_setpoint"] == cool:
        return
    try:
        await coordinator.client.async_update_zone(serial, index, heat=heat, cool=cool)
    except (CarrierError, ValueError) as exc:
        raise HomeAssistantError("Carrier rejected the heating/cooling target change") from exc
    for attempt in range(3):
        if attempt:
            await asyncio.sleep(3)
        try:
            await coordinator.async_request_refresh()
        except Exception as exc:
            raise HomeAssistantError("Carrier accepted targets but readback failed; check the official app") from exc
        system = coordinator.data.get(serial, {})
        if connectivity_state(system) != "online":
            raise HomeAssistantError("Carrier disconnected after target change; verify the official app")
        current = zone_values(get_zone(system, index) or {})
        if current["heat_setpoint"] == heat and current["cool_setpoint"] == cool:
            return
    raise HomeAssistantError("Carrier accepted targets but did not confirm both setpoints; check the official app")
