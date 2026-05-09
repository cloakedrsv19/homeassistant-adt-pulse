#!/usr/bin/env python3
"""
ADT Pulse Integration — Live Demo
==================================
Simulates a complete ADT Pulse session using mocked HTTP responses so the
demo runs without real portal credentials or internet access.

Covers:
  1. Login (portal version / SAT code / network ID extraction)
  2. Parallel data fetch  (panel status, sensors, gateway)
  3. Arm-state commands  (away, stay, night, disarm)
  4. Keepalive ping
  5. Sync-check (no change → changed)
  6. Session-expiry recovery  (API error → reset + re-login)
  7. Logout
"""
from __future__ import annotations

import asyncio
import sys
from unittest.mock import MagicMock

# ---------------------------------------------------------------------------
# Stub out homeassistant before importing adt_pulse
# ---------------------------------------------------------------------------
_HA_MODS = [
    "homeassistant",
    "homeassistant.config_entries",
    "homeassistant.const",
    "homeassistant.core",
    "homeassistant.exceptions",
    "homeassistant.helpers",
    "homeassistant.helpers.aiohttp_client",
    "homeassistant.helpers.entity",
    "homeassistant.helpers.entity_platform",
    "homeassistant.helpers.update_coordinator",
    "homeassistant.components",
    "homeassistant.components.alarm_control_panel",
    "homeassistant.components.binary_sensor",
    "voluptuous",
]
for _m in _HA_MODS:
    sys.modules[_m] = MagicMock()

import aiohttp  # noqa: E402
from aioresponses import CallbackResult, aioresponses  # noqa: E402

from adt_pulse.api import (  # noqa: E402
    ADTPulseAPI,
    ADTPulseAPIError,
    ADTPulseAuthError,
)
from adt_pulse.const import (  # noqa: E402
    ARM_STATE_AWAY,
    ARM_STATE_NIGHT,
    ARM_STATE_OFF,
    ARM_STATE_STAY,
)

# ---------------------------------------------------------------------------
# Colour helpers
# ---------------------------------------------------------------------------
RESET = "\033[0m"
BOLD  = "\033[1m"
CYAN  = "\033[96m"
GREEN = "\033[92m"
YELLOW= "\033[93m"
RED   = "\033[91m"
DIM   = "\033[2m"


def hdr(title: str) -> None:
    width = 62
    print(f"\n{CYAN}{BOLD}{'─' * width}{RESET}")
    print(f"{CYAN}{BOLD}  {title}{RESET}")
    print(f"{CYAN}{BOLD}{'─' * width}{RESET}")


def ok(msg: str) -> None:
    print(f"  {GREEN}✔{RESET}  {msg}")


def info(msg: str) -> None:
    print(f"  {YELLOW}ℹ{RESET}  {msg}")


def err(msg: str) -> None:
    print(f"  {RED}✘{RESET}  {msg}")


def field(label: str, value) -> None:
    print(f"       {DIM}{label:<22}{RESET}{BOLD}{value}{RESET}")


# ---------------------------------------------------------------------------
# Fake portal HTML / responses
# ---------------------------------------------------------------------------
SAT_CODE       = "dead1234-cafe-babe-f00d-123456abcdef"
NETWORK_ID     = "NET_8675309"
PORTAL_VERSION = "16.0.0-131"

_BASE_SCRIPT = (
    f"var cfg = {{'sat': '{SAT_CODE}'}};"
    f" var link = '/myhome/{PORTAL_VERSION}/summary.jsp"
    f"?networkid={NETWORK_ID}&partner=adt';"
)

def _page(body: str = "", extra_js: str = "") -> str:
    return (
        f"<html><body>{body}"
        f"<script>{_BASE_SCRIPT}{extra_js}</script>"
        f"</body></html>"
    )


SUMMARY = {
    ARM_STATE_OFF:   _page('<div id="divOrbTextSummary">All Quiet</div>'),
    ARM_STATE_AWAY:  _page('<div id="divOrbTextSummary">Armed Away</div>'),
    ARM_STATE_STAY:  _page('<div id="divOrbTextSummary">Armed Stay</div>'),
    ARM_STATE_NIGHT: _page('<div id="divOrbTextSummary">Armed Night</div>'),
}

