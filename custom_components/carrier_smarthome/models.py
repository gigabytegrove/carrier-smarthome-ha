"""Pure data normalization for Carrier entry-level thermostat responses."""
from __future__ import annotations
from typing import Any


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    import math
    return result if math.isfinite(result) else None


def _object(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def get_zone(system: dict[str, Any], index: int) -> dict[str, Any] | None:
    zones = system.get("zones") or []
    if not isinstance(zones, list):
        return None
    for zone in zones:
        if isinstance(zone, dict) and zone.get("index") == index:
            return zone
    return None


def zone_indices(system: dict[str, Any]) -> list[int]:
    zones = system.get("zones") or []
    if not isinstance(zones, list):
        return []
    return sorted({zone["index"] for zone in zones
                   if isinstance(zone, dict) and type(zone.get("index")) is int and zone["index"] >= 0})


def zone_values(zone: dict[str, Any]) -> dict[str, Any]:
    return {
        "temperature": _number(zone.get("rt")),
        "humidity": _number(zone.get("rh")),
        "outside_temperature": _number(zone.get("outside_temp")),
        "heat_setpoint": _number(_object(zone.get("htsp")).get("current")),
        "cool_setpoint": _number(_object(zone.get("clsp")).get("current")),
        "heat_max": _number(_object(zone.get("htsp")).get("max")),
        "cool_min": _number(_object(zone.get("clsp")).get("min")),
        "mode": zone.get("mode") if isinstance(zone.get("mode"), str) else None,
        "fan_mode": zone.get("fan_mode") if isinstance(zone.get("fan_mode"), str) else None,
        "schedule_enabled": zone.get("schedule_enabled"),
        "stage_status": zone.get("stage_status"),
    }


def temperature_unit(value: Any) -> str | None:
    """Return HA temperature unit constant-compatible symbol, or unknown."""
    text = str(value or "").strip().lower()
    if text in ("f", "fahrenheit", "imperial"):
        return "°F"
    if text in ("c", "celsius", "metric"):
        return "°C"
    return None


def sanitize_device_summary(systems: list[dict[str, Any]]) -> dict[str, Any]:
    """No names, serials, device IDs, location, WLAN, or other account data."""
    return {
        "entry_level_count": len(systems),
        "models": sorted({str(s.get("model")) for s in systems if s.get("model")}),
        "online_count": sum(_object(s.get("connection")).get("isConnected") is True for s in systems),
        "zone_count": sum(len(zone_indices(s)) for s in systems),
    }
