"""Async native Carrier SmartHome entry-level GraphQL client.

Endpoint and assistedLogin flow validated against publicly documented Carrier
client code and APK operation definitions. This project's target model still
requires on-device verification. No Matter transport, spoofing, or fake data.
"""
from __future__ import annotations

import asyncio
import logging
import math
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from collections.abc import Mapping
from typing import Any

from aiohttp import ClientError, ClientSession, ClientTimeout

_LOGGER = logging.getLogger(__name__)
BASE = "https://dataservice.infinity.iot.carrier.com"
GRAPHQL = BASE + "/graphql"
NO_AUTH = BASE + "/graphql-no-auth"
REFRESH = "https://sso.carrier.com/oauth2/default/v1/token"
# Public OAuth client identifier observed in MIT-licensed dahlb/carrier_api.
# This is not a client secret.
OAUTH_PUBLIC_CLIENT_ID = "0oa1ce7hwjuZbfOMB4x7"
MAX_BODY = 1_048_576
DEFAULT_RATE_LIMIT_DELAY = 120.0
MAX_RATE_LIMIT_DELAY = 3600.0
TIMEOUT = ClientTimeout(total=20, connect=8)

LOGIN_QUERY = """mutation assistedLogin($input: AssistedLoginInput!) {
  assistedLogin(input: $input) {
    success status errorMessage
    data { token_type expires_in access_token scope refresh_token }
  }
}"""

SYSTEMS_QUERY = """query getEntryLevelSystems($username: String!) {
  entryLevelSystems(username: $username) {
    serial name location_id model firmware temp_unit_format
    connection { isConnected deviceId }
    zones {
      index mode rt rh clsp { current min } htsp { current max }
      fan_mode schedule_enabled hold_end_time hold_countdown
      stage_status outside_temp
    }
  }
}"""

USER_DEVICES_QUERY = """query getUserWithDevices($userName: String!, $appVersion: String, $brand: String, $os: String, $osVersion: String) {
  user(userName: $userName, appVersion: $appVersion, brand: $brand, os: $os, osVersion: $osVersion) {
    locations { entryLevels { serial connection { isConnected } } }
  }
}"""

# Independent read-only connection and hardware identity view from Android 1.2.42.
# Only used by owner-side diagnostics; it never changes the established
# account listing or controls. No MAC or serial is logged or persisted.
USER_CONNECTIONS_QUERY = """query getUserWithDevices($userName: String!, $appVersion: String, $brand: String, $os: String, $osVersion: String) {
  user(userName: $userName, appVersion: $appVersion, brand: $brand, os: $os, osVersion: $osVersion) {
    locations { entryLevels { serial connection { isConnected macaddress } } }
  }
}"""

DETAIL_QUERY = """query getEntryLevelSystemData($serial: String!) {
  entryLevelSystem(serial: $serial) {
    serial name model firmware temp_unit_format
    connection { isConnected deviceId }
    zones {
      index mode rt rh clsp { current min } htsp { current max }
      fan_mode schedule_enabled hold_end_time hold_countdown stage_status outside_temp
    }
  }
}"""

SCHEDULES_QUERY = """query getEntryLevelSchedules($serial: String!) {
  entryLevelSchedules(serial: $serial) {
    index zone_index scene_name htsp clsp start_time day
  }
}"""

REMINDERS_QUERY = """query getEntryLevelReminders($serial: String!) {
  entryLevelReminders(serial: $serial) { id message type }
}"""

NOTIFICATION_PREFS_QUERY = """query getEntryLevelNotificationPrefs($serial: String!) {
  entryLevelNotificationPrefs(serial: $serial) {
    push { mute reminders {
      utilizedHvacFilter { enabled config { intervalInMonths lastExecutionDate nextExecutionDate } }
      utilizedVentilatorFilter { enabled config { intervalInMonths lastExecutionDate nextExecutionDate } }
      utilizedHumidifierFilter { enabled config { intervalInMonths lastExecutionDate nextExecutionDate } }
    } alerts { offline { enabled } } }
  }
}"""