SENSOR_PAGE = _page("""
<table id="sensor-status-table">
  <tr><th>Name</th><th>Zone</th><th>Type</th><th>Status</th></tr>
  <tr><td>Front Door</td><td>1</td><td>Door/Window</td><td>Closed</td></tr>
  <tr><td>Back Door</td><td>2</td><td>Door/Window</td><td>Open</td></tr>
  <tr><td>Living Room Motion</td><td>3</td><td>Motion</td><td>No Motion</td></tr>
  <tr><td>Smoke Detector</td><td>4</td><td>Fire/Smoke</td><td>Low Battery</td></tr>
  <tr><td>Garage Window</td><td>5</td><td>Door/Window</td><td>Tamper Alert</td></tr>
</table>
""")

GATEWAY_PAGE = _page("""
<table>
  <tr><td>Manufacturer</td><td>ADT Inc.</td></tr>
  <tr><td>Model Number</td><td>GSM-9000</td></tr>
  <tr><td>Connection Type</td><td>Broadband / LTE</td></tr>
  <tr><td>Status</td><td>Online</td></tr>
</table>
""")

import re  # noqa: E402

LOGIN_URL_RE   = re.compile(r"https://portal\.adtpulse\.com/myhome/.+/signin\.jsp")
LOGOUT_URL_RE  = re.compile(r"https://portal\.adtpulse\.com/myhome/.+/signout\.jsp")
SUMMARY_URL_RE = re.compile(r"https://portal\.adtpulse\.com/myhome/.+/summary\.jsp")
SYSTEM_URL_RE  = re.compile(r"https://portal\.adtpulse\.com/myhome/.+/system\.jsp")
GATEWAY_URL_RE = re.compile(r"https://portal\.adtpulse\.com/myhome/.+/gateway\.jsp")
KEEPALIVE_URL  = re.compile(r"https://portal\.adtpulse\.com/myhome/.+/KeepAlive")
SYNC_URL       = re.compile(r"https://portal\.adtpulse\.com/myhome/.+/SyncCheckServ")
ARM_URL        = "https://portal.adtpulse.com/rest/adt/ui/client/security/setArmState"

# ---------------------------------------------------------------------------
# Demo
# ---------------------------------------------------------------------------

