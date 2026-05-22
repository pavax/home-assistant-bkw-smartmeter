"""Constants for the BKW Smart Meter integration."""

from __future__ import annotations

from datetime import timedelta

from homeassistant.config_entries import ConfigEntry

DOMAIN = "bkw_smartmeter"

# OAuth2 / OpenID (Keycloak oneportal)
CLIENT_ID = "mybkw-webapp"
REDIRECT_URI = "https://my.bkw.ch/energy"
OAUTH_SCOPE = "openid profile email"

AUTHORIZE_URL = (
    "https://login.portal-services.ch/auth/realms/oneportal/"
    "protocol/openid-connect/auth"
)
TOKEN_URL = (
    "https://login.portal-services.ch/auth/realms/oneportal/"
    "protocol/openid-connect/token"
)

# Energy monitoring API
API_BASE_URL = "https://api-energy-monitoring.bkw.ch"
METERING_DATA_PATH = "/api/metering-data"

RESOLUTION_P1D = "P1D"
RESOLUTION_P1M = "P1M"

# BKW portal day boundaries for P1D (local midnight through portal end, UTC stop).
PORTAL_TIMEZONE = "Europe/Zurich"
# BKW portal dataType values (names are not intuitive — verify in DevTools per chart).
DATA_TYPE_CONSUMPTION = "CONSUMPTION_BKW"  # e.g. solar / feed-in (confirm for your meter)
DATA_TYPE_PRODUCTION = "PRODUCTION_BKW"  # Strombezug (grid import)
DATA_TYPE_STROMBEZUG = DATA_TYPE_PRODUCTION

# Portal day = one Swiss calendar day (Europe/Zurich), 00:00:00–23:59:59.999 local.
# UTC validity timestamps are derived from these local times for the API only.
# Example CEST: 2026-05-21 00:00 → 2026-05-20T22:00:00.000Z;
# 2026-05-21 23:59:59.999 → 2026-05-21T21:59:59.999Z.

# Sensor display (daily kWh values, e.g. 12.345)
SUGGESTED_DISPLAY_PRECISION = 3

# Polling and token refresh
UPDATE_INTERVAL_MINUTES = 15
MIN_UPDATE_INTERVAL_MINUTES = 1
CONF_UPDATE_INTERVAL_MINUTES = "update_interval_minutes"
TOKEN_REFRESH_MARGIN_SECONDS = 120


# Config entry keys
CONF_ACCESS_TOKEN = "access_token"
CONF_REFRESH_TOKEN = "refresh_token"
CONF_EXPIRES_AT = "expires_at"
CONF_METERING_POINT_CODE = "metering_point_code"
CONF_DATA_TYPE = "data_type"
CONF_CONSUMPTION_TOTAL_KWH = "consumption_total_kwh"
CONF_LAST_POLLED_DAY = "last_polled_day"
CONF_LAST_INTERVAL_TIMESTAMP = "last_interval_timestamp"

# Flow context keys (not persisted on entry)
FLOW_CODE_VERIFIER = "code_verifier"
FLOW_AUTHORIZE_URL = "authorize_url"

DEFAULT_DATA_TYPE = DATA_TYPE_PRODUCTION

METERING_POINT_MIN_LENGTH = 20
METERING_POINT_MAX_LENGTH = 40



def get_update_interval_minutes(entry: ConfigEntry) -> int:
    """Return configured poll interval in minutes (minimum 1)."""
    raw = entry.options.get(CONF_UPDATE_INTERVAL_MINUTES)
    if raw is None:
        return UPDATE_INTERVAL_MINUTES
    try:
        minutes = int(raw)
    except (TypeError, ValueError):
        return UPDATE_INTERVAL_MINUTES
    return max(MIN_UPDATE_INTERVAL_MINUTES, minutes)


def get_update_interval_timedelta(entry: ConfigEntry) -> timedelta:
    """Return configured poll interval for the data coordinator."""
    return timedelta(minutes=get_update_interval_minutes(entry))
