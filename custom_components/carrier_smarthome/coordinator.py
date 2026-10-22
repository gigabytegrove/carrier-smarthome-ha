"""Shared data coordinator for Carrier SmartHome entry-tier devices."""
from __future__ import annotations

import asyncio
import logging
from copy import deepcopy

from homeassistant.config_entries import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import CarrierAuthError, CarrierError, CarrierRateLimitError, CarrierSmartHomeClient
from .const import DOMAIN, POLL_INTERVAL
from .models import connectivity_state, zone_indices, get_zone, zone_values


class CarrierCoordinator(DataUpdateCoordinator[dict[str, dict]]):
    def __init__(self, hass, client: CarrierSmartHomeClient) -> None:
        super().__init__(hass, logger=logging.getLogger(__name__),
                         name=DOMAIN, update_interval=POLL_INTERVAL)
        self.client = client
        # Serialize explicit HVAC writes so overlapping HA controls cannot race.
        self.write_lock = asyncio.Lock()
        # Remember only a mode Carrier actually reported, never guess a default.
        self._last_non_off_modes: dict[tuple[str, int], str] = {}

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
        try:
            systems = await self.client.async_get_systems()
        except CarrierAuthError as exc:
            raise ConfigEntryAuthFailed("Carrier SmartHome authentication failed") from exc
        except CarrierRateLimitError as exc:
            raise UpdateFailed("Carrier requested slower polling", retry_after=exc.retry_after) from exc
        except CarrierError as exc:
            raise UpdateFailed("Carrier SmartHome could not load devices") from exc
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
