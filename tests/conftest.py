"""Shared pytest configuration and fixtures.

The homeassistant package is not installed in the test environment, so every
module that adt_pulse imports from homeassistant must be patched into
sys.modules *at import time* (i.e. at module level here, not inside a
fixture).  conftest.py is loaded by pytest before any test module, so this
is the right place to do it.
"""
from __future__ import annotations

import sys
from datetime import timedelta
from unittest.mock import MagicMock

# ---------------------------------------------------------------------------
# Proper base classes that adt_pulse subclasses — MagicMock() instances cannot
# be used as base classes, so we create minimal real classes instead.
# ---------------------------------------------------------------------------


class _DataUpdateCoordinator:
    """Minimal stand-in for homeassistant DataUpdateCoordinator."""

    def __class_getitem__(cls, item):
        return cls

    def __init__(self, hass, logger, *, name, update_interval, **kwargs):
        self.hass = hass
        self.logger = logger
        self.name = name
        self.update_interval = update_interval
        self.data = None

    def async_add_listener(self, callback, context=None):
        return lambda: None

    async def async_request_refresh(self):
        pass


class _UpdateFailed(Exception):
    """Minimal stand-in for homeassistant UpdateFailed."""


class _ConfigEntryAuthFailed(Exception):
    """Minimal stand-in for homeassistant ConfigEntryAuthFailed."""


# ---------------------------------------------------------------------------
# Build mocked homeassistant modules
# ---------------------------------------------------------------------------

_update_coordinator_mod = MagicMock()
_update_coordinator_mod.DataUpdateCoordinator = _DataUpdateCoordinator
_update_coordinator_mod.UpdateFailed = _UpdateFailed

_exceptions_mod = MagicMock()
_exceptions_mod.ConfigEntryAuthFailed = _ConfigEntryAuthFailed

sys.modules.update(
    {
        "homeassistant": MagicMock(),
        "homeassistant.config_entries": MagicMock(),
        "homeassistant.const": MagicMock(),
        "homeassistant.core": MagicMock(),
        "homeassistant.exceptions": _exceptions_mod,
        "homeassistant.helpers": MagicMock(),
        "homeassistant.helpers.aiohttp_client": MagicMock(),
        "homeassistant.helpers.entity": MagicMock(),
        "homeassistant.helpers.entity_platform": MagicMock(),
        "homeassistant.helpers.update_coordinator": _update_coordinator_mod,
        "homeassistant.components": MagicMock(),
        "homeassistant.components.alarm_control_panel": MagicMock(),
        "homeassistant.components.binary_sensor": MagicMock(),
        "voluptuous": MagicMock(),
    }
)

# ---------------------------------------------------------------------------
# Make the UpdateFailed / ConfigEntryAuthFailed stubs importable via the
# same names that the real HA package uses, so coordinator.py can catch them.
# ---------------------------------------------------------------------------
import importlib  # noqa: E402  (after sys.modules patching)

# Now that the stubs are in sys.modules we can safely import adt_pulse.
import pytest  # noqa: E402
import aiohttp  # noqa: E402

# ---------------------------------------------------------------------------
# Shared test constants
# ---------------------------------------------------------------------------

SAT_CODE = "abcdef12-1234-1234-1234-abcdef123456"
NETWORK_ID = "NET123"
PORTAL_VERSION = "16.0.0-200"

# ---------------------------------------------------------------------------
# HTML page helpers
# ---------------------------------------------------------------------------


def make_html(body: str = "", *, sat: str = SAT_CODE, nid: str = NETWORK_ID) -> str:
    """Return minimal portal HTML with embedded SAT code and network ID."""
    return (
        "<html><body>"
        f"{body}"
        "<script>"
        f"var s = {{'sat': '{sat}'}};"
        f"var u = '/myhome/16.0.0-131/summary.jsp?networkid={nid}&partner=adt';"
        "</script>"
        "</body></html>"
    )


SUMMARY_ARMED_AWAY = make_html('<div id="divOrbTextSummary">Armed Away</div>')
SUMMARY_ARMED_STAY = make_html('<div id="divOrbTextSummary">Armed Stay</div>')
SUMMARY_ARMED_HOME = make_html('<div id="divOrbTextSummary">Armed Home</div>')
SUMMARY_ARMED_NIGHT = make_html('<div id="divOrbTextSummary">Armed Night</div>')
SUMMARY_DISARMED = make_html('<div id="divOrbTextSummary">All Quiet</div>')
SUMMARY_ALARM = make_html('<div id="divOrbTextSummary">Alarm</div>')
SUMMARY_TROUBLE = make_html('<div id="divOrbTextSummary">Trouble</div>')
SUMMARY_NO_DIV = make_html("")

SENSOR_TABLE_HTML = make_html(
    """
    <table id="sensor-status-table">
      <tr><th>Name</th><th>Zone</th><th>Type</th><th>Status</th></tr>
      <tr><td>Front Door</td><td>1</td><td>Door/Window</td><td>Closed</td></tr>
      <tr><td>Motion Detector</td><td>2</td><td>Motion</td><td>Open</td></tr>
      <tr><td>Smoke Detector</td><td>3</td><td>Fire/Smoke</td><td>Low Battery</td></tr>
      <tr><td>Back Door</td><td>4</td><td>Door/Window</td><td>Tamper Alert</td></tr>
      <tr><td>Bad Row</td></tr>
    </table>
    """
)

GATEWAY_HTML = make_html(
    """
    <table>
      <tr><td>Manufacturer</td><td>ADT Inc.</td></tr>
      <tr><td>Model Number</td><td>GW-5000</td></tr>
      <tr><td>Connection Type</td><td>Broadband</td></tr>
      <tr><td>Status</td><td>Online</td></tr>
    </table>
    """
)

LOGIN_SUCCESS_HTML = make_html("")
LOGIN_FAILURE_HTML = (
    "<html><body>"
    "<div class='error'>Invalid username or password</div>"
    "</body></html>"
)

# ---------------------------------------------------------------------------
# URL regex patterns for aioresponses matching
# ---------------------------------------------------------------------------

import re  # noqa: E402

LOGIN_URL_RE = re.compile(r"https://portal\.adtpulse\.com/myhome/.+/signin\.jsp")
LOGOUT_URL_RE = re.compile(r"https://portal\.adtpulse\.com/myhome/.+/signout\.jsp")
SUMMARY_URL_RE = re.compile(r"https://portal\.adtpulse\.com/myhome/.+/summary\.jsp")
SYSTEM_URL_RE = re.compile(r"https://portal\.adtpulse\.com/myhome/.+/system\.jsp")
GATEWAY_URL_RE = re.compile(r"https://portal\.adtpulse\.com/myhome/.+/gateway\.jsp")
KEEPALIVE_URL_RE = re.compile(r"https://portal\.adtpulse\.com/myhome/.+/KeepAlive")
SYNC_URL_RE = re.compile(r"https://portal\.adtpulse\.com/myhome/.+/SyncCheckServ")
ARM_URL = "https://portal.adtpulse.com/rest/adt/ui/client/security/setArmState"

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def session():
    async with aiohttp.ClientSession() as s:
        yield s


@pytest.fixture
def api(session):
    from adt_pulse.api import ADTPulseAPI

    return ADTPulseAPI(
        username="user@example.com",
        password="s3cr3t",
        fingerprint="fp-abc123",
        session=session,
    )


@pytest.fixture
def auth_api(api):
    """An API instance pre-marked as authenticated with known state."""
    api._is_authenticated = True
    api._network_id = NETWORK_ID
    api._sat_code = SAT_CODE
    api._portal_version = "16.0.0-131"
    return api
