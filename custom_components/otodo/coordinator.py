"""Data coordinator for the otodo integration."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import OtodoAPI, OtodoAuthError, OtodoError
from .const import DOMAIN, FALLBACK_SCAN_INTERVAL, SSE_RECONNECT_DELAY

_LOGGER = logging.getLogger(__name__)


@dataclass
class OtodoData:
    """Runtime data for the otodo integration."""

    api: OtodoAPI
    coordinator: OtodoCoordinator


type OtodoConfigEntry = ConfigEntry[OtodoData]


class OtodoCoordinator(DataUpdateCoordinator[dict[int, dict]]):
    """Fetches every active project and its todos, keyed by project id."""

    config_entry: OtodoConfigEntry

    def __init__(self, hass: HomeAssistant, entry: OtodoConfigEntry, api: OtodoAPI) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=FALLBACK_SCAN_INTERVAL,
        )
        self.api = api

    async def _async_update_data(self) -> dict[int, dict]:
        try:
            projects = await self.api.list_projects()
            todos = await asyncio.gather(
                *(self.api.list_todos(p["id"]) for p in projects)
            )
        except OtodoAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except OtodoError as err:
            raise UpdateFailed(str(err)) from err
        return {
            p["id"]: {"name": p["name"], "todos": t}
            for p, t in zip(projects, todos, strict=True)
        }

    async def async_listen_events(self) -> None:
        """Refresh on every otodo change event, reconnecting forever.

        Runs as a config entry background task, so unloading cancels it.
        """
        reconnecting = False
        while True:
            try:
                if reconnecting:
                    # Catch up on anything missed while disconnected.
                    await self.async_request_refresh()
                reconnecting = True
                async for _ in self.api.events():
                    await self.async_request_refresh()
                _LOGGER.debug("otodo event stream closed, reconnecting")
            except OtodoAuthError:
                # The coordinator raises ConfigEntryAuthFailed and starts
                # reauthentication; reconnecting with the same key is pointless.
                _LOGGER.warning("otodo rejected the API key on the event stream")
                return
            except OtodoError as err:
                _LOGGER.debug("otodo event stream failed: %s", err)
            await asyncio.sleep(SSE_RECONNECT_DELAY)
