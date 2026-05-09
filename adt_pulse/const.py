"""Constants for the ADT Pulse integration."""

DOMAIN = "adt_pulse"
MANUFACTURER = "ADT"

CONF_FINGERPRINT = "fingerprint"
CONF_NETWORK_ID = "network_id"

ADT_PULSE_HOST = "https://portal.adtpulse.com"
ADT_PULSE_LOGIN_PATH = "/myhome/{version}/access/signin.jsp?e=ns&partner=adt"
ADT_PULSE_LOGOUT_PATH = "/myhome/{version}/access/signout.jsp?networkid={network_id}&partner=adt"
ADT_PULSE_SUMMARY_PATH = "/myhome/{version}/summary/summary.jsp"
ADT_PULSE_SYSTEM_PATH = "/myhome/{version}/system/system.jsp"
ADT_PULSE_GATEWAY_PATH = "/myhome/{version}/system/gateway.jsp"
ADT_PULSE_SYNC_CHECK_PATH = "/myhome/{version}/Ajax/SyncCheckServ?t={timestamp}"
ADT_PULSE_KEEPALIVE_PATH = "/myhome/{version}/KeepAlive"
ADT_PULSE_ARM_PATH = "/rest/adt/ui/client/security/setArmState"

DEFAULT_PORTAL_VERSION = "16.0.0-131"

UPDATE_INTERVAL_SECONDS = 30
KEEPALIVE_INTERVAL_SECONDS = 60

# Arm states
ARM_STATE_OFF = "off"
ARM_STATE_STAY = "stay"
ARM_STATE_AWAY = "away"
ARM_STATE_NIGHT = "night"

# Sensor types (matching ADT Pulse portal classifications)
SENSOR_TYPE_CO = "co"
SENSOR_TYPE_DOOR_WINDOW = "doorWindow"
SENSOR_TYPE_FIRE = "fire"
SENSOR_TYPE_FLOOD = "flood"
SENSOR_TYPE_GLASS = "glass"
SENSOR_TYPE_HEAT = "heat"
SENSOR_TYPE_MOTION = "motion"
SENSOR_TYPE_SHOCK = "shock"
SENSOR_TYPE_TEMPERATURE = "temperature"

# Panel states as reported by the portal
PANEL_STATUS_DISARMED = "All Quiet"
PANEL_STATUS_ARMED_AWAY = "Armed Away"
PANEL_STATUS_ARMED_STAY = "Armed Stay"
PANEL_STATUS_ARMED_NIGHT = "Armed Night"
PANEL_STATUS_ALARM = "Alarm"

# HTTP headers mimicking a real browser
REQUEST_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Linux; Android 13; Pixel 6) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/112.0.0.0 Mobile Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "same-origin",
    "x-dtpc": "8$293748291_101h1vFGIDAUTRVDPMSQLAKOSFDNHBKHC-0e0",
}
