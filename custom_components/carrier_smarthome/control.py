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
# Backoff for read-only checks AFTER one acknowledged mutation. Earlier checks
# improve perceived UI latency without multiplying writes to the thermostat.
# Total 64 seconds. Carrier may rate-limit; see CarrierRateLimitError handling.
READBACK_DELAYS = (0, 2, 4, 6, 8, 8, 10, 12, 14)
READBACK_ATTEMPTS = len(READBACK_DELAYS)
# Detail is a second native read path, not an independent physical reading.
# Query it promptly, because it may lead the account listing after a write.
DETAIL_CHECK_ATTEMPTS = frozenset((0, 2, 4, 6, 8))



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
    """Show user intent now; remove it only on verified completion or failure."""
    if coordinator.write_lock.locked():
        coordinator.optimistic.record(None, "command_blocked",
                                      reason="previous_command_pending")
        raise HomeAssistantError(
            "Previous Carrier command still being verified; no new HVAC command "
            "was sent. Check the current mode before trying again"
        )
    try:
        _state(coordinator, serial, index)
    except HomeAssistantError:
        coordinator.optimistic.record(None, "command_blocked",
                                      reason="device_or_cloud_unavailable")
        raise
    command_id = coordinator.begin_control(serial, index, desired)
    try:
        await _write_verified_command(coordinator, serial, index, desired, payload,
                                      command_id)
    except asyncio.CancelledError:
        coordinator.optimistic.finish(serial, index, command_id, "cancelled",
                                       reason="task_cancelled")
        raise
    except Exception:
        # A successful mutation acknowledgment is NOT physical confirmation.
        # On ambiguous readback, revert the display to last observed Carrier
        # data and explicitly record that the cloud outcome is uncertain.
        acknowledged = any(
            event["command_id"] == command_id and
            event["stage"] == "mutation_acknowledged"
            for event in coordinator.optimistic.events
        )
        coordinator.optimistic.finish(
            serial, index, command_id,
            "unconfirmed" if acknowledged else "reverted",
            reason="cloud_readback_uncertain" if acknowledged else "not_confirmed_by_cloud",
        )
        raise
    else:
        coordinator.optimistic.finish(serial, index, command_id, "verified")


async def _write_verified_command(coordinator, serial: str, index: int,
                                  desired: dict, payload: dict,
                                  command_id: int) -> None:
    # Do NOT queue HVAC commands behind a previous command's extended
    # confirmation window. Queued Cool/Off actions can execute much later and
    # appear to randomly override the operator's most recent selection.
    # A single HA event loop acquires an uncontended asyncio lock atomically.
    if coordinator.write_lock.locked():
        raise HomeAssistantError(
            "Previous Carrier command still being verified; no new HVAC command "
            "was sent. Check the current mode before trying again"
        )
    async with coordinator.write_lock:
        _state(coordinator, serial, index)
        coordinator.optimistic.record(command_id, "preflight_started")
        try:
            await coordinator.async_refresh()
        except Exception as exc:
            coordinator.optimistic.record(command_id, "preflight_failed",
                                          reason="cloud_refresh_failed")
            raise HomeAssistantError("Could not refresh Carrier status; no command sent") from exc
        current = _state(coordinator, serial, index)
        coordinator.optimistic.record(command_id, "preflight_observed",
                                      observed={k: current.get(k) for k in desired})
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
                    coordinator.optimistic.record(command_id, "already_confirmed",
                                                  source="detail_or_summary")
                    return
                # Summary was already at target BEFORE the write; that same
                # unchanged value cannot independently confirm this command.
                # Require the detail view to converge, or report uncertainty.
                require_detail_confirmation = True
            else:
                coordinator.optimistic.record(command_id, "already_confirmed",
                                              source="listing")
                return
        coordinator.optimistic.record(command_id, "mutation_sent")
        try:
            await coordinator.client.async_update_zone(serial, index, **payload)
        except (CarrierError, ValueError) as exc:
            coordinator.optimistic.record(command_id, "mutation_not_confirmed",
                                          reason="carrier_request_error")
            raise HomeAssistantError("Carrier mutation was not confirmed; check the official app before attempting another command") from exc
        coordinator.optimistic.record(command_id, "mutation_acknowledged")
        # One write only. Carrier cloud propagation may lag tens of seconds.
        # Readbacks remain read-only; the dedicated detail query is an
        # independent cross-check of the *same serial and zone*.
        detail_confirmed = False
        last_read_error = False
        for attempt, delay in enumerate(READBACK_DELAYS):
            if delay:
                await asyncio.sleep(delay)
            # Carrier's detailed native query can converge before the listing.
            # Try it first when available. This avoids an extra blocking list
            # request on the successful path and publishes only actual values.
            if attempt in DETAIL_CHECK_ATTEMPTS and hasattr(coordinator.client, "async_get_system_detail"):
                try:
                    detail = await coordinator.client.async_get_system_detail(serial)
                    if (detail.get("serial") == serial
                            and connectivity_state(detail) == "online"):
                        detail_zone = get_zone(detail, index)
                        if detail_zone is not None:
                            observed = zone_values(detail_zone)
                            coordinator.optimistic.record(
                                command_id, "verification_read", source="detail",
                                attempt=attempt + 1,
                                observed={k: observed.get(k) for k in desired},
                            )
                            if _target_ok(observed, desired):
                                if hasattr(coordinator, "publish_verified_detail"):
                                    if not coordinator.publish_verified_detail(serial, index, detail, desired):
                                        coordinator.optimistic.record(
                                            command_id, "verified_detail_not_published")
                                        continue
                                coordinator.optimistic.record(command_id, "verification_confirmed",
                                                              source="detail", attempt=attempt + 1)
                                detail_confirmed = True
                                break
                except CarrierRateLimitError as exc:
                    coordinator.optimistic.record(command_id, "verification_rate_limited",
                                                  source="detail")
                    raise HomeAssistantError(
                        "Carrier acknowledged the command but rate-limited confirmation; "
                        "check the official app before sending another command"
                    ) from exc
                except (CarrierError, ValueError, TypeError, AttributeError):
                    # A blocked detail API does not invalidate the listing.
                    coordinator.optimistic.record(command_id, "verification_read_failed",
                                                  source="detail")
            try:
                await coordinator.async_refresh()
                latest = _state(coordinator, serial, index)
                coordinator.optimistic.record(
                    command_id, "verification_read", source="listing",
                    attempt=attempt + 1, observed={k: latest.get(k) for k in desired})
                if _target_ok(latest, desired) and not require_detail_confirmation:
                    coordinator.optimistic.record(command_id, "verification_confirmed",
                                                  source="listing", attempt=attempt + 1)
                    return
            except Exception:
                coordinator.optimistic.record(command_id, "verification_read_failed",
                                              source="listing", attempt=attempt + 1)
                # Never repeat the write or assume failure when a read fails.
                last_read_error = True
                failure = getattr(coordinator, "last_exception", None)
                if getattr(failure, "retry_after", None) is not None:
                    raise HomeAssistantError(
                        "Carrier acknowledged the command but rate-limited verification; "
                        "check the official app before sending another command"
                    ) from (failure if isinstance(failure, BaseException) else None)
        if detail_confirmed:
            # The verified detailed GraphQL view confirmed the command. When
            # supported, publish its observed fields through the coordinator;
            # routine account-list polling still reconciles independently.
            return
        coordinator.optimistic.record(command_id, "verification_window_ended",
                                      reason="cloud_not_converged")
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
