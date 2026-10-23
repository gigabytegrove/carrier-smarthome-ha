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
        "matter_enabled": bool(getattr(getattr(coordinator, "matter", None), "has_bindings", False)),
        "matter_binding_count": len(getattr(getattr(coordinator, "matter", None), "_clients", {})),
        "matter_configuration": "explicit_per_thermostat_opt_in",
        "last_poll_succeeded": bool(coordinator.last_update_success),
        "last_successful_poll_utc": getattr(coordinator, "last_poll_utc", None),
        "last_error_category": getattr(coordinator, "last_error_kind", None),
        "last_error_utc": getattr(coordinator, "last_error_utc", None),
        "consecutive_poll_failures": getattr(coordinator, "consecutive_errors", 0),
        "seconds_since_success": getattr(coordinator, "seconds_since_success", None),
        "retry_wait_seconds": getattr(coordinator, "next_poll_wait_seconds", 0),
        "telemetry_in_grace_period": getattr(coordinator, "telemetry_in_grace", False),
        "telemetry_may_be_stale": (not coordinator.last_update_success or any(
            item.get("cloud_connection") != "online" for item in sanitize_telemetry(systems)
        )),
        "summary": sanitize_device_summary(systems),
        "devices": sanitize_telemetry(systems),
    }


async def async_get_config_entry_diagnostics(hass, entry) -> dict:
    """Return the diagnostics for this Home Assistant config entry."""
    coordinator = hass.data.get(DOMAIN, {}).get(entry.entry_id)
    if coordinator is None:
        return {"transport": "carrier_native_cloud_graphql", "configured": False}
    return build_diagnostics(coordinator)
