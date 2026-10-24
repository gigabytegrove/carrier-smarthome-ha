"""Bounded, privacy-safe Carrier cloud-control observation timeline.

Records *reported* changes only. Neither Carrier's API nor this integration
can infer whether a change came from the thermostat, schedule, app, or HA.
Snapshots are kept independently per cloud read source to avoid mistaking
detail-versus-listing propagation lag for a device state change.
"""
from __future__ import annotations

from collections import deque
from datetime import datetime, timezone
import math


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _snapshot(values: dict) -> dict:
    result = {}
    for key in ("mode", "fan_mode", "heat_setpoint",
                "cool_setpoint", "schedule_enabled"):
        value = values.get(key)
        if key == "mode":
            result[key] = value if isinstance(value, str) and value in {
                "off", "heat", "cool", "auto", "fanonly"
            } else None
        elif key == "fan_mode":
            result[key] = (value if isinstance(value, str)
                           and value in {"auto", "on"} else None)
        elif key == "schedule_enabled":
            result[key] = value if type(value) is bool else None
        else:
            result[key] = (value if type(value) in (int, float)
                           and math.isfinite(value) else None)
    return result


class CloudControlTrace:
    """Keep per-source baselines and changes without exporting device IDs."""

    def __init__(self) -> None:
        self.started_utc = _utc()
        self._last: dict[tuple[str, int, str], dict] = {}
        self._events: deque[dict] = deque(maxlen=100)

    def observe(self, serial: str, zone_index: int, source: str,
                values: dict, device_number: int,
                pending_command_id: int | None = None) -> None:
        if source not in {"listing", "detail"}:
            raise ValueError("Invalid Carrier observation source")
        snapshot = _snapshot(values)
        key = (serial, zone_index, source)
        before = self._last.get(key)
        if before is not None:
            # Sparse/missing fields are not proof of state transitions.
            snapshot = {field: value if value is not None else before.get(field)
                        for field, value in snapshot.items()}
        if before == snapshot:
            return
        self._last[key] = snapshot
        event = {
            "utc": _utc(),
            "source": source,
            "stage": "baseline" if before is None else "reported_change",
            "device_number": device_number,
            "zone_index": zone_index,
            "current": snapshot if before is None else {
                k: v for k, v in snapshot.items()
                if before.get(k) != v and v is not None
            },
        }
        if before is not None:
            event["previous"] = {
                k: before.get(k) for k in event["current"]
            }
            # An incomplete cloud payload is not a thermostat transition.
            if not event["current"]:
                return
        if type(pending_command_id) is int and pending_command_id > 0:
            event["command_pending_when_observed"] = pending_command_id
        self._events.append(event)

    @property
    def events(self) -> list[dict]:
        return [dict(row) for row in self._events]