# APK v1.2.42 explicitly defines these fields in getEntryLevelSystemData.
# The owner verified a smaller detail query on 2026-10-22; this wider read
# remains unverified until it is exercised by the owner in PowerShell.
# No identifiers other than the serial variable are echoed in diagnostic output.
EXTENDED_DETAIL_QUERY = """query getEntryLevelSystemData($serial: String!) {
  entryLevelSystem(serial: $serial) {
    serial model firmware temp_unit_format
    connection { isConnected rssi }
    zones {
      index mode rt rh outside_temp stage_status fan_mode
      schedule_enabled hold_end_time hold_countdown current_scene_name
      clsp { current min } htsp { current max }
    }
  }
}"""

ZONE_UPDATE = """mutation updateEntryLevelZone($input: EntryLevelZoneInput!) {
  updateEntryLevelZone(input: $input) { success }
}"""


class CarrierError(Exception):
    """Carrier client failure. Messages never include secrets/server bodies."""


class CarrierAuthError(CarrierError):
    """Authentication failed, was refused or expired."""


class CarrierTransportError(CarrierError):
    """HTTP, GraphQL or connectivity problem."""


class CarrierRateLimitError(CarrierTransportError):
    """Carrier asked us to slow polling; delay is bounded to one hour."""

    def __init__(self, retry_after: float) -> None:
        super().__init__("Carrier cloud rate limit reached")
        self.retry_after = retry_after


def retry_after_seconds(value: str | None, *, now: datetime | None = None) -> float:
    """Parse HTTP Retry-After delta or HTTP-date without trusting huge values."""
    if not isinstance(value, str) or not value.strip():
        return DEFAULT_RATE_LIMIT_DELAY
    raw = value.strip()
    try:
        result = float(raw)
    except ValueError:
        try:
            when = parsedate_to_datetime(raw)
            if when.tzinfo is None:
                return DEFAULT_RATE_LIMIT_DELAY
            reference = now or datetime.now(timezone.utc)
            result = (when - reference).total_seconds()
        except (TypeError, ValueError, OverflowError):
            return DEFAULT_RATE_LIMIT_DELAY
    if not math.isfinite(result):
        return DEFAULT_RATE_LIMIT_DELAY
    return max(1.0, min(result, MAX_RATE_LIMIT_DELAY))


class CarrierQueryError(CarrierTransportError):
    """GraphQL query was rejected; a known alternate read route may exist."""


