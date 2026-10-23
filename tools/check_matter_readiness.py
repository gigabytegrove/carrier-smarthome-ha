#!/usr/bin/env python3
"""Read-only local OHF Matter Server diagnostic; NEVER issues an HVAC write.

Run from inside the Home Assistant container (aiohttp is already installed).
The tool prints no fabric secrets, raw IDs, serials, MAC addresses or passwords.
"""
from __future__ import annotations

import argparse
import asyncio
import ipaddress
import json
import sys
from urllib.parse import urlsplit
from uuid import uuid4

import aiohttp

VENDOR_ID = 0x10EE
PRODUCT_ID = 0x0800
CLUSTER = 0x0201


def checked_url(value: str) -> str:
    try:
        parsed = urlsplit(value)
        ip = ipaddress.ip_address(parsed.hostname or "")
        port = parsed.port
    except (TypeError, ValueError) as exc:
        raise ValueError("Provide a valid private IPv4/IPv6 Matter Server URL") from exc
    if (parsed.scheme not in ("ws", "wss") or parsed.username or parsed.password
            or parsed.query or parsed.fragment or parsed.path not in ("", "/", "/ws")
            or not port or ip.is_unspecified or ip.is_multicast or ip.is_link_local
            or not (ip.is_private or ip.is_loopback)):
        raise ValueError("Matter Server must be an explicit trusted LAN/loopback ws[s] URL")
    return f"{parsed.scheme}://{parsed.netloc}/ws"


async def query(ws: aiohttp.ClientWebSocketResponse, command: str, args: dict) -> object:
    request_id = uuid4().hex
    await ws.send_json({"message_id": request_id, "command": command, "args": args})
    async with asyncio.timeout(12):
        for _ in range(100):
            message = await ws.receive_json(timeout=10)
            if not isinstance(message, dict) or message.get("message_id") != request_id:
                continue
            if message.get("error_code") is not None:
                raise RuntimeError(f"Matter Server refused read-only {command}: error_code={message['error_code']}")
            if "result" not in message:
                raise RuntimeError(f"Missing {command} result")
            return message["result"]
    raise RuntimeError(f"No matching {command} response")


def matches(node: object) -> bool:
    if not isinstance(node, dict):
        return False
    attrs = node.get("attributes")
    return bool(isinstance(attrs, dict)
                and type(attrs.get("0/40/2")) is int
                and type(attrs.get("0/40/4")) is int
                and attrs["0/40/2"] == VENDOR_ID
                and attrs["0/40/4"] == PRODUCT_ID)


async def inspect(url: str, *, node_id: int | None, endpoint: int) -> dict:
    timeout = aiohttp.ClientTimeout(total=18, connect=8)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.ws_connect(checked_url(url), timeout=8) as ws:
            hello = await ws.receive_json(timeout=8)
            if (not isinstance(hello, dict) or
                    type(hello.get("schema_version")) is not int or
                    hello["schema_version"] < 11 or
                    hello.get("min_supported_schema_version", 0) > 14):
                raise RuntimeError("Matter Server API version not compatible")
            nodes = await query(ws, "get_nodes", {"only_available": False})
            if not isinstance(nodes, list):
                raise RuntimeError("Malformed node list")
            result = {
                "server": "reachable",
                "schema_version": hello["schema_version"],
                "commissioned_nodes": len(nodes),
                "matching_carrier_nodes": sum(matches(n) for n in nodes),
                "available_matching_nodes": sum(matches(n) and n.get("available") is True
                                                for n in nodes),
                "writes_sent": 0,
            }
            if node_id is None:
                return result
            # Explicit ID only; never enumerate private device IDs to output.
            specific = await query(ws, "get_node", {"node_id": node_id})
            attrs = specific.get("attributes") if isinstance(specific, dict) else None
            path = f"{endpoint}/{CLUSTER}/28"
            if (not matches(specific) or specific.get("available") is not True
                    or not isinstance(attrs, dict) or path not in attrs):
                result["selected_thermostat"] = "not_verified"
                return result
            result["selected_thermostat"] = "matching_carrier_product_online"
            # The following is a *read*, never write_attribute or device_command.
            readback = await query(ws, "read_attribute", {
                "node_id": node_id,
                "attribute_path": [f"{endpoint}/{CLUSTER}/{a}" for a in (0, 17, 18, 28)],
            })
            result["live_attribute_read"] = (
                "success" if isinstance(readback, dict)
                and type(readback.get(path)) is int else "no_mode_returned"
            )
            result["thermostat_attributes_read"] = (
                sum(1 for value in readback.values() if type(value) is int)
                if isinstance(readback, dict) else 0
            )
            return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True, help="ws://PRIVATE-LAN-IP:5580/ws")
    parser.add_argument("--node", type=int, help="Commissioned Matter node ID (optional)")
    parser.add_argument("--endpoint", type=int, default=1, help="Thermostat endpoint (default: 1)")
    args = parser.parse_args(argv)
    if args.node is not None and not 1 <= args.node < 2**64:
        parser.error("--node must be a valid positive Matter node ID")
    if not 1 <= args.endpoint <= 240:
        parser.error("--endpoint must be between 1 and 240")
    try:
        url = checked_url(args.url)
        report = asyncio.run(inspect(url, node_id=args.node, endpoint=args.endpoint))
    except (ValueError, aiohttp.ClientError, asyncio.TimeoutError, RuntimeError, OSError) as exc:
        # Never echo a potentially sensitive supplied WebSocket URL.
        print(f"NOT READY: {type(exc).__name__}: {str(exc)[:130]}", file=sys.stderr)
        return 2
    print(json.dumps(report, sort_keys=True, indent=2))
    if report["available_matching_nodes"] < 1:
        return 3
    if args.node is not None and (
            report.get("selected_thermostat") != "matching_carrier_product_online"
            or report.get("live_attribute_read") != "success"):
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
