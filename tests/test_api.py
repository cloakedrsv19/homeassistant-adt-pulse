"""Tests for adt_pulse.api — ADTPulseAPI and _map_sensor_type."""
from __future__ import annotations

import re
from unittest.mock import AsyncMock, patch  # patch used in fetch_all test

import aiohttp
import pytest
from aioresponses import CallbackResult, aioresponses

from tests.conftest import (
    ARM_URL,
    GATEWAY_HTML,
    GATEWAY_URL_RE,
    KEEPALIVE_URL_RE,
    LOGIN_FAILURE_HTML,
    LOGIN_SUCCESS_HTML,
    LOGIN_URL_RE,
    LOGOUT_URL_RE,
    NETWORK_ID,
    PORTAL_VERSION,
    SAT_CODE,
    SENSOR_TABLE_HTML,
    SUMMARY_ALARM,
    SUMMARY_ARMED_AWAY,
    SUMMARY_ARMED_HOME,
    SUMMARY_ARMED_NIGHT,
    SUMMARY_ARMED_STAY,
    SUMMARY_DISARMED,
    SUMMARY_NO_DIV,
    SUMMARY_TROUBLE,
    SUMMARY_URL_RE,
    SYNC_URL_RE,
    SYSTEM_URL_RE,
    make_html,
)

from adt_pulse.api import (
    ADTPulseAPI,
    ADTPulseAPIError,
    ADTPulseAuthError,
    GatewayInfo,
    PanelStatus,
    SensorStatus,
    _map_sensor_type,
)
from adt_pulse.const import (
    ARM_STATE_AWAY,
    ARM_STATE_NIGHT,
    ARM_STATE_OFF,
    ARM_STATE_STAY,
    SENSOR_TYPE_CO,
    SENSOR_TYPE_DOOR_WINDOW,
    SENSOR_TYPE_FIRE,
    SENSOR_TYPE_FLOOD,
    SENSOR_TYPE_GLASS,
    SENSOR_TYPE_HEAT,
    SENSOR_TYPE_MOTION,
    SENSOR_TYPE_SHOCK,
    SENSOR_TYPE_TEMPERATURE,
)

# ===========================================================================
# _map_sensor_type (pure function — no async, no mocking)
# ===========================================================================


class TestMapSensorType:
    def test_door(self):
        assert _map_sensor_type("door") == SENSOR_TYPE_DOOR_WINDOW

    def test_window(self):
        assert _map_sensor_type("window") == SENSOR_TYPE_DOOR_WINDOW

    def test_doorwindow_combined(self):
        assert _map_sensor_type("Door/Window") == SENSOR_TYPE_DOOR_WINDOW

    def test_motion(self):
        assert _map_sensor_type("motion") == SENSOR_TYPE_MOTION

    def test_co(self):
        assert _map_sensor_type("co") == SENSOR_TYPE_CO

    def test_fire(self):
        assert _map_sensor_type("fire") == SENSOR_TYPE_FIRE

    def test_smoke_maps_to_fire(self):
        assert _map_sensor_type("smoke") == SENSOR_TYPE_FIRE

    def test_flood(self):
        assert _map_sensor_type("flood") == SENSOR_TYPE_FLOOD

    def test_water_maps_to_flood(self):
        assert _map_sensor_type("water") == SENSOR_TYPE_FLOOD

    def test_glass(self):
        assert _map_sensor_type("glass") == SENSOR_TYPE_GLASS

    def test_glassbreak_normalization(self):
        assert _map_sensor_type("glass-break") == SENSOR_TYPE_GLASS

    def test_heat(self):
        assert _map_sensor_type("heat") == SENSOR_TYPE_HEAT

    def test_shock(self):
        assert _map_sensor_type("shock") == SENSOR_TYPE_SHOCK

    def test_temperature(self):
        assert _map_sensor_type("temperature") == SENSOR_TYPE_TEMPERATURE

    def test_temp_abbreviation(self):
        assert _map_sensor_type("temp") == SENSOR_TYPE_TEMPERATURE

    def test_unknown_defaults_to_door_window(self):
        assert _map_sensor_type("laser_beam") == SENSOR_TYPE_DOOR_WINDOW

    def test_empty_string_defaults_to_door_window(self):
        assert _map_sensor_type("") == SENSOR_TYPE_DOOR_WINDOW

    def test_case_insensitive(self):
        assert _map_sensor_type("MOTION") == SENSOR_TYPE_MOTION

    def test_whitespace_normalized(self):
        assert _map_sensor_type("glass break") == SENSOR_TYPE_GLASS

    def test_underscores_normalized(self):
        assert _map_sensor_type("glass_break") == SENSOR_TYPE_GLASS

    def test_dashes_normalized(self):
        assert _map_sensor_type("glass-break") == SENSOR_TYPE_GLASS


