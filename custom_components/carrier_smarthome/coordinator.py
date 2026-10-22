"""Shared data coordinator for Carrier SmartHome entry-tier devices."""
from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import CarrierAuthError, CarrierError, CarrierSmartHomeClient
from .const import DOMAIN, POLL_INTERVAL


class CarrierCoordinator(DataUpdateCoordinator[dict[str, dict]]):
    def __init__(self, hass, client: CarrierSmartHomeClient) -> None:
        super().__init__(hass, logger=logging.getLogger(__name__),
                         name=DOMAIN, update_interval=POLL_INTERVAL)
        self.client = client

    async def _async_update_data(self) -> dict[str, dict]:
        try:
            systems = await self.client.async_get_systems()
        except CarrierAuthError as exc:
            raise ConfigEntryAuthFailed("Carrier SmartHome authentication failed") from exc
        except CarrierError as exc:
            raise UpdateFailed("Carrier SmartHome could not load devices") from exc
        result: dict[str, dict] = {}
        for system in systems:
            serial = system.get("serial")
            if isinstance(serial, str) and serial and serial not in result:
                result[serial] = system
        return result
