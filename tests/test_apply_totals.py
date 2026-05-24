"""Tests for cumulative total updates when BKW revises a published day (no HA import)."""


def apply_published_day_to_total(
    *,
    total_kwh: float,
    last_polled_day: str | None,
    last_applied_day_kwh: float | None,
    day_key: str,
    latest_day_kwh: float | None,
) -> tuple[float, str | None, float | None, bool]:
    """Mirror of custom_components.bkw_smartmeter.api.apply_published_day_to_total."""
    if latest_day_kwh is None:
        return total_kwh, last_polled_day, last_applied_day_kwh, False

    latest = float(latest_day_kwh)

    if last_polled_day != day_key:
        return total_kwh + latest, day_key, latest, True

    if last_applied_day_kwh is None:
        return total_kwh, day_key, latest, True

    if latest == float(last_applied_day_kwh):
        return total_kwh, last_polled_day, last_applied_day_kwh, False

    delta = latest - float(last_applied_day_kwh)
    return total_kwh + delta, day_key, latest, True


def test_new_published_day_adds_full_value() -> None:
    total, day, applied, updated = apply_published_day_to_total(
        total_kwh=100.0,
        last_polled_day="2026-05-21",
        last_applied_day_kwh=8.5,
        day_key="2026-05-22",
        latest_day_kwh=9.6,
    )
    assert updated is True
    assert total == 109.6
    assert day == "2026-05-22"
    assert applied == 9.6


def test_same_day_revision_applies_delta() -> None:
    total, day, applied, updated = apply_published_day_to_total(
        total_kwh=109.6,
        last_polled_day="2026-05-22",
        last_applied_day_kwh=9.6,
        day_key="2026-05-22",
        latest_day_kwh=11.0,
    )
    assert updated is True
    assert total == 111.0
    assert day == "2026-05-22"
    assert applied == 11.0


def test_same_day_unchanged_skips_persist() -> None:
    total, day, applied, updated = apply_published_day_to_total(
        total_kwh=111.0,
        last_polled_day="2026-05-22",
        last_applied_day_kwh=11.0,
        day_key="2026-05-22",
        latest_day_kwh=11.0,
    )
    assert updated is False
    assert total == 111.0
    assert applied == 11.0


def test_upgrade_syncs_applied_without_double_count() -> None:
    total, day, applied, updated = apply_published_day_to_total(
        total_kwh=109.6,
        last_polled_day="2026-05-22",
        last_applied_day_kwh=None,
        day_key="2026-05-22",
        latest_day_kwh=11.0,
    )
    assert updated is True
    assert total == 109.6
    assert applied == 11.0


def test_missing_api_value_leaves_total() -> None:
    total, day, applied, updated = apply_published_day_to_total(
        total_kwh=100.0,
        last_polled_day="2026-05-21",
        last_applied_day_kwh=8.5,
        day_key="2026-05-22",
        latest_day_kwh=None,
    )
    assert updated is False
    assert total == 100.0