class CarrierSmartHomeClient:
    """One account, lazy login, refresh and read/write GraphQL requests."""

    def __init__(self, session: ClientSession, username: str, password: str) -> None:
        if not username.strip() or not password:
            raise ValueError("Username and password must be provided")
        self.session = session
        self.username = username.strip()
        self._password = password
        self._access_token: str | None = None
        self._refresh_token: str | None = None
        self._token_type = "Bearer"
        self._expires = 0.0
        self._lock = asyncio.Lock()
        self._discovery_method = "systems"

    async def _post(self, url: str, data: Mapping[str, Any], *, token: str | None = None,
                    form: bool = False) -> dict[str, Any]:
        headers = {"Accept": "application/json"}
        if token:
            headers["Authorization"] = f"{self._token_type} {token}"
        headers["User-Agent"] = "carrier-smarthome-ha/0.5.3"
        if not form:
            headers["Content-Type"] = "application/json"
        kwargs: dict[str, Any] = {"data" if form else "json": dict(data)}
        try:
            async with self.session.post(url, headers=headers, timeout=TIMEOUT,
                                         allow_redirects=False, **kwargs) as response:
                if response.status in (401, 403):
                    raise CarrierAuthError("Carrier rejected the account/session")
                if response.status == 429:
                    raise CarrierRateLimitError(retry_after_seconds(response.headers.get("Retry-After")))
                if url in (NO_AUTH, REFRESH) and response.status == 400:
                    raise CarrierAuthError("Carrier login or refresh request rejected")
                if not 200 <= response.status < 300:
                    raise CarrierTransportError(f"Carrier API HTTP {response.status}")
                if response.content_length is not None and response.content_length > MAX_BODY:
                    raise CarrierTransportError("Carrier response exceeded size limit")
                body = await response.content.read(MAX_BODY + 1)
                if len(body) > MAX_BODY:
                    raise CarrierTransportError("Carrier response exceeded size limit")
        except (ClientError, asyncio.TimeoutError, OSError) as exc:
            raise CarrierTransportError("Unable to reach Carrier services") from exc
        try:
            import json
            result = json.loads(body)
        except (ValueError, UnicodeError) as exc:
            raise CarrierTransportError("Carrier returned invalid JSON") from exc
        if not isinstance(result, dict):
            raise CarrierTransportError("Carrier response must be an object")
        return result

    @staticmethod
    def _graphql_data(payload: Mapping[str, Any]) -> dict[str, Any]:
        if payload.get("errors"):
            # Never log raw GraphQL errors: they can include token/serial data.
            # Error *codes* are safe to inspect for revoked/expired auth.
            errors = payload["errors"]
            if isinstance(errors, list):
                for item in errors:
                    if isinstance(item, dict) and isinstance(item.get("extensions"), dict):
                        code = item["extensions"].get("code")
                        if isinstance(code, str) and code.upper() in {
                            "UNAUTHENTICATED", "UNAUTHORIZED", "INVALID_TOKEN", "TOKEN_EXPIRED",
                        }:
                            raise CarrierAuthError("Carrier session is no longer authorized")
            raise CarrierQueryError("Carrier rejected the GraphQL operation")
        data = payload.get("data")
        if not isinstance(data, dict):
            raise CarrierTransportError("Carrier GraphQL data was missing")
        return data

    async def _login_unlocked(self) -> None:
        payload = await self._post(NO_AUTH, {"operationName": "assistedLogin",
                           "query": LOGIN_QUERY,
                           "variables": {"input": {"username": self.username,
                                                    "password": self._password}}})
        data = self._graphql_data(payload).get("assistedLogin")
        if not isinstance(data, dict) or data.get("success") is not True:
            raise CarrierAuthError("Carrier SmartHome login was unsuccessful")
        self._set_tokens(data.get("data"))

    def _set_tokens(self, value: Any) -> None:
        if not isinstance(value, dict) or not isinstance(value.get("access_token"), str) or not value["access_token"]:
            raise CarrierAuthError("Carrier returned an invalid access token")
        raw_expiry = value.get("expires_in")
        try:
            expiry = float(raw_expiry)
        except (TypeError, ValueError) as exc:
            raise CarrierAuthError("Carrier returned an invalid token expiry") from exc
        if not 0 < expiry <= 86400 * 365:
            raise CarrierAuthError("Carrier returned an invalid token lifetime")
        token_type = str(value.get("token_type") or "Bearer")
        if token_type.lower() != "bearer":
            raise CarrierAuthError("Unsupported Carrier token type")
        refresh = value.get("refresh_token")
        self._token_type = "Bearer"
        self._access_token = value["access_token"]
        if isinstance(refresh, str) and refresh:
            self._refresh_token = refresh
        self._expires = time.monotonic() + expiry

    async def _refresh_unlocked(self) -> None:
        if not self._refresh_token:
            await self._login_unlocked()
            return
        try:
            data = await self._post(REFRESH, {
                "client_id": OAUTH_PUBLIC_CLIENT_ID,
                "grant_type": "refresh_token",
                "refresh_token": self._refresh_token,
                "scope": "offline_access",
            }, form=True)
            self._set_tokens(data)
        except CarrierAuthError:
            self._access_token = None
            self._refresh_token = None
            await self._login_unlocked()
        except CarrierTransportError:
            raise

    async def _token(self) -> str:
        if self._access_token and time.monotonic() < self._expires - 60:
            return self._access_token
        async with self._lock:
            if self._access_token and time.monotonic() < self._expires - 60:
                return self._access_token
            if self._refresh_token:
                await self._refresh_unlocked()
            else:
                await self._login_unlocked()
            assert self._access_token is not None
            return self._access_token

    async def _graphql(self, name: str, document: str, variables: dict[str, Any]) -> dict[str, Any]:
        token = await self._token()
        payload = await self._post(GRAPHQL, {"operationName": name, "query": document,
                                               "variables": variables}, token=token)
        return self._graphql_data(payload)

    async def async_get_systems(self) -> list[dict[str, Any]]:
        """First use existing entry-level list; fall back to APK app discovery route."""
        if self._discovery_method == "systems":
            try:
                data = await self._graphql("getEntryLevelSystems", SYSTEMS_QUERY,
                                           {"username": self.username})
                systems = data.get("entryLevelSystems")
                if not isinstance(systems, list):
                    raise CarrierQueryError("Carrier did not return an entry-level systems list")
                if any(not isinstance(system, dict) for system in systems):
                    raise CarrierTransportError("Carrier returned an invalid system")
                if systems:
                    return systems
                # A successful empty response can mean this model appears only
                # in the app's per-location entryLevels list.
                self._discovery_method = "user_devices"
            except CarrierQueryError:
                # Only try an alternate schema after a query-level rejection,
                # not for DNS/HTTP errors or expired authentication.
                self._discovery_method = "user_devices"
        user_data = await self._graphql("getUserWithDevices", USER_DEVICES_QUERY,
                                        {"userName": self.username, "appVersion": "1.2.42",
                                         "brand": "Carrier", "os": "Android"})
        user = user_data.get("user")
        if not isinstance(user, dict):
            raise CarrierTransportError("Carrier did not return a user device listing")
        serials: list[str] = []
        for location in user.get("locations") or []:
            if not isinstance(location, dict):
                continue
            for device in location.get("entryLevels") or []:
                if isinstance(device, dict):
                    serial = device.get("serial")
                    if isinstance(serial, str) and serial and serial not in serials:
                        serials.append(serial)
        systems: list[dict[str, Any]] = []
        for serial in serials:
            detail = await self._graphql("getEntryLevelSystemData", DETAIL_QUERY, {"serial": serial})
            system = detail.get("entryLevelSystem")
            if isinstance(system, dict):
                systems.append(system)
        return systems

    async def async_get_user_connection_inventory(self) -> list[dict[str, Any]]:
        """Read app-style connection flags and device hardware identities.

        This is a *separate*, not yet owner-verified GraphQL path; do not use it
        to declare a thermostat online or to modify device availability.
        Results MUST be kept locally, never logged, uploaded, or written to disk.
        """
        data = await self._graphql("getUserWithDevices", USER_CONNECTIONS_QUERY,
                                   {"userName": self.username, "appVersion": "1.2.42",
                                    "brand": "Carrier", "os": "Android"})
        user = data.get("user")
        if not isinstance(user, dict) or not isinstance(user.get("locations"), list):
            raise CarrierQueryError("Carrier did not return app device locations")
        result: list[dict[str, Any]] = []
        for location in user["locations"][:40]:
            if not isinstance(location, dict) or not isinstance(location.get("entryLevels"), list):
                continue
            for device in location["entryLevels"][:40]:
                if not isinstance(device, dict):
                    continue
                serial = device.get("serial")
                if not isinstance(serial, str) or not serial:
                    continue
                connection = device.get("connection")
                result.append({"serial": serial,
                               "connection": connection if isinstance(connection, dict) else {}})
        return result

    async def async_get_entry_level_feature(self, serial: str, feature: str) -> Any:
        """Optional owner-authorized read-only capability probe from APK documents.

        This method does not imply the backend enables a feature for this model.
        No mutation or direct LAN request is ever sent.
        """
        if not isinstance(serial, str) or not serial or len(serial) > 128:
            raise ValueError("Invalid Carrier device identity")
        definitions = {
            "schedules": ("getEntryLevelSchedules", SCHEDULES_QUERY, "entryLevelSchedules"),
            "reminders": ("getEntryLevelReminders", REMINDERS_QUERY, "entryLevelReminders"),
            "notification_prefs": (
                "getEntryLevelNotificationPrefs", NOTIFICATION_PREFS_QUERY,
                "entryLevelNotificationPrefs",
            ),
        }
        if feature not in definitions:
            raise ValueError("Unsupported Carrier feature probe")
        name, document, key = definitions[feature]
        result = await self._graphql(name, document, {"serial": serial})
        if key not in result or result[key] is None:
            raise CarrierQueryError("Carrier did not provide feature data")
        value = result[key]
        if not isinstance(value, (dict, list)):
            raise CarrierQueryError("Carrier returned an unexpected feature response")
        return value

    async def async_get_system_detail(self, serial: str) -> dict[str, Any]:
        """Cross-check a single entry-level device using the APK-derived query.

        Read-only: intended for diagnostics. Some Carrier accounts may expose
        the summary query without the detailed query; callers handle rejection.
        """
        if not isinstance(serial, str) or not serial or len(serial) > 128:
            raise ValueError("Invalid Carrier device identity")
        result = await self._graphql("getEntryLevelSystemData", DETAIL_QUERY,
                                     {"serial": serial})
        system = result.get("entryLevelSystem")
        if not isinstance(system, dict):
            raise CarrierQueryError("Carrier detail query did not return a device")
        return system

    async def async_get_extended_detail(self, serial: str) -> dict[str, Any]:
        """APK-derived optional detailed read. Rejection must not disable the
        independently verified baseline entry-level system polling route.
        """
        if not isinstance(serial, str) or not serial or len(serial) > 128:
            raise ValueError("Invalid Carrier device identity")
        result = await self._graphql("getEntryLevelSystemData", EXTENDED_DETAIL_QUERY,
                                     {"serial": serial})
        system = result.get("entryLevelSystem")
        if not isinstance(system, dict) or system.get("serial") != serial:
            raise CarrierQueryError("Carrier extended detail did not match the device")
        return system

    async def async_update_zone(self, serial: str, index: int, *,
                                mode: str | None = None,
                                heat: float | None = None, cool: float | None = None,
                                fan: str | None = None) -> None:
        if not isinstance(serial, str) or not serial or len(serial) > 128 or type(index) is not int or index < 0:
            raise ValueError("Invalid Carrier zone identity")
        inp: dict[str, Any] = {"serial": serial, "index": index}
        if mode is not None:
            if mode not in ("off", "heat", "cool", "auto", "fanonly"):
                raise ValueError("Unsupported Carrier HVAC mode")
            inp["mode"] = mode
        if (heat is None) != (cool is None):
            raise ValueError("Carrier setpoint mutations require both heat and cool values")
        if heat is not None and cool is not None:
            if not (isinstance(heat, (int, float)) and isinstance(cool, (int, float)) and
                    not isinstance(heat, bool) and not isinstance(cool, bool) and
                    math.isfinite(heat) and math.isfinite(cool) and
                    0 <= heat <= 120 and 0 <= cool <= 120 and heat <= cool):
                raise ValueError("Invalid Carrier thermostat setpoints")
            inp["htsp"] = {"current": heat}
            inp["clsp"] = {"current": cool}
        if fan is not None:
            # Two experimentally supported values only: the actual cloud has
            # reported auto, and Carrier documents an On option. The API's
            # exact enum for Circulation is unknown; never invent it.
            if fan not in ("auto", "on"):
                raise ValueError("Unverified Carrier fan mode (only auto/on allowed)")
            inp["fan_mode"] = fan
        if len(inp) == 2:
            raise ValueError("No Carrier zone change requested")
        result = await self._graphql("updateEntryLevelZone", ZONE_UPDATE, {"input": inp})
        success = result.get("updateEntryLevelZone")
        if not isinstance(success, dict) or success.get("success") is not True:
            raise CarrierTransportError("Carrier did not confirm the thermostat change")
