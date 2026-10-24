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
    """Accept the newest intent without waiting for a previous cloud readback.

    Preflight and mutations are serialized. Only read-only confirmation runs
    asynchronously. An older queued request is abandoned if superseded.
    """
    try:
        _state(coordinator, serial, index)
    except HomeAssistantError:
        coordinator.optimistic.record(None, "command_blocked",
                                      reason="device_or_cloud_unavailable")
        raise

    requested = dict(desired)
    previous = coordinator.optimistic.active(serial, index)
    force_write = False
    if previous is not None:
        pending = previous["requested"]
        # Clicking the already pending target again is not a second physical
        # request. Keep the original verification alive rather than resetting
        # the clock or issuing an identical cloud mutation.
        if _target_ok(pending, requested):
            coordinator.optimistic.record(
                previous["command_id"], "duplicate_request_ignored",
                requested=requested,
            )
            return
        # Ignore an unrelated setting which the cloud already reports as
        # selected. In particular, don't send "fan auto" just because Cool
        # is pending while the fan is already Auto.
        if (not any(key in pending for key in requested)
                and _target_ok(_state(coordinator, serial, index), requested)):
            coordinator.optimistic.record(
                previous["command_id"], "unchanged_control_ignored",
                requested=requested,
            )
            return
        # The overlay preserves all pending intent, but the actual Carrier
        # mutation MUST contain only fields changed by this new request.
        # A fan adjustment never re-sends a prior Cool/Heat mode request.
        force_write = any(key in pending for key in requested)
        desired = {**pending, **requested}
    command_id = coordinator.begin_control(serial, index, desired, requested)
    # Cancellation is limited to read-only verification. Never cancel a
    # mutation that Carrier might already be processing.
    coordinator.cancel_confirmation(serial, index)

    try:
        outcome, require_detail, require_transition = await _send_cloud_change(
            coordinator, serial, index, requested, _payload(requested),
            command_id, force_write=force_write,
        )
    except asyncio.CancelledError:
        coordinator.optimistic.finish(serial, index, command_id, "cancelled",
                                      reason="task_cancelled")
        raise
    except Exception:
        coordinator.optimistic.finish(serial, index, command_id, "reverted",
                                      reason="preflight_or_mutation_failed")
        raise

    if outcome == "already" and previous is None:
        coordinator.optimistic.finish(serial, index, command_id, "verified")
    elif outcome in ("already", "sent") and _current(
            coordinator, serial, index, command_id):
        # The HA service may now complete as soon as Carrier acknowledges
        # the write; the card remains pending while this task observes cloud.
        task = asyncio.create_task(
            _confirmation_worker(coordinator, serial, index, desired,
                                 command_id, require_detail,
                                 requested if require_transition else None),
            name="carrier_smarthome_confirm",
        )
        coordinator.track_confirmation(serial, index, task)


def _payload(desired: dict) -> dict:
    result = {}
    if "mode" in desired:
        result["mode"] = desired["mode"]
    if "fan_mode" in desired:
        result["fan"] = desired["fan_mode"]
    if "heat_setpoint" in desired or "cool_setpoint" in desired:
        if "heat_setpoint" not in desired or "cool_setpoint" not in desired:
            raise HomeAssistantError("Carrier requires both thermostat targets")
        result["heat"] = desired["heat_setpoint"]
        result["cool"] = desired["cool_setpoint"]
    return result


def _current(coordinator, serial: str, index: int, command_id: int) -> bool:
    return coordinator.optimistic.is_current(serial, index, command_id)


