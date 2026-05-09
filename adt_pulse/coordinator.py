"""DataUpdateCoordinator for ADT Pulse."""
from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import ADTPulseAPI, ADTPulseAuthError, ADTPulseAPIError, ADTPulseData
from .const import DOMAIN, UPDATE_INTERVAL_SECONDS

_LOGGER = logging.getLogger(__name__)


class ADTPulseCoordinator(DataUpdateCoordinator[ADTPulseData]):
    """Manages periodic polling and authentication lifecycle."""

    def __init__(
        self,
        hass: HomeAssistant,
        api: ADTPulseAPI,
        entry: ConfigEntry,
    ) -> None:
        self.api = api
        self.entry = entry
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=UPDATE_INTERVAL_SECONDS),
        )

    async def _async_update_data(self) -> ADTPulseData:
        """Fetch latest data from the ADT Pulse portal."""
        try:
            if not self.api.is_authenticated:
                await self.api.async_login()
            return await self.api.async_fetch_all()
        except ADTPulseAuthError as err:
            # Credentials are wrong — require the user to re-configure
            raise ConfigEntryAuthFailed(str(err)) from err
        except ADTPulseAPIError as err:
            raise UpdateFailed(str(err)) from err
