"""Privacy-safe, transient Home Assistant thermostat intent display.

The overlay is presentation-only: Carrier cloud observations remain untouched.
No credentials or hardware identifiers are stored in exported command events.
"""
from __future__ import annotations

from collections import deque
from datetime import datetime, timezone
import math
import re
from typing import Callable

_FIELDS = frozenset({"mode", "fan_mode", "heat_setpoint", "cool_setpoint"})
_MODES = frozenset({"off", "heat", "cool", "auto", "fanonly"})
_FAN_MODES = frozenset({"auto", "on"})
_SAFE_TAG = re.compile(r"[a-z][a-z0-9_]{0,55}\Z")


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_values(values: dict) -> dict:
    """Reject unsanitized strings/nonfinite values before exporting events."""
    clean = {}
    for key, value in values.items():
        if key not in _FIELDS:
            continue
        if key == "mode":
            clean[key] = value if isinstance(value, str) and value in _MODES else None
        elif key == "fan_mode":
            clean[key] = value if isinstance(value, str) and value in _FAN_MODES else None
        elif type(value) in (int, float) and math.isfinite(value):
            clean[key] = value
        else:
            clean[key] = None
    return clean


class OptimisticControlTracker:
    """Bounded history and active overlays, scoped to a single HA entry."""

    def __init__(self, on_change: Callable[[], None]) -> None:
        self._on_change = on_change
        self._next_id = 0
        self._active: dict[tuple[str, int], dict] = {}
        self._events: deque[dict] = deque(maxlen=160)

    def begin(self, serial: str, zone_index: int, desired: dict,
              previous: dict, device_number: int, *,
              requested: dict | None = None) -> int:
        key = (serial, zone_index)
        if not desired or _safe_values(desired) != desired:
            raise ValueError("Invalid thermostat control request")
        requested = desired if requested is None else requested
        if not requested or _safe_values(requested) != requested:
            raise ValueError("Invalid requested thermostat fields")
        # Later user intent immediately replaces pending display. The earlier
        # cloud mutation (if already sent) must be allowed to finish; only its
        # read-only confirmation can be abandoned.
        previous_command = self._active.get(key)
        if previous_command is not None:
            self.record(previous_command["command_id"], "superseded",
                        reason="newer_user_command")
        self._next_id += 1
        command_id = self._next_id
        safe_previous = _safe_values({k: previous.get(k) for k in desired})
        record = {
            "command_id": command_id,
            "device_number": device_number,
            "zone_index": zone_index,
            "requested": dict(desired),
            "carrier_reported_before": safe_previous,
            "requested_at_utc": _utc(),
            "state": "pending_cloud_confirmation",
        }
        self._active[key] = record
        self.record(command_id, "optimistic_applied", requested=requested,
                    pending_overlay=desired, observed=safe_previous,
                    device_number=device_number, zone_index=zone_index)
        self._on_change()
        return command_id

    def record(self, command_id: int | None, stage: str, *,
               reason: str | None = None, source: str | None = None,
               attempt: int | None = None, observed: dict | None = None,
               requested: dict | None = None, pending_overlay: dict | None = None,
               detail_reads: int | None = None, listing_reads: int | None = None,
               repeated_reads: int | None = None,
               device_number: int | None = None,
               zone_index: int | None = None) -> None:
        """Only fixed code-controlled tags and normalized values reach exports."""
        if not _SAFE_TAG.fullmatch(stage):
            raise ValueError("Unsafe command event stage")
        event: dict = {"utc": _utc(), "command_id": command_id, "stage": stage}
        for name, value in (("reason", reason), ("source", source)):
            if value is not None:
                if not _SAFE_TAG.fullmatch(value):
                    raise ValueError("Unsafe command event label")
                event[name] = value
        if type(attempt) is int and attempt > 0:
            event["verification_attempt"] = attempt
        if observed is not None:
            event["observed"] = _safe_values(observed)
        if requested is not None:
            event["requested"] = _safe_values(requested)
        if pending_overlay is not None:
            event["pending_overlay"] = _safe_values(pending_overlay)
        for name, value in (("detail_reads", detail_reads),
                            ("listing_reads", listing_reads),
                            ("repeated_reads", repeated_reads)):
            if type(value) is int and 0 <= value <= 1000:
                event[name] = value
        if type(device_number) is int and device_number > 0:
            event["device_number"] = device_number
        if type(zone_index) is int and zone_index >= 0:
            event["zone_index"] = zone_index
        self._events.append(event)

    def is_current(self, serial: str, zone_index: int,
                   command_id: int) -> bool:
        active = self._active.get((serial, zone_index))
        return active is not None and active["command_id"] == command_id

    def overlay(self, serial: str, zone_index: int) -> dict:
        record = self._active.get((serial, zone_index))
        return dict(record["requested"]) if record else {}

    def active(self, serial: str, zone_index: int) -> dict | None:
        record = self._active.get((serial, zone_index))
        return dict(record) if record else None

    @property
    def active_diagnostics(self) -> list[dict]:
        return [dict(row) for row in self._active.values()]

    @property
    def events(self) -> list[dict]:
        return [dict(row) for row in self._events]

    def finish(self, serial: str, zone_index: int, command_id: int,
               outcome: str, *, reason: str | None = None) -> None:
        key = (serial, zone_index)
        record = self._active.get(key)
        if record is None or record["command_id"] != command_id:
            return
        if outcome not in {"verified", "reverted", "unconfirmed", "cancelled"}:
            raise ValueError("Invalid command outcome")
        self.record(command_id, outcome, reason=reason)
        if outcome != "verified":
            self.record(command_id, "optimistic_rollback", reason=reason)
        del self._active[key]
        self._on_change()
