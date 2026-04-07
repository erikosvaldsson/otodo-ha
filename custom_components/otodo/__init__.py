"""The otodo integration."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import timedelta
import logging

import aiohttp

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .api import OtodoAPI
from .const import CONF_API_KEY, CONF_URL, DOMAIN
from . import todo as todo  # noqa: F401 - eager import to avoid blocking call in event loop

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.TODO]
FALLBACK_SCAN_INTERVAL = timedelta(minutes=5)


@dataclass
class OtodoData:
    """Runtime data for the otodo integration."""

    api: OtodoAPI
    coordinator: DataUpdateCoordinator[dict[int, dict]]


type OtodoConfigEntry = ConfigEntry[OtodoData]


async def _listen_sse(
    hass: HomeAssistant,
    api: OtodoAPI,
    coordinator: DataUpdateCoordinator,
) -> None:
    """Listen to SSE events from otodo and trigger coordinator refreshes."""
    url = f"{api._url}/api/events"
    session = async_get_clientsession(hass)
    timeout = aiohttp.ClientTimeout(total=0)

    while True:
        try:
            async with session.get(
                url, headers=api._headers, timeout=timeout
            ) as resp:
                if resp.status != 200:
                    _LOGGER.warning("SSE endpoint returned %s", resp.status)
                else:
                    while True:
                        line = await resp.content.readline()
                        if not line:
                            break
                        if line.decode().strip().startswith("data:"):
                            await coordinator.async_request_refresh()
        except asyncio.CancelledError:
            return
        except Exception:
            _LOGGER.debug("SSE connection lost, reconnecting", exc_info=True)
        await asyncio.sleep(30)


async def async_setup_entry(hass: HomeAssistant, entry: OtodoConfigEntry) -> bool:
    session = async_get_clientsession(hass)
    api = OtodoAPI(entry.data[CONF_URL], entry.data[CONF_API_KEY], session)

    async def _async_update_data() -> dict[int, dict]:
        projects = await api.list_projects()
        result: dict[int, dict] = {}
        for p in projects:
            result[p["id"]] = {
                "name": p["name"],
                "todos": await api.list_todos(p["id"]) or [],
            }
        return result

    coordinator: DataUpdateCoordinator[dict[int, dict]] = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name=DOMAIN,
        update_method=_async_update_data,
        update_interval=FALLBACK_SCAN_INTERVAL,
    )

    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = OtodoData(api=api, coordinator=coordinator)

    task = hass.async_create_background_task(
        _listen_sse(hass, api, coordinator), f"{DOMAIN}_sse"
    )
    entry.async_on_unload(lambda: task.cancel())

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: OtodoConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
