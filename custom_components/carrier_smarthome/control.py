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

MODES = frozenset({"off", "heat", "cool", "auto"})


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