# ===========================================================================
# async_login
# ===========================================================================


class TestAsyncLogin:
    async def test_successful_login_sets_authenticated(self, api):
        with aioresponses() as m:
            m.post(LOGIN_URL_RE, status=200, body=LOGIN_SUCCESS_HTML)
            await api.async_login()
        assert api.is_authenticated is True

    async def test_successful_login_extracts_sat_code(self, api):
        with aioresponses() as m:
            m.post(LOGIN_URL_RE, status=200, body=LOGIN_SUCCESS_HTML)
            await api.async_login()
        assert api._sat_code == SAT_CODE

    async def test_successful_login_extracts_network_id_from_html(self, api):
        with aioresponses() as m:
            m.post(LOGIN_URL_RE, status=200, body=LOGIN_SUCCESS_HTML)
            await api.async_login()
        assert api._network_id == NETWORK_ID

    async def test_login_failure_raises_auth_error(self, api):
        """Redirect back to signin with 'error' in body → ADTPulseAuthError."""
        with aioresponses() as m:
            m.post(LOGIN_URL_RE, status=200, body=LOGIN_FAILURE_HTML)
            with pytest.raises(ADTPulseAuthError):
                await api.async_login()
        assert api.is_authenticated is False

    async def test_http_503_raises_api_error_not_auth_error(self, api):
        """Bug-fix: a transient server error must NOT raise ADTPulseAuthError,
        which would permanently disable the integration via ConfigEntryAuthFailed."""
        with aioresponses() as m:
            m.post(LOGIN_URL_RE, status=503)
            with pytest.raises(ADTPulseAPIError):
                await api.async_login()

    async def test_http_503_does_not_raise_auth_error(self, api):
        with aioresponses() as m:
            m.post(LOGIN_URL_RE, status=503)
            with pytest.raises(Exception) as exc_info:
                await api.async_login()
        assert not isinstance(exc_info.value, ADTPulseAuthError)

    async def test_http_404_raises_api_error(self, api):
        with aioresponses() as m:
            m.post(LOGIN_URL_RE, status=404)
            with pytest.raises(ADTPulseAPIError):
                await api.async_login()

    async def test_network_error_raises_api_error(self, api):
        with aioresponses() as m:
            m.post(LOGIN_URL_RE, exception=aiohttp.ClientConnectionError("refused"))
            with pytest.raises(ADTPulseAPIError):
                await api.async_login()

    async def test_network_error_leaves_not_authenticated(self, api):
        with aioresponses() as m:
            m.post(LOGIN_URL_RE, exception=aiohttp.ClientConnectionError("refused"))
            with pytest.raises(ADTPulseAPIError):
                await api.async_login()
        assert api.is_authenticated is False


# ===========================================================================
# async_logout
# ===========================================================================


class TestAsyncLogout:
    async def test_logout_when_authenticated_sends_request(self, auth_api):
        with aioresponses() as m:
            m.get(LOGOUT_URL_RE, status=200)
            await auth_api.async_logout()
        assert auth_api.is_authenticated is False

    async def test_logout_when_not_authenticated_skips_request(self, api):
        # No aioresponses mock — any HTTP call would raise
        await api.async_logout()  # must not raise
        assert api.is_authenticated is False

    async def test_logout_clears_auth_even_on_network_error(self, auth_api):
        with aioresponses() as m:
            m.get(LOGOUT_URL_RE, exception=aiohttp.ClientConnectionError("gone"))
            await auth_api.async_logout()  # must not raise
        assert auth_api.is_authenticated is False


# ===========================================================================
# reset_authentication
# ===========================================================================


class TestResetAuthentication:
    def test_clears_authenticated_flag(self, auth_api):
        assert auth_api.is_authenticated is True
        auth_api.reset_authentication()
        assert auth_api.is_authenticated is False

    def test_idempotent_when_already_unauthenticated(self, api):
        assert api.is_authenticated is False
        api.reset_authentication()
        assert api.is_authenticated is False


# ===========================================================================
# async_fetch_all
# ===========================================================================


