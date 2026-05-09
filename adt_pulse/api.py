"""ADT Pulse API client for Home Assistant integration."""
from __future__ import annotations

import asyncio
import logging
import re
import time
from dataclasses import dataclass, field

import aiohttp
from bs4 import BeautifulSoup

from .const import (
    ADT_PULSE_ARM_PATH,
    ADT_PULSE_GATEWAY_PATH,
    ADT_PULSE_HOST,
    ADT_PULSE_KEEPALIVE_PATH,
    ADT_PULSE_LOGIN_PATH,
    ADT_PULSE_LOGOUT_PATH,
    ADT_PULSE_SUMMARY_PATH,
    ADT_PULSE_SYNC_CHECK_PATH,
    ADT_PULSE_SYSTEM_PATH,
    ARM_STATE_AWAY,
    ARM_STATE_NIGHT,
    ARM_STATE_OFF,
    ARM_STATE_STAY,
    DEFAULT_PORTAL_VERSION,
    REQUEST_HEADERS,
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

_LOGGER = logging.getLogger(__name__)

# Regex patterns for parsing portal HTML responses
_RE_NETWORK_ID = re.compile(r'networkid=([^&"\']+)')
_RE_SAT_CODE = re.compile(r'["\']sat["\']\s*:\s*["\']([a-f0-9\-]{36})["\']')
_RE_PORTAL_VERSION = re.compile(r"/myhome/([^/]+)/")
_RE_SYNC_CHECK = re.compile(r"(\d+)-(\d+)-(\d+)")

SENSOR_TYPE_ICON_MAP = {
    "co": SENSOR_TYPE_CO,
    "doorwindow": SENSOR_TYPE_DOOR_WINDOW,
    "door": SENSOR_TYPE_DOOR_WINDOW,
    "window": SENSOR_TYPE_DOOR_WINDOW,
    "fire": SENSOR_TYPE_FIRE,
    "smoke": SENSOR_TYPE_FIRE,
    "flood": SENSOR_TYPE_FLOOD,
    "water": SENSOR_TYPE_FLOOD,
    "glass": SENSOR_TYPE_GLASS,
    "glassbreak": SENSOR_TYPE_GLASS,
    "heat": SENSOR_TYPE_HEAT,
    "motion": SENSOR_TYPE_MOTION,
    "shock": SENSOR_TYPE_SHOCK,
    "temperature": SENSOR_TYPE_TEMPERATURE,
    "temp": SENSOR_TYPE_TEMPERATURE,
}


@dataclass
class SensorStatus:
    """Represents the status of a single sensor."""

    name: str
    zone: str
    sensor_type: str
    status: str
    is_open: bool = False
    is_tampered: bool = False
    low_battery: bool = False
    is_trouble: bool = False


@dataclass
class PanelStatus:
    """Represents the current state of the security panel."""

    arm_state: str = ARM_STATE_OFF  # off, stay, away, night
    is_alarm: bool = False
    is_trouble: bool = False
    sat_code: str | None = None


@dataclass
class GatewayInfo:
    """Represents gateway device information."""

    manufacturer: str | None = None
    model: str | None = None
    connection_type: str | None = None
    status: str | None = None


@dataclass
class ADTPulseData:
    """Container for all polled ADT Pulse data."""

    panel: PanelStatus = field(default_factory=PanelStatus)
    sensors: list[SensorStatus] = field(default_factory=list)
    gateway: GatewayInfo = field(default_factory=GatewayInfo)


class ADTPulseAuthError(Exception):
    """Raised when authentication fails."""


class ADTPulseAPIError(Exception):
    """Raised when an API call fails."""


class ADTPulseAPI:
    """Async API client for the ADT Pulse web portal."""

    def __init__(
        self,
        username: str,
        password: str,
        fingerprint: str,
        session: aiohttp.ClientSession,
    ) -> None:
        self._username = username
        self._password = password
        self._fingerprint = fingerprint
        self._session = session
        self._is_authenticated = False
        self._network_id: str | None = None
        self._portal_version: str = DEFAULT_PORTAL_VERSION
        self._sat_code: str | None = None
        self._last_sync: str = "1-0-0"

    # ------------------------------------------------------------------ #
    # Public interface                                                     #
    # ------------------------------------------------------------------ #

    @property
    def is_authenticated(self) -> bool:
        return self._is_authenticated

    async def async_login(self) -> None:
        """Authenticate with the ADT Pulse portal."""
        login_url = ADT_PULSE_HOST + ADT_PULSE_LOGIN_PATH.format(
            version=self._portal_version
        )
        payload = {
            "usernameForm": self._username,
            "passwordForm": self._password,
            "fingerprint": self._fingerprint,
            "sun": "yes",
        }
        headers = {
            **REQUEST_HEADERS,
            "Content-Type": "application/x-www-form-urlencoded",
            "Origin": ADT_PULSE_HOST,
            "Referer": login_url,
        }

        try:
            async with self._session.post(
                login_url,
                data=payload,
                headers=headers,
                allow_redirects=True,
                ssl=True,
            ) as resp:
                if resp.status not in (200, 302):
                    raise ADTPulseAPIError(
                        f"Login returned HTTP {resp.status}"
                    )
                final_url = str(resp.url)
                html = await resp.text()

            # Extract portal version from redirect URL
            version_match = _RE_PORTAL_VERSION.search(final_url)
            if version_match:
                self._portal_version = version_match.group(1)

            # Detect failed login (redirected back to sign-in page)
            if "signin" in final_url and "error" in html.lower():
                raise ADTPulseAuthError("Invalid credentials or fingerprint")

            # Extract network ID
            nid_match = _RE_NETWORK_ID.search(final_url) or _RE_NETWORK_ID.search(html)
            if nid_match:
                self._network_id = nid_match.group(1)

            # Extract SAT code from page JS
            sat_match = _RE_SAT_CODE.search(html)
            if sat_match:
                self._sat_code = sat_match.group(1)

            self._is_authenticated = True
            _LOGGER.debug(
                "ADT Pulse login successful: version=%s network_id=%s",
                self._portal_version,
                self._network_id,
            )
        except aiohttp.ClientError as err:
            raise ADTPulseAPIError(f"Network error during login: {err}") from err

    async def async_logout(self) -> None:
        """Terminate the authenticated session."""
        if not self._is_authenticated:
            return
        url = ADT_PULSE_HOST + ADT_PULSE_LOGOUT_PATH.format(
            version=self._portal_version,
            network_id=self._network_id or "",
        )
        try:
            async with self._session.get(url, headers=REQUEST_HEADERS, ssl=True):
                pass
        except aiohttp.ClientError:
            pass
        finally:
            self._is_authenticated = False

    async def async_fetch_all(self) -> ADTPulseData:
        """Fetch panel status, sensors, and gateway info in parallel."""
        self._ensure_authenticated()
        panel, sensors, gateway = await asyncio.gather(
            self._async_get_panel_status(),
            self._async_get_sensors(),
            self._async_get_gateway(),
        )
        return ADTPulseData(panel=panel, sensors=sensors, gateway=gateway)

    async def async_set_arm_state(self, arm: str, current_arm: str) -> None:
        """Arm or disarm the security panel.

        arm: target state (off | stay | away | night)
        current_arm: current state reported by panel
        """
        self._ensure_authenticated()
        if not self._sat_code:
            # Re-fetch summary to get SAT code
            await self._async_get_panel_status()
        url = ADT_PULSE_HOST + ADT_PULSE_ARM_PATH
        payload = {
            "sat": self._sat_code or "",
            "arm": arm,
            "armState": current_arm,
            "networkid": self._network_id or "",
        }
        headers = {
            **REQUEST_HEADERS,
            "Content-Type": "application/x-www-form-urlencoded",
            "Origin": ADT_PULSE_HOST,
            "Referer": ADT_PULSE_HOST
            + ADT_PULSE_SUMMARY_PATH.format(version=self._portal_version),
        }
        try:
            async with self._session.post(
                url, data=payload, headers=headers, ssl=True
            ) as resp:
                if resp.status not in (200, 302):
                    raise ADTPulseAPIError(
                        f"Arm/disarm request failed with HTTP {resp.status}"
                    )
        except aiohttp.ClientError as err:
            raise ADTPulseAPIError(f"Network error during arm/disarm: {err}") from err

    async def async_keepalive(self) -> bool:
        """Send a keepalive ping to maintain the session. Returns True if alive."""
        if not self._is_authenticated:
            return False
        url = ADT_PULSE_HOST + ADT_PULSE_KEEPALIVE_PATH.format(
            version=self._portal_version
        )
        try:
            async with self._session.post(
                url,
                data={"networkid": self._network_id or ""},
                headers=REQUEST_HEADERS,
                ssl=True,
            ) as resp:
                return resp.status == 200
        except aiohttp.ClientError:
            return False

    async def async_sync_check(self) -> bool:
        """Check if portal state has changed since last poll. Returns True if changed."""
        if not self._is_authenticated:
            return False
        url = ADT_PULSE_HOST + ADT_PULSE_SYNC_CHECK_PATH.format(
            version=self._portal_version,
            timestamp=int(time.time() * 1000),
        )
        try:
            async with self._session.get(
                url, headers=REQUEST_HEADERS, ssl=True
            ) as resp:
                text = await resp.text()
            match = _RE_SYNC_CHECK.match(text.strip())
            if not match:
                return False
            changed = text.strip() != self._last_sync
            self._last_sync = text.strip()
            return changed
        except aiohttp.ClientError:
            return False

    # ------------------------------------------------------------------ #
    # Internal helpers                                                     #
    # ------------------------------------------------------------------ #

    def reset_authentication(self) -> None:
        """Mark session as unauthenticated so the next call triggers re-login."""
        self._is_authenticated = False

    def _ensure_authenticated(self) -> None:
        if not self._is_authenticated:
            raise ADTPulseAuthError("Not authenticated — call async_login() first")

    def _make_url(self, path_template: str) -> str:
        return ADT_PULSE_HOST + path_template.format(version=self._portal_version)

    async def _async_fetch_page(self, url: str) -> BeautifulSoup:
        """Fetch an HTML page and return a BeautifulSoup object."""
        try:
            async with self._session.get(
                url, headers=REQUEST_HEADERS, ssl=True
            ) as resp:
                if resp.status != 200:
                    raise ADTPulseAPIError(f"HTTP {resp.status} fetching {url}")
                html = await resp.text()
        except aiohttp.ClientError as err:
            raise ADTPulseAPIError(f"Network error fetching {url}: {err}") from err
        return BeautifulSoup(html, "html.parser")

    async def _async_get_panel_status(self) -> PanelStatus:
        """Parse the summary page to determine panel arm state."""
        url = self._make_url(ADT_PULSE_SUMMARY_PATH)
        soup = await self._async_fetch_page(url)
        raw_html = str(soup)

        # Refresh SAT code
        sat_match = _RE_SAT_CODE.search(raw_html)
        if sat_match:
            self._sat_code = sat_match.group(1)

        # Refresh network ID
        nid_match = _RE_NETWORK_ID.search(raw_html)
        if nid_match:
            self._network_id = nid_match.group(1)

        panel = PanelStatus()

        # The summary page has a security status string in #divOrbTextSummary or similar
        status_div = (
            soup.find("div", id="divOrbTextSummary")
            or soup.find("div", class_="p_armingStateText")
            or soup.find("span", class_="p_boldNormalText")
        )
        status_text = status_div.get_text(strip=True).lower() if status_div else ""

        if "away" in status_text:
            panel.arm_state = ARM_STATE_AWAY
        elif "stay" in status_text or "home" in status_text:
            panel.arm_state = ARM_STATE_STAY
        elif "night" in status_text:
            panel.arm_state = ARM_STATE_NIGHT
        else:
            panel.arm_state = ARM_STATE_OFF

        panel.is_alarm = "alarm" in status_text
        panel.is_trouble = "trouble" in status_text
        panel.sat_code = self._sat_code

        return panel

    async def _async_get_sensors(self) -> list[SensorStatus]:
        """Parse the system page for sensor list and statuses."""
        url = self._make_url(ADT_PULSE_SYSTEM_PATH)
        soup = await self._async_fetch_page(url)
        sensors: list[SensorStatus] = []

        # Sensors are listed in a table — each row is one sensor
        table = soup.find("table", id="sensor-status-table") or soup.find(
            "table", class_="p_sensorList"
        )
        if not table:
            # Fallback: find any table with sensor data
            tables = soup.find_all("table")
            for t in tables:
                if t.find("th", string=re.compile(r"sensor|zone|device", re.I)):
                    table = t
                    break

        if not table:
            _LOGGER.warning("ADT Pulse: could not find sensor table on system page")
            return sensors

        rows = table.find_all("tr")[1:]  # skip header row
        for row in rows:
            cells = row.find_all("td")
            if len(cells) < 3:
                continue

            # Typical columns: Name | Zone | Type | Status
            name = cells[0].get_text(strip=True)
            zone = cells[1].get_text(strip=True)
            raw_type = cells[2].get_text(strip=True).lower()
            status_cell = cells[3] if len(cells) > 3 else cells[-1]
            status_text = status_cell.get_text(strip=True).lower()

            # Map raw type string to our sensor type constant
            sensor_type = _map_sensor_type(raw_type)

            is_open = any(
                kw in status_text for kw in ("open", "motion", "active", "alert")
            )
            is_tampered = "tamper" in status_text
            low_battery = "low battery" in status_text or "low batt" in status_text
            is_trouble = "trouble" in status_text

            sensors.append(
                SensorStatus(
                    name=name,
                    zone=zone,
                    sensor_type=sensor_type,
                    status=status_text,
                    is_open=is_open,
                    is_tampered=is_tampered,
                    low_battery=low_battery,
                    is_trouble=is_trouble,
                )
            )

        return sensors

    async def _async_get_gateway(self) -> GatewayInfo:
        """Fetch gateway device information."""
        url = self._make_url(ADT_PULSE_GATEWAY_PATH)
        try:
            soup = await self._async_fetch_page(url)
        except ADTPulseAPIError:
            return GatewayInfo()

        info = GatewayInfo()
        # Gateway info appears in definition-list / table rows
        for row in soup.find_all("tr"):
            cells = row.find_all("td")
            if len(cells) >= 2:
                label = cells[0].get_text(strip=True).lower()
                value = cells[1].get_text(strip=True)
                if "manufacturer" in label:
                    info.manufacturer = value
                elif "model" in label:
                    info.model = value
                elif "connection" in label:
                    info.connection_type = value
                elif "status" in label:
                    info.status = value

        return info


def _map_sensor_type(raw: str) -> str:
    """Convert a raw type string from the portal to our sensor type constant."""
    raw = raw.lower().replace(" ", "").replace("-", "").replace("_", "")
    for key, mapped in SENSOR_TYPE_ICON_MAP.items():
        if key in raw:
            return mapped
    return SENSOR_TYPE_DOOR_WINDOW  # safe default
