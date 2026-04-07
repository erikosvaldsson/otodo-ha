"""The otodo integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import OtodoAPI
from .const import CONF_API_KEY, CONF_URL, DOMAIN
from . import todo as todo  # noqa: F401 - eager import to avoid blocking call in event loop

PLATFORMS = [Platform.TODO]

type OtodoConfigEntry = ConfigEntry[OtodoAPI]


async def async_setup_entry(hass: HomeAssistant, entry: OtodoConfigEntry) -> bool:
    session = async_get_clientsession(hass)
    entry.runtime_data = OtodoAPI(
        entry.data[CONF_URL], entry.data[CONF_API_KEY], session
    )
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: OtodoConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