class TestAsyncFetchAll:
    async def test_raises_auth_error_when_not_authenticated(self, api):
        with pytest.raises(ADTPulseAuthError):
            await api.async_fetch_all()

    async def test_calls_all_three_sub_methods(self, auth_api):
        panel = PanelStatus(arm_state=ARM_STATE_AWAY)
        sensors = [
            SensorStatus(
                name="Front Door",
                zone="1",
                sensor_type=SENSOR_TYPE_DOOR_WINDOW,
                status="closed",
            )
        ]
        gateway = GatewayInfo(manufacturer="ADT")

        with (
            patch.object(
                auth_api, "_async_get_panel_status", new=AsyncMock(return_value=panel)
            ) as mp,
            patch.object(
                auth_api, "_async_get_sensors", new=AsyncMock(return_value=sensors)
            ) as ms,
            patch.object(
                auth_api, "_async_get_gateway", new=AsyncMock(return_value=gateway)
            ) as mg,
        ):
            result = await auth_api.async_fetch_all()

        mp.assert_called_once()
        ms.assert_called_once()
        mg.assert_called_once()
        assert result.panel is panel
        assert result.sensors is sensors
        assert result.gateway is gateway


# ===========================================================================
# async_set_arm_state
# ===========================================================================


class TestAsyncSetArmState:
    async def test_raises_auth_error_when_not_authenticated(self, api):
        with pytest.raises(ADTPulseAuthError):
            await api.async_set_arm_state(ARM_STATE_AWAY, ARM_STATE_OFF)

    async def test_includes_networkid_in_payload(self, auth_api):
        captured: dict = {}

        def capture(url, **kwargs):
            captured.update(kwargs.get("data", {}))
            return CallbackResult(status=200)

        with aioresponses() as m:
            m.post(ARM_URL, callback=capture)
            await auth_api.async_set_arm_state(ARM_STATE_AWAY, ARM_STATE_OFF)

        assert "networkid" in captured
        assert captured["networkid"] == NETWORK_ID

    async def test_includes_sat_in_payload(self, auth_api):
        captured: dict = {}

        def capture(url, **kwargs):
            captured.update(kwargs.get("data", {}))
            return CallbackResult(status=200)

        with aioresponses() as m:
            m.post(ARM_URL, callback=capture)
            await auth_api.async_set_arm_state(ARM_STATE_AWAY, ARM_STATE_OFF)

        assert captured["sat"] == SAT_CODE

    async def test_includes_arm_state_in_payload(self, auth_api):
        captured: dict = {}

        def capture(url, **kwargs):
            captured.update(kwargs.get("data", {}))
            return CallbackResult(status=200)

        with aioresponses() as m:
            m.post(ARM_URL, callback=capture)
            await auth_api.async_set_arm_state(ARM_STATE_AWAY, ARM_STATE_OFF)

        assert captured["arm"] == ARM_STATE_AWAY
        assert captured["armState"] == ARM_STATE_OFF

    async def test_http_error_raises_api_error(self, auth_api):
        with aioresponses() as m:
            m.post(ARM_URL, status=500)
            with pytest.raises(ADTPulseAPIError):
                await auth_api.async_set_arm_state(ARM_STATE_AWAY, ARM_STATE_OFF)

    async def test_no_sat_code_fetches_panel_first(self, auth_api):
        """When _sat_code is None, panel status is fetched first to get the code."""
        auth_api._sat_code = None
        with (
            patch.object(
                auth_api,
                "_async_get_panel_status",
                new=AsyncMock(
                    return_value=PanelStatus(sat_code=SAT_CODE),
                    side_effect=lambda: setattr(auth_api, "_sat_code", SAT_CODE)
                    or PanelStatus(sat_code=SAT_CODE),
                ),
            ) as mock_panel,
            aioresponses() as m,
        ):
            m.post(ARM_URL, status=200)
            await auth_api.async_set_arm_state(ARM_STATE_AWAY, ARM_STATE_OFF)

        mock_panel.assert_called_once()


# ===========================================================================
# async_keepalive
# ===========================================================================


class TestAsyncKeepalive:
    async def test_returns_false_when_not_authenticated(self, api):
        result = await api.async_keepalive()
        assert result is False

    async def test_returns_true_on_200(self, auth_api):
        with aioresponses() as m:
            m.post(KEEPALIVE_URL_RE, status=200)
            result = await auth_api.async_keepalive()
        assert result is True

    async def test_returns_false_on_non_200(self, auth_api):
        with aioresponses() as m:
            m.post(KEEPALIVE_URL_RE, status=503)
            result = await auth_api.async_keepalive()
        assert result is False

    async def test_returns_false_on_network_error(self, auth_api):
        with aioresponses() as m:
            m.post(KEEPALIVE_URL_RE, exception=aiohttp.ClientConnectionError("gone"))
            result = await auth_api.async_keepalive()
        assert result is False


# ===========================================================================
# async_sync_check
# ===========================================================================


