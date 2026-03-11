"""Sensor platform for Octopus Cheapest Time.

Each config entry contains both the hub (rate entity) config AND the task config,
since the hub + first task are created together in one flow. The hub entry holds
CONF_CURRENT_RATE_ENTITY, CONF_NEXT_RATE_ENTITY, CONF_TASK_NAME, CONF_TASK_DURATION.
Options can override CONF_TASK_NAME and CONF_TASK_DURATION.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from homeassistant.components.sensor import SensorEntity, SensorDeviceClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
    UpdateFailed,
)
from homeassistant.util import dt as dt_util

from .const import (
    DOMAIN,
    CONF_TASK_NAME,
    CONF_TASK_DURATION,
    CONF_CURRENT_RATE_ENTITY,
    CONF_NEXT_RATE_ENTITY,
    SEARCH_WINDOW_HOURS,
    DEFAULT_SCAN_INTERVAL,
    OCTOPUS_ATTR_RATES,
    OCTOPUS_ATTR_START,
    OCTOPUS_ATTR_END,
    OCTOPUS_ATTR_VALUE,
    ATTR_CHEAPEST_START,
    ATTR_CHEAPEST_END,
    ATTR_AVERAGE_COST_GBP,
    ATTR_AVERAGE_COST_PENCE,
    ATTR_TIME_UNTIL_START,
    ATTR_TASK_DURATION_MINUTES,
    ATTR_TODAY_SLOTS,
    ATTR_TOMORROW_SLOTS,
    ATTR_TOTAL_WINDOWS,
    ATTR_ALL_WINDOWS,
    ATTR_CURRENT_RATE_ENTITY,
    ATTR_NEXT_RATE_ENTITY,
)

_LOGGER = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------

def _round_to_half_hour(hours: float) -> float:
    """Round to nearest 0.5."""
    return round(hours * 2) / 2


def _extract_rates(hass: HomeAssistant, entity_id: str, label: str) -> list[dict]:
    """
    Pull the raw rate list from a state's attributes.

    Checks two locations to handle different OctopusEnergy versions:
      1. state.attributes["rates"]            — current / confirmed format
      2. state.attributes["event_data"]["rates"] — older versions
    """
    if not entity_id:
        return []

    state = hass.states.get(entity_id)
    if state is None:
        # Entity may not be registered yet on first startup — logged at debug
        # level to avoid noisy warnings during HA boot; coordinator will retry.
        _LOGGER.debug("[%s] Entity '%s' not found yet (may still be loading).", label, entity_id)
        return []

    attrs = state.attributes
    rates = attrs.get(OCTOPUS_ATTR_RATES)

    if rates is None:
        event_data = attrs.get("event_data", {})
        if isinstance(event_data, dict):
            rates = event_data.get(OCTOPUS_ATTR_RATES)

    if rates is None:
        _LOGGER.warning(
            "[%s] No 'rates' on '%s'. Attributes present: %s",
            label, entity_id, list(attrs.keys()),
        )
        return []

    if not isinstance(rates, list):
        _LOGGER.warning("[%s] 'rates' is not a list on '%s'.", label, entity_id)
        return []

    _LOGGER.debug("[%s] Loaded %d slots from '%s'.", label, len(rates), entity_id)
    return rates


def _parse_slots(raw: list[dict], source: str) -> list[dict]:
    """Convert raw rate dicts to normalised slot dicts with datetime objects."""
    parsed = []
    for r in raw:
        try:
            start = r.get(OCTOPUS_ATTR_START)
            end = r.get(OCTOPUS_ATTR_END)
            value = r.get(OCTOPUS_ATTR_VALUE)
            if start is None or end is None or value is None:
                continue
            if isinstance(start, str):
                start = datetime.fromisoformat(start)
            if isinstance(end, str):
                end = datetime.fromisoformat(end)
            if start.tzinfo is None:
                start = start.replace(tzinfo=timezone.utc)
            if end.tzinfo is None:
                end = end.replace(tzinfo=timezone.utc)
            parsed.append({
                "start": start,
                "end": end,
                "value": float(value),          # £/kWh inc VAT
                "duration_minutes": (end - start).total_seconds() / 60,
                "source": source,
            })
        except (ValueError, TypeError, KeyError) as err:
            _LOGGER.debug("Skipping slot from %s: %s", source, err)
    return parsed


def _find_cheapest_windows(
    slots: list[dict],
    duration_minutes: int,
    now: datetime,
) -> list[dict]:
    """
    Sliding-window search over contiguous slots.
    Returns all valid windows sorted cheapest-first.
    """
    cutoff = now + timedelta(hours=SEARCH_WINDOW_HOURS)
    future = sorted(
        [s for s in slots if s["start"] >= now and s["start"] < cutoff],
        key=lambda x: x["start"],
    )

    results = []
    n = len(future)

    for i in range(n):
        accum = 0.0
        cost = 0.0
        j = i

        while j < n and accum < duration_minutes:
            slot = future[j]
            if j > i:
                gap = (slot["start"] - future[j - 1]["end"]).total_seconds() / 60
                if gap > 1:   # non-contiguous — stop extending this window
                    break
            needed = duration_minutes - accum
            contrib = min(slot["duration_minutes"], needed)
            cost += slot["value"] * (contrib / 60)
            accum += contrib
            j += 1

        if accum >= duration_minutes - 0.5:   # 30 s tolerance
            w_start = future[i]["start"]
            avg = cost / (duration_minutes / 60)
            results.append({
                "start": w_start,
                "end": w_start + timedelta(minutes=duration_minutes),
                "average_cost_gbp": round(avg, 6),
                "average_cost_pence": round(avg * 100, 4),
            })

    results.sort(key=lambda x: x["average_cost_gbp"])
    return results


# ---------------------------------------------------------------------------
# Coordinator
# ---------------------------------------------------------------------------

class CheapestTimeCoordinator(DataUpdateCoordinator):
    """Polls rate entities and recomputes the cheapest window every 5 minutes."""

    def __init__(
        self,
        hass: HomeAssistant,
        task_name: str,
        task_duration: int,
        current_entity: str,
        next_entity: str,
    ) -> None:
        self.task_name = task_name
        self.task_duration = task_duration
        self.current_entity = current_entity
        self.next_entity = next_entity

        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_{task_name}",
            update_interval=timedelta(seconds=DEFAULT_SCAN_INTERVAL),
        )

    async def _async_update_data(self) -> dict:
        today_raw = _extract_rates(self.hass, self.current_entity, "today")
        tomorrow_raw = _extract_rates(self.hass, self.next_entity, "tomorrow")

        if not today_raw and not tomorrow_raw:
            raise UpdateFailed(
                f"No rates found. today='{self.current_entity}' "
                f"tomorrow='{self.next_entity}'"
            )

        today_slots = _parse_slots(today_raw, "today")
        tomorrow_slots = _parse_slots(tomorrow_raw, "tomorrow")

        # Merge and deduplicate by start time
        seen: set = set()
        merged: list[dict] = []
        for slot in today_slots + tomorrow_slots:
            if slot["start"] not in seen:
                seen.add(slot["start"])
                merged.append(slot)

        if not merged:
            raise UpdateFailed("Rate slots could not be parsed. Check HA logs.")

        now = dt_util.utcnow()
        windows = _find_cheapest_windows(merged, self.task_duration, now)

        return {
            "windows": windows,
            "now": now,
            "today_slots": len(today_slots),
            "tomorrow_slots": len(tomorrow_slots),
            "current_entity": self.current_entity,
            "next_entity": self.next_entity,
            "task_duration": self.task_duration,
        }


# ---------------------------------------------------------------------------
# Platform setup
# ---------------------------------------------------------------------------

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Create one sensor per config entry."""
    # Merge data + options so edits via the options flow take effect
    cfg = {**entry.data, **entry.options}

    coordinator = CheapestTimeCoordinator(
        hass=hass,
        task_name=cfg[CONF_TASK_NAME],
        task_duration=cfg[CONF_TASK_DURATION],
        current_entity=cfg[CONF_CURRENT_RATE_ENTITY],
        next_entity=cfg[CONF_NEXT_RATE_ENTITY],
    )

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    # Use async_refresh instead of async_config_entry_first_refresh so a
    # temporary unavailability of OctopusEnergy entities during HA startup
    # does not permanently fail the config entry — the coordinator will retry.
    await coordinator.async_refresh()
    async_add_entities(
        [
            CheapestTimeSensor(coordinator, entry),
            TimeUntilStartSensor(coordinator, entry),
        ],
        True,
    )


