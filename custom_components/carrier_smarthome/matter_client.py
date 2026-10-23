"""Direct WebSocket client for the OHF matter.js controller server.

The standalone Matter Server owns secure fabrics/commissioning/credentials.
This integration does NOT create another broker or expose a duplicate climate
entity. Commands are opt-in and require a commissioned, verified Matter node.
"""
from __future__ import annotations

import asyncio
import ipaddress
from typing import Any
from urllib.parse import urlsplit
from aiohttp import ClientError
from uuid import uuid4

from .matter_protocol import (
    MatterNotReady, MatterWriteUncertain, decode, path, plan_mode, plan_setpoint,
    THERMOSTAT_CLUSTER,
)


def validate_server_url(value: str) -> str:
    """Accept explicit private/LAN Matter Servers; reject public destinations.

    Matter Servers commonly expose plain ws:// on a trusted local subnet.
    Users must keep that port LAN-restricted: WebSocket is not authenticated.
    """
    try:
        url = urlsplit(value)
        ip = ipaddress.ip_address(url.hostname or "")
        port = url.port
    except (ValueError, TypeError):
        raise MatterNotReady("Matter Server must use an explicit valid private or loopback IP and port") from None
    if url.username or url.password or url.fragment or url.query:
        raise MatterNotReady("Matter Server URL cannot contain credentials or parameters")
    if url.scheme not in ("ws", "wss") or url.path not in ("", "/", "/ws"):
        raise MatterNotReady("Matter Server expects ws[s]://<private-ip>:5580/ws")
    if (not (ip.is_private or ip.is_loopback) or ip.is_unspecified
            or ip.is_multicast or ip.is_link_local):
        raise MatterNotReady("Matter Server must use a trusted private or loopback address")
    if not port or not 1 <= port <= 65535:
        raise MatterNotReady("Matter Server port required")
    # Preserve the slash between authority and endpoint; a bare trailing slash
    # must not accidentally become `:5580ws`.
    return f"{url.scheme}://{url.netloc}/ws"


class MatterWsClient:
    def __init__(self, session: Any, server_url: str, node_id: int, endpoint: int) -> None:
        self.session = session
        self.server_url = validate_server_url(server_url)
        if type(node_id) is not int or not 1 <= node_id < 2**64:
            raise MatterNotReady("Matter node ID must be positive")
        path(endpoint, THERMOSTAT_CLUSTER, 0x1C)
        self.node_id = node_id
        self.endpoint = endpoint

    async def _rpc(self, ws: Any, command: str, args: dict[str, Any]) -> Any:
        request_id = uuid4().hex
        await ws.send_json({"message_id": request_id, "command": command, "args": args})
        # Bound the *entire* exchange, not 100 x 20-second receives.
        async with asyncio.timeout(15):
            for _ in range(100):
                response = await ws.receive_json(timeout=10)
                if not isinstance(response, dict) or response.get("message_id") != request_id:
                    continue
                if response.get("error_code") is not None:
                    raise MatterNotReady(f"Matter Server rejected {command}; code {response['error_code']}")
                if "result" not in response:
                    raise MatterNotReady("Matter Server response missing result")
                return response["result"]
        raise MatterNotReady("Matter Server sent too many unrelated messages")

    async def _handshake(self, ws: Any) -> None:
        info = await ws.receive_json(timeout=10)
        if not isinstance(info, dict) or type(info.get("schema_version")) is not int:
            raise MatterNotReady("Matter Server did not send valid handshake")
        if info["schema_version"] < 11 or info.get("min_supported_schema_version", 0) > 14:
            raise MatterNotReady("Incompatible Matter Server API version")

    async def get_state(self):
        try:
            async with self.session.ws_connect(self.server_url, timeout=10) as ws:
                await self._handshake(ws)
                node = await self._rpc(ws, "get_node", {"node_id": self.node_id})
                return decode(node, self.endpoint)
        except MatterNotReady:
            raise
        except (ClientError, OSError, asyncio.TimeoutError, ValueError, RuntimeError) as exc:
            raise MatterNotReady("Matter Server cannot be reached") from exc

    async def write(self, *, mode: str | None = None, setpoint_kind: str | None = None,
                    setpoint_c: float | None = None):
        """Single write followed by readback; never retry an uncertain result."""
        if (mode is None) == (setpoint_kind is None):
            raise MatterNotReady("Request exactly one HVAC action at a time")
        if setpoint_kind is not None and setpoint_c is None:
            raise MatterNotReady("Setpoint temperature required")
        try:
            async with self.session.ws_connect(self.server_url, timeout=10) as ws:
                await self._handshake(ws)
                node = await self._rpc(ws, "get_node", {"node_id": self.node_id})
                if mode is not None:
                    address, value = plan_mode(node, self.endpoint, mode)
                else:
                    address, value = plan_setpoint(node, self.endpoint,
                                                   setpoint_kind, setpoint_c)
                # Verify live reachability through a real Matter Read before
                # sending any write. get_node alone may contain cached data
                # from a prior server subscription.
                observed = await self._rpc(ws, "read_attribute", {
                    "node_id": self.node_id, "attribute_path": address,
                })
                if (not isinstance(observed, dict)
                        or type(observed.get(address)) is not int):
                    raise MatterNotReady("Matter did not provide a live thermostat read")
                if observed[address] == value:
                    return {"transport": "matter", "confirmed": True, "changed": False}
                # Irreversible boundary: even a lost ACK may mean HVAC changed.
                try:
                    result = await self._rpc(ws, "write_attribute", {
                        "node_id": self.node_id, "attribute_path": address, "value": value,
                    })
                    if not isinstance(result, list) or not result or any(
                        not isinstance(item, dict) or item.get("Status") != 0
                        for item in result
                    ):
                        raise MatterWriteUncertain("Matter write not positively acknowledged")
                    actual = await self._rpc(ws, "read_attribute", {
                        "node_id": self.node_id, "attribute_path": address,
                    })
                    if not isinstance(actual, dict) or actual.get(address) != value:
                        raise MatterWriteUncertain("Matter write acknowledged but readback unconfirmed")
                except MatterWriteUncertain:
                    raise
                except Exception as exc:
                    raise MatterWriteUncertain("Matter write outcome unknown; no cloud fallback") from exc
                return {"transport": "matter", "confirmed": True}
        except (MatterNotReady, MatterWriteUncertain):
            raise
        except (ClientError, OSError, asyncio.TimeoutError, ValueError, RuntimeError) as exc:
            raise MatterNotReady("Matter Server unavailable before write") from exc