class TestAsyncSyncCheck:
    async def test_returns_false_when_not_authenticated(self, api):
        result = await api.async_sync_check()
        assert result is False

    async def test_returns_false_when_state_unchanged(self, auth_api):
        auth_api._last_sync = "1-0-0"
        with aioresponses() as m:
            m.get(SYNC_URL_RE, status=200, body="1-0-0")
            result = await auth_api.async_sync_check()
        assert result is False

    async def test_returns_true_when_state_changed(self, auth_api):
        auth_api._last_sync = "1-0-0"
        with aioresponses() as m:
            m.get(SYNC_URL_RE, status=200, body="2-0-0")
            result = await auth_api.async_sync_check()
        assert result is True

    async def test_updates_last_sync_on_change(self, auth_api):
        auth_api._last_sync = "1-0-0"
        with aioresponses() as m:
            m.get(SYNC_URL_RE, status=200, body="5-3-1")
            await auth_api.async_sync_check()
        assert auth_api._last_sync == "5-3-1"

    async def test_returns_false_on_non_matching_body(self, auth_api):
        with aioresponses() as m:
            m.get(SYNC_URL_RE, status=200, body="not-a-sync-token")
            result = await auth_api.async_sync_check()
        assert result is False

    async def test_returns_false_on_network_error(self, auth_api):
        with aioresponses() as m:
            m.get(SYNC_URL_RE, exception=aiohttp.ClientConnectionError("gone"))
            result = await auth_api.async_sync_check()
        assert result is False


# ===========================================================================
# _async_get_panel_status — arm state parsing
# ===========================================================================


class TestAsyncGetPanelStatus:
    async def _fetch_panel(self, auth_api, html: str) -> PanelStatus:
        with aioresponses() as m:
            m.get(SUMMARY_URL_RE, status=200, body=html)
            return await auth_api._async_get_panel_status()

    async def test_armed_away(self, auth_api):
        panel = await self._fetch_panel(auth_api, SUMMARY_ARMED_AWAY)
        assert panel.arm_state == ARM_STATE_AWAY

    async def test_armed_stay(self, auth_api):
        panel = await self._fetch_panel(auth_api, SUMMARY_ARMED_STAY)
        assert panel.arm_state == ARM_STATE_STAY

    async def test_armed_home_maps_to_stay(self, auth_api):
        panel = await self._fetch_panel(auth_api, SUMMARY_ARMED_HOME)
        assert panel.arm_state == ARM_STATE_STAY

    async def test_armed_night(self, auth_api):
        panel = await self._fetch_panel(auth_api, SUMMARY_ARMED_NIGHT)
        assert panel.arm_state == ARM_STATE_NIGHT

    async def test_disarmed(self, auth_api):
        panel = await self._fetch_panel(auth_api, SUMMARY_DISARMED)
        assert panel.arm_state == ARM_STATE_OFF

    async def test_alarm_sets_is_alarm(self, auth_api):
        panel = await self._fetch_panel(auth_api, SUMMARY_ALARM)
        assert panel.is_alarm is True

    async def test_trouble_sets_is_trouble(self, auth_api):
        panel = await self._fetch_panel(auth_api, SUMMARY_TROUBLE)
        assert panel.is_trouble is True

    async def test_normal_status_does_not_set_alarm(self, auth_api):
        panel = await self._fetch_panel(auth_api, SUMMARY_DISARMED)
        assert panel.is_alarm is False

    async def test_no_status_div_defaults_to_off(self, auth_api):
        panel = await self._fetch_panel(auth_api, SUMMARY_NO_DIV)
        assert panel.arm_state == ARM_STATE_OFF

    async def test_extracts_sat_code(self, auth_api):
        panel = await self._fetch_panel(auth_api, SUMMARY_DISARMED)
        assert panel.sat_code == SAT_CODE
        assert auth_api._sat_code == SAT_CODE

    async def test_http_error_raises_api_error(self, auth_api):
        with aioresponses() as m:
            m.get(SUMMARY_URL_RE, status=403)
            with pytest.raises(ADTPulseAPIError):
                await auth_api._async_get_panel_status()

    async def test_fallback_to_arming_state_class(self, auth_api):
        """Arm state is parsed from p_armingStateText if divOrbTextSummary absent."""
        html = make_html('<div class="p_armingStateText">Armed Away</div>')
        panel = await self._fetch_panel(auth_api, html)
        assert panel.arm_state == ARM_STATE_AWAY


# ===========================================================================
# _async_get_sensors — sensor table parsing
# ===========================================================================


