"""Fail-closed mapping for a certified Carrier Matter 1.1 thermostat.

Pure protocol layer: no I/O, pairing codes, fabric keys or network assumptions.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Mapping

THERMOSTAT_CLUSTER = 0x201
CARRIER_VENDOR_ID = 0x10EE
CARRIER_PRODUCT_ID = 0x0800
MODES_TO_MATTER = {"off": 0, "auto": 1, "cool": 3, "heat": 4, "fanonly": 7}
MATTER_TO_MODES = {v: k for k, v in MODES_TO_MATTER.items()}
CLOUD_ONLY = "cloud"
MATTER_ONLY = "matter"
MATTER_PREFERRED = "matter_preferred"
TRANSPORT_MODES = frozenset((CLOUD_ONLY, MATTER_ONLY, MATTER_PREFERRED))


class MatterNotReady(Exception):
    """Safe preflight failure BEFORE any local write is sent."""


class MatterWriteUncertain(Exception):
    """Matter write possibly reached the device; NEVER auto-fallback."""


@dataclass(frozen=True)
class ThermostatState:
    mode: str | None
    temperature_c: float | None
    heat_target_c: float | None
    cool_target_c: float | None
    max_heat_c: float | None
    min_cool_c: float | None
    endpoint: int


def path(endpoint: int, cluster: int, attribute: int) -> str:
    if type(endpoint) is not int or not 1 <= endpoint <= 240:
        raise MatterNotReady("Thermostat endpoint not verified")
    return f"{endpoint}/{cluster}/{attribute}"


def _raw_number(value: Any) -> int | None:
    return value if type(value) is int and -32768 <= value <= 32767 else None


def _temperature(value: Any) -> float | None:
    raw = _raw_number(value)
    return None if raw is None or raw == -32768 else raw / 100.0


def _hundredth_celsius(value: Any) -> int:
    if type(value) not in (int, float) or not math.isfinite(value):
        raise MatterNotReady("Setpoint must be a finite temperature")
    if not -40 <= value <= 75:
        raise MatterNotReady("Setpoint outside conservative Matter thermostat safety bounds")
    return round(value * 100)


def validate_node(node: Mapping[str, Any], endpoint: int) -> Mapping[str, Any]:
    """Match VID/PID and thermostat endpoint; names or IP are insufficient."""
    if not isinstance(node, Mapping) or node.get("available") is not True:
        raise MatterNotReady("Matter thermostat unavailable or not commissioned")
    attributes = node.get("attributes")
    if not isinstance(attributes, Mapping):
        raise MatterNotReady("Matter node has no attribute listing")
    if (attributes.get("0/40/2") != CARRIER_VENDOR_ID or
            attributes.get("0/40/4") != CARRIER_PRODUCT_ID):
        raise MatterNotReady("Matter vendor/product does not match certified Carrier thermostat")
    if path(endpoint, THERMOSTAT_CLUSTER, 0x1C) not in attributes:
        raise MatterNotReady("Selected Matter endpoint has no thermostat systemMode")
    return attributes


def decode(node: Mapping[str, Any], endpoint: int) -> ThermostatState:
    a = validate_node(node, endpoint)
    def read(attr: int) -> float | None:
        return _temperature(a.get(path(endpoint, THERMOSTAT_CLUSTER, attr)))
    raw_mode = a.get(path(endpoint, THERMOSTAT_CLUSTER, 0x1C))
    return ThermostatState(
        mode=MATTER_TO_MODES.get(raw_mode) if type(raw_mode) is int else None,
        temperature_c=read(0),
        heat_target_c=read(0x12),
        cool_target_c=read(0x11),
        max_heat_c=read(0x16) if read(0x16) is not None else read(0x04),
        min_cool_c=read(0x17) if read(0x17) is not None else read(0x05),
        endpoint=endpoint,
    )


def plan_mode(node: Mapping[str, Any], endpoint: int, desired: str) -> tuple[str, int]:
    a = validate_node(node, endpoint)
    if desired not in MODES_TO_MATTER:
        raise MatterNotReady("Unrecognized HVAC mode")
    address, value = path(endpoint, THERMOSTAT_CLUSTER, 0x1C), MODES_TO_MATTER[desired]
    if desired == "fanonly" and value != a.get(address):
        raise MatterNotReady("Matter fan-only mode not proven on this thermostat")
    return address, value


def plan_setpoint(node: Mapping[str, Any], endpoint: int,
                  kind: str, target_c: float) -> tuple[str, int]:
    a = validate_node(node, endpoint)
    attributes = {"cool": 0x11, "heat": 0x12}
    if kind not in attributes:
        raise MatterNotReady("Select heating or cooling setpoint")
    address = path(endpoint, THERMOSTAT_CLUSTER, attributes[kind])
    if address not in a:
        raise MatterNotReady("Matter setpoint not exposed on this endpoint")
    raw = _hundredth_celsius(target_c)
    state = decode(node, endpoint)
    if kind == "heat" and state.max_heat_c is not None and target_c > state.max_heat_c:
        raise MatterNotReady("Heating target exceeds Matter reported limit")
    if kind == "cool" and state.min_cool_c is not None and target_c < state.min_cool_c:
        raise MatterNotReady("Cooling target below Matter reported limit")
    return address, raw


def select_transport(mode: str, *, matter_ready: bool, cloud_ready: bool) -> str:
    """Pre-write selection only. Never retry through cloud after Matter uncertainty."""
    if mode not in TRANSPORT_MODES:
        raise ValueError("Unsupported control transport selection")
    if mode == CLOUD_ONLY:
        if cloud_ready:
            return CLOUD_ONLY
        raise MatterNotReady("Carrier cloud unavailable")
    if matter_ready:
        return MATTER_ONLY
    if mode == MATTER_PREFERRED and cloud_ready:
        return CLOUD_ONLY
    raise MatterNotReady("Matter unavailable; selected policy forbids cloud fallback")
