"""Privacy-minimized diagnostics for the native Carrier SmartHome alpha.

No account email, passwords, tokens, serials, MAC addresses or cloud device IDs.
Thermostat readings are last *reported* values and can be stale when offline.
"""
from __future__ import annotations

from .const import DOMAIN
from .models import sanitize_device_summary, sanitize_telemetry


def build_diagnostics(coordinator) -> dict:
    """Build a JSON-safe, identifier-free snapshot for support investigation."""
    systems = list(coordinator.data.values()) if isinstance(coordinator.data, dict) else []
    return {
        "transport": "carrier_native_cloud_graphql",
        "matter_enabled": False,
        "last_poll_succeeded": bool(coordinator.last_update_success),
        "telemetry_may_be_stale": any(
            item.get("cloud_connection") != "online" for item in sanitize_telemetry(systems)
        ),
        "summary": sanitize_device_summary(systems),
        "devices": sanitize_telemetry(systems),
    }


async def async_get_config_entry_diagnostics(hass, entry) -> dict:
    """Return the diagnostics for this Home Assistant config entry."""
    coordinator = hass.data.get(DOMAIN, {}).get(entry.entry_id)
    if coordinator is None:
        return {"transport": "carrier_native_cloud_graphql", "configured": False}
    return build_diagnostics(coordinator)
