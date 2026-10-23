"""Shared data coordinator for Carrier SmartHome entry-tier devices."""
from __future__ import annotations

import asyncio
import logging
import math
import time
from datetime import datetime, timedelta, timezone
from copy import deepcopy

from homeassistant.config_entries import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import CarrierAuthError, CarrierError, CarrierRateLimitError, CarrierSmartHomeClient
from .const import DOMAIN, POLL_INTERVAL, TRANSIENT_GRACE_SECONDS, MAX_POLL_BACKOFF_SECONDS
from .models import connectivity_state, zone_indices, get_zone, zone_values
from .optimistic import OptimisticControlTracker


class CarrierCoordinator(DataUpdateCoordinator[dict[str, dict]]):
    def __init__(self, hass, client: CarrierSmartHomeClient) -> None:
        super().__init__(hass, logger=logging.getLogger(__name__),
                         name=DOMAIN, update_interval=POLL_INTERVAL)
        self.client = client
        # Serialize explicit HVAC writes so overlapping HA controls cannot race.
        self.write_lock = asyncio.Lock()
        # Local UI intent never changes confirmed Carrier data or diagnostic sensors.
        self.optimistic = OptimisticControlTracker(self._notify_optimistic_change)
        # Remember only a mode Carrier actually reported, never guess a default.
        self._last_non_off_modes: dict[tuple[str, int], str] = {}
        # These fields contain only status/timing, never credentials or IDs.
        self.last_poll_utc: str | None = None
        self.last_error_kind: str | None = None
        self.last_error_utc: str | None = None
        self.consecutive_errors = 0
        self._last_success_monotonic: float | None = None
        self._next_poll_not_before = 0.0

    def _notify_optimistic_change(self) -> None:
        # Notify HA climate listeners immediately, before the first network await.
        notify = getattr(self, "async_update_listeners", None)
        if callable(notify):
            notify()

    def begin_control(self, serial: str, index: int, desired: dict) -> int:
        zone = get_zone(self.data.get(serial, {}), index)
        if zone is None:
            raise ValueError("Thermostat zone unavailable")
        # Export only a numbered slot, never Carrier's serial or cloud IDs.
        device_number = sorted(self.data).index(serial) + 1
        return self.optimistic.begin(serial, index, desired, zone_values(zone),
                                     device_number)

    @property
    def seconds_since_success(self) -> int | None:
        if self._last_success_monotonic is None:
            return None
        return max(0, int(time.monotonic() - self._last_success_monotonic))

    @property
    def next_poll_wait_seconds(self) -> int:
        return max(0, math.ceil(self._next_poll_not_before - time.monotonic()))

    @property
    def telemetry_usable(self) -> bool:
        """Bridge one short cloud failure, never an explicit device offline flag.

        HA may show the last online readings briefly while API recovery is in
        progress. Writes cannot use these readings: the command preflight
        always requires coordinator.last_update_success.
        """
        age = self.seconds_since_success
        return bool(self.data and
                    (self.last_update_success or
                     (age is not None and age <= TRANSIENT_GRACE_SECONDS)))

    @property
    def telemetry_in_grace(self) -> bool:
        return bool(not self.last_update_success and self.telemetry_usable)

    def _failure(self, kind: str, wait_seconds: float) -> None:
        self.last_error_kind = kind
        self.last_error_utc = datetime.now(timezone.utc).isoformat()
        self.consecutive_errors += 1
        delay = max(POLL_INTERVAL.total_seconds(), min(MAX_POLL_BACKOFF_SECONDS, wait_seconds))
        self._next_poll_not_before = max(self._next_poll_not_before, time.monotonic() + delay)
        self.update_interval = timedelta(seconds=delay)


    def last_non_off_mode(self, serial: str, index: int) -> str | None:
        return self._last_non_off_modes.get((serial, index))

    def publish_verified_detail(self, serial: str, index: int,
                                detail: dict, desired: dict) -> bool:
        """Push only *observed and validated* control values into HA promptly.

        The detailed Carrier GraphQL response can advance before the account
        listing. Never invent control values, mark a disconnected unit online,
        or replace unrelated sensors with sparse detail-query data.
        """
        if not self.last_update_success or detail.get("serial") != serial:
            return False
        if connectivity_state(detail) != "online":
            return False
        original = self.data.get(serial)
        if not isinstance(original, dict) or connectivity_state(original) != "online":
            return False
        detail_zone = get_zone(detail, index)
        original_zone = get_zone(original, index)
        if detail_zone is None or original_zone is None:
            return False
        actual = zone_values(detail_zone)
        if not desired or any(actual.get(key) != value for key, value in desired.items()):
            return False
        new_data = self.data.copy()
        replacement = original.copy()
        zones = original.get("zones")
        if not isinstance(zones, list):
            return False
        new_zones = list(zones)
        for position, zone in enumerate(new_zones):
            if not isinstance(zone, dict) or zone.get("index") != index:
                continue
            replacement_zone = deepcopy(zone)
            for key, value in desired.items():
                if key == "mode":
                    replacement_zone["mode"] = actual["mode"]
                elif key == "fan_mode":
                    replacement_zone["fan_mode"] = actual["fan_mode"]
                elif key == "heat_setpoint":
                    replacement_zone.setdefault("htsp", {})["current"] = actual[key]
                elif key == "cool_setpoint":
                    replacement_zone.setdefault("clsp", {})["current"] = actual[key]
                else:
                    return False
            new_zones[position] = replacement_zone
            replacement["zones"] = new_zones
            new_data[serial] = replacement
            mode = actual["mode"]
            if "mode" in desired and mode in {"heat", "cool", "auto", "fanonly"}:
                self._last_non_off_modes[(serial, index)] = mode
            self.async_set_updated_data(new_data)
            return True
        return False

    async def _async_update_data(self) -> dict[str, dict]:
        # Don't hit Carrier again during Retry-After / bounded transport backoff.
        if self.next_poll_wait_seconds:
            raise UpdateFailed("Carrier cloud recovery cooldown active")
        try:
            systems = await self.client.async_get_systems()
        except CarrierAuthError as exc:
            self._failure("authentication", POLL_INTERVAL.total_seconds())
            raise ConfigEntryAuthFailed("Carrier SmartHome authentication failed") from exc
        except CarrierRateLimitError as exc:
            self._failure("rate_limited", exc.retry_after)
            # Home Assistant's coordinator honors UpdateFailed.retry_after and
            # schedules the next refresh without hammering Carrier.
            raise UpdateFailed("Carrier rate-limited polling; respecting Retry-After",
                               retry_after=exc.retry_after) from exc
        except CarrierError as exc:
            retry = min(MAX_POLL_BACKOFF_SECONDS, POLL_INTERVAL.total_seconds() * (2 ** min(self.consecutive_errors, 3)))
            self._failure("transport_or_graphql", retry)
            raise UpdateFailed("Carrier SmartHome cloud request failed; will retry") from exc
        # A transient empty listing must not erase a previously discovered
        # thermostat and make all entities unavailable without explanation.
        if not systems and self.data:
            self._failure("empty_listing", POLL_INTERVAL.total_seconds())
            raise UpdateFailed("Carrier temporarily returned no thermostats; preserving last-known records")
        # Only mark data fresh when the query actually completed successfully.
        self._last_success_monotonic = time.monotonic()
        self.last_poll_utc = datetime.now(timezone.utc).isoformat()
        self.last_error_kind = None
        self.consecutive_errors = 0
        self._next_poll_not_before = 0.0
        self.update_interval = POLL_INTERVAL
        result: dict[str, dict] = {}
        for system in systems:
            serial = system.get("serial")
            if isinstance(serial, str) and serial and serial not in result:
                result[serial] = system
                if connectivity_state(system) == "online":
                    for index in zone_indices(system):
                        zone = get_zone(system, index)
                        mode = zone_values(zone)["mode"] if zone else None
                        if mode in {"heat", "cool", "auto", "fanonly"}:
                            self._last_non_off_modes[(serial, index)] = mode
        return result
