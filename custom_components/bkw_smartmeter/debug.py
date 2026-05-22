"""Debug helpers for BKW Smart Meter (no secrets in logs)."""

from __future__ import annotations

from datetime import datetime, timezone
import logging
from typing import Any
from urllib.parse import urlencode

_LOGGER = logging.getLogger(__name__)


def mask_metering_point(code: str) -> str:
    """Return a partially masked metering point code for logs."""
    if len(code) <= 12:
        return code
    return f"{code[:8]}…{code[-8:]}"


def format_token_expiry(expires_at: float | None) -> str:
    """Human-readable access token expiry."""
    if expires_at is None:
        return "unknown"
    remaining = expires_at - datetime.now(timezone.utc).timestamp()
    if remaining <= 0:
        return "expired"
    return f"in {int(remaining)}s"


def build_metering_data_url(base_url: str, path: str, params: dict[str, str]) -> str:
    """Build a human-readable metering-data URL for logs.

    Colons in ISO timestamps stay as ``:`` (not ``%3A``). Both forms are
    equivalent on the wire; aiohttp encodes query params when sending the request.
    """
    base = base_url.rstrip("/")
    p = path if path.startswith("/") else f"/{path}"
    # safe=':.' keeps timestamps readable: 2026-05-21T10:00:00.000Z
    return f"{base}{p}?{urlencode(params, safe=':.')}"


def log_metering_request(
    *,
    method: str,
    url: str,
    params: dict[str, str],
    data_type: str,
    metering_point: str,
    token_expires_at: float | None,
    resolution: str | None = None,
) -> None:
    """Log outgoing metering-data request (no tokens)."""
    _LOGGER.debug(
        "Metering request: %s %s | resolution=%s dataType=%s meteringPoint=%s "
        "token_expires=%s",
        method,
        url.split("?")[0],
        resolution or params.get("resolution"),
        data_type,
        mask_metering_point(metering_point),
        format_token_expiry(token_expires_at),
    )
    _LOGGER.debug("Metering params: %s", params)


def log_metering_response(
    *,
    status: int,
    interval_count: int,
    first_interval: dict[str, Any] | None,
    last_interval: dict[str, Any] | None,
    body_preview: str | None = None,
) -> None:
    """Log metering-data response summary."""
    if status >= 400 and body_preview:
        _LOGGER.debug(
            "Metering response error: status=%s body=%s",
            status,
            body_preview[:500],
        )
        return
    _LOGGER.debug(
        "Metering response: status=%s intervals=%s first=%s last=%s",
        status,
        interval_count,
        first_interval,
        last_interval,
    )


def log_auth_event(event: str, *, status: int | None = None, detail: str = "") -> None:
    """Log OAuth2 events without secrets."""
    if status is not None:
        _LOGGER.debug("Auth %s: HTTP %s %s", event, status, detail)
    else:
        _LOGGER.debug("Auth %s: %s", event, detail)
