"""Account sign-in flow for Carrier SmartHome entry-tier systems."""
from __future__ import annotations

import logging

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import TextSelector, TextSelectorConfig, TextSelectorType

from .api import CarrierAuthError, CarrierError, CarrierSmartHomeClient
from .const import DOMAIN
from .models import zone_indices
from .matter_client import MatterWsClient
from .matter_protocol import CLOUD_ONLY, MATTER_ONLY, MATTER_PREFERRED, MatterNotReady
from .matter_runtime import OPTIONS_BINDINGS, binding_key

_LOGGER = logging.getLogger(__name__)


def _credentials_schema(defaults: dict | None = None):
    defaults = defaults or {}
    return vol.Schema({
        vol.Required(CONF_USERNAME, default=defaults.get(CONF_USERNAME, "")): str,
        vol.Required(CONF_PASSWORD): TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD)),
    })


class CarrierSmartHomeConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 2

    @staticmethod
    def async_get_options_flow(config_entry):
        return CarrierSmartHomeOptionsFlow()

    async def async_step_user(self, user_input=None):
        errors = {}
        if user_input is not None:
            username = user_input[CONF_USERNAME].strip()
            password = user_input[CONF_PASSWORD]
            if not username or not password:
                errors["base"] = "invalid_auth"
            else:
                client = CarrierSmartHomeClient(async_get_clientsession(self.hass), username, password)
                try:
                    systems = await client.async_get_systems()
                except CarrierAuthError:
                    errors["base"] = "invalid_auth"
                except CarrierError:
                    errors["base"] = "cannot_connect"
                else:
                    if not systems:
                        errors["base"] = "no_devices"
                    else:
                        await self.async_set_unique_id(username.casefold())
                        self._abort_if_unique_id_configured()
                        return self.async_create_entry(
                            title="Carrier SmartHome",
                            data={CONF_USERNAME: username, CONF_PASSWORD: password})
        return self.async_show_form(step_id="user", data_schema=_credentials_schema(user_input), errors=errors)

    async def async_step_reauth(self, entry_data):
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input=None):
        errors = {}
        entry = self._get_reauth_entry()
        if user_input is not None:
            username = entry.data[CONF_USERNAME]
            password = user_input[CONF_PASSWORD]
            try:
                await CarrierSmartHomeClient(async_get_clientsession(self.hass), username,
                                             password).async_get_systems()
            except CarrierAuthError:
                errors["base"] = "invalid_auth"
            except CarrierError:
                errors["base"] = "cannot_connect"
            else:
                return self.async_update_reload_and_abort(entry, data_updates={CONF_PASSWORD: password})
        return self.async_show_form(step_id="reauth_confirm",
                                    data_schema=vol.Schema({vol.Required(CONF_PASSWORD): TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD))}), errors=errors)




class CarrierSmartHomeOptionsFlow(config_entries.OptionsFlow):
    """Bind one explicitly chosen Carrier serial/zone to a commissioned Matter node."""

    def __init__(self):
        self._target = None

    async def async_step_init(self, user_input=None):
        coordinator = self.hass.data.get(DOMAIN, {}).get(self.config_entry.entry_id)
        systems = getattr(coordinator, "data", None) or {}
        choices = {
            binding_key(serial, zone): f"{system.get('name') or 'Carrier Thermostat'} (zone {zone})"
            for serial, system in systems.items()
            for zone in zone_indices(system)
        }
        if not choices:
            return self.async_abort(reason="no_devices")
        if user_input is not None:
            self._target = user_input["target"]
            if self._target not in choices:
                return self.async_abort(reason="no_devices")
            return await self.async_step_transport()
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({vol.Required("target"): vol.In(choices)}),
        )

    async def async_step_transport(self, user_input=None):
        existing = dict(self.config_entry.options.get(OPTIONS_BINDINGS, {}))
        binding = existing.get(self._target, {})
        errors = {}
        if user_input is not None:
            policy = user_input["policy"]
            if policy == CLOUD_ONLY:
                existing.pop(self._target, None)
                return self.async_create_entry(title="", data={
                    **self.config_entry.options, OPTIONS_BINDINGS: existing
                })
            if user_input.get("verified_same_device") is not True:
                errors["base"] = "identity_not_verified"
            try:
                if errors:
                    raise MatterNotReady("Identity confirmation required")
                url = user_input["url"].strip()
                node_id = int(user_input["node_id"])
                endpoint = int(user_input["endpoint"])
                client = MatterWsClient(async_get_clientsession(self.hass),
                                        url, node_id, endpoint)
                # Read-only verification: matching certified VID/PID,
                # commissioned/online node and thermostat endpoint.
                await client.get_state()
                if any(
                    previous.get("url") == client.server_url
                    and previous.get("node_id") == node_id
                    and previous.get("endpoint") == endpoint
                    for target, previous in existing.items()
                    if target != self._target and isinstance(previous, dict)
                ):
                    raise ValueError("Matter node/endpoint already bound to another Carrier thermostat")
            except (MatterNotReady, ValueError, TypeError, KeyError):
                errors.setdefault("base", "matter_not_ready")
            except Exception:
                _LOGGER.exception("Matter server check failed during configuration")
                errors["base"] = "matter_not_ready"
            else:
                existing[self._target] = {
                    "policy": policy, "url": client.server_url,
                    "node_id": node_id, "endpoint": endpoint,
                }
                return self.async_create_entry(title="", data={
                    **self.config_entry.options, OPTIONS_BINDINGS: existing
                })
        return self.async_show_form(step_id="transport", errors=errors,
                                    data_schema=vol.Schema({
            vol.Required("policy", default=binding.get("policy", CLOUD_ONLY)):
                vol.In({CLOUD_ONLY: "Carrier cloud only",
                        MATTER_ONLY: "Local Matter only",
                        MATTER_PREFERRED: "Prefer local Matter, then cloud"}),
            vol.Optional("url", default=binding.get("url", "ws://127.0.0.1:5580/ws")): str,
            vol.Optional("node_id", default=binding.get("node_id", 1)):
                vol.All(vol.Coerce(int), vol.Range(min=1, max=2**64 - 1)),
            vol.Optional("endpoint", default=binding.get("endpoint", 1)):
                vol.All(vol.Coerce(int), vol.Range(min=1, max=240)),
            vol.Required("verified_same_device", default=False): bool,
        }))
