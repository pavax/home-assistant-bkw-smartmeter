"""BKW Smart Meter integration for Home Assistant."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import ConfigType

from .api import BkwApi
from .const import DOMAIN
from .coordinator import BkwSmartMeterCoordinator

PLATFORMS: list[Platform] = [Platform.SENSOR]

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def async_update_tokens(
    hass: HomeAssistant,
    entry: ConfigEntry,
    tokens: dict[str, Any],
) -> None:
    """Persist refreshed tokens on the config entry."""
    hass.config_entries.async_update_entry(
        entry,
        data={**entry.data, **tokens},
    )


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up BKW Smart Meter from YAML (not used)."""
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up BKW Smart Meter from a config entry."""
    async def update_tokens(tokens: dict[str, Any]) -> None:
        await async_update_tokens(hass, entry, tokens)

    api = BkwApi(hass, dict(entry.data), update_tokens)
    coordinator = BkwSmartMeterCoordinator(hass, entry, api)

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    await coordinator.async_config_entry_first_refresh()

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    return True


async def _async_update_listener(
    hass: HomeAssistant, entry: ConfigEntry
) -> None:
    """Apply options and fetch data immediately (no full reload)."""
    coordinator: BkwSmartMeterCoordinator | None = hass.data.get(DOMAIN, {}).get(
        entry.entry_id
    )
    if coordinator is None:
        await async_reload_entry(hass, entry)
        return
    await coordinator.async_apply_config_entry()


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
    return unload_ok


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload config entry."""
    await async_unload_entry(hass, entry)
    await async_setup_entry(hass, entry)
