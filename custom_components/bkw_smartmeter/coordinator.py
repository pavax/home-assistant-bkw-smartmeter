"""Data update coordinator for BKW Smart Meter."""



from __future__ import annotations



import logging

from typing import Any



from homeassistant.config_entries import ConfigEntry

from homeassistant.core import HomeAssistant

from homeassistant.exceptions import ConfigEntryAuthFailed

from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed



from .api import BkwApi, BkwApiError, get_polling_day

from .auth import BkwAuthError

from .debug import mask_metering_point

from .const import (
    CONF_CONSUMPTION_TOTAL_KWH,
    CONF_LAST_INTERVAL_TIMESTAMP,
    CONF_LAST_POLLED_DAY,
    DOMAIN,
    get_update_interval_minutes,
    get_update_interval_timedelta,
)



_LOGGER = logging.getLogger(__name__)


class BkwSmartMeterCoordinator(DataUpdateCoordinator[dict[str, Any]]):

    """Fetch BKW metering data periodically."""



    config_entry: ConfigEntry



    def __init__(

        self,

        hass: HomeAssistant,

        entry: ConfigEntry,

        api: BkwApi,

    ) -> None:

        """Initialize coordinator."""

        self.api = api

        super().__init__(

            hass,

            _LOGGER,

            config_entry=entry,

            name=DOMAIN,

            update_interval=get_update_interval_timedelta(entry),

        )

    async def async_apply_config_entry(self) -> None:
        """Apply config/options changes and fetch data immediately."""
        self.api.update_from_entry(dict(self.config_entry.data))
        self.update_interval = get_update_interval_timedelta(self.config_entry)
        _LOGGER.debug(
            "Options applied: dataType=%s interval=%s min — requesting refresh",
            self.api.data_type,
            get_update_interval_minutes(self.config_entry),
        )
        await self.async_request_refresh()

    async def _async_update_data(self) -> dict[str, Any]:

        """Fetch latest published daily total (P1D) and update cumulative total."""

        _LOGGER.debug(

            "Coordinator update start: meteringPoint=%s dataType=%s",

            mask_metering_point(self.api.metering_point_code),

            self.api.data_type,

        )

        polling_day = get_polling_day()

        try:

            latest_day_kwh = await self.api.async_get_daily_total(polling_day)

        except BkwAuthError as err:

            _LOGGER.debug("Coordinator auth failed: %s", err)

            raise ConfigEntryAuthFailed(str(err)) from err

        except BkwApiError as err:

            _LOGGER.debug("Coordinator API failed: %s (status=%s)", err, err.status)

            raise UpdateFailed(f"BKW API error: {err}") from err

        except Exception as err:

            _LOGGER.debug("Coordinator unexpected error: %s", err, exc_info=True)

            raise UpdateFailed(f"Error communicating with BKW API: {err}") from err



        total_kwh = float(

            self.config_entry.data.get(CONF_CONSUMPTION_TOTAL_KWH, 0.0)

        )

        last_polled = _get_last_polled_day(self.config_entry.data)

        day_key = polling_day.isoformat()



        if latest_day_kwh is not None and day_key != last_polled:

            _LOGGER.debug(

                "New published day applied: %s v=%s kWh (total %s -> %s)",

                day_key,

                latest_day_kwh,

                total_kwh,

                total_kwh + float(latest_day_kwh),

            )

            total_kwh += float(latest_day_kwh)

            await self._persist_totals(total_kwh, day_key)

        else:

            _LOGGER.debug(

                "No new published day: day=%s kwh=%s last_polled=%s",

                day_key,

                latest_day_kwh,

                last_polled,

            )



        result = {

            "latest_day_kwh": latest_day_kwh,

            "total_kwh": total_kwh,

            "data_date": day_key,

        }

        _LOGGER.debug(

            "Coordinator update done: data_date=%s latest_day_kwh=%s total_kwh=%s",

            day_key,

            latest_day_kwh,

            total_kwh,

        )

        return result



    async def _persist_totals(self, total_kwh: float, day_key: str) -> None:

        """Persist cumulative consumption and last counted day on the config entry."""

        self.hass.config_entries.async_update_entry(

            self.config_entry,

            data={

                **self.config_entry.data,

                CONF_CONSUMPTION_TOTAL_KWH: total_kwh,

                CONF_LAST_POLLED_DAY: day_key,

                CONF_LAST_INTERVAL_TIMESTAMP: day_key,

            },

        )





def _get_last_polled_day(entry_data: dict[str, Any]) -> str | None:

    """Return the last day already applied to the cumulative total."""

    raw = entry_data.get(CONF_LAST_POLLED_DAY) or entry_data.get(

        CONF_LAST_INTERVAL_TIMESTAMP

    )

    if not raw:

        return None

    if "T" in raw:

        return raw.split("T", 1)[0]

    return raw


