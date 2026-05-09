# ADT Pulse — Home Assistant Custom Integration

Connects your ADT Pulse security system to Home Assistant running on a Raspberry Pi 4 (64-bit / aarch64).

## Supported Devices & Entities

| Entity Type | Description |
|---|---|
| `alarm_control_panel` | Security panel — arm Away / Home (Stay) / Night / Disarm |
| `binary_sensor` | All sensor zones: door/window, motion, smoke/fire, CO, flood, glass-break, heat, shock |

## Prerequisites

- Home Assistant OS or Supervised running on Raspberry Pi 4 (64-bit)
- ADT Pulse account (username + password)
- **Device fingerprint** — a 2FA token string required by ADT Pulse. See [Obtaining a Fingerprint](#obtaining-a-fingerprint) below.

## Installation

### Option A — HACS (recommended)

1. Open HACS → Integrations → ⋮ → Custom repositories.
2. Add this repository URL with category **Integration**.
3. Install **ADT Pulse** and restart Home Assistant.

### Option B — Manual

1. Copy the `custom_components/adt_pulse/` folder into your Home Assistant
   `config/custom_components/` directory.
2. Restart Home Assistant.

## Configuration

1. Go to **Settings → Devices & Services → Add Integration**.
2. Search for **ADT Pulse**.
3. Enter your:
   - **Username** — ADT Pulse portal email
   - **Password** — ADT Pulse portal password
   - **Device Fingerprint** — see below

## Obtaining a Fingerprint

ADT Pulse uses device fingerprinting as its 2FA mechanism. You need a fingerprint
string from an already-authenticated device/session.

**Method 1 — Browser DevTools**

1. Open `https://portal.adtpulse.com` in Chrome/Firefox.
2. Log in and open DevTools → Network tab.
3. Find the POST request to `signin.jsp` and inspect the form payload.
4. Copy the value of the `fingerprint` field.

**Method 2 — Homebridge ADT Pulse wizard**

If you run homebridge, use the built-in setup wizard from the
[homebridge-adt-pulse](https://github.com/mrjackyliang/homebridge-adt-pulse) plugin
which automates fingerprint retrieval.

## Update Interval

The integration polls the ADT Pulse portal every **30 seconds** and sends keepalive
pings every **60 seconds** to maintain the session.

## Entities Created

After a successful setup the following entities will appear:

- `alarm_control_panel.adt_pulse_security_panel`
- One `binary_sensor.*` per zone discovered in the portal

Each binary sensor exposes the following attributes:

| Attribute | Description |
|---|---|
| `zone` | ADT zone number |
| `sensor_type` | Sensor classification (motion, doorWindow, …) |
| `status` | Raw status text from portal |
| `tampered` | Tamper alert active |
| `low_battery` | Low battery alert |
| `trouble` | Trouble condition reported |
