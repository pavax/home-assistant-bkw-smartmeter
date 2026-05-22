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
    CONF_EXPIRES_AT,
    CONF_REFRESH_TOKEN,
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
                raise BkwAuthError(
                    body.get("error_description", body.get("error", resp.reason))
                )
            log_auth_event(
                "exchange_code_ok",
                status=resp.status,
                detail=f"expires_in={body.get('expires_in')}",
            )
    except ClientResponseError as err:
        log_auth_event("exchange_code_error", detail=str(err))
        raise BkwAuthError(str(err)) from err
    except ClientError as err:
        log_auth_event("exchange_code_error", detail=str(err))
        raise BkwAuthError(str(err)) from err

    return _normalize_token_response(body)


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
                raise BkwAuthError(
                    body.get("error_description", body.get("error", resp.reason))
                )
            log_auth_event(
                "refresh_ok",
                status=resp.status,
                detail=f"expires_in={body.get('expires_in')}",
            )
    except ClientResponseError as err:
        log_auth_event("refresh_error", detail=str(err))
        raise BkwAuthError(str(err)) from err
    except ClientError as err:
        log_auth_event("refresh_error", detail=str(err))
        raise BkwAuthError(str(err)) from err

    return _normalize_token_response(body)


def _normalize_token_response(body: dict[str, Any]) -> dict[str, Any]:
    """Map token response to config entry fields."""
    expires_in = int(body.get("expires_in", 600))
    return {
        CONF_ACCESS_TOKEN: body["access_token"],
        CONF_REFRESH_TOKEN: body.get("refresh_token"),
        CONF_EXPIRES_AT: time.time() + expires_in,
    }


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
    }

