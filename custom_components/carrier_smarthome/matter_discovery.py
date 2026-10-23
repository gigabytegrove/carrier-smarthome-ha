"""Reuse the first-party Home Assistant Matter controller when already configured.

The native Matter integration manages commissioning and controller lifecycle.
Never provision Docker, access host sockets, share fabric keys, or spawn a
second Matter controller from HACS custom integration code.
"""
from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Mapping
from typing import Any

HA_MATTER_SOURCE = "home_assistant_matter"


@dataclass(frozen=True)
class HomeAssistantMatterSource:
    entry_id: str
    server_url: str


def find_home_assistant_matter(hass: Any) -> HomeAssistantMatterSource | None:
    """Return only an already-loaded official Matter config entry.

    A config entry may exist but not be loaded; in that case fail closed
    instead of guessing an address or using a potentially stale fabric.
    """
    if hass is None:
        return None
    for entry in hass.config_entries.async_loaded_entries("matter"):
        data = getattr(entry, "data", {})
        url = data.get("url") if isinstance(data, Mapping) else None
        if isinstance(url, str) and url:
            return HomeAssistantMatterSource(entry.entry_id, url)
    return None


def resolve_source(hass: Any, binding: dict) -> tuple[str, bool, int | None]:
    """Resolve selected controller without trusting a user-edited URL.

    Saved bindings contain only the official Matter config-entry ID and fabric
    fingerprint. The server URL must always come from that exact loaded entry.
    Manual legacy bindings preserve their original private-IP validation.
    """
    if binding.get("source") != HA_MATTER_SOURCE:
        return binding["url"], False, None
    source = find_home_assistant_matter(hass)
    if source is None or source.entry_id != binding.get("matter_entry_id"):
        raise ValueError("The selected Home Assistant Matter controller is not loaded")
    fabric_id = binding.get("fabric_id")
    if type(fabric_id) is not int or fabric_id < 0:
        raise ValueError("Home Assistant Matter fabric identity is unverified")
    return source.server_url, True, fabric_id
