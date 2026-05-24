"""PKCE and OAuth2 token handling for BKW portal."""

from __future__ import annotations

import base64
import hashlib
import logging
import secrets
import time
from typing import Any

from aiohttp import ClientError, ClientResponseError
from yarl import URL

from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .debug import log_auth_event
from .const import (
    CLIENT_ID,
    CONF_ACCESS_TOKEN,
    CONF_AUTHENTICATED_AT,
    CONF_EXPIRES_AT,
    CONF_REFRESH_EXPIRES_AT,
    CONF_REFRESH_TOKEN,
    CONF_TOKEN_SCOPE,
    OAUTH_SCOPE,
    REDIRECT_URI,
    TOKEN_REFRESH_MARGIN_SECONDS,
    TOKEN_URL,
)

_LOGGER = logging.getLogger(__name__)


class BkwAuthError(Exception):
    """Authentication failed."""


def generate_code_verifier(code_verifier_length: int = 128) -> str:
    """Generate a PKCE code verifier (RFC 7636)."""
    if not 43 <= code_verifier_length <= 128:
        msg = "code_verifier_length must be between 43 and 128"
        raise ValueError(msg)
    return secrets.token_urlsafe(96)[:code_verifier_length]


def compute_code_challenge(code_verifier: str) -> str:
    """Compute S256 PKCE code challenge."""
    if not 43 <= len(code_verifier) <= 128:
        msg = "code_verifier length must be between 43 and 128"
        raise ValueError(msg)
    hashed = hashlib.sha256(code_verifier.encode("ascii")).digest()
    encoded = base64.urlsafe_b64encode(hashed)
    return encoded.decode("ascii").replace("=", "")


def build_authorize_url(authorize_base: str, code_verifier: str) -> str:
    """Build the browser authorization URL with PKCE."""
    url = URL(authorize_base).with_query(
        {
            "client_id": CLIENT_ID,
            "response_type": "code",
            "scope": OAUTH_SCOPE,
            "redirect_uri": REDIRECT_URI,
            "code_challenge": compute_code_challenge(code_verifier),
            "code_challenge_method": "S256",
        }
    )
    return str(url)


async def async_exchange_code(
    hass: Any,
    code: str,
    code_verifier: str,
) -> dict[str, Any]:
    """Exchange authorization code for tokens."""
    session = async_get_clientsession(hass)
    data = {
        "grant_type": "authorization_code",
        "client_id": CLIENT_ID,
        "code": code.strip(),
        "redirect_uri": REDIRECT_URI,
        "code_verifier": code_verifier,
    }
    log_auth_event("exchange_code_start", detail=f"redirect_uri={REDIRECT_URI}")
    try:
        async with session.post(
            TOKEN_URL,
            data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        ) as resp:
            body = await resp.json(content_type=None)
            if resp.status >= 400:
                log_auth_event(
                    "exchange_code_failed",
                    status=resp.status,
                    detail=str(body.get("error", body)),
                )
                _LOGGER.error("Token exchange failed: %s", body)
                raise BkwAuthError(_auth_error_message(body))
            log_auth_event(
                "exchange_code_ok",
                status=resp.status,
                detail=(
                    f"expires_in={body.get('expires_in')} "
                    f"refresh_expires_in={body.get('refresh_expires_in')} "
                    f"scope={body.get('scope', '')}"
                ),
            )
    except ClientResponseError as err:
        log_auth_event("exchange_code_error", detail=str(err))
        raise BkwAuthError(str(err)) from err
    except ClientError as err:
        log_auth_event("exchange_code_error", detail=str(err))
        raise BkwAuthError(str(err)) from err

    return _normalize_token_response(body, set_authenticated_at=True)