async def run_demo() -> None:
    print(f"\n{BOLD}{'=' * 62}{RESET}")
    print(f"{BOLD}   ADT Pulse Home Assistant Integration — Demo{RESET}")
    print(f"{BOLD}{'=' * 62}{RESET}")

    async with aiohttp.ClientSession() as session:
        api = ADTPulseAPI(
            username="demo@example.com",
            password="S3cur3P@ss!",
            fingerprint="fp-DEMO-1234-ABCD",
            session=session,
        )

        # ── 1. Login ──────────────────────────────────────────────────────
        hdr("1 · Login")
        with aioresponses() as m:
            m.post(LOGIN_URL_RE, status=200, body=_page())
            await api.async_login()

        ok(f"Authenticated successfully")
        field("Portal version", api._portal_version)
        field("Network ID",     api._network_id)
        field("SAT code",       api._sat_code)

        # ── 2. Fetch all (parallel) ────────────────────────────────────────
        hdr("2 · Parallel Data Fetch  (panel + sensors + gateway)")
        _panel_state = ARM_STATE_OFF  # current panel state for this demo

        with aioresponses() as m:
            m.get(SUMMARY_URL_RE, status=200, body=SUMMARY[ARM_STATE_OFF])
            m.get(SYSTEM_URL_RE,  status=200, body=SENSOR_PAGE)
            m.get(GATEWAY_URL_RE, status=200, body=GATEWAY_PAGE)
            data = await api.async_fetch_all()

        panel   = data.panel
        sensors = data.sensors
        gateway = data.gateway

        ok("Panel status")
        field("Arm state",   panel.arm_state)
        field("Alarm",       panel.is_alarm)
        field("Trouble",     panel.is_trouble)

        ok(f"Sensors  ({len(sensors)} zones found)")
        STATUS_ICONS = {
            True:  f"{RED}OPEN{RESET}",
            False: f"{GREEN}closed{RESET}",
        }
        for s in sensors:
            flags = []
            if s.is_open:     flags.append(f"{RED}OPEN{RESET}")
            if s.is_tampered: flags.append(f"{RED}TAMPER{RESET}")
            if s.low_battery: flags.append(f"{YELLOW}LOW-BATT{RESET}")
            if s.is_trouble:  flags.append(f"{YELLOW}TROUBLE{RESET}")
            flag_str = "  ".join(flags) if flags else f"{GREEN}OK{RESET}"
            print(f"         Zone {s.zone:<4} {s.name:<25} [{s.sensor_type}]  {flag_str}")

        ok("Gateway info")
        field("Manufacturer",   gateway.manufacturer)
        field("Model",          gateway.model)
        field("Connection",     gateway.connection_type)
        field("Status",         gateway.status)

        # ── 3. Arm / Disarm ───────────────────────────────────────────────
        hdr("3 · Arm / Disarm Commands")

        arm_sequence = [
            (ARM_STATE_AWAY,  "ARM AWAY"),
            (ARM_STATE_STAY,  "ARM STAY"),
            (ARM_STATE_NIGHT, "ARM NIGHT"),
            (ARM_STATE_OFF,   "DISARM"),
        ]

        for target, label in arm_sequence:
            with aioresponses() as m:
                captured: dict = {}

                def _cb(url, **kwargs):
                    captured.update(kwargs.get("data", {}))
                    return CallbackResult(status=200)

                m.post(ARM_URL, callback=_cb)
                await api.async_set_arm_state(target, _panel_state)
                _panel_state = target

            ok(f"{label}")
            field("sat",       captured.get("sat", "—"))
            field("arm",       captured.get("arm", "—"))
            field("armState",  captured.get("armState", "—"))
            field("networkid", captured.get("networkid", "—"))

        # ── 4. Keepalive ──────────────────────────────────────────────────
        hdr("4 · Keepalive Ping")

        with aioresponses() as m:
            m.post(KEEPALIVE_URL, status=200)
            alive = await api.async_keepalive()
        ok(f"Keepalive returned → {BOLD}{alive}{RESET}")

        with aioresponses() as m:
            m.post(KEEPALIVE_URL, status=503)
            alive = await api.async_keepalive()
        info(f"Keepalive on 503   → {BOLD}{alive}{RESET}  (portal temporarily unavailable)")

        # ── 5. Sync check ────────────────────────────────────────────────
        hdr("5 · Sync Check  (detect portal state changes)")

        api._last_sync = "1-0-0"
        with aioresponses() as m:
            m.get(SYNC_URL, status=200, body="1-0-0")
            changed = await api.async_sync_check()
        info(f"Poll 1 (same token '1-0-0')   → changed={BOLD}{changed}{RESET}")

        with aioresponses() as m:
            m.get(SYNC_URL, status=200, body="2-1-0")
            changed = await api.async_sync_check()
        ok(f"Poll 2 (new token  '2-1-0')   → changed={BOLD}{changed}{RESET}  (data refresh triggered)")
        field("_last_sync updated to", api._last_sync)

        # ── 6. Session-expiry recovery ────────────────────────────────────
        hdr("6 · Session Expiry & Automatic Recovery")

        info("Simulating portal session expiry (API error on fetch) …")
        try:
            with aioresponses() as m:
                m.get(SUMMARY_URL_RE, status=401)
                m.get(SYSTEM_URL_RE,  status=401)
                m.get(GATEWAY_URL_RE, status=401)
                await api.async_fetch_all()
        except ADTPulseAPIError as exc:
            err(f"ADTPulseAPIError caught: {exc}")

        info("Coordinator calls reset_authentication() → forces re-login next poll")
        api.reset_authentication()
        field("is_authenticated", api.is_authenticated)

        info("Next poll: re-login then fetch …")
        with aioresponses() as m:
            m.post(LOGIN_URL_RE,   status=200, body=_page())
            m.get(SUMMARY_URL_RE,  status=200, body=SUMMARY[ARM_STATE_OFF])
            m.get(SYSTEM_URL_RE,   status=200, body=SENSOR_PAGE)
            m.get(GATEWAY_URL_RE,  status=200, body=GATEWAY_PAGE)
            if not api.is_authenticated:
                await api.async_login()
            data = await api.async_fetch_all()
        ok(f"Session recovered — {len(data.sensors)} sensors fetched")

        # ── 7. Logout ────────────────────────────────────────────────────
        hdr("7 · Logout")
        with aioresponses() as m:
            m.get(LOGOUT_URL_RE, status=200)
            await api.async_logout()
        ok("Logged out")
        field("is_authenticated", api.is_authenticated)

    # ── Summary ────────────────────────────────────────────────────────────
    print(f"\n{CYAN}{BOLD}{'═' * 62}{RESET}")
    print(f"{GREEN}{BOLD}  Demo complete — all stages executed successfully.{RESET}")
    print(f"{CYAN}{BOLD}{'═' * 62}{RESET}\n")


if __name__ == "__main__":
    asyncio.run(run_demo())
