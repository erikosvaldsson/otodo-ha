"""Config flow for otodo integration."""

from __future__ import annotations

from collections.abc import Mapping
import logging
from typing import Any

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_API_KEY, CONF_URL, CONF_VERIFY_SSL
from homeassistant.helpers.selector import (
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)
import voluptuous as vol

from . import api_from_data
from .api import (
    OtodoAuthError,
    OtodoCertificateError,
    OtodoError,
    OtodoFingerprintError,
    OtodoHTTPSRequiredError,
    OtodoTLSHandshakeError,
    parse_fingerprint,
)
from .const import CONF_FINGERPRINT, DOMAIN

_LOGGER = logging.getLogger(__name__)

CONNECTION_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_URL): TextSelector(TextSelectorConfig(type=TextSelectorType.URL)),
        vol.Required(CONF_API_KEY): TextSelector(
            TextSelectorConfig(type=TextSelectorType.PASSWORD)
        ),
        vol.Required(CONF_VERIFY_SSL, default=True): bool,
        vol.Optional(CONF_FINGERPRINT): str,
    }
)

REAUTH_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_API_KEY): TextSelector(
            TextSelectorConfig(type=TextSelectorType.PASSWORD)
        ),
    }
)


def _normalize(user_input: dict[str, Any]) -> dict[str, Any]:
    """Return complete entry data from form input.

    Every key is always present, so clearing the fingerprint on reconfigure
    removes it instead of keeping the old value.
    """
    return {
        CONF_URL: user_input[CONF_URL].strip().rstrip("/"),
        CONF_API_KEY: user_input[CONF_API_KEY].strip(),
        CONF_VERIFY_SSL: user_input.get(CONF_VERIFY_SSL, True),
        CONF_FINGERPRINT: (user_input.get(CONF_FINGERPRINT) or "").strip(),
    }


class OtodoConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for otodo."""

    VERSION = 1

    async def _validate(self, data: dict[str, Any]) -> dict[str, str]:
        """Try the connection; return form errors keyed by field ("base" for general)."""
        if data[CONF_FINGERPRINT]:
            try:
                parse_fingerprint(data[CONF_FINGERPRINT])
            except ValueError:
                return {CONF_FINGERPRINT: "invalid_fingerprint"}
        try:
            await api_from_data(self.hass, data).validate()
        except OtodoAuthError:
            return {"base": "invalid_auth"}
        except OtodoHTTPSRequiredError:
            return {CONF_URL: "https_required"}
        except OtodoFingerprintError:
            return {CONF_FINGERPRINT: "fingerprint_mismatch"}
        except OtodoCertificateError:
            return {"base": "certificate_untrusted"}
        except OtodoTLSHandshakeError:
            return {"base": "tls_handshake"}
        except OtodoError as err:
            _LOGGER.debug("otodo connection check failed: %s", err)
            return {"base": "cannot_connect"}
        except Exception:
            _LOGGER.exception("Unexpected error validating otodo connection")
            return {"base": "unknown"}
        return {}

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            data = _normalize(user_input)
            await self.async_set_unique_id(data[CONF_URL])
            self._abort_if_unique_id_configured()
            errors = await self._validate(data)
            if not errors:
                return self.async_create_entry(title="otodo", data=data)

        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(CONNECTION_SCHEMA, user_input),
            errors=errors,
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Change the URL, key or TLS settings without re-adding the integration.

        Entities are keyed by entry id, so they and their history survive.
        """
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            data = _normalize(user_input)
            other = self.hass.config_entries.async_entry_for_domain_unique_id(
                DOMAIN, data[CONF_URL]
            )
            if other is not None and other.entry_id != entry.entry_id:
                return self.async_abort(reason="already_configured")
            errors = await self._validate(data)
            if not errors:
                return self.async_update_reload_and_abort(
                    entry, unique_id=data[CONF_URL], data=data
                )

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self.add_suggested_values_to_schema(
                CONNECTION_SCHEMA, user_input or dict(entry.data)
            ),
            errors=errors,
        )

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        entry = self._get_reauth_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            data = _normalize({**entry.data, CONF_API_KEY: user_input[CONF_API_KEY]})
            errors = await self._validate(data)
            if not errors:
                return self.async_update_reload_and_abort(entry, data=data)

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=REAUTH_SCHEMA,
            description_placeholders={"url": entry.data[CONF_URL]},
            errors=errors,
        )
