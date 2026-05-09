"""Tests for ADTPulseCoordinator._async_update_data error-handling logic."""
from __future__ import annotations

from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from adt_pulse.api import (
    ADTPulseAPIError,
    ADTPulseAuthError,
    ADTPulseData,
    PanelStatus,
)
from adt_pulse.coordinator import ADTPulseCoordinator

# The homeassistant stubs are injected via tests/conftest.py.
# Import the stub exception classes so we can reference them.
from homeassistant.exceptions import ConfigEntryAuthFailed  # type: ignore[import]
from homeassistant.helpers.update_coordinator import UpdateFailed  # type: ignore[import]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_coordinator(api: MagicMock) -> ADTPulseCoordinator:
    hass = MagicMock()
    entry = MagicMock()
    coordinator = ADTPulseCoordinator(hass, api, entry)
    return coordinator


def _mock_api(*, is_authenticated: bool = True) -> MagicMock:
    api = MagicMock()
    api.is_authenticated = is_authenticated
    api.async_login = AsyncMock()
    api.async_fetch_all = AsyncMock(
        return_value=ADTPulseData(panel=PanelStatus())
    )
    api.reset_authentication = MagicMock()
    return api


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestAsyncUpdateData:
    async def test_fetches_data_when_authenticated(self):
        api = _mock_api(is_authenticated=True)
        coordinator = _make_coordinator(api)

        result = await coordinator._async_update_data()

        api.async_login.assert_not_called()
        api.async_fetch_all.assert_called_once()
        assert isinstance(result, ADTPulseData)

    async def test_logs_in_first_when_not_authenticated(self):
        api = _mock_api(is_authenticated=False)
        coordinator = _make_coordinator(api)

        await coordinator._async_update_data()

        api.async_login.assert_called_once()
        api.async_fetch_all.assert_called_once()

    async def test_auth_error_raises_config_entry_auth_failed(self):
        api = _mock_api(is_authenticated=True)
        api.async_fetch_all = AsyncMock(
            side_effect=ADTPulseAuthError("bad credentials")
        )
        coordinator = _make_coordinator(api)

        with pytest.raises(ConfigEntryAuthFailed):
            await coordinator._async_update_data()

    async def test_api_error_raises_update_failed(self):
        api = _mock_api(is_authenticated=True)
        api.async_fetch_all = AsyncMock(
            side_effect=ADTPulseAPIError("connection lost")
        )
        coordinator = _make_coordinator(api)

        with pytest.raises(UpdateFailed):
            await coordinator._async_update_data()

    async def test_api_error_resets_authentication(self):
        """Bug-fix: on ADTPulseAPIError reset_authentication() is called so the
        next poll will attempt a fresh login rather than looping on UpdateFailed."""
        api = _mock_api(is_authenticated=True)
        api.async_fetch_all = AsyncMock(
            side_effect=ADTPulseAPIError("connection lost")
        )
        coordinator = _make_coordinator(api)

        with pytest.raises(UpdateFailed):
            await coordinator._async_update_data()

        api.reset_authentication.assert_called_once()

    async def test_auth_error_does_not_reset_authentication(self):
        """A credential failure should NOT reset authentication — it must
        propagate as ConfigEntryAuthFailed to stop the coordinator."""
        api = _mock_api(is_authenticated=True)
        api.async_fetch_all = AsyncMock(
            side_effect=ADTPulseAuthError("invalid creds")
        )
        coordinator = _make_coordinator(api)

        with pytest.raises(ConfigEntryAuthFailed):
            await coordinator._async_update_data()

        api.reset_authentication.assert_not_called()

    async def test_login_auth_error_raises_config_entry_auth_failed(self):
        """ADTPulseAuthError during login (not fetch) also becomes
        ConfigEntryAuthFailed."""
        api = _mock_api(is_authenticated=False)
        api.async_login = AsyncMock(
            side_effect=ADTPulseAuthError("wrong password")
        )
        coordinator = _make_coordinator(api)

        with pytest.raises(ConfigEntryAuthFailed):
            await coordinator._async_update_data()

    async def test_login_api_error_raises_update_failed(self):
        """ADTPulseAPIError during login → UpdateFailed (transient, retried)."""
        api = _mock_api(is_authenticated=False)
        api.async_login = AsyncMock(
            side_effect=ADTPulseAPIError("portal unreachable")
        )
        coordinator = _make_coordinator(api)

        with pytest.raises(UpdateFailed):
            await coordinator._async_update_data()