# ---------------------------------------------------------------------------
# Sensor: cheapest start timestamp
# ---------------------------------------------------------------------------

class CheapestTimeSensor(CoordinatorEntity, SensorEntity):
    """Reports the cheapest start time and related metadata."""

    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_has_entity_name = True

    def __init__(self, coordinator: CheapestTimeCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._entry = entry
        slug = coordinator.task_name.lower().replace(" ", "_")
        self._attr_unique_id = f"{DOMAIN}_{slug}_cheapest_start"
        self._attr_name = f"Cheapest Start: {coordinator.task_name}"
        self._attr_icon = "mdi:clock-check-outline"

    @property
    def native_value(self) -> datetime | None:
        if not self.coordinator.data:
            return None
        windows = self.coordinator.data.get("windows", [])
        return windows[0]["start"] if windows else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        if not self.coordinator.data:
            return {}

        data = self.coordinator.data
        windows = data.get("windows", [])
        now: datetime = data["now"]

        base = {
            ATTR_TASK_DURATION_MINUTES: data["task_duration"],
            ATTR_CURRENT_RATE_ENTITY: data["current_entity"],
            ATTR_NEXT_RATE_ENTITY: data["next_entity"],
            ATTR_TODAY_SLOTS: data["today_slots"],
            ATTR_TOMORROW_SLOTS: data["tomorrow_slots"],
        }

        if not windows:
            return {
                **base,
                ATTR_TOTAL_WINDOWS: 0,
                "message": (
                    "No windows found. Tomorrow's rates may not be published yet "
                    "(Agile publishes ~4pm daily)."
                ),
            }

        best = windows[0]
        raw_hours = (best["start"] - now).total_seconds() / 3600
        time_until = _round_to_half_hour(max(raw_hours, 0.0))

        top5 = [
            {
                "start": w["start"].isoformat(),
                "end": w["end"].isoformat(),
                "average_cost_pence_per_kwh": w["average_cost_pence"],
            }
            for w in windows[:5]
        ]

        return {
            **base,
            ATTR_CHEAPEST_START: best["start"].isoformat(),
            ATTR_CHEAPEST_END: best["end"].isoformat(),
            ATTR_AVERAGE_COST_GBP: best["average_cost_gbp"],
            ATTR_AVERAGE_COST_PENCE: best["average_cost_pence"],
            ATTR_TIME_UNTIL_START: time_until,
            ATTR_TOTAL_WINDOWS: len(windows),
            ATTR_ALL_WINDOWS: top5,
        }


# ---------------------------------------------------------------------------
# Sensor: hours until cheapest start (numeric — usable by ESPHome directly)
# ---------------------------------------------------------------------------

class TimeUntilStartSensor(CoordinatorEntity, SensorEntity):
    """
    A plain numeric sensor exposing time_until_start_hours.

    Rounded to the nearest 0.5 h, same as the attribute on CheapestTimeSensor.
    ESPHome and other integrations can subscribe to this directly without
    needing a template sensor in HA.

    Entity ID example: sensor.time_until_start_40degwash
    """

    _attr_has_entity_name = True
    _attr_native_unit_of_measurement = "h"
    _attr_icon = "mdi:timer-sand"
    _attr_suggested_display_precision = 1

    def __init__(self, coordinator: CheapestTimeCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._entry = entry
        slug = coordinator.task_name.lower().replace(" ", "_")
        self._attr_unique_id = f"{DOMAIN}_{slug}_time_until_start"
        self._attr_name = f"Time Until Start: {coordinator.task_name}"

    @property
    def native_value(self) -> float | None:
        """Return hours until the cheapest start, rounded to nearest 0.5."""
        if not self.coordinator.data:
            return None
        windows = self.coordinator.data.get("windows", [])
        if not windows:
            return None
        now: datetime = self.coordinator.data["now"]
        raw_hours = (windows[0]["start"] - now).total_seconds() / 3600
        return _round_to_half_hour(max(raw_hours, 0.0))