class TestAsyncGetSensors:
    async def _fetch_sensors(self, auth_api, html: str) -> list[SensorStatus]:
        with aioresponses() as m:
            m.get(SYSTEM_URL_RE, status=200, body=html)
            return await auth_api._async_get_sensors()

    async def test_returns_correct_count(self, auth_api):
        sensors = await self._fetch_sensors(auth_api, SENSOR_TABLE_HTML)
        # 4 valid rows (the 5th has only 1 cell and is skipped)
        assert len(sensors) == 4

    async def test_sensor_names_and_zones(self, auth_api):
        sensors = await self._fetch_sensors(auth_api, SENSOR_TABLE_HTML)
        assert sensors[0].name == "Front Door"
        assert sensors[0].zone == "1"
        assert sensors[1].name == "Motion Detector"
        assert sensors[1].zone == "2"

    async def test_sensor_types_mapped(self, auth_api):
        sensors = await self._fetch_sensors(auth_api, SENSOR_TABLE_HTML)
        assert sensors[0].sensor_type == SENSOR_TYPE_DOOR_WINDOW
        assert sensors[1].sensor_type == SENSOR_TYPE_MOTION
        assert sensors[2].sensor_type == SENSOR_TYPE_FIRE

    async def test_open_status_detected(self, auth_api):
        sensors = await self._fetch_sensors(auth_api, SENSOR_TABLE_HTML)
        assert sensors[0].is_open is False  # "Closed"
        assert sensors[1].is_open is True   # "Open"

    async def test_low_battery_detected(self, auth_api):
        sensors = await self._fetch_sensors(auth_api, SENSOR_TABLE_HTML)
        assert sensors[2].low_battery is True  # "Low Battery"

    async def test_tamper_detected(self, auth_api):
        sensors = await self._fetch_sensors(auth_api, SENSOR_TABLE_HTML)
        assert sensors[3].is_tampered is True  # "Tamper Alert"

    async def test_no_table_returns_empty_list(self, auth_api):
        html = make_html("<p>No sensors here</p>")
        sensors = await self._fetch_sensors(auth_api, html)
        assert sensors == []

    async def test_short_row_skipped(self, auth_api):
        """Rows with fewer than 3 cells must be skipped (no IndexError)."""
        html = make_html(
            """
            <table id="sensor-status-table">
              <tr><th>Name</th><th>Zone</th><th>Type</th><th>Status</th></tr>
              <tr><td>Only Two</td><td>1</td></tr>
              <tr><td>Good Row</td><td>2</td><td>Motion</td><td>Closed</td></tr>
            </table>
            """
        )
        sensors = await self._fetch_sensors(auth_api, html)
        assert len(sensors) == 1
        assert sensors[0].name == "Good Row"

    async def test_fallback_table_detection(self, auth_api):
        """Falls back to any table containing a 'sensor'/'zone' header."""
        html = make_html(
            """
            <table>
              <tr><th>Sensor</th><th>Zone</th><th>Type</th><th>Status</th></tr>
              <tr><td>Hallway</td><td>5</td><td>Motion</td><td>Closed</td></tr>
            </table>
            """
        )
        sensors = await self._fetch_sensors(auth_api, html)
        assert len(sensors) == 1
        assert sensors[0].name == "Hallway"


# ===========================================================================
# _async_get_gateway — gateway info parsing
# ===========================================================================


class TestAsyncGetGateway:
    async def test_parses_manufacturer(self, auth_api):
        with aioresponses() as m:
            m.get(GATEWAY_URL_RE, status=200, body=GATEWAY_HTML)
            info = await auth_api._async_get_gateway()
        assert info.manufacturer == "ADT Inc."

    async def test_parses_model(self, auth_api):
        with aioresponses() as m:
            m.get(GATEWAY_URL_RE, status=200, body=GATEWAY_HTML)
            info = await auth_api._async_get_gateway()
        assert info.model == "GW-5000"

    async def test_parses_connection_type(self, auth_api):
        with aioresponses() as m:
            m.get(GATEWAY_URL_RE, status=200, body=GATEWAY_HTML)
            info = await auth_api._async_get_gateway()
        assert info.connection_type == "Broadband"

    async def test_parses_status(self, auth_api):
        with aioresponses() as m:
            m.get(GATEWAY_URL_RE, status=200, body=GATEWAY_HTML)
            info = await auth_api._async_get_gateway()
        assert info.status == "Online"

    async def test_returns_empty_gateway_on_api_error(self, auth_api):
        with aioresponses() as m:
            m.get(GATEWAY_URL_RE, status=500)
            info = await auth_api._async_get_gateway()
        assert isinstance(info, GatewayInfo)
        assert info.manufacturer is None
        assert info.model is None
