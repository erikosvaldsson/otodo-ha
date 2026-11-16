"""The otodo integration."""

from __future__ import annotations

from homeassistant.const import CONF_API_KEY, CONF_URL, CONF_VERIFY_SSL, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from . import todo as todo  # noqa: F401 - eager import to avoid blocking call in event loop
from .api import OtodoAPI
from .const import CONF_FINGERPRINT, DOMAIN
from .coordinator import OtodoConfigEntry, OtodoCoordinator, OtodoData

PLATFORMS = [Platform.TODO]


def api_from_data(hass: HomeAssistant, data: dict) -> OtodoAPI:
    """Build an API client from config entry data (or config flow input)."""
    return OtodoAPI(
        data[CONF_URL],
        data[CONF_API_KEY],
        async_get_clientsession(hass),
        # Entries created before HTTPS support lack these keys.
        verify_ssl=data.get(CONF_VERIFY_SSL, True),
        fingerprint=data.get(CONF_FINGERPRINT) or None,
    )


async def async_setup_entry(hass: HomeAssistant, entry: OtodoConfigEntry) -> bool:
    api = api_from_data(hass, dict(entry.data))
    coordinator = OtodoCoordinator(hass, entry, api)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = OtodoData(api=api, coordinator=coordinator)

    entry.async_create_background_task(
        hass, coordinator.async_listen_events(), f"{DOMAIN}_events"
    )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: OtodoConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
