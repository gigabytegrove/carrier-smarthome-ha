"""Explicit, per-thermostat Matter transport with cloud as an independent choice.

Matter Server manages commissioning and credentials. Only opted-in, validated
node/endpoint bindings can issue local commands. No artificial optimistic state.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Awaitable, Callable

from .matter_client import MatterWsClient
from .matter_discovery import resolve_source
from .matter_protocol import (
    CLOUD_ONLY, MATTER_ONLY, MATTER_PREFERRED, MatterNotReady,
    MatterWriteUncertain,
)
from .matter_routing import DualTransportRouter

_LOGGER = logging.getLogger(__name__)
FRESH_SECONDS = 45
OPTIONS_BINDINGS = "matter_bindings"


def binding_key(serial: str, zone: int) -> str:
    return f"{serial}|{zone}"


def degrees_from_c(value: float | None, unit: str) -> float | None:
    if value is None:
        return None
    return round(value * 9 / 5 + 32, 2) if unit == "°F" else round(value, 2)


def degrees_to_c(value: float, unit: str) -> float:
    return (value - 32) * 5 / 9 if unit == "°F" else value


class MatterManager:
    """Only one runtime climate entity per native Carrier serial/zone."""

    def __init__(self, session: Any, options: dict, coordinator: Any) -> None:
        self.coordinator = coordinator
        self._clients: dict[str, MatterWsClient] = {}
        self._routers: dict[str, DualTransportRouter] = {}
        self._policies: dict[str, str] = {}
        self._readings: dict[str, tuple[float, Any]] = {}
        self._last_non_off: dict[str, str] = {}
        raw = options.get(OPTIONS_BINDINGS, {})
        hass = getattr(coordinator, "hass", None)
        if not isinstance(raw, dict):
            return
        for key, binding in raw.items():
            if not isinstance(key, str) or not isinstance(binding, dict):
                continue
            policy = binding.get("policy")
            if policy not in (MATTER_ONLY, MATTER_PREFERRED):
                continue
            # Keep Matter-only fail-closed when its controller is missing:
            # skipping a binding must never silently switch it to cloud.
            self._policies[key] = policy
            try:
                url, trusted, fabric_id = resolve_source(hass, binding)
                client = MatterWsClient(
                    session, url, binding["node_id"], binding["endpoint"],
                    trusted_ha_source=trusted, expected_fabric_id=fabric_id)
            except (AttributeError, KeyError, TypeError, ValueError, MatterNotReady):
                _LOGGER.warning("Matter controller unavailable; preserving selected control policy")
                continue
            self._clients[key] = client
            self._routers[key] = DualTransportRouter(
                client, lambda key=key: self._cloud_ready(key)
            )

    @property
    def has_bindings(self) -> bool:
        return bool(self._clients)

    def policy(self, serial: str, zone: int) -> str:
        return self._policies.get(binding_key(serial, zone), CLOUD_ONLY)

    def _cloud_ready(self, key: str) -> bool:
        # This is an availability *hint* only; existing cloud write preflight
        # still performs a fresh Carrier read and its own safety validation.
        if not self.coordinator.last_update_success:
            return False
        from .models import connectivity_state
        serial = key.rsplit("|", 1)[0]
        return connectivity_state(self.coordinator.data.get(serial, {})) == "online"

    def last_non_off_mode(self, serial: str, zone: int) -> str | None:
        return self._last_non_off.get(binding_key(serial, zone))

    def state(self, serial: str, zone: int) -> Any | None:
        cached = self._readings.get(binding_key(serial, zone))
        if cached and time.monotonic() - cached[0] <= FRESH_SECONDS:
            return cached[1]
        return None

    async def refresh_one(self, key: str) -> bool:
        client = self._clients.get(key)
        if client is None:
            return False
        try:
            state = await client.get_state()
        except Exception as exc:
            # A local controller failure must not prevent cloud-only operation.
            _LOGGER.debug("Configured Matter controller not ready (%s)", type(exc).__name__)
            self._readings.pop(key, None)
            self.coordinator.async_update_listeners()
            return False
        self._readings[key] = (time.monotonic(), state)
        if state.mode in ("heat", "cool", "auto"):
            self._last_non_off[key] = state.mode
        self.coordinator.async_update_listeners()
        return True

    async def refresh_all(self) -> None:
        # Never poll arbitrary or unconfigured Matter node IDs.
        for key in self._clients:
            await self.refresh_one(key)

    async def execute(self, serial: str, zone: int,
                      cloud_write: Callable[[], Awaitable[None]],
                      matter_write: Callable[[MatterWsClient], Awaitable[Any]]) -> str:
        key = binding_key(serial, zone)
        policy = self._policies.get(key, CLOUD_ONLY)
        if policy == CLOUD_ONLY:
            await cloud_write()
            return CLOUD_ONLY
        router = self._routers.get(key)
        if router is None:
            if policy == MATTER_PREFERRED and self._cloud_ready(key):
                await cloud_write()
                return CLOUD_ONLY
            raise MatterNotReady("Selected Matter controller not loaded; no local command sent")

        async def guarded_matter(client):
            # Serialize with legacy Carrier cloud controls. In particular,
            # reject another command while a cloud command is being verified.
            # The cloud write path acquires this same lock itself; never hold
            # it while invoking cloud_write or a safe cloud fallback.
            lock = self.coordinator.write_lock
            if lock.locked():
                raise MatterNotReady("Another Carrier HVAC command is still being verified")
            async with lock:
                return await matter_write(client)

        try:
            result = await router.execute(policy, cloud_write=cloud_write,
                                          matter_write=guarded_matter)
        except MatterWriteUncertain as exc:
            # A lost Matter ACK is NOT authorization to invoke Carrier cloud.
            await self.refresh_one(key)
            raise MatterWriteUncertain(
                "Matter command may have changed HVAC. No cloud retry was sent; "
                "check the thermostat before trying again"
            ) from exc
        if result.transport == MATTER_ONLY:
            await self.refresh_one(key)
        return result.transport
