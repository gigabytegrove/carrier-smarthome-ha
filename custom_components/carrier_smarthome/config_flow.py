"""Account sign-in flow for Carrier SmartHome entry-tier systems."""
from __future__ import annotations

import logging

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import CarrierAuthError, CarrierError, CarrierSmartHomeClient
from .const import CONF_ENABLE_CONTROL, DEFAULT_ENABLE_CONTROL, DOMAIN

_LOGGER = logging.getLogger(__name__)


def _credentials_schema(defaults: dict | None = None):
    defaults = defaults or {}
    return vol.Schema({
        vol.Required(CONF_USERNAME, default=defaults.get(CONF_USERNAME, "")): str,
        vol.Required(CONF_PASSWORD): str,
    })


class CarrierSmartHomeConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

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
                            data={CONF_USERNAME: username, CONF_PASSWORD: password},
                            options={CONF_ENABLE_CONTROL: DEFAULT_ENABLE_CONTROL})
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
                                    data_schema=vol.Schema({vol.Required(CONF_PASSWORD): str}), errors=errors)

    @staticmethod
    def async_get_options_flow(config_entry):
        return CarrierOptionsFlow()


class CarrierOptionsFlow(config_entries.OptionsFlow):
    async def async_step_init(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(data={CONF_ENABLE_CONTROL: bool(user_input[CONF_ENABLE_CONTROL])})
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({vol.Required(CONF_ENABLE_CONTROL,
                default=self.config_entry.options.get(CONF_ENABLE_CONTROL, DEFAULT_ENABLE_CONTROL)): bool}),
        )
