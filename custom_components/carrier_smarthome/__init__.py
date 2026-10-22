"""Carrier SmartHome native GraphQL integration for Home Assistant."""
from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import CarrierSmartHomeClient
from .const import DOMAIN, PLATFORMS
from .coordinator import CarrierCoordinator
from homeassistant.helpers import entity_registry as er


async def async_setup_entry(hass, entry: ConfigEntry) -> bool:
    client = CarrierSmartHomeClient(async_get_clientsession(hass),
                                    entry.data[CONF_USERNAME], entry.data[CONF_PASSWORD])
    coordinator = CarrierCoordinator(hass, client)
    await coordinator.async_config_entry_first_refresh()
    if not coordinator.data:
        raise ConfigEntryNotReady("Carrier did not report any entry-level thermostats")
    # Retire ONLY the obsolete entities owned by this integration. Keep the
    # existing IDs/history of all supported sensors and the climate entity.
    # A Carrier-provided comfort scene or equipment stage was not established
    # for this thermostat; these old diagnostics showed Unavailable indefinitely.
    registry = er.async_get(hass)
    for old in er.async_entries_for_config_entry(registry, entry.entry_id):
        if old.platform != DOMAIN:
            continue
        obsolete_switch = (old.domain == "switch" and
                           old.unique_id.endswith("_hvac_power"))
        unsupported_sensor = (old.domain == "sensor" and
                              old.unique_id.endswith((
                                  "_last_cloud_reported_stage_status",
                                  "_last_cloud_reported_current_scene")))
        if obsolete_switch or unsupported_sensor:
            registry.async_remove(old.entity_id)
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_migrate_entry(hass, entry: ConfigEntry) -> bool:
    """Delete pre-Alpha-10 control gates; never break stored credentials."""
    if entry.version > 2:
        return False
    hass.config_entries.async_update_entry(entry, version=2, options={})
    return True


async def async_unload_entry(hass, entry: ConfigEntry) -> bool:
    ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return ok
