"""Config flow for otodo integration."""

from __future__ import annotations

import aiohttp
import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import OtodoAPI
from .const import CONF_API_KEY, CONF_URL, DOMAIN

DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_URL): str,
        vol.Required(CONF_API_KEY): str,
    }
)


class OtodoConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for otodo."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, str] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            session = async_get_clientsession(self.hass)
            api = OtodoAPI(user_input[CONF_URL], user_input[CONF_API_KEY], session)
            try:
                if await api.validate():
                    await self.async_set_unique_id(user_input[CONF_URL])
                    self._abort_if_unique_id_configured()
                    return self.async_create_entry(
                        title="otodo", data=user_input
                    )
                errors["base"] = "invalid_auth"
            except aiohttp.ClientError:
                errors["base"] = "cannot_connect"

        return self.async_show_form(
            step_id="user", data_schema=DATA_SCHEMA, errors=errors
        )
