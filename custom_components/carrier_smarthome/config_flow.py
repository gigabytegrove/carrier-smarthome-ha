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
from .matter_discovery import find_home_assistant_matter, HA_MATTER_SOURCE
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
    """One-time Carrier-to-HA-Matter selection; no manual controller fields."""

    def __init__(self):
        self._target = None
        self._policy = CLOUD_ONLY
        self._source = None
        self._fabric = None
        self._candidates = {}
        self._candidate = None

    def _existing(self):
        raw = self.config_entry.options.get(OPTIONS_BINDINGS, {})
        return dict(raw) if isinstance(raw, dict) else {}

    def _save(self, existing):
        return self.async_create_entry(
            title="", data={**self.config_entry.options, OPTIONS_BINDINGS: existing})

    def _is_duplicate(self, existing, *, url, node_id, endpoint, source_entry_id=None):
        for target, previous in existing.items():
            if target == self._target or not isinstance(previous, dict):
                continue
            if (previous.get("node_id") != node_id
                    or previous.get("endpoint") != endpoint):
                continue
            if source_entry_id and previous.get("matter_entry_id") == source_entry_id:
                return True
            if previous.get("url") == url:
                return True
        return False

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
            target = user_input["target"]
            if target not in choices:
                return self.async_abort(reason="no_devices")
            self._target = target
            return await self.async_step_transport()
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({vol.Required("target"): vol.In(choices)}))

    async def async_step_transport(self, user_input=None):
        existing = self._existing()
        prior = existing.get(self._target, {})
        if user_input is not None:
            self._policy = user_input["policy"]
            if self._policy == CLOUD_ONLY:
                existing.pop(self._target, None)
                return self._save(existing)
            return await self.async_step_auto()
        return self.async_show_form(step_id="transport", data_schema=vol.Schema({
            vol.Required("policy", default=prior.get("policy", CLOUD_ONLY)): vol.In({
                CLOUD_ONLY: "Carrier cloud only",
                MATTER_ONLY: "Local Matter only",
                MATTER_PREFERRED: "Prefer local Matter, then cloud",
            }),
        }))

    async def async_step_auto(self, user_input=None):
        """Use the native Home Assistant Matter fabric without a server URL."""
        source = find_home_assistant_matter(self.hass)
        if source is None:
            return await self.async_step_matter_required()
        self._source = source
        session = async_get_clientsession(self.hass)
        try:
            client = MatterWsClient(session, source.server_url, 1, 1,
                                    trusted_ha_source=True)
            self._fabric, found = await client.discover_thermostats()
            self._candidates = {f"{c['node_id']}:{c['endpoint']}": c
                                for c in found}
        except MatterNotReady:
            return await self.async_step_matter_required()
        if not self._candidates:
            return await self.async_step_matter_required()
        if user_input is not None:
            candidate_id = user_input["candidate"]
            if candidate_id not in self._candidates:
                return self.async_show_form(
                    step_id="auto", errors={"base": "matter_not_ready"},
                    data_schema=vol.Schema({
                        vol.Required("candidate"): vol.In({
                            key: f"Carrier Matter thermostat (node {value['node_id']}, endpoint {value['endpoint']})"
                            for key, value in self._candidates.items()})}))
            self._candidate = self._candidates[candidate_id]
            return await self.async_step_confirm()
        choices = {
            key: f"Carrier Matter thermostat (node {value['node_id']}, endpoint {value['endpoint']})"
            for key, value in self._candidates.items()
        }
        return self.async_show_form(
            step_id="auto",
            data_schema=vol.Schema({vol.Required("candidate"): vol.In(choices)}))

    async def async_step_confirm(self, user_input=None):
        errors = {}
        if user_input is not None:
            if user_input.get("verified_same_device") is not True:
                errors["base"] = "identity_not_verified"
            else:
                source = find_home_assistant_matter(self.hass)
                if source is None or source.entry_id != self._source.entry_id:
                    errors["base"] = "matter_not_ready"
                else:
                    candidate = self._candidate
                    existing = self._existing()
                    try:
                        client = MatterWsClient(
                            async_get_clientsession(self.hass), source.server_url,
                            candidate["node_id"], candidate["endpoint"],
                            trusted_ha_source=True,
                            expected_fabric_id=self._fabric)
                        # Recheck live device identity and fabric at save time.
                        await client.get_state()
                        if self._is_duplicate(
                                existing, url=source.server_url,
                                node_id=candidate["node_id"],
                                endpoint=candidate["endpoint"],
                                source_entry_id=source.entry_id):
                            raise ValueError("Matter thermostat already linked")
                    except (MatterNotReady, ValueError, TypeError):
                        errors["base"] = "matter_not_ready"
                    else:
                        existing[self._target] = {
                            "source": HA_MATTER_SOURCE,
                            "matter_entry_id": source.entry_id,
                            "fabric_id": self._fabric,
                            "policy": self._policy,
                            "node_id": candidate["node_id"],
                            "endpoint": candidate["endpoint"],
                        }
                        return self._save(existing)
        return self.async_show_form(
            step_id="confirm", errors=errors,
            data_schema=vol.Schema({
                vol.Required("verified_same_device", default=False): bool,
            }))

    async def async_step_matter_required(self, user_input=None):
        """Explain native HA commissioning; retain advanced legacy migration."""
        if user_input is not None:
            if user_input["next_action"] == "advanced":
                return await self.async_step_advanced()
            return await self.async_step_auto()
        return self.async_show_form(
            step_id="matter_required", data_schema=vol.Schema({
                vol.Required("next_action"): vol.In({
                    "retry": "I added my device to Home Assistant Matter — retry",
                    "advanced": "Advanced: connect an existing Matter Server",
                }),
            }))

    async def async_step_advanced(self, user_input=None):
        """Expert/manual backwards-compatible path; never silently install a daemon."""
        existing = self._existing()
        previous = existing.get(self._target, {})
        errors = {}
        if user_input is not None:
            if user_input.get("verified_same_device") is not True:
                errors["base"] = "identity_not_verified"
            else:
                try:
                    client = MatterWsClient(
                        async_get_clientsession(self.hass), user_input["url"].strip(),
                        user_input["node_id"], user_input["endpoint"])
                    await client.get_state()
                    if self._is_duplicate(
                            existing, url=client.server_url,
                            node_id=client.node_id, endpoint=client.endpoint):
                        raise MatterNotReady("Matter device already linked")
                except (MatterNotReady, ValueError, TypeError, KeyError):
                    errors["base"] = "matter_not_ready"
                else:
                    existing[self._target] = {
                        "policy": self._policy, "url": client.server_url,
                        "node_id": client.node_id, "endpoint": client.endpoint,
                    }
                    return self._save(existing)
        return self.async_show_form(
            step_id="advanced", errors=errors, data_schema=vol.Schema({
                vol.Required("url", default=previous.get(
                    "url", "ws://127.0.0.1:5580/ws")): str,
                vol.Required("node_id", default=previous.get("node_id", 1)):
                    vol.All(vol.Coerce(int), vol.Range(min=1, max=2**64 - 1)),
                vol.Required("endpoint", default=previous.get("endpoint", 1)):
                    vol.All(vol.Coerce(int), vol.Range(min=1, max=240)),
                vol.Required("verified_same_device", default=False): bool,
            }))
