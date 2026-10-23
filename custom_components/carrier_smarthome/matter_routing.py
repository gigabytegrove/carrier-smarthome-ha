"""Dual-transport HVAC command routing without unsafe retries.

Cloud fallback is allowed only when no Matter write has started. A missing ACK
can mean that HVAC did change: never fire a second cloud command in that case.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from .matter_protocol import (
    CLOUD_ONLY, MATTER_ONLY, MATTER_PREFERRED,
    MatterNotReady, MatterWriteUncertain, select_transport,
)


@dataclass(frozen=True)
class RouteResult:
    transport: str
    cloud_fallback: bool
    verified: bool


class DualTransportRouter:
    """One command at a time; never queue stale commands behind verification."""

    def __init__(self, matter_client: Any | None, cloud_online: Callable[[], bool]) -> None:
        self._matter = matter_client
        self._cloud_online = cloud_online
        self._lock = asyncio.Lock()

    async def _local_ready(self) -> bool:
        if self._matter is None:
            return False
        try:
            await self._matter.get_state()
            return True
        except MatterNotReady:
            return False

    async def execute(self, policy: str, *,
                      cloud_write: Callable[[], Awaitable[None]],
                      matter_write: Callable[[Any], Awaitable[Any]]) -> RouteResult:
        if self._lock.locked():
            raise MatterNotReady("Previous HVAC command is still being verified")
        async with self._lock:
            ready = await self._local_ready() if policy != CLOUD_ONLY else False
            route = select_transport(policy, matter_ready=ready,
                                     cloud_ready=self._cloud_online())
            if route == CLOUD_ONLY:
                await cloud_write()
                return RouteResult(CLOUD_ONLY, policy == MATTER_PREFERRED, True)
            try:
                result = await matter_write(self._matter)
            except MatterWriteUncertain:
                # Never attempt cloud write after Matter network uncertainty.
                raise
            except MatterNotReady:
                # Matter Client contract: this error occurs before a write.
                if policy != MATTER_PREFERRED or not self._cloud_online():
                    raise
                await cloud_write()
                return RouteResult(CLOUD_ONLY, True, True)
            if not isinstance(result, dict) or result.get("confirmed") is not True:
                raise MatterWriteUncertain("Matter write lacks confirmed readback")
            return RouteResult(MATTER_ONLY, False, True)
