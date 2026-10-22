"""Pure data normalization for Carrier entry-level thermostat responses."""
from __future__ import annotations
from typing import Any
import re


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


def _slug(value: Any) -> str | None:
    """Constrain untrusted free-form GraphQL fields before exposing in HA."""
    if not isinstance(value, str) or not re.fullmatch(r"[a-zA-Z][a-zA-Z0-9_-]{0,39}", value):
        return None
    return value.lower()


def _scene(value: Any) -> str | None:
    """Avoid leaking custom user-named profiles into exported diagnostics."""
    name = _slug(value)
    if name in {"home", "away", "sleep", "wake", "manual", "vacation"}:
        return name
    return "custom" if isinstance(value, str) and bool(value.strip()) else None


def zone_values(zone: dict[str, Any]) -> dict[str, Any]:
    return {
        "temperature": _number(zone.get("rt")),
        "humidity": _number(zone.get("rh")),
        "outside_temperature": _number(zone.get("outside_temp")),
        "heat_setpoint": _number(_object(zone.get("htsp")).get("current")),
        "cool_setpoint": _number(_object(zone.get("clsp")).get("current")),
        "heat_max": _number(_object(zone.get("htsp")).get("max")),
        "cool_min": _number(_object(zone.get("clsp")).get("min")),
        "mode": _slug(zone.get("mode")),
        "fan_mode": _slug(zone.get("fan_mode")),
        "schedule_enabled": zone.get("schedule_enabled") if type(zone.get("schedule_enabled")) is bool else None,
        "hold_countdown_raw": _number(zone.get("hold_countdown")),
        "current_scene": _scene(zone.get("current_scene_name")),
        "stage_status": _slug(zone.get("stage_status")),
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
        "offline_count": sum(_object(s.get("connection")).get("isConnected") is False for s in systems),
        "unknown_connection_count": sum(type(_object(s.get("connection")).get("isConnected")) is not bool for s in systems),
    }


def connectivity_state(system: dict[str, Any]) -> str:
    """Do not confuse an absent isConnected field with a confirmed offline state."""
    status = _object(system.get("connection")).get("isConnected")
    if status is True:
        return "online"
    if status is False:
        return "offline"
    return "unknown"


def sanitize_telemetry(systems: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Expose only climate fields; never include serials, device IDs, names or locations.

    This output is safe to copy into issue reports even when cloud devices are
    offline; an offline device can retain *stale* temperature values.
    """
    devices = []
    for system in systems[:20]:
        model = system.get("model")
        if not isinstance(model, str) or not re.fullmatch(r"[A-Za-z0-9_-]{3,40}", model):
            model = "unknown"
        unit = temperature_unit(system.get("temp_unit_format")) or "unknown"
        zones = []
        for index in zone_indices(system)[:8]:
            raw = get_zone(system, index)
            if raw is None:
                continue
            values = zone_values(raw)
            mode = values["mode"]
            if not isinstance(mode, str) or mode not in {"off", "heat", "cool", "auto", "fanonly"}:
                mode = "unknown"
            zones.append({
                "index": index,
                "mode": mode,
                "room_temperature": values["temperature"],
                "heat_setpoint": values["heat_setpoint"],
                "cool_setpoint": values["cool_setpoint"],
                "humidity_percent": values["humidity"],
                "outside_temperature": values["outside_temperature"],
                "fan_mode": values["fan_mode"],
                "stage_status": values["stage_status"],
                "schedule_enabled": values["schedule_enabled"],
                "current_scene": values["current_scene"],
                "heat_max": values["heat_max"],
                "cool_min": values["cool_min"],
                "hold_countdown_raw": values["hold_countdown_raw"],
            })
        devices.append({"model": model, "cloud_connection": connectivity_state(system),
                        "temperature_unit": unit, "zones": zones})
    return devices


def normalize_hardware_id(value: Any) -> str | None:
    """Canonical 48-bit Wi-Fi MAC-like value for *local-only* identity testing.

    Reject random serials that aren't 12 hex digits; never log this value.
    """
    if not isinstance(value, str):
        return None
    digits = re.sub(r"[:-]", "", value).strip().upper()
    return digits if re.fullmatch(r"[0-9A-F]{12}", digits) else None


def hardware_identity_match(expected: Any, *observed: Any) -> str:
    """Confirm exact match; serial mismatches alone are inconclusive.

    A Carrier serial is not necessarily a WLAN MAC; only MAC evidence can
    support an explicit mismatch, and a missing value is UNKNOWN.
    The caller supplies MAC observations, never arbitrary record names.
    """
    target = normalize_hardware_id(expected)
    if target is None:
        return "not_checked"
    clean = [normalize_hardware_id(item) for item in observed]
    clean = [item for item in clean if item is not None]
    if target in clean:
        return "matched"
    if clean:
        return "different_mac"
    return "unverified"