async def _send_cloud_change(coordinator, serial: str, index: int,
                             desired: dict, payload: dict, command_id: int,
                             *, force_write: bool) -> tuple[str, bool, bool]:
    # Serialize actual cloud mutations, NOT the 64-second verification window.
    # Rapid commands wait only for an in-flight mutation, with latest-wins
    # coalescing so obsolete queued requests never execute later.
    async with coordinator.write_lock:
        if not _current(coordinator, serial, index, command_id):
            coordinator.optimistic.record(command_id, "superseded_before_send")
            return "superseded", False, False
        _state(coordinator, serial, index)
        coordinator.optimistic.record(command_id, "preflight_started")
        try:
            await coordinator.async_refresh()
        except Exception as exc:
            coordinator.optimistic.record(command_id, "preflight_failed",
                                          reason="cloud_refresh_failed")
            raise HomeAssistantError(
                "Could not refresh Carrier status; no command sent"
            ) from exc
        if not _current(coordinator, serial, index, command_id):
            coordinator.optimistic.record(command_id, "superseded_before_send")
            return "superseded", False, False
        current = _state(coordinator, serial, index)
        coordinator.optimistic.record(
            command_id, "preflight_observed",
            observed={key: current.get(key) for key in desired},
        )
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
        require_detail_confirmation = force_write
        # A cloud view still at the target can be older than an earlier
        # in-flight write. Do not accept it as proof of a rapid reversal.
        require_transition = force_write and _target_ok(current, desired)
        # If we supersede a previous command, NEVER treat a matching stale
        # cloud reading as proof that the new reversal has been applied.
        if not force_write and _target_ok(current, desired):
            if "mode" in desired and hasattr(coordinator.client, "async_get_system_detail"):
                try:
                    detail = await coordinator.client.async_get_system_detail(serial)
                    detail_zone = (get_zone(detail, index)
                                   if detail.get("serial") == serial else None)
                except CarrierRateLimitError as exc:
                    raise HomeAssistantError(
                        "Carrier rate-limited mode verification; no command sent"
                    ) from exc
                except (CarrierError, ValueError, TypeError, AttributeError):
                    detail_zone = None
                if not _current(coordinator, serial, index, command_id):
                    coordinator.optimistic.record(command_id, "superseded_before_send")
                    return "superseded", False, False
                if detail_zone is None or _target_ok(zone_values(detail_zone), desired):
                    coordinator.optimistic.record(command_id, "already_confirmed",
                                                  source="detail_or_summary")
                    return "already", False, False
                require_detail_confirmation = True
            else:
                coordinator.optimistic.record(command_id, "already_confirmed",
                                              source="listing")
                return "already", False, False

        if not _current(coordinator, serial, index, command_id):
            coordinator.optimistic.record(command_id, "superseded_before_send")
            return "superseded", False, False
        coordinator.optimistic.record(
            command_id, "mutation_sent", requested=desired,
        )
        # Shield and drain the network operation on caller cancellation: an
        # uncertain in-flight write must finish before the lock can release.
        mutation = asyncio.create_task(
            coordinator.client.async_update_zone(serial, index, **payload)
        )
        try:
            await asyncio.shield(mutation)
        except asyncio.CancelledError:
            try:
                await mutation
            finally:
                coordinator.optimistic.record(
                    command_id, "mutation_call_cancelled",
                    reason="caller_cancelled_after_send",
                )
            raise
        except (CarrierError, ValueError) as exc:
            coordinator.optimistic.record(command_id, "mutation_not_confirmed",
                                          reason="carrier_request_error")
            raise HomeAssistantError(
                "Carrier mutation was not confirmed; check the official app "
                "before attempting another command"
            ) from exc
        coordinator.optimistic.record(command_id, "mutation_acknowledged")
        return "sent", require_detail_confirmation, require_transition


async def _confirmation_worker(coordinator, serial: str, index: int,
                               desired: dict, command_id: int,
                               require_detail: bool,
                               transition_target: dict | None) -> None:
    try:
        confirmed = await _readback(coordinator, serial, index, desired,
                                    command_id, require_detail, transition_target)
    except asyncio.CancelledError:
        coordinator.optimistic.record(command_id, "verification_cancelled",
                                      reason="new_command_or_unload")
        coordinator.optimistic.finish(serial, index, command_id, "cancelled",
                                      reason="readback_cancelled")
        raise
    except Exception:
        # Readback is inherently ambiguous after an acknowledged mutation.
        # Never repeat the write, and never log Carrier's raw exception text.
        coordinator.optimistic.record(command_id, "verification_read_failed",
                                      reason="readback_exception")
        coordinator.optimistic.finish(serial, index, command_id, "unconfirmed",
                                      reason="cloud_readback_uncertain")
    else:
        if not _current(coordinator, serial, index, command_id):
            return
        if confirmed:
            coordinator.optimistic.finish(serial, index, command_id, "verified")
        else:
            coordinator.optimistic.record(command_id, "verification_window_ended",
                                          reason="cloud_not_converged")
            coordinator.optimistic.finish(serial, index, command_id, "unconfirmed",
                                          reason="cloud_readback_uncertain")


