"""Carrier SmartHome native GraphQL alpha for Home Assistant."""
from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import CarrierSmartHomeClient
from .const import DOMAIN, PLATFORMS
from .coordinator import CarrierCoordinator


async def async_setup_entry(hass, entry: ConfigEntry) -> bool:
    client = CarrierSmartHomeClient(async_get_clientsession(hass),
                                    entry.data[CONF_USERNAME], entry.data[CONF_PASSWORD])
    coordinator = CarrierCoordinator(hass, client)
    await coordinator.async_config_entry_first_refresh()
    if not coordinator.data:
        raise ConfigEntryNotReady("Carrier did not report any entry-level thermostats")
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(async_update_options))
    return True


async def async_update_options(hass, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass, entry: ConfigEntry) -> bool:
    ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return ok
