"""BKW energy monitoring API client."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
import json
import logging
from typing import Any
from zoneinfo import ZoneInfo

from aiohttp import ClientError, ClientResponseError
from yarl import URL

from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .auth import (
    BkwAuthError,
    async_refresh_tokens,
    token_needs_refresh,
    tokens_from_entry,
)
from .debug import (
    build_metering_data_url,
    format_token_expiry,
    log_metering_request,
    log_metering_response,
    mask_metering_point,
)
from .const import (
    API_BASE_URL,
    CONF_ACCESS_TOKEN,
    CONF_DATA_TYPE,
    CONF_EXPIRES_AT,
    CONF_METERING_POINT_CODE,
    CONF_REFRESH_TOKEN,
    DEFAULT_DATA_TYPE,
    METERING_DATA_PATH,
    PORTAL_TIMEZONE,
    RESOLUTION_P1D,
)

_LOGGER = logging.getLogger(__name__)


class BkwApiError(Exception):
    """API request failed."""

    def __init__(self, message: str, *, status: int | None = None) -> None:
        """Initialize API error."""
        super().__init__(message)
        self.status = status


def _portal_tz() -> ZoneInfo:
    return ZoneInfo(PORTAL_TIMEZONE)


def now_in_portal_tz(now: datetime | None = None) -> datetime:
    """Current time in Europe/Zurich (or convert aware/naive input)."""
    tz = _portal_tz()
    if now is None:
        return datetime.now(tz)
    if now.tzinfo is None:
        return now.replace(tzinfo=tz)
    return now.astimezone(tz)


def swiss_portal_day_end_local(swiss_day: date) -> datetime:
    """End of the P1D portal slice on a Swiss calendar day (23:59:59.999 local)."""
    tz = _portal_tz()
    start_next_day = datetime.combine(
        swiss_day + timedelta(days=1), time.min, tzinfo=tz
    )
    return start_next_day - timedelta(milliseconds=1)


def swiss_portal_day_end_utc(swiss_day: date) -> datetime:
    """Same instant as ``swiss_portal_day_end_local``, as UTC (for the API)."""
    return swiss_portal_day_end_local(swiss_day).astimezone(timezone.utc)


def is_swiss_portal_day_published(now: datetime, swiss_day: date) -> bool:
    """Return True once the Swiss calendar has moved past ``swiss_day``."""
    return now_in_portal_tz(now).date() > swiss_day


def get_polling_day(now: datetime | None = None) -> date:
    """Latest published portal day as a Swiss calendar date (YYYY-MM-DD in Zurich)."""
    now_local = now_in_portal_tz(now)
    today = now_local.date()
    if is_swiss_portal_day_published(now_local, today):
        return today
    return today - timedelta(days=1)


def p1d_window_for_swiss_day(
    swiss_day: date,
) -> tuple[datetime, datetime, datetime, datetime]:
    """Return P1D period: (start_utc, stop_utc, start_swiss, stop_swiss)."""
    tz = _portal_tz()
    start_swiss = datetime.combine(swiss_day, time.min, tzinfo=tz)
    start_utc = start_swiss.astimezone(timezone.utc)
    stop_swiss = swiss_portal_day_end_local(swiss_day)
    stop_utc = stop_swiss.astimezone(timezone.utc)
    return start_utc, stop_utc, start_swiss, stop_swiss


def get_p1d_validity_window(swiss_day: date) -> tuple[datetime, datetime]:
    """UTC validity range for the API (Swiss calendar day ``swiss_day``)."""
    start_utc, stop_utc, _, _ = p1d_window_for_swiss_day(swiss_day)
    return start_utc, stop_utc


def _format_validity_start(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def _format_validity_stop_dt(stop: datetime) -> str:
    """Format an explicit validity stop (UTC)."""
    return stop.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.999Z")


def daily_total_kwh(intervals: list[dict[str, Any]]) -> float | None:
    """Extract kWh total from a P1D (or similar aggregate) response."""
    if not intervals:
        return None
    total = 0.0
    has_value = False
    for item in intervals:
        val = item.get("v")
        if val is None:
            continue
        has_value = True
        total += float(val)
    return total if has_value else None


def parse_api_error_message(body: str) -> str:
    """Extract a readable message from a BKW API error body."""
    try:
        payload = json.loads(body)
    except (json.JSONDecodeError, TypeError):
        return body
    return str(payload.get("message") or payload.get("error") or body)


class BkwApi:
    """Client for BKW energy monitoring API."""

    def __init__(
        self,
        hass: Any,
        entry_data: dict[str, Any],
        update_tokens: Any,
    ) -> None:
        """Initialize API client."""
        self._hass = hass
        self._entry_data = entry_data
        self._update_tokens = update_tokens
        self._session = async_get_clientsession(hass)

    @property
    def metering_point_code(self) -> str:
        """Metering point code from config."""
        return self._entry_data[CONF_METERING_POINT_CODE]

    @property
    def data_type(self) -> str:
        """Measurement data type."""
        return self._entry_data.get(CONF_DATA_TYPE, DEFAULT_DATA_TYPE)

    def update_from_entry(self, entry_data: dict[str, Any]) -> None:
        """Sync runtime config from an updated config entry."""
        self._entry_data.update(entry_data)

    async def async_ensure_token(self) -> str:
        """Return a valid access token, refreshing if needed."""
        tokens = tokens_from_entry(self._entry_data)
        if not token_needs_refresh(tokens.get(CONF_EXPIRES_AT)):
            _LOGGER.debug(
                "Using cached access token (expires %s)",
                format_token_expiry(tokens.get(CONF_EXPIRES_AT)),
            )
            return tokens[CONF_ACCESS_TOKEN]

        if not tokens.get(CONF_REFRESH_TOKEN):
            raise BkwAuthError("No refresh token available")

        _LOGGER.debug("Refreshing access token")
        new_tokens = await async_refresh_tokens(
            self._hass, tokens[CONF_REFRESH_TOKEN]
        )
        if new_tokens.get(CONF_REFRESH_TOKEN) is None:
            new_tokens[CONF_REFRESH_TOKEN] = tokens[CONF_REFRESH_TOKEN]

        await self._update_tokens(new_tokens)
        self._entry_data.update(new_tokens)
        return new_tokens[CONF_ACCESS_TOKEN]

    async def async_get_daily_total(self, swiss_day: date) -> float | None:
        """Fetch daily total kWh (P1D)."""
        start_utc, stop_utc, start_swiss, stop_swiss = p1d_window_for_swiss_day(
            swiss_day
        )
        validity_start = _format_validity_start(start_utc)
        validity_stop = _format_validity_stop_dt(stop_utc)
        _LOGGER.debug(
            "Portal day %s (Swiss): %s → %s | API UTC: %s → %s",
            swiss_day,
            start_swiss.isoformat(),
            stop_swiss.isoformat(),
            validity_start,
            validity_stop,
        )
        intervals = await self._async_request_metering_data(
            resolution=RESOLUTION_P1D,
            validity_start=validity_start,
            validity_stop=validity_stop,
        )
        return daily_total_kwh(intervals)

    async def _async_request_metering_data(
        self,
        *,
        resolution: str,
        validity_start: str,
        validity_stop: str,
    ) -> list[dict[str, Any]]:
        """Perform a metering-data GET with the given resolution and validity range."""
        tokens = tokens_from_entry(self._entry_data)
        _LOGGER.debug(
            "Token state before request: needs_refresh=%s expires=%s",
            token_needs_refresh(tokens.get(CONF_EXPIRES_AT)),
            format_token_expiry(tokens.get(CONF_EXPIRES_AT)),
        )

        access_token = await self.async_ensure_token()

        url = URL(API_BASE_URL).joinpath(METERING_DATA_PATH.lstrip("/"))
        params = {
            "resolution": resolution,
            "measurementValidityStart": validity_start,
            "measurementValidityStop": validity_stop,
            "dataType": self.data_type,
            "meteringPointCode": self.metering_point_code,
        }
        request_url = build_metering_data_url(
            API_BASE_URL, METERING_DATA_PATH, params
        )

        log_metering_request(
            method="GET",
            url=request_url,
            params=params,
            data_type=self.data_type,
            metering_point=self.metering_point_code,
            token_expires_at=tokens_from_entry(self._entry_data).get(CONF_EXPIRES_AT),
            resolution=resolution,
        )

        headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
        }

        try:
            async with self._session.get(
                str(url), params=params, headers=headers
            ) as resp:
                body = await resp.text()
                if resp.status == 401:
                    _LOGGER.error(
                        "Metering data unauthorized | resolution=%s meteringPoint=%s dataType=%s",
                        resolution,
                        mask_metering_point(self.metering_point_code),
                        self.data_type,
                    )
                    raise BkwAuthError("Unauthorized")
                if resp.status >= 400:
                    message = parse_api_error_message(body)
                    log_metering_response(
                        status=resp.status,
                        interval_count=0,
                        first_interval=None,
                        last_interval=None,
                        body_preview=body,
                    )
                    _LOGGER.error(
                        "Metering data request failed (%s): %s",
                        resp.status,
                        message,
                    )
                    _LOGGER.error("Failed request URL: %s", request_url)
                    _LOGGER.error(
                        "Failed request params (authoritative): %s", params
                    )
                    raise BkwApiError(message, status=resp.status)
                data = json.loads(body)
        except BkwAuthError:
            raise
        except BkwApiError:
            raise
        except (ClientResponseError, ClientError, json.JSONDecodeError) as err:
            _LOGGER.error(
                "Metering data request failed: %s | url=%s",
                err,
                request_url,
            )
            raise BkwApiError(str(err)) from err

        if not isinstance(data, list):
            _LOGGER.warning(
                "Unexpected metering response type=%s preview=%s",
                type(data).__name__,
                str(data)[:300],
            )
            return []

        first = data[0] if data else None
        last = data[-1] if data else None
        log_metering_response(
            status=200,
            interval_count=len(data),
            first_interval=first,
            last_interval=last,
        )

        return data
