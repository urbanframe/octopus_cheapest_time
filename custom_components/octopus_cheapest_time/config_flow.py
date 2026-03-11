"""Config flow for Octopus Cheapest Time.

Architecture
============
One config entry per TASK. Each entry holds:
  - current_rate_entity  }  copied from the first setup and editable
  - next_rate_entity     }  only by removing/re-adding the integration
  - task_name
  - task_duration

Setup flow (2 steps):
  Step 1 (user)        — enter the two rate entities ONCE.
                         The unique_id guard prevents a second hub being added.
  Step 2 (first_task)  — enter the first task name + duration.
                         Creates the config entry with all four values.

Adding more tasks:
  Run "Add Integration" again → the unique_id guard fires → user is shown
  the "add_task" step which only asks for name + duration and re-uses the
  rate entities already stored in the existing entry.

Options flow (per entry — name + duration only):
  Editing is limited to task_name and task_duration so there are no
  vol.In() / dropdown conflicts. Rate entities are intentionally read-only
  here; remove and re-add the integration to change them.
"""
from __future__ import annotations

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
import homeassistant.helpers.config_validation as cv

from .const import (
    DOMAIN,
    CONF_CURRENT_RATE_ENTITY,
    CONF_NEXT_RATE_ENTITY,
    CONF_TASK_NAME,
    CONF_TASK_DURATION,
)

_HUB_UNIQUE_ID = f"{DOMAIN}_hub"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _octopus_entities(hass: HomeAssistant) -> list[str]:
    """Sorted list of likely OctopusEnergy rate event entities."""
    reg = er.async_get(hass)
    found = [
        e.entity_id for e in reg.entities.values()
        if e.platform == "octopus_energy"
        or ("octopus_energy" in e.entity_id and "day_rates" in e.entity_id)
    ]
    return sorted(found)


def _entity_validator(hass: HomeAssistant) -> vol.Validator:
    entities = _octopus_entities(hass)
    return vol.In(entities) if entities else cv.string


def _existing_hub_entry(hass: HomeAssistant) -> config_entries.ConfigEntry | None:
    """Return the first existing entry for this domain (any task holds the entity config)."""
    entries = hass.config_entries.async_entries(DOMAIN)
    return entries[0] if entries else None


def _task_schema(defaults: dict | None = None) -> vol.Schema:
    d = defaults or {}
    return vol.Schema({
        vol.Required(CONF_TASK_NAME, default=d.get(CONF_TASK_NAME, "")): cv.string,
        vol.Required(CONF_TASK_DURATION, default=d.get(CONF_TASK_DURATION, 60)): vol.All(
            vol.Coerce(int), vol.Range(min=1, max=1440)
        ),
    })


# ---------------------------------------------------------------------------
# Main config flow
# ---------------------------------------------------------------------------

class OctopusCheapestTimeConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Two-step setup; subsequent runs go straight to add_task."""

    VERSION = 1

    def __init__(self) -> None:
        self._current_entity: str = ""
        self._next_entity: str = ""

    # ------------------------------------------------------------------
    # Entry point
    # ------------------------------------------------------------------
    async def async_step_user(self, user_input: dict | None = None):
        """
        First run  → show entity pickers (step 1 of 2).
        Subsequent → skip to add_task using saved entity config.
        """
        existing = _existing_hub_entry(self.hass)
        if existing is not None:
            # Rate entities already configured — go straight to add a task
            saved = {**existing.data, **existing.options}
            self._current_entity = saved.get(CONF_CURRENT_RATE_ENTITY, "")
            self._next_entity = saved.get(CONF_NEXT_RATE_ENTITY, "")
            return await self.async_step_add_task()

        # First-time setup
        errors: dict = {}
        if user_input is not None:
            self._current_entity = user_input[CONF_CURRENT_RATE_ENTITY].strip()
            self._next_entity = user_input[CONF_NEXT_RATE_ENTITY].strip()
            if not self._current_entity:
                errors[CONF_CURRENT_RATE_ENTITY] = "entity_required"
            elif not self._next_entity:
                errors[CONF_NEXT_RATE_ENTITY] = "entity_required"
            else:
                return await self.async_step_first_task()

        sel = _entity_validator(self.hass)
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required(CONF_CURRENT_RATE_ENTITY, default=""): sel,
                vol.Required(CONF_NEXT_RATE_ENTITY, default=""): sel,
            }),
            errors=errors,
        )

    # ------------------------------------------------------------------
    # Step 2a — first task (collected right after entity setup)
    # ------------------------------------------------------------------
    async def async_step_first_task(self, user_input: dict | None = None):
        errors: dict = {}
        if user_input is not None:
            name = user_input[CONF_TASK_NAME].strip()
            duration = user_input[CONF_TASK_DURATION]
            if not name:
                errors[CONF_TASK_NAME] = "name_required"
            elif duration < 1:
                errors[CONF_TASK_DURATION] = "invalid_duration"
            else:
                return self.async_create_entry(
                    title=name,
                    data={
                        CONF_CURRENT_RATE_ENTITY: self._current_entity,
                        CONF_NEXT_RATE_ENTITY: self._next_entity,
                        CONF_TASK_NAME: name,
                        CONF_TASK_DURATION: duration,
                    },
                )
        return self.async_show_form(
            step_id="first_task",
            data_schema=_task_schema(),
            errors=errors,
        )

    # ------------------------------------------------------------------
    # Step 2b — add another task (re-uses saved entity config)
    # ------------------------------------------------------------------
    async def async_step_add_task(self, user_input: dict | None = None):
        errors: dict = {}
        if user_input is not None:
            name = user_input[CONF_TASK_NAME].strip()
            duration = user_input[CONF_TASK_DURATION]
            if not name:
                errors[CONF_TASK_NAME] = "name_required"
            elif duration < 1:
                errors[CONF_TASK_DURATION] = "invalid_duration"
            else:
                return self.async_create_entry(
                    title=name,
                    data={
                        CONF_CURRENT_RATE_ENTITY: self._current_entity,
                        CONF_NEXT_RATE_ENTITY: self._next_entity,
                        CONF_TASK_NAME: name,
                        CONF_TASK_DURATION: duration,
                    },
                )
        return self.async_show_form(
            step_id="add_task",
            data_schema=_task_schema(),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return OctopusCheapestTimeOptionsFlow()


# ---------------------------------------------------------------------------
# Options flow — task name + duration ONLY (no entity pickers → no errors)
# ---------------------------------------------------------------------------

class OctopusCheapestTimeOptionsFlow(config_entries.OptionsFlow):
    """Edit a task's name and duration only."""

    async def async_step_init(self, user_input: dict | None = None):
        errors: dict = {}
        current = {**self.config_entry.data, **self.config_entry.options}

        if user_input is not None:
            name = user_input.get(CONF_TASK_NAME, "").strip()
            duration = user_input[CONF_TASK_DURATION]
            if not name:
                errors[CONF_TASK_NAME] = "name_required"
            elif duration < 1:
                errors[CONF_TASK_DURATION] = "invalid_duration"
            else:
                return self.async_create_entry(title="", data=user_input)

        return self.async_show_form(
            step_id="init",
            data_schema=_task_schema(current),
            errors=errors,
        )