def _observed_conflict(observed: dict, target: dict) -> bool:
    """Only a valid, reported *different* value proves a transition.

    Missing/unknown fan or mode fields must never count as seeing the
    intervening state during Cool -> Off or Fan On -> Auto.
    """
    for key, value in target.items():
        actual = observed.get(key)
        if key == "mode":
            valid = actual in MODES if isinstance(actual, str) else False
        elif key == "fan_mode":
            valid = actual in FANS if isinstance(actual, str) else False
        else:
            valid = (type(actual) in (int, float)
                     and math.isfinite(actual))
        if valid and actual != value:
            return True
    return False


def _record_observation(coordinator, command_id: int, desired: dict,
                        source: str, attempt: int, observed: dict,
                        previous_samples: dict, read_counts: dict) -> None:
    """Record meaningful changes, not 20 near-identical readback events."""
    read_counts[source] += 1
    sample = {key: observed.get(key) for key in desired}
    if previous_samples.get(source) == sample:
        read_counts["repeated"] += 1
        return
    previous_samples[source] = sample
    coordinator.optimistic.record(
        command_id, "verification_read", source=source, attempt=attempt,
        observed=sample,
    )


async def _readback(coordinator, serial: str, index: int, desired: dict,
                    command_id: int, require_detail: bool,
                    transition_target: dict | None) -> bool:
    seen_opposite = transition_target is None
    previous_samples: dict[str, dict] = {}
    read_counts = {"detail": 0, "listing": 0, "repeated": 0}
    # The first readback is immediate; all subsequent checks are read-only,
    # for at most the original ~64-second observation window.
    try:
        for attempt, delay in enumerate(READBACK_DELAYS):
            if not _current(coordinator, serial, index, command_id):
                return False
            if delay:
                await asyncio.sleep(delay)
            if not _current(coordinator, serial, index, command_id):
                return False

            if (attempt in DETAIL_CHECK_ATTEMPTS
                    and hasattr(coordinator.client, "async_get_system_detail")):
                try:
                    detail = await coordinator.client.async_get_system_detail(serial)
                    if not _current(coordinator, serial, index, command_id):
                        return False
                    if (detail.get("serial") == serial
                            and connectivity_state(detail) == "online"):
                        zone = get_zone(detail, index)
                        if zone is not None:
                            observed = zone_values(zone)
                            _record_observation(
                                coordinator, command_id, desired, "detail",
                                attempt + 1, observed, previous_samples, read_counts,
                            )
                            if transition_target and _observed_conflict(observed, transition_target):
                                seen_opposite = True
                            if _target_ok(observed, desired) and seen_opposite:
                                if coordinator.publish_verified_detail(
                                        serial, index, detail, desired):
                                    coordinator.optimistic.record(
                                        command_id, "verification_confirmed",
                                        source="detail", attempt=attempt + 1,
                                    )
                                    return True
                                coordinator.optimistic.record(
                                    command_id, "verified_detail_not_published",
                                )
                except CarrierRateLimitError:
                    coordinator.optimistic.record(command_id, "verification_rate_limited",
                                                  source="detail")
                    return False
                except (CarrierError, ValueError, TypeError, AttributeError):
                    coordinator.optimistic.record(command_id, "verification_read_failed",
                                                  source="detail", attempt=attempt + 1)

            if not _current(coordinator, serial, index, command_id):
                return False
            try:
                await coordinator.async_refresh()
                if not _current(coordinator, serial, index, command_id):
                    return False
                observed = _state(coordinator, serial, index)
                _record_observation(
                    coordinator, command_id, desired, "listing",
                    attempt + 1, observed, previous_samples, read_counts,
                )
                if transition_target and _observed_conflict(observed, transition_target):
                    seen_opposite = True
                if (_target_ok(observed, desired)
                        and seen_opposite and not require_detail):
                    coordinator.optimistic.record(
                        command_id, "verification_confirmed",
                        source="listing", attempt=attempt + 1,
                    )
                    return True
            except asyncio.CancelledError:
                raise
            except Exception:
                coordinator.optimistic.record(command_id, "verification_read_failed",
                                              source="listing", attempt=attempt + 1)
                failure = getattr(coordinator, "last_exception", None)
                if getattr(failure, "retry_after", None) is not None:
                    coordinator.optimistic.record(command_id, "verification_rate_limited",
                                                  source="listing")
                    return False
        return False
    finally:
        coordinator.optimistic.record(
            command_id, "verification_summary",
            detail_reads=read_counts["detail"],
            listing_reads=read_counts["listing"],
            repeated_reads=read_counts["repeated"],
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