async def async_refresh_tokens(hass: Any, refresh_token: str) -> dict[str, Any]:
    """Refresh access token using refresh token."""
    session = async_get_clientsession(hass)
    data = {
        "grant_type": "refresh_token",
        "client_id": CLIENT_ID,
        "refresh_token": refresh_token,
    }
    log_auth_event("refresh_start")
    try:
        async with session.post(
            TOKEN_URL,
            data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        ) as resp:
            body = await resp.json(content_type=None)
            if resp.status >= 400:
                log_auth_event(
                    "refresh_failed",
                    status=resp.status,
                    detail=str(body.get("error", body)),
                )
                _LOGGER.error("Token refresh failed: %s", body)
                raise BkwAuthError(_auth_error_message(body))
            log_auth_event(
                "refresh_ok",
                status=resp.status,
                detail=(
                    f"expires_in={body.get('expires_in')} "
                    f"refresh_expires_in={body.get('refresh_expires_in')} "
                    f"scope={body.get('scope', '')}"
                ),
            )
    except ClientResponseError as err:
        log_auth_event("refresh_error", detail=str(err))
        raise BkwAuthError(str(err)) from err
    except ClientError as err:
        log_auth_event("refresh_error", detail=str(err))
        raise BkwAuthError(str(err)) from err

    return _normalize_token_response(body, set_authenticated_at=False)
    """Return a user-facing auth error message."""
    error = str(body.get("error", ""))
    description = str(body.get("error_description", body.get("error", "")))
    if error == "invalid_grant" or "not active" in description.lower():
        return (
            "BKW login session expired. Reconfigure the integration to sign in again."
        )
    return description


def _refresh_expires_at(refresh_expires_in: Any) -> float | None:
    """Map Keycloak refresh_expires_in to an absolute timestamp.

    Offline tokens may return 0 (no fixed expiry); keep refreshing on schedule.
    """
    if refresh_expires_in is None:
        return None
    try:
        seconds = int(refresh_expires_in)
    except (TypeError, ValueError):
        return None
    if seconds <= 0:
        return None
    return time.time() + seconds


def _normalize_token_response(
    body: dict[str, Any], *, set_authenticated_at: bool
) -> dict[str, Any]:
    """Map token response to config entry fields."""
    now = time.time()
    expires_in = int(body.get("expires_in", 600))
    scope = body.get("scope")
    result: dict[str, Any] = {
        CONF_ACCESS_TOKEN: body["access_token"],
        CONF_REFRESH_TOKEN: body.get("refresh_token"),
        CONF_EXPIRES_AT: now + expires_in,
        CONF_REFRESH_EXPIRES_AT: _refresh_expires_at(body.get("refresh_expires_in")),
    }
    if set_authenticated_at:
        result[CONF_AUTHENTICATED_AT] = now
    if scope:
        result[CONF_TOKEN_SCOPE] = scope
    return result


def token_needs_refresh(expires_at: float | None) -> bool:
    """Return True if access token should be refreshed before use."""
    if expires_at is None:
        return True
    return time.time() >= (expires_at - TOKEN_REFRESH_MARGIN_SECONDS)


def tokens_from_entry(entry_data: dict[str, Any]) -> dict[str, Any]:
    """Extract token fields from config entry data."""
    return {
        CONF_ACCESS_TOKEN: entry_data[CONF_ACCESS_TOKEN],
        CONF_REFRESH_TOKEN: entry_data[CONF_REFRESH_TOKEN],
        CONF_EXPIRES_AT: entry_data.get(CONF_EXPIRES_AT),
        CONF_REFRESH_EXPIRES_AT: entry_data.get(CONF_REFRESH_EXPIRES_AT),
        CONF_AUTHENTICATED_AT: entry_data.get(CONF_AUTHENTICATED_AT),
        CONF_TOKEN_SCOPE: entry_data.get(CONF_TOKEN_SCOPE),
    }


def has_offline_access(entry_data: dict[str, Any]) -> bool:
    """Return True when the stored token was issued with offline_access."""
    scope = entry_data.get(CONF_TOKEN_SCOPE) or ""
    return "offline_access" in scope.split()

