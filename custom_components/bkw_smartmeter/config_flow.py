"""Config flow for BKW Smart Meter."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult

from .api import BkwApi, BkwApiError, get_polling_day
from .debug import mask_metering_point
from .auth import (
    BkwAuthError,
    async_exchange_code,
    build_authorize_url,
    generate_code_verifier,
)
from .const import (
    AUTHORIZE_URL,
    CONF_ACCESS_TOKEN,
    CONF_DATA_TYPE,
    CONF_EXPIRES_AT,
    CONF_METERING_POINT_CODE,
    CONF_REFRESH_TOKEN,
    CONF_UPDATE_INTERVAL_MINUTES,
    DEFAULT_DATA_TYPE,
    DOMAIN,
    FLOW_AUTHORIZE_URL,
    FLOW_CODE_VERIFIER,
    MAX_UPDATE_INTERVAL_MINUTES,
    MIN_UPDATE_INTERVAL_MINUTES,
    METERING_POINT_MAX_LENGTH,
    METERING_POINT_MIN_LENGTH,
    UPDATE_INTERVAL_MINUTES,
    get_update_interval_minutes,
)

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required("code"): str,
    }
)

STEP_METERING_POINT_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_METERING_POINT_CODE): str,
        vol.Optional(CONF_DATA_TYPE, default=DEFAULT_DATA_TYPE): str,
    }
)


class BkwSmartMeterConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for BKW Smart Meter."""

    VERSION = 1
    MINOR_VERSION = 1

    def __init__(self) -> None:
        """Initialize config flow."""
        self._code_verifier: str | None = None
        self._authorize_url: str | None = None
        self._tokens: dict[str, Any] | None = None

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> BkwSmartMeterOptionsFlowHandler:
        """Get options flow."""
        return BkwSmartMeterOptionsFlowHandler()

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Start PKCE login: show authorize URL and accept pasted code."""
        errors: dict[str, str] = {}

        if user_input is None:
            self._code_verifier = generate_code_verifier()
            self._authorize_url = build_authorize_url(
                AUTHORIZE_URL, self._code_verifier
            )
            self.context[FLOW_CODE_VERIFIER] = self._code_verifier
            self.context[FLOW_AUTHORIZE_URL] = self._authorize_url

            return self.async_show_form(
                step_id="user",
                data_schema=STEP_USER_DATA_SCHEMA,
                description_placeholders={
                    "authorize_url": self._authorize_url,
                },
            )

        code_verifier = self.context.get(FLOW_CODE_VERIFIER) or self._code_verifier
        if not code_verifier:
            return self.async_abort(reason="missing_pkce")

        try:
            self._tokens = await async_exchange_code(
                self.hass, user_input["code"], code_verifier
            )
        except BkwAuthError:
            errors["base"] = "invalid_auth"
        except Exception:  # noqa: BLE001
            _LOGGER.exception("Unexpected error during token exchange")
            errors["base"] = "cannot_connect"

        if not errors and self.source == config_entries.SOURCE_REAUTH:
            reauth_entry = self._get_reauth_entry()
            return self.async_update_reload_and_abort(
                reauth_entry,
                data={**reauth_entry.data, **self._tokens},
            )

        if errors:
            authorize_url = self.context.get(FLOW_AUTHORIZE_URL) or self._authorize_url
            if not authorize_url and code_verifier:
                authorize_url = build_authorize_url(AUTHORIZE_URL, code_verifier)
            return self.async_show_form(
                step_id="user",
                data_schema=STEP_USER_DATA_SCHEMA,
                errors=errors,
                description_placeholders={
                    "authorize_url": authorize_url or AUTHORIZE_URL,
                },
            )

        return await self.async_step_metering_point()

    async def async_step_metering_point(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Collect metering point code."""
        if user_input is None:
            return self.async_show_form(
                step_id="metering_point",
                data_schema=STEP_METERING_POINT_SCHEMA,
            )

        metering_point = user_input[CONF_METERING_POINT_CODE].strip()
        if not (
            METERING_POINT_MIN_LENGTH
            <= len(metering_point)
            <= METERING_POINT_MAX_LENGTH
        ):
            return self.async_show_form(
                step_id="metering_point",
                data_schema=STEP_METERING_POINT_SCHEMA,
                errors={"base": "invalid_metering_point"},
            )

        await self.async_set_unique_id(metering_point)
        self._abort_if_unique_id_configured()

        if not self._tokens:
            return self.async_abort(reason="missing_tokens")

        data_type = user_input.get(CONF_DATA_TYPE, DEFAULT_DATA_TYPE)
        errors: dict[str, str] = {}

        async def _noop_update(_tokens: dict[str, Any]) -> None:
            return None

        api = BkwApi(
            self.hass,
            {
                **self._tokens,
                CONF_METERING_POINT_CODE: metering_point,
                CONF_DATA_TYPE: data_type,
            },
            _noop_update,
        )
        val_day = get_polling_day()
        _LOGGER.debug(
            "Validating metering point %s dataType=%s swiss_day=%s",
            mask_metering_point(metering_point),
            data_type,
            val_day,
        )
        try:
            await api.async_get_daily_total(val_day)
            _LOGGER.debug(
                "Validation OK for %s / %s",
                mask_metering_point(metering_point),
                data_type,
            )
        except BkwAuthError:
            errors["base"] = "invalid_auth"
        except BkwApiError as err:
            _LOGGER.error(
                "Validation failed for %s dataType=%s: %s (status=%s)",
                mask_metering_point(metering_point),
                data_type,
                err,
                err.status,
            )
            errors["base"] = "invalid_data_type"
        except Exception:  # noqa: BLE001
            _LOGGER.exception("Unexpected error validating metering point")
            errors["base"] = "cannot_connect"

        if errors:
            return self.async_show_form(
                step_id="metering_point",
                data_schema=STEP_METERING_POINT_SCHEMA,
                errors=errors,
            )

        return self.async_create_entry(
            title=f"BKW {metering_point[-8:]}",
            data={
                **self._tokens,
                CONF_METERING_POINT_CODE: metering_point,
                CONF_DATA_TYPE: data_type,
            },
        )

    async def async_step_reauth(
        self, entry_data: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle reauthentication."""
        self.context["source"] = config_entries.SOURCE_REAUTH
        return await self.async_step_user()

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Allow reconfigure (reauth) from integration menu."""
        return await self.async_step_reauth()


class BkwSmartMeterOptionsFlowHandler(config_entries.OptionsFlow):
    """Handle options for BKW Smart Meter."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage integration options."""
        if user_input is not None:
            self.hass.config_entries.async_update_entry(
                self.config_entry,
                data={
                    **self.config_entry.data,
                    CONF_DATA_TYPE: user_input[CONF_DATA_TYPE],
                },
            )
            return self.async_create_entry(
                title="",
                data={
                    CONF_DATA_TYPE: user_input[CONF_DATA_TYPE],
                    CONF_UPDATE_INTERVAL_MINUTES: user_input[
                        CONF_UPDATE_INTERVAL_MINUTES
                    ],
                },
            )

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_DATA_TYPE,
                        default=self.config_entry.data.get(
                            CONF_DATA_TYPE, DEFAULT_DATA_TYPE
                        ),
                    ): str,
                    vol.Optional(
                        CONF_UPDATE_INTERVAL_MINUTES,
                        default=get_update_interval_minutes(self.config_entry),
                    ): vol.All(
                        vol.Coerce(int),
                        vol.Range(
                            min=MIN_UPDATE_INTERVAL_MINUTES,
                            max=MAX_UPDATE_INTERVAL_MINUTES,
                        ),
                    ),
                }
            ),
        )
