"""Config flow for ADT Pulse integration."""
from __future__ import annotations

import logging
from typing import Any
from collections.abc import Mapping

import aiohttp
import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import ADTPulseAPI, ADTPulseAuthError, ADTPulseAPIError
from .const import CONF_FINGERPRINT, DOMAIN

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_USERNAME): str,
        vol.Required(CONF_PASSWORD): str,
        vol.Required(CONF_FINGERPRINT): str,
    }
)


class ADTPulseConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the initial setup flow for ADT Pulse."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Show the credentials form and validate on submit."""
        errors: dict[str, str] = {}

        if user_input is not None:
            await self.async_set_unique_id(user_input[CONF_USERNAME].lower())
            self._abort_if_unique_id_configured()

            session = async_get_clientsession(self.hass)
            api = ADTPulseAPI(
                username=user_input[CONF_USERNAME],
                password=user_input[CONF_PASSWORD],
                fingerprint=user_input[CONF_FINGERPRINT],
                session=session,
            )

            try:
                await api.async_login()
            except ADTPulseAuthError:
                errors["base"] = "invalid_auth"
            except ADTPulseAPIError:
                errors["base"] = "cannot_connect"
            except Exception:  # noqa: BLE001
                _LOGGER.exception("Unexpected error during ADT Pulse login")
                errors["base"] = "unknown"
            else:
                await api.async_logout()
                return self.async_create_entry(
                    title=f"ADT Pulse ({user_input[CONF_USERNAME]})",
                    data=user_input,
                )

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
            description_placeholders={
                "fingerprint_help": (
                    "A unique device identifier string required by ADT Pulse 2FA. "
                    "Obtain it from your existing ADT Pulse mobile app session."
                )
            },
        )

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        """Handle re-authentication when credentials expire."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Show re-auth form and update the existing entry on success."""
        errors: dict[str, str] = {}
        reauth_entry = self._get_reauth_entry()

        if user_input is not None:
            session = async_get_clientsession(self.hass)
            api = ADTPulseAPI(
                username=user_input[CONF_USERNAME],
                password=user_input[CONF_PASSWORD],
                fingerprint=user_input[CONF_FINGERPRINT],
                session=session,
            )
            try:
                await api.async_login()
            except ADTPulseAuthError:
                errors["base"] = "invalid_auth"
            except ADTPulseAPIError:
                errors["base"] = "cannot_connect"
            except Exception:  # noqa: BLE001
                _LOGGER.exception("Unexpected error during ADT Pulse re-auth")
                errors["base"] = "unknown"
            else:
                await api.async_logout()
                return self.async_update_reload_and_abort(
                    reauth_entry,
                    data_updates=user_input,
                )

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=self.add_suggested_values_to_schema(
                STEP_USER_DATA_SCHEMA,
                reauth_entry.data,
            ),
            errors=errors,
        )
